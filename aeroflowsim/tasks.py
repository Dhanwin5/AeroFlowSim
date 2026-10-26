# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Long work (meshing, solving) in a separate helper process, so a GUI never freezes and Cancel always works.

Why a process and not a thread: Python threads share one interpreter lock, so a busy solver makes
the window stutter, and Gmsh cannot be interrupted from a thread. A separate process runs on its
own CPU core and can always be stopped.

Why one *warm* process: starting Python and importing numpy/scipy takes about 1.4 s on Windows,
much longer than a small mesh (0.04 s). So the Worker starts its helper process once and keeps it
running; jobs are sent to it one after another through a queue.

How Stop / Cancel works:
  - a 2D run (its solver reports info with every iteration): the progress callback returns True, the
    solver ends cleanly after that iteration and the run finishes normally with the flow of that moment,
    marked "stopped" (not converged), so it can be looked at and continued (restart);
  - a 1D run: the progress callback raises StopRequested, the run ends without results (they take seconds);
  - a mesh (Gmsh has no progress callback), or a run that does not answer Stop within a grace time:
    the helper process is terminated and a fresh one is started in the background. A 2D run that has
    answered (stage SAVING_STOPPED) is never terminated while it saves its results.

The child sends messages back (all plain, picklable Python objects):
    ("stage", text)                      what it is doing now
    ("progress", iterations, residuals, extras)  new residual history, sent in batches every 0.1 s;
                                         extras: one dict per iteration from solvers that report more
                                         (residual per equation, monitors such as thrust), else None
    ("done", payload)                    a dict with the outputs (see _mesh_job and _run_job)
    ("stopped",)                         the run ended early because Stop was pressed
    ("error", text)                      the job failed (the message names the problem)
Every message carries the job number first, so messages of a cancelled job are ignored.

This module imports no GUI code; aeroflowsim/gui/jobs.py turns its messages into Qt signals.
"""

import multiprocessing
import queue as queue_module
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

PROGRESS_INTERVAL_S = 0.1   # [s] the child sends residual batches at most this often
STOP_GRACE_S = 10.0         # [s] a run gets this long to answer Stop before the process is terminated
SAVING_STOPPED = "Stopped: saving the results of this moment"   # stage text of a 2D run that is ending


class StopRequested(Exception):
    """Raised inside the progress callback to end a run early."""


@dataclass
class Job:
    """One piece of work for the helper process."""

    kind: str                 # "mesh" or "run"
    case_folder: str          # template folder, e.g. cases/nozzle_axi (the child loads the case itself)
    params: dict              # validated inputs
    out_dir: str | None       # where the outputs are written (mesh files, or results)
    mesh: object = None       # run only: a Mesh / Mesh1D object, or the path of a saved mesh.npz
    restart: str = None       # run only: path of a previous run.npz to carry on from, or None (fresh start)
    geometry: dict = None     # mesh only: the edited workspace geometry (GeometryDocument.to_dict()), or None
    folder: str = None        # mesh only: the project folder (files imported into the workspace are there)
    extras: dict = None       # run only: project post-processing settings (report definitions, patches, ...)


@dataclass
class Task:
    """What the GUI knows about the current (or last) job; updated by Worker.poll()."""

    number: int
    job: Job
    status: str = "running"   # "running", "finished", "stopped", "cancelled" or "failed"
    stage: str = "Starting"   # short text of what is being done
    iterations: list = field(default_factory=list)   # residual history so far [-]
    residuals: list = field(default_factory=list)
    equation_residuals: list = field(default_factory=list)   # per iteration: residual of each equation [-]
    monitors: dict = field(default_factory=dict)             # name -> list of values per iteration
    positivity: int = 0       # faces that fell back to first order in the latest iteration
    payload: dict | None = None   # outputs when finished
    error: str = ""           # one-line message when failed
    details: str = ""         # traceback of a failure (for the Messages panel)
    started: float = field(default_factory=time.perf_counter)
    ended: float | None = None

    @property
    def running(self) -> bool:
        return self.status == "running"

    @property
    def elapsed_s(self) -> float:
        """Wall-clock time since the job was sent [s]."""
        return (self.ended or time.perf_counter()) - self.started


# ---- the helper (child) process -------------------------------------------------------------------

def _mesh_job(job, send):
    """Build the mesh. A face-based Mesh is saved as mesh.npz + mesh.vtu in out_dir (the parent
    loads the .npz); a 1D mesh is small and sent back as an object."""
    from aeroflowsim.discovery import load_case
    from aeroflowsim.mesh import Mesh
    from aeroflowsim.vtk import mesh_cell_data, write_vtu

    case = load_case(job.case_folder)
    send("stage", "Building the mesh")
    t0 = time.perf_counter()
    document = None
    if job.geometry is not None:
        from aeroflowsim.geometry_model import GeometryDocument
        document = GeometryDocument.from_dict(job.geometry)
    from aeroflowsim.workspace_mesh import mesh_for
    mesh = mesh_for(case, job.params, document, job.folder)     # the template's own mesher if not edited
    build_s = time.perf_counter() - t0
    if not isinstance(mesh, Mesh):
        return {"mesh": mesh, "build_s": build_s}
    send("stage", f"Saving the mesh ({mesh.n_cells:,} cells)")
    out = Path(job.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mesh.save(out / "mesh.npz")
    write_vtu(out / "mesh.vtu", mesh, mesh_cell_data(mesh))
    return {"mesh_path": str(out / "mesh.npz"), "vtu_path": str(out / "mesh.vtu"),
            "n_cells": mesh.n_cells, "build_s": build_s}


def _run_job(job, send, stop_event):
    """Solve with aeroflowsim.run_case (the one engine), sending the residual history in batches."""
    from aeroflowsim.discovery import load_case
    from aeroflowsim.engine import run_case
    from aeroflowsim.mesh import Mesh

    case = load_case(job.case_folder)
    mesh = job.mesh
    if isinstance(mesh, (str, Path)):
        send("stage", "Loading the mesh")
        mesh = Mesh.load(mesh)
    restart = None
    if job.restart:
        from aeroflowsim.result_io import continuation_data
        send("stage", "Reading the previous result")
        restart = continuation_data(job.restart)          # the run carries on from it
    batch_its, batch_res, batch_extra = [], [], []
    last_sent = [time.perf_counter()]

    def progress(iteration, residual, info=None):
        batch_its.append(iteration)
        batch_res.append(residual)
        if info is not None:        # plain numbers only (they are pickled to the parent process)
            batch_extra.append({"residuals": [float(r) for r in info.get("residuals", ())],
                                "monitors": {k: float(v) for k, v in info.get("monitors", {}).items()},
                                "positivity": int(info.get("positivity", 0))})
        now = time.perf_counter()
        if now - last_sent[0] >= PROGRESS_INTERVAL_S:
            flush()
            last_sent[0] = now
        if stop_event.is_set():
            if info is None:                # a 1D solver: end at once, no result
                raise StopRequested()
            if not stopping[0]:             # a 2D solver: it ends cleanly and returns the flow of this moment
                stopping[0] = True
                flush()
                send("stage", SAVING_STOPPED)
            return True
        return False

    stopping = [False]

    def flush():
        send("progress", list(batch_its), list(batch_res), list(batch_extra) if batch_extra else None)
        batch_its.clear()
        batch_res.clear()
        batch_extra.clear()

    send("stage", "Solving")
    t0 = time.perf_counter()
    try:
        output = run_case(case, job.params, mesh=mesh, progress=progress, out_dir=job.out_dir, restart=restart,
                          extras=job.extras)
    finally:
        if batch_its:
            flush()
    return {"result": output.result, "reference": output.reference, "reference_lines": output.reference_lines,
            "checks": output.checks, "params": output.params, "out_dir": job.out_dir,
            "run_s": time.perf_counter() - t0}


def _worker_main(jobs, messages, stop_event):
    """The helper process: wait for a job, do it, report; until it receives None."""
    while True:
        item = jobs.get()
        if item is None:
            return
        number, job = item

        def send(kind, *args):
            messages.put((number, kind, *args))

        try:
            if job.kind == "mesh":
                payload = _mesh_job(job, send)
            elif job.kind == "run":
                payload = _run_job(job, send, stop_event)
            else:
                raise ValueError(f"Unknown job kind '{job.kind}'.")
            send("done", payload)
        except StopRequested:
            send("stopped")
        except Exception as error:      # every failure goes back to the GUI as a readable message
            details = traceback.format_exc(limit=6)
            send("error", f"{type(error).__name__}: {error}", details)


# ---- the parent side ------------------------------------------------------------------------------

class Worker:
    """Owns the warm helper process and the current Task. Call poll() regularly (e.g. every 0.1 s)."""

    def __init__(self):
        self._ctx = multiprocessing.get_context("spawn")   # same on Windows, Linux and macOS
        self._process = None
        self._jobs = self._messages = self._stop_event = None
        self._numbers = 0
        self.task: Task | None = None
        self._stop_asked_at = None

    # -- process management --

    def start(self):
        """Start the helper process now (it warms up in the background); safe to call again."""
        if self._process is not None and self._process.is_alive():
            return
        self._jobs = self._ctx.Queue()
        self._messages = self._ctx.Queue()
        self._stop_event = self._ctx.Event()
        self._process = self._ctx.Process(target=_worker_main, args=(self._jobs, self._messages, self._stop_event),
                                          daemon=True, name="aeroflowsim-worker")
        self._process.start()

    def _kill(self):
        """Terminate the helper process (e.g. Gmsh in the middle of meshing) and start a fresh one."""
        if self._process is not None:
            self._process.terminate()
            self._process.join(5)
        self._process = None
        self.start()

    def shutdown(self):
        """Stop the helper process (when the window closes)."""
        if self._process is not None and self._process.is_alive():
            if self.task is not None and self.task.running:
                self._process.terminate()
            else:
                self._jobs.put(None)
            self._process.join(5)
            if self._process.is_alive():
                self._process.terminate()
        self._process = None

    # -- jobs --

    def submit(self, job: Job) -> Task:
        """Send a job to the helper process. Only one job at a time."""
        if self.task is not None and self.task.running:
            raise RuntimeError("A job is already running; cancel it first.")
        self.start()
        self._stop_event.clear()
        self._stop_asked_at = None
        self._numbers += 1
        self.task = Task(self._numbers, job)
        self._jobs.put((self._numbers, job))
        return self.task

    def cancel(self):
        """Stop the current job: a run is asked to stop cleanly, a mesh is terminated at once."""
        task = self.task
        if task is None or not task.running or task.stage == SAVING_STOPPED:
            return                              # (a stopped 2D run is already saving its results)
        if task.job.kind == "run":
            self._stop_event.set()
            self._stop_asked_at = time.perf_counter()
            task.stage = "Stopping"
        else:
            self._kill()
            self._finish(task, "cancelled")

    def poll(self) -> list:
        """Read every message that arrived; update self.task. Returns the messages (for logging)."""
        received = []
        task = self.task
        while self._messages is not None:
            try:
                message = self._messages.get_nowait()
            except queue_module.Empty:
                break
            except (EOFError, OSError):        # queue closed after the process was terminated
                break
            received.append(message)
            if task is None or message[0] != task.number or not task.running:
                continue                        # from an older, cancelled job
            kind = message[1]
            if kind == "stage":
                task.stage = message[2]
                if message[2] == SAVING_STOPPED:
                    self._stop_asked_at = None  # it has answered Stop and saves its results: never terminate it
            elif kind == "progress":
                task.iterations.extend(message[2])
                task.residuals.extend(message[3])
                for extra in (message[4] if len(message) > 4 and message[4] else ()):
                    task.equation_residuals.append(extra["residuals"])
                    for name, value in extra["monitors"].items():
                        task.monitors.setdefault(name, []).append(value)
                    task.positivity = extra["positivity"]
            elif kind == "done":
                task.payload = message[2]
                self._finish(task, "finished")
            elif kind == "stopped":
                self._finish(task, "stopped")
            elif kind == "error":
                task.error = message[2]
                task.details = message[3] if len(message) > 3 else ""
                self._finish(task, "failed")
        if task is not None and task.running:
            if self._stop_asked_at is not None and time.perf_counter() - self._stop_asked_at > STOP_GRACE_S:
                self._kill()                    # the run did not stop in time
                self._finish(task, "cancelled")
            elif self._process is None or not self._process.is_alive():
                code = None if self._process is None else self._process.exitcode
                task.error = f"The helper process stopped unexpectedly (exit code {code})."
                self._finish(task, "failed")
                self._process = None
        return received

    def wait(self, timeout=None) -> Task | None:
        """Poll until the current job ends (for scripts and tests; a GUI uses a timer instead)."""
        end = None if timeout is None else time.perf_counter() + timeout
        while self.task is not None and self.task.running:
            if end is not None and time.perf_counter() > end:
                raise TimeoutError("The background job did not finish in time.")
            self.poll()
            time.sleep(0.02)
        return self.task

    @staticmethod
    def _finish(task, status):
        task.status = status
        task.ended = time.perf_counter()

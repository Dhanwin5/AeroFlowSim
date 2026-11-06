# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Background runs for the AI connector: one run at a time, live progress, Stop, and a time limit.

A run is aeroflowsim.project.run_project(), the same function the command line uses (the GUI does the same steps
in its helper process), so a run started by an AI gives the same numbers as one started by hand. It runs in a
thread of the server process: the server has no window that could freeze, and a thread lets job_status read the
progress without any copying.

Stop works like the GUI's Stop: a 2D / 3D solver is asked to end cleanly after the current iteration (its
progress callback returns True) and saves the flow of that moment, marked "stopped", so continue_run carries on
from it; a 1D case ends without results (it takes seconds anyway). The time limit uses the same clean stop.
"""

import threading
import time
from dataclasses import dataclass, field

from aeroflowsim.tasks import StopRequested

MAX_HISTORY = 200000          # iterations kept for job_status (the whole history is in the result file anyway)


@dataclass
class ConnectorJob:
    id: str
    project: str                       # project name (folder name without .afsproj)
    status: str = "running"            # running, finished, stopped, failed
    iterations: list = field(default_factory=list)
    residuals: list = field(default_factory=list)
    monitors: dict = field(default_factory=dict)
    error: str = ""
    started: float = field(default_factory=time.time)
    ended: float | None = None
    stop_reason: str = ""              # "" / "asked" / "time limit"
    max_iterations: int | None = None
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    @property
    def running(self) -> bool:
        return self.status == "running"

    def elapsed_s(self) -> float:
        return (self.ended or time.time()) - self.started


class JobManager:
    def __init__(self, one_at_a_time=True, max_hours=12.0):
        self.one_at_a_time = one_at_a_time
        self.max_seconds = max_hours * 3600.0
        self.jobs: dict[str, ConnectorJob] = {}
        self._count = 0
        self._lock = threading.Lock()

    def running(self) -> list[ConnectorJob]:
        return [j for j in self.jobs.values() if j.running]

    def running_for(self, project_name) -> ConnectorJob | None:
        return next((j for j in self.running() if j.project == project_name), None)

    def start(self, project, fresh=False, on_done=None) -> ConnectorJob:
        """Start run_project(project) in a thread. on_done(job, output_or_None) is called in that thread at the end."""
        from aeroflowsim.project import run_project
        with self._lock:
            if self.running_for(project.name):
                raise RuntimeError(f"Project '{project.name}' is already running.")
            if self.one_at_a_time and self.running():
                raise RuntimeError(f"Another run is going on (project '{self.running()[0].project}'); one run at a "
                                   "time. Wait for it or stop it.")
            self._count += 1
            job = ConnectorJob(f"job-{self._count}", project.name,
                               max_iterations=project.values.get("max_iter"))
            self.jobs[job.id] = job

        def progress(iteration, residual, info=None):
            if len(job.iterations) < MAX_HISTORY:
                job.iterations.append(int(iteration))
                job.residuals.append(float(residual))
                for name, value in ((info or {}).get("monitors") or {}).items():
                    job.monitors.setdefault(name, []).append(float(value))
            if not job._stop.is_set() and time.time() - job.started > self.max_seconds:
                job.stop_reason = "time limit"
                job._stop.set()
            if job._stop.is_set():
                if info is not None:
                    return True                 # 2D / 3D: end cleanly after this iteration, keep the flow
                raise StopRequested()           # 1D: end now, no results
            return False

        def work():
            output = None
            try:
                output = run_project(project, progress=progress, fresh=fresh)
                status = output.result.info.get("status") if getattr(output.result, "info", None) else None
                job.status = "stopped" if (status == "stopped" or job._stop.is_set()) else "finished"
            except StopRequested:
                job.status = "stopped"
            except Exception as error:          # noqa: BLE001 - every failure is reported, never raised in a thread
                job.status = "failed"
                job.error = f"{type(error).__name__}: {error}"[:600]
            finally:
                job.ended = time.time()
                if on_done is not None:
                    try:
                        on_done(job, output)
                    except Exception:           # noqa: BLE001 - provenance must never hide the run's own result
                        pass

        job._thread = threading.Thread(target=work, daemon=True, name=f"aeroflowsim-{job.id}")
        job._thread.start()
        return job

    def stop(self, job_id) -> ConnectorJob:
        job = self.get(job_id)
        if job.running:
            job.stop_reason = job.stop_reason or "asked"
            job._stop.set()
        return job

    def get(self, job_id) -> ConnectorJob:
        if job_id not in self.jobs:
            raise KeyError(f"There is no job '{job_id}' in this session.")
        return self.jobs[job_id]

    def wait(self, job_id, timeout=None) -> ConnectorJob:
        job = self.get(job_id)
        if job._thread is not None:
            job._thread.join(timeout)
        return job

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run a case in the background so a GUI can show live progress and stop it.

Why a background thread? A GUI must stay responsive while the solver iterates: it redraws
the residual plot and listens for the Stop button. So the solver runs in a separate
"thread" (a second line of execution inside the same program), and the GUI simply reads
the latest numbers from the RunJob object every fraction of a second.

The thread calls aeroflowsim.run_case(), exactly the function the command line and scripts use,
so a run started from the GUI gives the same numbers as the same run from the command line.

How Stop works without changing the case contract: the case calls progress(iteration,
residual) after every iteration. Our progress function records the residual and, if Stop
was pressed, raises StopRequested. That exception jumps out of the case's loop, and the
job ends with status "stopped". (The case does not return, so a stopped run has no fields.)

Nothing here imports the GUI; the job can be tested with pytest.
"""

import threading
import time

from aeroflowsim.engine import run_case
from aeroflowsim.tasks import StopRequested   # one definition, shared with the process-based Worker


class RunJob:
    """One solver run of one case, executed in a background thread."""

    def __init__(self):
        self.iterations = []    # iteration numbers reported so far [-]
        self.residuals = []     # normalised residual at those iterations [-]
        self.status = "idle"    # "idle", "running", "finished", "stopped" or "failed"
        self.error = ""         # error message if status == "failed"
        self.result = None      # Result returned by case.run (when finished)
        self.reference = None   # reference fields from case.reference (when finished)
        self.reference_lines = []  # exact overlay lines from case.reference_lines (when finished)
        self.checks = []        # validity check results (when finished), see aeroflowsim/checks.py
        self.output = None      # the whole RunOutput of aeroflowsim.run_case (when finished)
        self.elapsed_s = 0.0    # wall-clock run time [s]
        self._start_time = 0.0  # time.perf_counter() at start [s]
        self._stop_event = threading.Event()  # set when the user presses Stop
        self._lock = threading.Lock()         # protects the lists while both threads use them
        self._thread = None

    # ---- called by the GUI ------------------------------------------------------------

    def start(self, case, params, mesh):
        """Begin solving case with the given (validated) params and mesh in the background."""
        self.status = "running"
        self._start_time = time.perf_counter()
        self._thread = threading.Thread(target=self._work, args=(case, params, mesh), daemon=True)
        self._thread.start()

    def stop(self):
        """Ask the running solver to stop at its next iteration."""
        self._stop_event.set()

    def wait(self, timeout=None):
        """Block until the run has ended (used by tests and the command line)."""
        if self._thread is not None:
            self._thread.join(timeout)

    @property
    def running(self) -> bool:
        return self.status == "running"

    def snapshot(self):
        """Copies of (iterations, residuals) that are safe to plot while the run continues."""
        with self._lock:
            return list(self.iterations), list(self.residuals)

    def current_elapsed_s(self) -> float:
        """Run time so far [s] (or the final run time once the run has ended)."""
        if self.running:
            return time.perf_counter() - self._start_time
        return self.elapsed_s

    # ---- runs in the background thread -------------------------------------------------

    def _progress(self, iteration, residual):
        """The progress callback handed to case.run()."""
        with self._lock:
            self.iterations.append(iteration)
            self.residuals.append(residual)
        if self._stop_event.is_set():
            raise StopRequested()

    def _work(self, case, params, mesh):
        """Run the case through the shared engine; record how the run ended."""
        try:
            output = run_case(case, params, mesh=mesh, progress=self._progress)
            self.output, self.reference_lines, self.checks = output, output.reference_lines, output.checks
            self.result, self.reference = output.result, output.reference
            status = "finished"
        except StopRequested:
            status = "stopped"
        except Exception as error:  # any solver error is shown in the GUI instead of crashing it
            self.error = f"{type(error).__name__}: {error}"
            status = "failed"
        self.elapsed_s = time.perf_counter() - self._start_time
        self.status = status  # set last, so result/reference are ready when the GUI sees "finished"

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run step: Run / Stop, live progress and residual plot, and the messages of this run.

The solver runs in the background worker (aeroflowsim/tasks.py); the main window forwards its
updates here. The residual plot is redrawn at most about three times a second, so even very fast
solvers never slow the window down.
"""

import time

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QProgressBar, QVBoxLayout, QWidget

from aeroflowsim.gui.figures import PlotCanvas, residual_figure
from aeroflowsim.euler.setup import EQUATIONS
from aeroflowsim.gui.logic import history_extras, progress_fraction
from aeroflowsim.gui.widgets import Banner

REDRAW_S = 0.3   # [s] shortest time between two redraws of the live residual plot


class RunPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.run_button = QPushButton("Run")
        self.run_button.setToolTip("Mesh if needed, then solve (F5)")
        self.run_button.clicked.connect(window.run_case)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setToolTip("End the run after the current iteration (Shift+F5)")
        self.stop_button.clicked.connect(window.cancel_job)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.info = QLabel()
        bar = QHBoxLayout()
        for w in (self.run_button, self.stop_button, self.progress):
            bar.addWidget(w)
        self.banner = Banner()
        self.plot = PlotCanvas()
        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(self.info)
        layout.addWidget(self.banner)
        layout.addWidget(self.plot, 1)
        self._last_draw = 0.0
        self._history = ([], [], None)          # what the plot shows: iterations, residuals, tolerance
        self._extra = {}                        # 2D solvers: residual per equation and the monitors

    def refresh(self):
        w = self.window
        project = w.project
        running = w.runner.busy and w.runner.task.job.kind == "run"
        has_solver = project is not None and project.case.has_solver
        self.run_button.setEnabled(has_solver and not w.runner.busy)
        self.stop_button.setEnabled(running)
        if project is None:
            return
        if not has_solver:
            self.banner.show_message(project.case.solver_message, "info")
            return
        record = project.steps.get("run") or {}
        status = project.status("run")
        if running:
            self.banner.hide_message()
        elif status == "error":
            self.banner.show_message(f"The last run failed: {record.get('error')}", "error")
        elif status == "ok":
            done = "converged" if record.get("converged") else "finished but NOT converged"
            self.banner.show_message(f"Up to date: {done} after {record.get('iterations', 0):,} iterations "
                                     f"({record.get('run_s') or 0:.3g} s). See Results.", "info")
        elif status == "outdated":
            self.banner.show_message("The last results come from older inputs. Press Run to update them.", "warning")
        else:
            self.banner.show_message("Not run yet. Press Run (the mesh is made first if needed).", "info")

    def show_task(self, task, force=False):
        """Live view of a running (or just ended) job."""
        if task.job.kind == "mesh":
            self.info.setText(f"{task.stage} ... {task.elapsed_s:.1f} s")
            self.progress.setRange(0, 0)
            return
        self.progress.setRange(0, 1000)
        params = task.job.params
        if task.iterations:
            it, res = task.iterations[-1], task.residuals[-1]
            self.progress.setValue(int(1000 * progress_fraction(params, it, res)))
            text = f"{task.stage}: iteration {it:,}, residual {res:.3e}, {task.elapsed_s:.1f} s"
            if task.positivity:
                text += f", first-order fallback at {task.positivity} faces"
            self.info.setText(text)
        else:
            self.info.setText(f"{task.stage} ... {task.elapsed_s:.1f} s")
        now = time.perf_counter()
        if force or now - self._last_draw > REDRAW_S:
            self._last_draw = now
            self._history = (task.iterations, task.residuals, params.get("tol"))
            self._extra = ({"equation_residuals": task.equation_residuals, "equations": EQUATIONS,
                            "monitors": task.monitors} if task.equation_residuals else {})
            self.redraw()

    def reset(self):
        """Empty progress, text and plot (a project was opened)."""
        self.info.setText("")
        self.progress.setValue(0)
        self._history = ([], [], None)
        self._extra = {}
        self.redraw()

    def redraw(self):
        """Draw the residual plot again (new data, or a theme change)."""
        residual_figure(*self._history, figure=self.plot.figure, prefs=self.window.units, **self._extra)
        self.plot.canvas.draw_idle()

    def show_history(self, result, tol):
        """The residual history of finished results (e.g. after opening a project)."""
        self._history = (list(range(1, len(result.residuals) + 1)), result.residuals, tol)
        self._extra = history_extras(result)
        self.redraw()
        self.progress.setValue(1000 if result.converged else self.progress.value())

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
        self.numerics_button = QPushButton("Suggested numerics...")
        self.numerics_button.setToolTip("CFL number, first-order start and initial solution suggested from the flow "
                                        "inputs, each with its reason (applied only if you press Apply).")
        self.numerics_button.clicked.connect(self.show_numerics_suggestions)
        self.diagnose_button = QPushButton("What to try...")
        self.diagnose_button.setToolTip("After a run that diverged or needed CFL reductions: what to change, and why.")
        self.diagnose_button.clicked.connect(self.show_diagnosis)
        bar = QHBoxLayout()
        for w in (self.run_button, self.stop_button, self.progress, self.numerics_button, self.diagnose_button):
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
        flow_solver = project.case.schema.euler_solver
        self.numerics_button.setVisible(flow_solver)
        self.diagnose_button.setVisible(flow_solver)
        self.diagnose_button.setEnabled(bool(self._diagnosis()))
        record = project.steps.get("run") or {}
        status = project.status("run")
        if running:
            self.banner.hide_message()
        elif status == "error":
            self.banner.show_message(f"The last run failed: {record.get('error')}", "error")
        elif status == "ok" and self._diagnosis() and w.results["result"].info.get("status") == "diverged":
            self.banner.show_message("The run DIVERGED (the solution became unphysical). Press 'What to try...' "
                                     "for suggestions; the Validity checks say where it failed.", "error")
        elif status == "ok" and record.get("status") == "stopped":
            self.banner.show_message(f"Stopped by you after {record.get('iterations', 0):,} iterations: the Results step "
                                     "shows the flow of that moment (NOT converged). To continue from it, set Initial "
                                     "solution to 'Previous result (restart)' and press Run.", "warning")
        elif status == "ok":
            done = "converged" if record.get("converged") else "finished but NOT converged"
            self.banner.show_message(f"Up to date: {done} after {record.get('iterations', 0):,} iterations "
                                     f"({record.get('run_s') or 0:.3g} s). See Results.", "info")
        elif status == "outdated":
            self.banner.show_message("The last results come from older inputs. Press Run to update them.", "warning")
        else:
            self.banner.show_message("Not run yet. Press Run (the mesh is made first if needed).", "info")

    def _diagnosis(self):
        """The smart rule's suggestions for the last result (empty if it ran well)."""
        from aeroflowsim.smart_rules import diagnose
        w = self.window
        if w.project is None or w.results is None:
            return []
        try:
            return diagnose(w.project.case, w.results["params"], w.results["result"])
        except (ValueError, KeyError, AttributeError):
            return []

    def show_diagnosis(self):
        from aeroflowsim.gui.geometry_forms import SuggestionsDialog
        SuggestionsDialog(self._diagnosis(), self._apply, self, title="What to try",
                          intro="The last run diverged or needed CFL reductions. Things to try, with the reason.",
                          empty="Nothing to suggest: the last run was stable.").exec()

    def show_numerics_suggestions(self):
        from aeroflowsim.gui.geometry_forms import SuggestionsDialog
        from aeroflowsim.smart_rules import numerics_suggestions
        project = self.window.project
        try:
            found = numerics_suggestions(project.case, project.params())
        except ValueError as error:
            found = []
            self.window.log(f"No numerics suggestions: {error}", "warning")
        SuggestionsDialog(found, self._apply, self, title="Suggested numerics",
                          intro="Suggestions from the flow inputs (Mach number, initial solution, time scheme).",
                          empty="No suggestions: the numerics already suit these flow inputs.").exec()

    def _apply(self, suggestion):
        self.window.set_inputs(suggestion.inputs, f"suggested {suggestion.title.lower()}")

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

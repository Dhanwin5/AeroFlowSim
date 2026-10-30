# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run step: Run / Continue, Start from scratch, Stop, live progress and residual plot, messages.

The solver runs in the background worker (aeroflowsim/tasks.py); the main window forwards its
updates here. The residual plot is redrawn at most about three times a second, so even very fast
solvers never slow the window down.

Like the best CFD tools, Run CARRIES ON from the current solution when the project has one on this mesh
(after a Stop at iteration 158 the next iteration is 159, and the plot continues); "Start from scratch" is the
only way to begin again from the Initial solution. A new mesh starts from scratch by itself (the old flow
does not fit it).
"""

import time

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QProgressBar, QVBoxLayout, QWidget

from aeroflowsim.gui.figures import PlotCanvas, residual_figure
from aeroflowsim.euler.setup import EQUATIONS
from aeroflowsim.gui.logic import history_extras, progress_fraction
from aeroflowsim.gui.widgets import Banner

REDRAW_S = 0.3   # [s] shortest time between two redraws of the live residual plot



def _solver_text(window) -> str:
    """', Numba, 15 threads' from the run's info (Run diagnostics); '' for old results or 1D templates."""
    info = getattr((window.results or {}).get("result"), "info", None) or {}
    if "backend" not in info:
        return ""
    if info["backend"] == "numba":
        return f", Numba, {info.get('threads', 1)} threads"
    return ", NumPy"

class RunPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.run_button = QPushButton("Run")
        self.run_button.setToolTip("Mesh if needed, then solve (F5). With a solution on this mesh, the run carries "
                                   "on from it.")
        self.run_button.clicked.connect(window.run_case)
        self.fresh_button = QPushButton("Start from scratch")
        self.fresh_button.setToolTip("Begin again from iteration 1 with the Initial solution (uniform or quasi-1D), "
                                     "instead of carrying on from the current solution.")
        self.fresh_button.clicked.connect(window.run_from_scratch)
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
        self.start_button = QPushButton("Start options...")
        self.start_button.setToolTip("Patch regions on top of the Initial solution (for a start from scratch), and "
                                     "whether a run on a new mesh starts from the old solution interpolated onto it.")
        self.start_button.clicked.connect(self.show_start_options)
        bar = QHBoxLayout()
        for w in (self.run_button, self.fresh_button, self.stop_button, self.progress, self.numerics_button,
                  self.start_button, self.diagnose_button):
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
        self._before = None                     # history of the run being continued (drawn before the new part)

    def refresh(self):
        w = self.window
        project = w.project
        running = w.runner.busy and w.runner.task.job.kind == "run"
        has_solver = project is not None and project.case.has_solver
        self.run_button.setEnabled(has_solver and not w.runner.busy)
        self.stop_button.setEnabled(running)
        if project is None:
            return
        _path, done = w.continuation() if has_solver else (None, 0)
        self.run_button.setText(f"Continue (from iteration {done + 1:,})" if done and not running else "Run")
        self.fresh_button.setVisible(bool(done) or running)
        self.fresh_button.setEnabled(bool(done) and not w.runner.busy)
        if not has_solver:
            self.banner.show_message(project.case.solver_message, "info")
            return
        flow_solver = project.case.schema.euler_solver
        self.numerics_button.setVisible(flow_solver)
        self.diagnose_button.setVisible(flow_solver)
        self.start_button.setVisible(flow_solver)
        self.start_button.setEnabled(not w.runner.busy)
        patches = len(project.post.get("init_patches") or [])
        self.start_button.setText(f"Start options ({patches} patch region{'s' if patches != 1 else ''})..."
                                  if patches else "Start options...")
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
                                     "shows the flow of that moment (NOT converged). Press Continue to carry on from "
                                     f"iteration {record.get('iterations', 0) + 1:,}, or Start from scratch.", "warning")
        elif status == "ok":
            done = "converged" if record.get("converged") else "finished but NOT converged"
            self.banner.show_message(f"Up to date: {done} after {record.get('iterations', 0):,} iterations "
                                     f"({record.get('run_s') or 0:.3g} s{_solver_text(w)}). See Results.", "info")
        elif status == "outdated" and done:
            self.banner.show_message("The inputs changed since the last run. Continue carries on from the current "
                                     "flow with the new inputs (usually much faster); Start from scratch begins again "
                                     "from the Initial solution.", "warning")
        elif status == "outdated" and w.results is not None and flow_solver and \
                project.interpolation_source(w.mesh) is not None:
            self.banner.show_message("The mesh has changed since the last run. Press Run to update the results: it starts "
                                     "from the previous solution interpolated onto the new mesh (usually much faster); "
                                     "Start options turns this off.", "warning")
        elif status == "outdated" and w.results is not None:
            self.banner.show_message("The last results come from older inputs (or another mesh). Press Run to update "
                                     "them: it starts from the Initial solution, because the old flow does not fit "
                                     "this mesh.", "warning")
        elif status == "outdated":
            self.banner.show_message("The last results come from older inputs. Press Run to update them.", "warning")
        else:
            self.banner.show_message("Not run yet. Press Run (the mesh is made first if needed).", "info")

    def show_start_options(self):
        from aeroflowsim.gui.post_panels import InitialisationDialog
        project = self.window.project
        if project is None:
            return
        dialog = InitialisationDialog(self, project, self.window.units)
        if dialog.exec():
            dialog.apply()
            self.window.update_title()
            self.refresh()

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

    def start(self, previous=None):
        """A run was sent: previous = the Result it carries on from (its history is drawn first), or None."""
        self._before = None
        if previous is not None and len(previous.residuals):
            extras = history_extras(previous)
            self._before = (list(range(1, len(previous.residuals) + 1)), list(previous.residuals), extras)

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
            its, res, eq, mons = task.iterations, task.residuals, task.equation_residuals, task.monitors
            if self._before is not None and task.job.restart:      # carry the earlier history on
                b_its, b_res, b_extra = self._before
                cut = len(b_its) if not its else min(len(b_its), its[0] - 1)
                its, res = b_its[:cut] + list(its), b_res[:cut] + list(res)
                if eq and b_extra:
                    eq = [list(r) for r in b_extra["equation_residuals"][:cut]] + list(eq)
                    mons = {k: list(b_extra["monitors"].get(k, ()))[:cut] + list(v) for k, v in mons.items()}
            self._history = (its, res, params.get("tol"))
            self._extra = ({"equation_residuals": eq, "equations": EQUATIONS, "monitors": mons} if eq else {})
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

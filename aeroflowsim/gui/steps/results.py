# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Results step: field plots against the reference, key numbers, colour pictures (shape view, x-t
diagram, 2D contour) and export. Out-of-date results carry an amber banner and are never shown as
current. Validity checks are in the Validity checks panel.

2D results get the post-processing workspace instead (Prompt 7b): panels on the left (Display, Surfaces, Reports,
XY plot, Snapshots, Fields; gui/post_panels.py), one, two or four linked views of the flow (gui/flow_view.py) and
the plots and key numbers below them. Every number comes from aeroflowsim/post/."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from aeroflowsim.gui.figures import PlotCanvas, field_figure, message_figure, residual_figure, wall_figure
from aeroflowsim.gui.theme import paper_style
from aeroflowsim.gui.logic import (available_views, cell_value_rows, display_field, flow_plots, history_extras,
                                   is_face_mesh, key_number_rows, key_result_tiles, results_mesh_mismatch,
                                   run_status_text)
from aeroflowsim.gui.vtk_view import MeshView
from aeroflowsim.gui.widgets import Banner, SummaryCard, ValueTable
from aeroflowsim.runner import fields_csv_text
from aeroflowsim.visualise import COLORMAPS, contour_2d, shape_view, xt_diagram


def _number(text):
    try:
        return float(text)
    except ValueError:
        return None


class ResultsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.banner = Banner()
        self.card = SummaryCard()
        self.field = QComboBox()
        self.field.currentIndexChanged.connect(lambda _: self.draw_field())
        self.field_plot = PlotCanvas()
        self.numbers = ValueTable(["Quantity", "Value", "Unit"])
        self.numbers.setMinimumWidth(360)        # values never cut off next to the field plot
        csv = QPushButton("Save CSV...")
        csv.clicked.connect(self.save_csv)
        png = QPushButton("Save PNG...")
        png.clicked.connect(self.save_png)
        folder = QPushButton("Open results folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(window.project.results_dir))))
        # 2D results: the field in the VTK view, with its own colour map, range and mesh edges
        self.flow_view = MeshView()
        self.flow_view.cell_picked.connect(self.cell_picked)
        self.flow_cmap = QComboBox()
        self.flow_cmap.addItems(COLORMAPS)
        self.flow_cmap.setCurrentText("turbo")
        self.flow_auto = QCheckBox("Auto range", checked=True)
        self.flow_min, self.flow_max = QLineEdit(), QLineEdit()
        for box in (self.flow_min, self.flow_max):
            box.setFixedWidth(84)
            box.setAlignment(Qt.AlignRight)
            box.editingFinished.connect(lambda: self.draw_field(keep_camera=True))
        self.flow_edges = QCheckBox("Mesh edges")
        self.flow_cmap.currentIndexChanged.connect(lambda _: self.draw_field(keep_camera=True))
        self.flow_auto.toggled.connect(lambda _: self.draw_field(keep_camera=True))
        self.flow_edges.toggled.connect(self.flow_view.set_edges)
        self.flow_controls = QWidget()
        controls = QHBoxLayout(self.flow_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        for w in (QLabel("Colour map"), self.flow_cmap, self.flow_auto, QLabel("min"), self.flow_min, QLabel("max"),
                  self.flow_max, self.flow_edges):
            controls.addWidget(w)
        vtu = QPushButton("Save .vtu...")
        vtu.setToolTip("The solution for ParaView: every field per cell, and the velocity vector.")
        vtu.clicked.connect(self.save_vtu)
        self.vtu_button = vtu
        top = QHBoxLayout()
        for w in (QLabel("Field"), self.field, self.flow_controls):
            top.addWidget(w)
        top.addStretch(1)
        for w in (csv, png, vtu, folder):
            top.addWidget(w)
        self.field.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.field_stack = QStackedWidget()
        self.field_stack.addWidget(self.field_plot)
        self.field_stack.addWidget(self.flow_view)
        plot_area = QWidget()
        plot_layout = QVBoxLayout(plot_area)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.addLayout(top)
        plot_layout.addWidget(self.field_stack, 1)
        numbers_area = QWidget()
        numbers_layout = QVBoxLayout(numbers_area)
        numbers_layout.setContentsMargins(0, 0, 0, 0)
        numbers_layout.addWidget(QLabel("<b>Key numbers</b>"))
        numbers_layout.addWidget(self.numbers, 1)
        upper = QSplitter()
        upper.addWidget(plot_area)
        upper.addWidget(numbers_area)
        upper.setStretchFactor(0, 3)
        upper.setStretchFactor(1, 2)

        # Colour pictures (same choices as before: view, field, colour map, range, overlays).
        self.view = QComboBox()
        self.cfield = QComboBox()
        self.cmap = QComboBox()
        self.cmap.addItems(COLORMAPS)
        self.auto = QCheckBox("Automatic colour range", checked=True)
        self.vmin, self.vmax = QLineEdit(), QLineEdit()
        self.lines = QCheckBox("Show exact wave paths", checked=True)
        self.mesh_lines = QCheckBox("Show mesh lines")
        self.mirror = QCheckBox("Mirror about the axis")
        self.range_note = QLabel()
        self.range_note.setObjectName("note")
        contour_png = QPushButton("Save picture...")
        contour_png.clicked.connect(self.save_contour)
        grid = QGridLayout()
        grid.addWidget(QLabel("View"), 0, 0)
        grid.addWidget(self.view, 0, 1)
        grid.addWidget(QLabel("Field"), 1, 0)
        grid.addWidget(self.cfield, 1, 1)
        grid.addWidget(QLabel("Colour map"), 2, 0)
        grid.addWidget(self.cmap, 2, 1)
        grid.addWidget(self.auto, 3, 0, 1, 2)
        grid.addWidget(QLabel("Minimum"), 4, 0)
        grid.addWidget(self.vmin, 4, 1)
        grid.addWidget(QLabel("Maximum"), 5, 0)
        grid.addWidget(self.vmax, 5, 1)
        grid.addWidget(self.range_note, 6, 0, 1, 2)
        for i, w in enumerate((self.lines, self.mesh_lines, self.mirror, contour_png)):
            grid.addWidget(w, 7 + i, 0, 1, 2)
        controls = QWidget()
        controls.setLayout(grid)
        self.contour_plot = PlotCanvas()
        contour_box = QGroupBox("Colour pictures")
        box_layout = QHBoxLayout(contour_box)
        box_layout.addWidget(controls)
        box_layout.addWidget(self.contour_plot, 1)
        self.contour_box = contour_box
        self.view.currentIndexChanged.connect(lambda _: self._fill_contour_fields())
        for w in (self.cfield, self.cmap):
            w.currentIndexChanged.connect(lambda _: self.draw_contour())
        for w in (self.auto, self.lines, self.mesh_lines, self.mirror):
            w.toggled.connect(lambda _: self.draw_contour())
        for w in (self.vmin, self.vmax):
            w.editingFinished.connect(self.draw_contour)

        for combo in (self.view, self.cfield, self.cmap):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        controls.setMaximumWidth(300)
        # 2D results: wall pressure / Cp and the convergence history under the field view
        self.flow_plot_choice = QComboBox()
        self.flow_plot_choice.currentIndexChanged.connect(lambda _: self.draw_flow_plot())
        self.flow_plot = PlotCanvas()
        flow_box = QGroupBox("Plots")
        flow_layout = QVBoxLayout(flow_box)
        row = QHBoxLayout()
        row.addWidget(QLabel("Plot"))
        row.addWidget(self.flow_plot_choice)
        row.addStretch(1)
        flow_layout.addLayout(row)
        flow_layout.addWidget(self.flow_plot, 1)
        self.flow_box = flow_box
        splitter = QSplitter(Qt.Vertical)      # field plot + key numbers above, colour pictures below
        splitter.addWidget(upper)
        splitter.addWidget(contour_box)
        splitter.addWidget(flow_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        self._build_post()
        layout = QVBoxLayout(self)
        layout.addWidget(self.banner)
        layout.addWidget(self.card)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.post_area, 1)
        self.splitter = splitter
        self._shown = None

    # ---- the 2D post-processing workspace ----------------------------------------------------

    def _build_post(self):
        from aeroflowsim.gui.flow_view import ViewGrid
        from aeroflowsim.gui.post_panels import (DisplayPanel, FieldsPanel, ReportsPanel, SnapshotsPanel,
                                                 SurfacesPanel, XYPanel)
        self._solution = None
        self._snapshot_cache = {}
        self.awaiting = None                 # "point", "line_1", "line_2" while a surface is made by clicking
        self._line_start = None
        self.grid = ViewGrid()
        for v in self.grid.views:
            self._connect_view(v)
        self.display = DisplayPanel(self)
        self.surfaces_panel = SurfacesPanel(self)
        self.reports = ReportsPanel(self)
        self.xy = XYPanel(self)
        self.snapshots_panel = SnapshotsPanel(self)
        self.fields_panel = FieldsPanel(self)
        self.surfaces_panel.changed.connect(self._surfaces_changed)
        self.post_tabs = QTabWidget()
        for panel, name in ((self.display, "Display"), (self.surfaces_panel, "Surfaces"), (self.reports, "Reports"),
                            (self.xy, "XY plot"), (self.snapshots_panel, "Snapshots"), (self.fields_panel, "Fields")):
            self.post_tabs.addTab(panel, name)
        self.post_tabs.setTabPosition(QTabWidget.West)      # every tab visible, also in a narrow panel
        self.post_tabs.setMinimumWidth(360)
        self.plots2d_choice = QComboBox()
        self.plots2d_choice.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.plots2d_choice.currentIndexChanged.connect(lambda _: self.draw_plot2d())
        self.plots2d = PlotCanvas()
        plots = QWidget()
        pl = QVBoxLayout(plots)
        pl.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("Plot"))
        row.addWidget(self.plots2d_choice)
        row.addStretch(1)
        for text, slot in (("Save .vtu...", self.save_vtu), ("Export...", self.export_fields),
                           ("Report...", self.make_report)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        pl.addLayout(row)
        pl.addWidget(self.plots2d, 1)
        self.numbers2d = ValueTable(["Quantity", "Value", "Unit"])
        lower = QTabWidget()
        self.lower_tabs = lower
        lower.addTab(plots, "Plots")
        lower.addTab(self.numbers2d, "Key numbers")
        right = QSplitter(Qt.Vertical)
        right.addWidget(self.grid)
        right.addWidget(lower)
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 2)
        area = QSplitter()
        area.addWidget(self.post_tabs)
        area.addWidget(right)
        area.setStretchFactor(0, 0)
        area.setStretchFactor(1, 1)
        area.setSizes([360, 1000])
        self.post_area = area
        self.post_area.setVisible(False)

    def _connect_view(self, v):
        v.probe_requested.connect(self.probe)
        v.point_surface_requested.connect(lambda x, y: self.surfaces_panel.add(self._point_surface(x, y)))
        v.line_surface_requested.connect(lambda x0, y0, x1, y1: self.surfaces_panel.add(
            self._line_surface(x0, y0, x1, y1)))
        v.seed_requested.connect(lambda x, y: self.display.add_seed(x, y))
        v.clicked.connect(self._view_clicked)
        v.cell_picked.connect(self.cell_picked)

    def _point_surface(self, x, y):
        from aeroflowsim.post.surfaces import Surface
        return Surface.point((x, y), name="probe")

    def _line_surface(self, x0, y0, x1, y1):
        from aeroflowsim.post.surfaces import Surface
        return Surface.line((x0, y0), (x1, y1), name="line")

    def _view_clicked(self, x, y):
        if self.awaiting == "point":
            self.awaiting = None
            self.surfaces_panel.add(self._point_surface(x, y))
        elif self.awaiting == "line_1":
            self._line_start = (x, y)
            self.awaiting = "line_2"
            self.window.log("Now click the end point of the line")
        elif self.awaiting == "line_2":
            self.awaiting = None
            self.surfaces_panel.add(self._line_surface(*self._line_start, x, y))

    def solution(self):
        """The current result as a post.Solution (None for 1D results or results of an older mesh)."""
        w = self.window
        if w.results is None or not is_face_mesh(w.mesh) or results_mesh_mismatch(w.results["result"], w.mesh):
            return None
        if self._solution is None or self._solution_key != id(w.results):
            from aeroflowsim.post.solution import Solution
            try:
                self._solution = Solution.from_payload(w.mesh, w.results, case=w.project.case, base=w.project.folder,
                                                       custom_fields=dict(w.project.custom_fields))
            except ValueError as exc:
                self.window.log(f"Post-processing not available: {exc}", "warning")
                self._solution = None
            self._solution_key = id(w.results)
            self._snapshot_cache = {}
        return self._solution

    def snapshot_solution(self, name):
        if name not in self._snapshot_cache:
            from aeroflowsim.post.snapshots import snapshot_mesh
            from aeroflowsim.post.solution import Solution
            from aeroflowsim.result_io import load_run
            from aeroflowsim.post.snapshots import snapshot_path
            project = self.window.project
            sol = self.solution()
            payload = load_run(snapshot_path(project, name))
            mesh = sol.mesh if sol is not None and len(payload["result"].fields["rho"].values) == sol.mesh.n_cells                 else snapshot_mesh(project, name)
            self._snapshot_cache[name] = Solution.from_payload(mesh, payload, case=project.case, base=project.folder,
                                                               name=name, custom_fields=dict(project.custom_fields))
        return self._snapshot_cache[name]

    def view_solution(self, k):
        """The Solution view k shows: the current result, a snapshot, or a difference A - B (as a solution whose
        shown field is the difference)."""
        from aeroflowsim.gui.post_panels import SOURCE_CURRENT
        source = self.display.sources[k] if k < len(self.display.sources) else SOURCE_CURRENT
        sol = self.solution()
        if sol is None:
            return None
        if source == SOURCE_CURRENT:
            return sol
        if source.startswith("Difference: "):
            other = source.split(" - ", 1)[1]
            return self._difference_solution(sol, self.snapshot_solution(other), self.display.scenes[k].field)
        return self.snapshot_solution(source)

    def _difference_solution(self, a, b, name):
        from aeroflowsim.post.compare import difference
        d = difference(a, b, name)
        key = f"diff_{name}"
        fields = dict(a.fields)
        out = a.with_fields(fields, name=f"{a.name} - {b.name}")
        out.fields[key] = d.values
        out.units[key] = d.unit
        out.labels[key] = f"Difference of {d.label}" + (" (interpolated)" if d.interpolated else "")
        out._difference_of = (name, key)
        return out

    def surfaces(self, project_only=False):
        from aeroflowsim.post.surfaces import default_surfaces, surfaces_from
        project = self.window.project
        own = surfaces_from(project.post["surfaces"]) if project else []
        if project_only:
            return own
        sol = self.solution()
        names = {s.name for s in own}
        return own + [s for s in (default_surfaces(sol) if sol is not None else []) if s.name not in names]

    def surface_by_name(self, name):
        return next((s for s in self.surfaces() if s.name == name), None)

    def set_view_count(self, n):
        self.grid.set_count(n)
        for v in self.grid.views:
            if not getattr(v, "_connected", False):
                self._connect_view(v)
                v._connected = True
        self.draw_all()

    def draw_all(self, keep_camera=True):
        for k in range(self.grid.count):
            self.draw_view(k, keep_camera)

    def draw_view(self, k, keep_camera=True):
        from aeroflowsim.gui.results_logic import hover_text, prepare, scene_problem
        from aeroflowsim.post.surfaces import evaluate_surface
        if k >= self.grid.count:
            return
        view = self.grid.views[k]
        sol = self.view_solution(k)
        if sol is None:
            mismatch = results_mesh_mismatch(self.window.results["result"], self.window.mesh)                 if self.window.results else None
            view.clear(mismatch or "No 2D result")
            return
        scene = self.display.scenes[k]
        diff = getattr(sol, "_difference_of", None)
        if diff is not None:                     # a difference view: show A - B with a diverging map
            from aeroflowsim.gui.results_logic import Scene
            scene = Scene.from_dict({**scene.to_dict(), "field": diff[1], "cmap": "RdBu_r", "log_scale": False})
        problem = scene_problem(sol, scene)
        if k == self.display.view_index:
            self.display.set_problem(problem)
        if problem:
            if scene.log_scale:
                scene.log_scale = False
            if scene.revolve and not sol.axisymmetric:
                scene.revolve = False
        snaps = []
        if scene.range_mode == "Over all snapshots":
            from aeroflowsim.post.snapshots import list_snapshots
            snaps = [self.snapshot_solution(s["name"]) for s in list_snapshots(self.window.project)]
            snaps = [s for s in snaps if s.mesh.n_cells == sol.mesh.n_cells]
        try:
            data = prepare(sol, scene, self.window.units, snaps, {s.name: s for s in self.surfaces()})
        except Exception as exc:                 # noqa: BLE001 - show the problem, never crash the page
            view.clear(f"Cannot draw this scene: {exc}")
            return
        overlays = []
        for s in self.surfaces(project_only=True):
            if s.visible and not s.problem(sol):
                try:
                    overlays.append(evaluate_surface(sol, s))
                except ValueError:
                    pass
        view.hover = lambda x, y, sol=sol, scene=scene: hover_text(sol, scene, (x, y), self.window.units)
        first = not getattr(view, "_drawn_once", False)
        view.draw(sol, scene, data, overlays, keep_camera=keep_camera and not first)
        view._drawn_once = True

    def save_view_picture(self, k, path, scale=2, transparent=False, paper=True):
        from aeroflowsim.post.surfaces import evaluate_surface
        sol = self.view_solution(k)
        overlays = [evaluate_surface(sol, s) for s in self.surfaces(project_only=True) if s.visible and not s.problem(sol)]             if sol is not None else []
        self.grid.views[k].picture(path, scale, transparent, paper, overlays)
        self.window.log(f"Picture saved to {path}")

    def probe(self, x, y):
        from aeroflowsim.gui.results_logic import probe_rows
        sol = self.solution()
        if sol is None:
            return
        unit, k = self.surfaces_panel.length()
        self.window.show_properties(f"Probe at ({x * k:.4g}, {y * k:.4g}) {unit}", probe_rows(sol, (x, y), self.window.units))

    def compare_with(self, name):
        """Two views side by side (current and snapshot) and a difference in a third: 4-view layout."""
        from aeroflowsim.gui.post_panels import SOURCE_CURRENT
        d = self.display
        d.layout_choice.blockSignals(True)
        d.layout_choice.setCurrentText("Four views")
        d.layout_choice.blockSignals(False)
        d._update_views_list()
        field = d.scenes[0].field
        from aeroflowsim.gui.results_logic import Scene
        d.sources[:4] = [SOURCE_CURRENT, name, f"Difference: {SOURCE_CURRENT} - {name}", SOURCE_CURRENT]
        for k in range(1, 4):
            d.scenes[k] = Scene.from_dict(d.scenes[0].to_dict())
        d.scenes[3] = Scene.from_dict({**d.scenes[0].to_dict(), "field": field, "contour_lines": True})
        d.fill_sources()
        self.set_view_count(4)
        d._load(d.view_index)

    def snapshots_changed(self):
        self._snapshot_cache = {}
        self.snapshots_panel.fill()
        self.display.fill_sources()
        self.xy.fill()

    def custom_fields_changed(self):
        sol = self.solution()
        if sol is not None:
            sol.custom_fields = dict(self.window.project.custom_fields)
            sol._cache.pop("fields", None)
        self._snapshot_cache = {}
        self.fields_panel.fill()
        self.display.fill()
        self.reports.fill()
        self.xy.fill()

    def _surfaces_changed(self):
        self.display.fill_seed_surfaces()
        self.reports.fill()
        self.xy.fill()
        self.draw_all()

    def _fill_post(self):
        result = self.window.results["result"]
        self.numbers2d.set_rows(key_number_rows(result, self.window.results.get("reference"),
                                                self.window.results.get("run_s"), self.window.units))
        plots = flow_plots(result)
        self._panel_figures = {}
        self.plots2d_choice.blockSignals(True)
        self.plots2d_choice.clear()
        self.plots2d_choice.addItems(plots)
        self.plots2d_choice.blockSignals(False)
        self.draw_plot2d()
        for panel in (self.display, self.surfaces_panel, self.reports, self.xy, self.snapshots_panel,
                      self.fields_panel):
            panel.fill()
        self.draw_all(keep_camera=False)

    def show_figure(self, fig, name):
        """Show a figure made by a panel (e.g. the XY plot) in the Plots area under the view."""
        if self.plots2d_choice.findText(name) < 0:
            self.plots2d_choice.blockSignals(True)
            self.plots2d_choice.addItem(name)
            self.plots2d_choice.blockSignals(False)
        self.plots2d_choice.blockSignals(True)
        self.plots2d_choice.setCurrentText(name)
        self.plots2d_choice.blockSignals(False)
        self._panel_figures = getattr(self, "_panel_figures", {})
        self._panel_figures[name] = fig
        self.plots2d.set_figure(fig)
        self.lower_tabs.setCurrentIndex(0)

    def draw_plot2d(self):
        payload = self.window.results
        which = self.plots2d_choice.currentText()
        if payload is None or not which:
            return
        result = payload["result"]
        if which in getattr(self, "_panel_figures", {}):
            self.plots2d.set_figure(self._panel_figures[which])
            return
        if which == "Convergence history":
            fig = residual_figure(list(range(1, len(result.residuals) + 1)), result.residuals,
                                  payload["params"].get("tol"), prefs=self.window.units, **history_extras(result))
        else:
            fig = wall_figure(result, which, self.window.units)
        self.plots2d.set_figure(fig)

    def export_fields(self):
        from aeroflowsim.gui.post_panels import _number  # noqa: F401  (keeps the import list short)
        from aeroflowsim.post import export
        sol = self.solution()
        if sol is None:
            return
        path, kind = QFileDialog.getSaveFileName(self, "Export fields", str(Path(self.window.project.results_dir) /
                                                                            f"{self.window.project.name}_fields.csv"),
                                                 "CSV, cell centres (*.csv);;CSV, nodes (*.csv);;"
                                                 "VTU with node data (*.vtu);;Tecplot ASCII (*.dat)")
        if not path:
            return
        fields = tuple(dict.fromkeys(["rho", "u", "v", "p", "T", "M", "p0", "T0", "s", *sol.custom_fields]))
        if kind.startswith("VTU"):
            export.fields_vtu(sol, path, fields)
        elif kind.startswith("Tecplot"):
            export.fields_tecplot(sol, path, fields)
        else:
            from aeroflowsim.gui.results_logic import display_values

            def convert(values, unit):
                return display_values(values, unit, self.window.units)
            export.fields_csv(sol, path, fields, "node" if "nodes" in kind else "cell", convert=convert)
        self.window.log(f"Fields exported to {path}")

    def make_report(self):
        self.window.make_report()

    # ---- what to show -----------------------------------------------------------------------

    def refresh(self):
        w = self.window
        project = w.project
        if project is None:
            return
        status = project.status("results")
        if status == "disabled":
            self.banner.show_message(f"{project.case.solver_message} The mesh quality checks are in the "
                                     "Validity checks panel.", "info")
            self.splitter.setVisible(False)
            self.card.setVisible(False)
            return
        if w.results is None:
            self.banner.show_message("No results yet. Run the case in the Run step.", "info")
            self.splitter.setVisible(False)
            self.post_area.setVisible(False)
            self.card.setVisible(False)
            return
        two_d = is_face_mesh(w.mesh)
        self.splitter.setVisible(not two_d)
        self.post_area.setVisible(two_d)
        self.card.setVisible(True)
        self.card.set_outdated(status in ("outdated", "error"))
        if status == "outdated":
            self.banner.show_message("OUT OF DATE: these results were computed from older inputs (or an older "
                                     "template). Run again to update them.", "warning")
        elif status == "error":
            self.banner.show_message("The last run failed; these are the results of the run before it, made from "
                                     "older inputs.", "warning")
        else:
            self.banner.hide_message()
        if self._shown is not w.results:
            self._shown = w.results
            self._fill()
            if two_d:
                self._fill_post()

    def _fill(self):
        payload = self.window.results
        result = payload["result"]
        self.field.blockSignals(True)
        self.field.clear()
        units = self.window.units
        for key, f in result.fields.items():
            self.field.addItem(f"{f.label} [{units.label(f.unit)}]", key)
        if is_face_mesh(self.window.mesh) and "M" in result.fields:
            self.field.setCurrentIndex(self.field.findData("M"))   # 2D flow: the Mach number says most
        self.field.blockSignals(False)
        self.numbers.set_rows(key_number_rows(result, payload.get("reference"), payload.get("run_s"), units))
        tiles = key_result_tiles(result, units)
        status = run_status_text(result, payload.get("run_s"))
        self.card.set_results(status if tiles else f"{status}. All numbers are in the Key numbers table.", tiles)
        two_d = is_face_mesh(self.window.mesh)
        self.field_stack.setCurrentWidget(self.flow_view if two_d else self.field_plot)
        self.flow_controls.setVisible(two_d)
        self.vtu_button.setVisible(two_d)
        self._first_draw = True
        self.draw_field()
        plots = flow_plots(result) if two_d else []
        self.flow_box.setVisible(bool(plots))
        self.flow_plot_choice.blockSignals(True)
        self.flow_plot_choice.clear()
        self.flow_plot_choice.addItems(plots)
        self.flow_plot_choice.blockSignals(False)
        self.draw_flow_plot()
        if two_d:                                # the field view gets most of the height, the plots the rest
            height = max(self.splitter.height(), 600)
            self.splitter.setSizes([int(0.55 * height), 0, int(0.45 * height)])
        views = available_views(result, self.window.mesh)
        self.contour_box.setVisible(bool(views))
        self.view.blockSignals(True)
        self.view.clear()
        self.view.addItems(views)
        self.view.blockSignals(False)
        self._fill_contour_fields()

    def draw_field(self, keep_camera=False):
        payload = self.window.results
        key = self.field.currentData()
        if payload is None or key is None:
            return
        mismatch = results_mesh_mismatch(payload["result"], self.window.mesh)
        self.vtu_button.setEnabled(mismatch is None)
        if mismatch is not None:                 # results of an older mesh: never painted on the new one
            if is_face_mesh(self.window.mesh):
                self.flow_view.clear(mismatch)
            else:
                self.field_plot.set_figure(message_figure(mismatch))
            return
        if is_face_mesh(self.window.mesh):
            f = display_field(payload["result"].fields[key], self.window.units)
            clim = None
            if self.flow_auto.isChecked():
                self.flow_min.setText(f"{float(f.values.min()):.5g}")
                self.flow_max.setText(f"{float(f.values.max()):.5g}")
            else:
                lo, hi = _number(self.flow_min.text()), _number(self.flow_max.text())
                clim = (lo, hi) if lo is not None and hi is not None and hi > lo else None
            for box in (self.flow_min, self.flow_max):
                box.setEnabled(not self.flow_auto.isChecked())
            mesh = self.window.mesh
            bbox = mesh.info.get("body_bbox")
            body = (bbox[0], bbox[2], bbox[1], bbox[3]) if bbox is not None and len(bbox) == 4 else None
            self.flow_view.show_mesh(mesh, f.values, f"{f.label} [{f.unit}]", edges=self.flow_edges.isChecked(),
                                     body_bounds=body, cmap=self.flow_cmap.currentText(), clim=clim,
                                     keep_camera=keep_camera or not getattr(self, "_first_draw", True))
            self._first_draw = False
            return
        reference = payload.get("reference") or {}
        self.field_plot.set_figure(field_figure(self.window.mesh, payload["result"].fields[key], reference.get(key),
                                                self.window.units))

    def draw_flow_plot(self):
        payload = self.window.results
        which = self.flow_plot_choice.currentText()
        if payload is None or not which:
            return
        result = payload["result"]
        if which == "Convergence history":
            fig = residual_figure(list(range(1, len(result.residuals) + 1)), result.residuals,
                                  payload["params"].get("tol"), prefs=self.window.units, **history_extras(result))
        else:
            fig = wall_figure(result, which, self.window.units)
        self.flow_plot.set_figure(fig)

    def set_dark(self, dark):
        self.flow_view.set_dark(dark)
        self.grid.set_dark(dark)
        if self.post_area.isVisible():
            self.draw_all()

    def cell_picked(self, cell):
        payload = self.window.results
        if payload is None or results_mesh_mismatch(payload["result"], self.window.mesh) is not None:
            return
        self.window.show_properties(f"Cell #{cell}",
                                    cell_value_rows(payload["result"], self.window.mesh, cell, self.window.units))

    def save_vtu(self):
        from aeroflowsim.vtk import solution_cell_data, write_vtu
        payload = self.window.results
        if results_mesh_mismatch(payload["result"], self.window.mesh) is not None:
            return
        path = self._ask("Save the solution for ParaView", f"{self.window.project.name}_solution.vtu",
                         "VTK unstructured grid (*.vtu)")
        if path:
            write_vtu(path, self.window.mesh, solution_cell_data(payload["result"]))
            self.window.log(f"Solution saved to {path}")

    def _contour_fields(self):
        result = self.window.results["result"]
        return result.snapshots.fields if self.view.currentText() == "x-t diagram" else result.fields

    def _fill_contour_fields(self):
        if self.window.results is None or not self.view.count():
            return
        fields = self._contour_fields()
        self.cfield.blockSignals(True)
        self.cfield.clear()
        for key, f in fields.items():
            self.cfield.addItem(f"{f.label} [{self.window.units.label(f.unit)}]", key)
        self.cfield.blockSignals(False)
        view = self.view.currentText()
        self.lines.setVisible(view == "x-t diagram" and bool(self.window.results.get("reference_lines")))
        self.mesh_lines.setVisible(view == "2D contour")
        self.mirror.setVisible(view == "2D contour")
        self.draw_contour()

    def contour_figure(self):
        payload, mesh = self.window.results, self.window.mesh
        key = self.cfield.currentData()
        if payload is None or key is None or results_mesh_mismatch(payload["result"], mesh) is not None:
            return None
        result = payload["result"]
        f = display_field(self._contour_fields()[key], self.window.units)
        self.vmin.setEnabled(not self.auto.isChecked())
        self.vmax.setEnabled(not self.auto.isChecked())
        vmin = vmax = None
        self.range_note.setText("")
        if self.auto.isChecked():
            self.vmin.setText(f"{float(f.values.min()):g}")
            self.vmax.setText(f"{float(f.values.max()):g}")
        else:
            vmin, vmax = _number(self.vmin.text()), _number(self.vmax.text())
            if vmin is None or vmax is None or vmax <= vmin:
                self.range_note.setText("Maximum must be a number larger than minimum; using the automatic range.")
                vmin = vmax = None
        cmap = self.cmap.currentText()
        view = self.view.currentText()
        length = self.window.units.unit_for("m")      # axes in the user's length unit
        if view == "Shape view":
            x = mesh.positions(len(f.values))
            r = result.shape.radius_at(x) if result.shape is not None else None
            return shape_view(x, r, f.values, f.label, f.unit, cmap=cmap, vmin=vmin, vmax=vmax, note=result.shape_note,
                              length=length)
        if view == "x-t diagram":
            lines = payload.get("reference_lines") if self.lines.isChecked() else []
            x = mesh.positions(f.values.shape[1])
            return xt_diagram(x, result.snapshots.times, f.values, f.label, f.unit, cmap=cmap, vmin=vmin, vmax=vmax,
                              lines=lines or [], length=length)
        return contour_2d(mesh.x, mesh.y, f.values, f.label, f.unit, cmap=cmap, vmin=vmin, vmax=vmax,
                          show_mesh=self.mesh_lines.isChecked(), mirror=self.mirror.isChecked(), length=length)

    def draw_contour(self):
        fig = self.contour_figure()
        if fig is not None:
            self.contour_plot.set_figure(fig)

    # ---- export -----------------------------------------------------------------------------

    def _ask(self, title, name, kind):
        start = str(Path(self.window.project.results_dir) / name)
        path, _ = QFileDialog.getSaveFileName(self, title, start, kind)
        return path

    def save_csv(self):
        payload = self.window.results
        mismatch = results_mesh_mismatch(payload["result"], self.window.mesh)
        if mismatch is not None:
            self.window.log(mismatch, "warning")
            return
        path = self._ask("Save fields as CSV", f"{self.window.project.name}_fields.csv", "CSV files (*.csv)")
        if path:
            Path(path).write_text(fields_csv_text(self.window.mesh, payload["result"], payload.get("reference"),
                                                  self.window.units), encoding="utf-8")
            self.window.log(f"Fields saved to {path}")

    def save_png(self):
        payload = self.window.results
        key = self.field.currentData()
        mismatch = results_mesh_mismatch(payload["result"], self.window.mesh)
        if mismatch is not None:
            self.window.log(mismatch, "warning")
            return
        path = self._ask("Save field plot", f"{self.window.project.name}_{key}.png", "PNG pictures (*.png)")
        if path and is_face_mesh(self.window.mesh):
            self.flow_view.save_picture(path)    # the 2D field as shown (colour map, range, zoom)
            self.window.log(f"Picture saved to {path}")
        elif path:
            with paper_style():                  # saved pictures: light "paper" style in both themes, user's units
                reference = payload.get("reference") or {}
                field_figure(self.window.mesh, payload["result"].fields[key], reference.get(key),
                             self.window.units).savefig(path, dpi=150)
            self.window.log(f"Plot saved to {path}")

    def save_contour(self):
        if self.contour_figure() is None:        # nothing to save (e.g. results of an older mesh)
            return
        view = self.view.currentText().split()[0].lower()
        path = self._ask("Save picture", f"{self.window.project.name}_{view}_{self.cfield.currentData()}.png",
                         "PNG pictures (*.png)")
        if path:
            with paper_style():                  # same picture, drawn again in the light style
                self.contour_figure().savefig(path, dpi=150)
            self.window.log(f"Picture saved to {path}")

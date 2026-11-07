# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Results step of a 3D run: a PyVista view with the walls, a moveable slice plane, an iso-surface or streamlines,
coloured by a field; click to probe; key numbers beside it; export .vtu / CSV. Full 3D release stage: the 2D
post-processing panels as tabs beside the view - Patches (which boundaries are drawn), XY plot (a field along a plane
cut of the walls, e.g. Cp along a wing section: view3d.wall_cut), Reports (the project's report definitions, the flux
and zone balance: post.definitions / post.integrals) and Snapshots (save the result, compare key numbers with one:
post.snapshots / post.compare). No new math here: every number comes from aeroflowsim/post.

All geometry (slices, iso-surfaces, streamlines, probes) comes from aeroflowsim/post/view3d.py (no Qt, tested); this
file only draws it. A slice or iso-surface is computed on the cells it crosses only, so moving the slider stays quick on
large meshes."""

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSlider, QSplitter, QTabWidget,
                               QVBoxLayout, QWidget)

from aeroflowsim.gui.theme import view_colours
from aeroflowsim.gui.widgets import ValueTable

DISPLAYS = ("Walls", "Slice plane", "Iso-surface", "Streamlines")
AXES = ("x", "y", "z")


def _poly(surface):
    """pyvista PolyData of a view3d.Surface."""
    faces = np.column_stack([np.full(len(surface.triangles), 3), surface.triangles]).ravel()
    mesh = pv.PolyData(surface.points, faces)
    mesh.point_data["value"] = surface.values
    return mesh


class Results3DPanel(QWidget):
    """Field view and controls of a 3D result (see the module docstring)."""

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.sol = None
        self.node_cache = {}
        self.view = QtInteractor(self)
        self.view.enable_point_picking(callback=self._picked, show_message=False, use_picker=True,
                                       show_point=False, left_clicking=False)
        self.field = QComboBox()
        self.display = QComboBox()
        self.display.addItems(DISPLAYS)
        self.axis = QComboBox()
        self.axis.addItems(AXES)
        self.position = QSlider(Qt.Horizontal)
        self.position.setRange(0, 1000)
        self.position.setValue(500)
        self.level = QLineEdit()
        self.level.setPlaceholderText("level (SI)")
        self.walls = QCheckBox("Show walls", checked=True)
        self.probe_text = QLabel("Right-click a point to probe it.")
        self.probe_text.setWordWrap(True)
        self.numbers = ValueTable(["Quantity", "Value", "Unit"])
        vtu = QPushButton("Save .vtu...")
        vtu.clicked.connect(self.save_vtu)
        csv = QPushButton("Save CSV...")
        csv.clicked.connect(self.save_csv)
        for w in (self.field, self.display, self.axis):
            w.currentIndexChanged.connect(lambda _=None: self.draw())
        self.position.valueChanged.connect(lambda _=None: self.draw())
        self.level.editingFinished.connect(self.draw)
        self.walls.toggled.connect(lambda _=None: self.draw())
        form = QFormLayout()
        form.addRow("Field", self.field)
        form.addRow("Display", self.display)
        form.addRow("Slice normal", self.axis)
        form.addRow("Slice position", self.position)
        form.addRow("Iso level", self.level)
        form.addRow(self.walls)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addLayout(form)
        side_layout.addWidget(self.probe_text)
        side_layout.addWidget(QLabel("<b>Key numbers</b>"))
        side_layout.addWidget(self.numbers, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(vtu)
        buttons.addWidget(csv)
        side_layout.addLayout(buttons)
        self.tabs = QTabWidget()
        self.tabs.addTab(side, "View")
        self.tabs.addTab(self._patches_tab(), "Patches")
        self.tabs.addTab(self._xy_tab(), "XY plot")
        self.tabs.addTab(self._reports_tab(), "Reports")
        self.tabs.addTab(self._snapshots_tab(), "Snapshots")
        splitter = QSplitter()
        splitter.addWidget(self.view)
        splitter.addWidget(self.tabs)
        splitter.setSizes([900, 380])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    # ---- data -----------------------------------------------------------------------------------------

    def set_solution(self, sol, rows=()):
        from aeroflowsim.post.fields import field_choices_3d
        self.sol = sol
        self.node_cache = {}
        self.field.blockSignals(True)
        self.field.clear()
        for key, label in field_choices_3d(sol):
            self.field.addItem(label, key)
        index = self.field.findData("M")
        self.field.setCurrentIndex(max(index, 0))
        self.field.blockSignals(False)
        self.numbers.set_rows(list(rows))
        self.patch_list.blockSignals(True)
        self.patch_list.clear()
        for patch in sol.mesh.patches:
            item = QListWidgetItem(f"{patch.name} ({patch.type})")
            item.setData(Qt.UserRole, patch.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if patch.type == "wall" else Qt.Unchecked)
            self.patch_list.addItem(item)
        self.patch_list.blockSignals(False)
        self.xy_field.clear()
        for key, label in field_choices_3d(sol):
            self.xy_field.addItem(label, key)
        self.xy_field.setCurrentIndex(max(self.xy_field.findData("Cp"), 0))
        self.refresh_snapshots()
        self.draw(reset_camera=True)

    def node_values(self, key):
        from aeroflowsim.post.fields import node_values
        if key not in self.node_cache:
            self.node_cache[key] = node_values(self.sol, key)
        return self.node_cache[key]

    def surfaces(self):
        """The view3d surfaces (and streamlines) of the current settings: (list of Surface, list of polylines)."""
        from aeroflowsim.post import view3d
        from aeroflowsim.post.fields import field_values
        sol, mesh = self.sol, self.sol.mesh
        key = self.field.currentData()
        colour = self.node_values(key)
        walls = self.shown_patches()
        out, lines = [], []
        mode = self.display.currentText()
        if self.walls.isChecked() or mode == "Walls":
            out.append(view3d.patch_surface(mesh, walls, colour))
        if mode == "Slice plane":
            k = AXES.index(self.axis.currentText())
            lo, hi = mesh.nodes[:, k].min(), mesh.nodes[:, k].max()
            origin = np.zeros(3)
            origin[k] = lo + (hi - lo) * self.position.value() / 1000.0
            normal = np.eye(3)[k]
            out.append(view3d.slice_plane(mesh, colour, origin, normal))
        elif mode == "Iso-surface":
            try:
                level = float(self.level.text())
            except ValueError:
                level = 0.5 * (float(colour.min()) + float(colour.max()))
                self.level.setText(f"{level:.6g}")
            out.append(view3d.iso_surface(mesh, colour, level))
        elif mode == "Streamlines":
            lo, hi = mesh.nodes.min(axis=0), mesh.nodes.max(axis=0)
            t = np.linspace(0.05, 0.95, 12)
            seeds = np.column_stack([np.full(12, lo[0] + 0.01 * (hi[0] - lo[0])),
                                     lo[1] + t * (hi[1] - lo[1]), np.full(12, 0.5 * (lo[2] + hi[2]))])
            vel = np.array([field_values(sol, k) for k in ("u", "v", "w")])
            lines = view3d.streamlines(mesh, vel, seeds, max_steps=600)
        return out, lines

    # ---- drawing ----------------------------------------------------------------------------------------

    def draw(self, reset_camera=False):
        if self.sol is None or self.field.currentData() is None:
            return
        camera = None if reset_camera else self.view.camera_position
        self.view.clear()
        colours = view_colours(getattr(self.page.window, "dark", False))
        self.view.set_background(colours["background"])
        surfaces, lines = self.surfaces()
        values = np.concatenate([s.values for s in surfaces if s.n_triangles] or [np.zeros(1)])
        clim = (float(values.min()), float(values.max()) if values.max() > values.min() else float(values.min()) + 1.0)
        title = self.field.currentText()
        for s in surfaces:
            if s.n_triangles:
                self.view.add_mesh(_poly(s), scalars="value", cmap="turbo", clim=clim, show_scalar_bar=True,
                                   scalar_bar_args={"title": title, "color": colours["text"]})
        for line in lines:
            if len(line) > 1:
                self.view.add_mesh(pv.lines_from_points(line), color=colours["outline"], line_width=2)
        self.view.add_axes()
        if camera is None:
            self.view.view_isometric()
            self.view.reset_camera()
        else:
            self.view.camera_position = camera

    def _picked(self, point, *args):
        from aeroflowsim.post import view3d
        from aeroflowsim.post.fields import field_values
        if self.sol is None or point is None:
            return
        names = ("p", "T", "M", "u", "v", "w")
        out = view3d.probe(self.sol.mesh, point, {k: field_values(self.sol, k) for k in names})
        self.probe_text.setText(f"Cell {out['cell']} at ({point[0]:.4g}, {point[1]:.4g}, {point[2]:.4g}) m: "
                                + ", ".join(f"{k} = {out[k]:.5g}" for k in names))

    # ---- export ------------------------------------------------------------------------------------------

    def save_vtu(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save ParaView file", "results.vtu", "ParaView (*.vtu)")
        if path:
            from aeroflowsim.post.export import fields_vtu
            fields_vtu(self.sol, path)

    def save_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save cell values", "results.csv", "CSV (*.csv)")
        if path:
            from aeroflowsim.post.export import fields_csv
            fields_csv(self.sol, path)

    # ---- Patches, XY plot, Reports, Snapshots (full 3D release stage) ----------------------------------------

    def _patches_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Boundaries drawn with Show walls (and cut by the XY plot):"))
        self.patch_list = QListWidget()
        self.patch_list.itemChanged.connect(lambda _=None: self.draw())
        lay.addWidget(self.patch_list, 1)
        return w

    def shown_patches(self) -> list:
        """Names of the checked patches (the walls by default)."""
        out = []
        for i in range(self.patch_list.count()):
            item = self.patch_list.item(i)
            if item.checkState() == Qt.Checked:
                out.append(item.data(Qt.UserRole))
        return out

    def _xy_tab(self):
        from aeroflowsim.gui.figures import PlotCanvas
        w = QWidget()
        form = QFormLayout(w)
        self.xy_field = QComboBox()
        self.xy_normal = QComboBox()
        self.xy_normal.addItems(AXES)
        self.xy_normal.setCurrentText("z")
        self.xy_position = QLineEdit("0")
        self.xy_along = QComboBox()
        self.xy_along.addItems(AXES)
        plot = QPushButton("Plot")
        plot.clicked.connect(self.plot_cut)
        self.xy_canvas = PlotCanvas()
        self.xy_canvas.setMinimumHeight(230)
        self.xy_note = QLabel("A field along the cut of the checked patches (Patches tab) by a plane, e.g. Cp along a "
                              "wing section at a span position.")
        self.xy_note.setWordWrap(True)
        save = QPushButton("Save CSV...")
        save.clicked.connect(self.save_cut)
        form.addRow("Field", self.xy_field)
        form.addRow("Cut plane normal", self.xy_normal)
        form.addRow("Plane position [m]", self.xy_position)
        form.addRow("Plot against", self.xy_along)
        form.addRow(plot)
        form.addRow(self.xy_canvas)
        form.addRow(self.xy_note)
        form.addRow(save)
        return w

    def cut(self):
        """(points, values) of the current XY-plot settings (view3d.wall_cut)."""
        from aeroflowsim.post import view3d
        key = self.xy_field.currentData()
        k = AXES.index(self.xy_normal.currentText())
        origin = np.zeros(3)
        origin[k] = float(self.xy_position.text() or 0.0)
        surface = view3d.patch_surface(self.sol.mesh, self.shown_patches(), self.node_values(key))
        return view3d.wall_cut(surface, origin, np.eye(3)[k], AXES.index(self.xy_along.currentText()))

    def plot_cut(self):
        from matplotlib.figure import Figure
        if self.sol is None:
            return None
        try:
            points, values = self.cut()
        except ValueError as error:
            self.xy_note.setText(str(error))
            return None
        a = AXES.index(self.xy_along.currentText())
        fig = Figure(figsize=(5, 3.2), layout="constrained")
        ax = fig.add_subplot()
        ax.plot(points[:, a], values, ".", ms=3)
        ax.set_xlabel(f"{AXES[a]} [m]")
        ax.set_ylabel(self.xy_field.currentText())
        if self.xy_field.currentData() == "Cp":
            ax.invert_yaxis()                                   # the usual way of showing Cp
        self.xy_canvas.set_figure(fig)
        self.xy_note.setText(f"{len(points)} points on the cut." if len(points) else
                             "The plane does not cut the checked patches: change its position.")
        return points, values

    def save_cut(self):
        if self.sol is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save the cut", "cut.csv", "CSV (*.csv)")
        if path:
            from aeroflowsim.post.export import table_csv
            points, values = self.cut()
            table_csv(path, ["x [m]", "y [m]", "z [m]", self.xy_field.currentData()],
                      [(*q, v) for q, v in zip(points.tolist(), values.tolist())], "AeroFlowSim wall cut (SI)")

    def _reports_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        go = QPushButton("Evaluate")
        go.clicked.connect(self.evaluate_reports)
        self.report_table = ValueTable(["Report", "Value", "Unit"])
        self.balance_table = ValueTable(["Where", "Mass [kg/s]", "Energy [W]"])
        note = QLabel("The project's report definitions (force, surface and volume reports), evaluated on this "
                      "3D result, and the flux balance.")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addWidget(go)
        lay.addWidget(self.report_table, 1)
        lay.addWidget(QLabel("<b>Flux balance</b> (outward positive; zones and interfaces when there are zones)"))
        lay.addWidget(self.balance_table, 1)
        return w

    def evaluate_reports(self):
        from aeroflowsim.post.definitions import definitions_from, evaluate_definitions
        from aeroflowsim.post.integrals import flux_balance, zone_balance
        from aeroflowsim.post.surfaces import default_surfaces
        if self.sol is None:
            return None
        project = getattr(self.page.window, "project", None)
        defs = definitions_from((project.post.get("report_definitions") if project else None) or [])
        values = evaluate_definitions(self.sol, defs, default_surfaces(self.sol))
        self.report_table.set_rows([(n, f"{v:.6g}" if np.isfinite(v) else "-", u) for n, (v, u) in values.items()])
        fb = flux_balance(self.sol)
        rows = [(r[0], f"{r[2]:.6g}", f"{r[-1]:.6g}") for r in fb["rows"]]
        rows.append(("Net (out - in)", f"{fb['net'][0]:.6g}", f"{fb['net'][-1]:.6g}"))
        if self.sol.mesh.cell_zones:
            zb = zone_balance(self.sol)
            rows += [(f"Zone {z}", f"{r[0]:.6g}", f"{r[-1]:.6g}") for z, *r in zb["zones"]]
            rows += [(f"{a} -> {b}", f"{r[0]:.6g}", f"{r[-1]:.6g}") for a, b, *r in zb["interfaces"]]
        self.balance_table.set_rows(rows)
        return values, fb

    def _snapshots_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.snapshot_list = QListWidget()
        save = QPushButton("Save the current result as a snapshot...")
        save.clicked.connect(lambda: self.save_snapshot())
        compare = QPushButton("Compare key numbers with the selected snapshot")
        compare.clicked.connect(lambda: self.compare_snapshot())
        self.compare_table = ValueTable(["Quantity", "Current", "Snapshot", "Unit", "Change %"])
        lay.addWidget(save)
        lay.addWidget(self.snapshot_list)
        lay.addWidget(compare)
        lay.addWidget(self.compare_table, 1)
        return w

    def refresh_snapshots(self):
        from aeroflowsim.post.snapshots import list_snapshots
        project = getattr(self.page.window, "project", None)
        self.snapshot_list.clear()
        for snap in (list_snapshots(project) if project is not None else []):
            self.snapshot_list.addItem(f"{snap['name']}")

    def save_snapshot(self, name=None):
        from aeroflowsim.post.snapshots import save_snapshot
        project = getattr(self.page.window, "project", None)
        if project is None:
            return None
        if name is None:
            name, ok = QInputDialog.getText(self, "Save snapshot", "Name of the snapshot:")
            if not ok or not name.strip():
                return None
        folder = save_snapshot(project, name.strip())
        self.refresh_snapshots()
        return folder

    def compare_snapshot(self, name=None):
        from aeroflowsim.post.compare import key_number_table
        item = self.snapshot_list.currentItem()
        name = name or (item.text() if item else None)
        if self.sol is None or not name:
            return None
        other = self.page.snapshot_solution(name)
        rows = key_number_table(self.sol, other)
        self.compare_table.set_rows([(k, f"{a:.6g}", f"{b:.6g}", u, f"{c:+.3g}") for k, a, b, u, c in rows])
        return rows

    def close_view(self):
        self.view.close()

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Results step of a 3D run: a PyVista view with the walls, a moveable slice plane, an iso-surface or streamlines,
coloured by a field; click to probe; key numbers beside it; export .vtu / CSV.

All geometry (slices, iso-surfaces, streamlines, probes) comes from aeroflowsim/post/view3d.py (no Qt, tested); this
file only draws it. A slice or iso-surface is computed on the cells it crosses only, so moving the slider stays quick on
large meshes."""

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSlider, QSplitter, QVBoxLayout, QWidget)

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
        splitter = QSplitter()
        splitter.addWidget(self.view)
        splitter.addWidget(side)
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
        walls = [p.name for p in mesh.patches if p.type == "wall"]
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
                                   scalar_bar_args={"title": title})
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

    def close_view(self):
        self.view.close()

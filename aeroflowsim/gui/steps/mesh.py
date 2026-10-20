# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh step: Generate, the mesh in the VTK view (colour by a quality field, edges on/off, click a
cell or a boundary edge to see its values), the quality summary and .vtu export.

Validity checks of the mesh appear in the Validity checks panel. Small meshes (under 50,000
cells) are rebuilt automatically after an input change; for larger ones the page says so and
waits for Generate (the main window decides, see MainWindow.maybe_auto_mesh).
"""

import shutil

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QPushButton, QSplitter,
                               QStackedWidget, QVBoxLayout, QWidget)

from aeroflowsim.gui.figures import PlotCanvas, mesh1d_figure
from aeroflowsim.gui.logic import is_face_mesh, mesh_1d_rows, mesh_summary_rows, readable
from aeroflowsim.gui.vtk_view import MeshView
from aeroflowsim.gui.widgets import Banner, ValueTable
from aeroflowsim.mesh import CELL_TYPES
from aeroflowsim.mesh_quality import QUALITY_COLORINGS, quality_summary

NO_COLOUR = "Nothing"


class MeshPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.generate = QPushButton("Generate mesh")
        self.generate.setToolTip("Build the mesh from the Geometry and Mesh inputs (Ctrl+G)")
        self.generate.clicked.connect(window.generate_mesh)
        self.colour = QComboBox()
        self.colour.addItems([NO_COLOUR, *QUALITY_COLORINGS])
        self.colour.currentTextChanged.connect(lambda _: self.show_mesh())
        self.edges = QCheckBox("Edges", checked=True)
        self.edges.toggled.connect(self._edges_toggled)
        self.pick = QComboBox()
        self.pick.addItems(["Click: cells", "Click: boundary edges"])
        self.pick.currentIndexChanged.connect(self._pick_mode)
        self.export = QPushButton("Export .vtu...")
        self.export.setToolTip("Save the mesh with its quality fields for ParaView")
        self.export.clicked.connect(self.export_vtu)
        self.colour_label = QLabel("Colour by")
        self.two_d_controls = [self.colour_label, self.colour, self.pick, self.export]   # hidden for 1D meshes
        bar = QHBoxLayout()
        for w in (self.generate, self.colour_label, self.colour, self.edges, self.pick):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(self.export)

        self.banner = Banner()
        self.view = MeshView()
        self.view.cell_picked.connect(self.cell_picked)
        self.view.edge_picked.connect(self.edge_picked)
        self.plot1d = PlotCanvas()
        self.empty = QLabel("No mesh yet. Press Generate mesh.")
        self.stack = QStackedWidget()
        for w in (self.empty, self.view, self.plot1d):
            self.stack.addWidget(w)
        self.summary = ValueTable(["Mesh", "Value"])
        self.summary.setMinimumWidth(300)
        splitter = QSplitter()
        splitter.addWidget(self.stack)
        splitter.addWidget(self.summary)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(self.banner)
        layout.addWidget(splitter, 1)
        self._quality_cache = {}

    def _edges_toggled(self, on):
        if is_face_mesh(self.window.mesh):
            self.view.set_edges(on)
        else:
            self.show_mesh()

    def _pick_mode(self, index):
        self.view.pick_mode = "edge" if index == 1 else "cell"

    def quality(self, name):
        """Per-cell quality field of the current mesh (computed once per mesh)."""
        mesh = self.window.mesh
        key = (id(mesh), name)
        if key not in self._quality_cache:
            self._quality_cache = {k: v for k, v in self._quality_cache.items() if k[0] == id(mesh)}
            self._quality_cache[key] = QUALITY_COLORINGS[name][0](mesh)
        return self._quality_cache[key]

    def refresh(self):
        """Status banner, buttons and (if the mesh object changed) the drawing."""
        w = self.window
        project = w.project
        busy = w.runner.busy
        self.generate.setEnabled(project is not None and not busy)
        self.export.setEnabled(w.mesh is not None and is_face_mesh(w.mesh))
        if project is None:
            return
        status = project.status("mesh")
        record = project.steps.get("mesh") or {}
        if status == "error":
            self.banner.show_message(f"The last mesh attempt failed: {record.get('error')}", "error")
        elif status == "outdated":
            note = w.auto_mesh_note or "Inputs changed since this mesh was made. Press Generate mesh to update it."
            self.banner.show_message(f"This mesh is out of date. {note}", "warning")
        elif problems := project.problems(("geometry", "mesh")):
            self.banner.show_message(f"{len(problems)} geometry/mesh input(s) to fix before meshing.", "error")
        else:
            self.banner.hide_message()
        if getattr(self, "_shown", None) is not w.mesh:
            self.show_mesh()

    def show_mesh(self):
        mesh = self.window.mesh
        self._shown = mesh
        for w in self.two_d_controls:            # colour-by, click and .vtu only make sense for 2D/3D meshes
            w.setVisible(mesh is None or is_face_mesh(mesh))
        if mesh is None:
            self.stack.setCurrentWidget(self.empty)
            self.summary.set_rows([])
            return
        if not is_face_mesh(mesh):
            self.plot1d.set_figure(mesh1d_figure(mesh, edges=self.edges.isChecked()))
            self.stack.setCurrentWidget(self.plot1d)
            self.summary.set_rows(mesh_1d_rows(mesh))
            return
        self.stack.setCurrentWidget(self.view)
        name = self.colour.currentText()
        values = None if name == NO_COLOUR else self.quality(name)
        title = "" if name == NO_COLOUR else f"{name} [{QUALITY_COLORINGS[name][1]}]"
        bbox = mesh.info.get("body_bbox")
        body = (bbox[0], bbox[2], bbox[1], bbox[3]) if bbox is not None and len(bbox) == 4 else None
        self.view.show_mesh(mesh, values, title, edges=self.edges.isChecked(), body_bounds=body)
        self.summary.set_rows(mesh_summary_rows(mesh, quality_summary(mesh)) +
                              [(f"patch {p.name}", f"{p.type}, {p.count} faces") for p in mesh.patches])

    def cell_picked(self, cell):
        mesh = self.window.mesh
        c = mesh.cell_centres[cell]
        rows = [("type", CELL_TYPES[int(mesh.cell_types[cell])].name, ""),
                ("centre x", *readable(c[0], "m", 6)), ("centre y", *readable(c[1], "m", 6)),
                ("volume (per m depth)", f"{mesh.cell_volumes[cell]:.4g}", "m³")]
        rows += [(name, *readable(self.quality(name)[cell], unit)) for name, (_, unit) in QUALITY_COLORINGS.items()]
        self.window.show_properties(f"Cell #{cell}", rows)

    def edge_picked(self, patch_index, face):
        mesh = self.window.mesh
        patch = mesh.patches[patch_index]
        c = mesh.face_centres[face]
        rows = [("boundary", patch.name, ""), ("type", patch.type, ""), ("faces in boundary", f"{patch.count}", ""),
                ("face number", f"{face}", ""), ("centre x", *readable(c[0], "m", 6)),
                ("centre y", *readable(c[1], "m", 6)), ("edge length", *readable(mesh.face_areas[face], "m"))]
        self.window.show_properties(f"Boundary '{patch.name}'", rows)

    def export_vtu(self):
        project = self.window.project
        source = project.mesh_dir / "mesh.vtu"
        if not source.is_file():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export mesh for ParaView", str(project.folder / "mesh.vtu"),
                                              "VTK unstructured grid (*.vtu)")
        if path:
            shutil.copy2(source, path)
            self.window.log(f"Mesh exported to {path}")


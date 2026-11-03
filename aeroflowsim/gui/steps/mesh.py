# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh step: Generate, the mesh in the VTK view (colour by a quality field, edges on/off, click a
cell or a boundary edge to see its values), the quality summary and .vtu export.

3D meshes: the view shows the boundary faces in their patch colours (or coloured by the quality field of the cells
behind them); "Cut" x / y / z shows the whole cells a plane passes through (moved with the slider), coloured by the
field; the histogram under the summary shows the field over all cells; "Worst cell" zooms to the worst one. A long
Gmsh job is stopped with the Cancel button of the Mesh chip in the workflow strip.

Validity checks of the mesh appear in the Validity checks panel. Small meshes (under 50,000
cells) are rebuilt automatically after an input change; for larger ones the page says so and
waits for Generate (the main window decides, see MainWindow.maybe_auto_mesh).
"""

import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QSplitter,
                               QStackedWidget, QVBoxLayout, QWidget)

from aeroflowsim.gui.figures import PlotCanvas, mesh1d_figure, quality_histogram_figure
from aeroflowsim.gui.logic import is_face_mesh, mesh_1d_rows, mesh_section, mesh_summary_rows, readable, worst_cell
from aeroflowsim.gui.vtk_view import MeshView
from aeroflowsim.gui.widgets import Banner, ValueTable
from aeroflowsim.mesh import CELL_TYPES
from aeroflowsim.mesh_quality import QUALITY_COLORINGS, colorings, quality_summary

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
        self.pick.addItems(["Click: cells", "Click: boundary edges / faces"])
        self.pick.currentIndexChanged.connect(self._pick_mode)
        self.export = QPushButton("Export mesh...")
        self.export.setToolTip("Save the mesh for ParaView (.vtu, with its quality fields) or another solver (Gmsh .msh, "
                               "SU2, CGNS), with the boundary names")
        self.export.clicked.connect(self.export_mesh)
        self.colour_label = QLabel("Colour by")
        self.cut = QComboBox(toolTip="3D: show the cells a plane passes through (normal along x, y or z)")
        self.cut.addItems(["off", "x", "y", "z"])
        self.cut.currentIndexChanged.connect(lambda _: self.show_mesh(keep_camera=True))
        self.cut_position = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=50, toolTip="Position of the cut")
        self.cut_position.setMaximumWidth(120)
        self.cut_position.valueChanged.connect(lambda _: self.show_mesh(keep_camera=True))
        self.cut_label = QLabel("Cut")
        self.worst = QPushButton("Worst cell", toolTip="Zoom to the worst cell of the colour field (skewness if none)")
        self.worst.clicked.connect(self.show_worst)
        self.three_d_controls = [self.cut_label, self.cut, self.cut_position, self.worst]   # 3D meshes only
        self.two_d_controls = [self.colour_label, self.colour, self.pick, self.export]   # hidden for 1D meshes
        bar = QHBoxLayout()
        for w in (self.generate, self.colour_label, self.colour, self.edges, self.pick, self.cut_label, self.cut,
                  self.cut_position, self.worst):
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
        self.histogram = PlotCanvas()                  # the quality field over all cells
        self.histogram.setMinimumHeight(220)
        side = QSplitter(Qt.Vertical)
        side.addWidget(self.summary)
        side.addWidget(self.histogram)
        splitter = QSplitter()
        splitter.addWidget(self.stack)
        splitter.addWidget(side)
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
            self._quality_cache[key] = colorings(mesh)[name][0](mesh)
        return self._quality_cache[key]

    def _update_colour_items(self, mesh):
        """The colour-by list fits the mesh (3D meshes have the tetrahedron measures too); keeps the choice."""
        names = [NO_COLOUR, *(colorings(mesh) if is_face_mesh(mesh) else QUALITY_COLORINGS)]
        if [self.colour.itemText(i) for i in range(self.colour.count())] != names:
            current = self.colour.currentText()
            self.colour.blockSignals(True)
            self.colour.clear()
            self.colour.addItems(names)
            self.colour.setCurrentText(current if current in names else NO_COLOUR)
            self.colour.blockSignals(False)

    def show_worst(self):
        """Zoom to the worst cell of the colour field (3D: skewness when no field is chosen) and show its values."""
        mesh = self.window.mesh
        if not is_face_mesh(mesh):
            return
        name = self.colour.currentText()
        if name == NO_COLOUR:
            name = "Skewness (equivolume for tetrahedra)" if mesh.dim == 3 else "Equiangle skewness"
        cell = worst_cell(self.quality(name), name)
        if cell >= 0:
            self.view.highlight_cell(cell, zoom=True)
            self.cell_picked(cell)

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

    def show_mesh(self, keep_camera=False):
        mesh = self.window.mesh
        keep_camera = keep_camera and mesh is getattr(self, "_shown", None)
        self._shown = mesh
        for w in self.two_d_controls:            # colour-by, click and .vtu only make sense for 2D/3D meshes
            w.setVisible(mesh is None or is_face_mesh(mesh))
        three_d = is_face_mesh(mesh) and mesh.dim == 3
        for w in self.three_d_controls:
            w.setVisible(three_d)
        self.histogram.setVisible(is_face_mesh(mesh))
        if mesh is None:
            self.stack.setCurrentWidget(self.empty)
            self.summary.set_rows([])
            return
        if not is_face_mesh(mesh):
            self.plot1d.set_figure(mesh1d_figure(mesh, edges=self.edges.isChecked()))
            self.stack.setCurrentWidget(self.plot1d)
            self.summary.set_rows(mesh_1d_rows(mesh, self.window.units))
            return
        self.stack.setCurrentWidget(self.view)
        self._update_colour_items(mesh)
        fields = colorings(mesh)
        name = self.colour.currentText()
        values = None if name == NO_COLOUR else self.quality(name)
        title = "" if name == NO_COLOUR else f"{name} [{fields[name][1]}]"
        if three_d:
            cut = mesh_section(mesh, self.cut.currentText(), self.cut_position.value() / 100.0)
            self.view.show_mesh_3d(mesh, values, title, edges=self.edges.isChecked(), cut=cut, keep_camera=keep_camera)
        else:
            bbox = mesh.info.get("body_bbox")
            body = (bbox[0], bbox[2], bbox[1], bbox[3]) if bbox is not None and len(bbox) == 4 else None
            self.view.show_mesh(mesh, values, title, edges=self.edges.isChecked(), body_bounds=body,
                                keep_camera=keep_camera)
        self.summary.set_rows(mesh_summary_rows(mesh, quality_summary(mesh), self.window.units) +
                              [(f"patch {p.name}", f"{p.type}, {p.count} faces") for p in mesh.patches])
        shown = name if name != NO_COLOUR else ("Skewness (equivolume for tetrahedra)" if three_d else
                                                "Equiangle skewness")
        self.histogram.set_figure(quality_histogram_figure(self.quality(shown), shown, fields[shown][1]))

    def cell_picked(self, cell):
        mesh = self.window.mesh
        c = mesh.cell_centres[cell]
        units = self.window.units                        # Properties follow View > Units
        rows = [("type", CELL_TYPES[int(mesh.cell_types[cell])].name, ""),
                ("centre x", *readable(c[0], "m", 6, prefs=units)), ("centre y", *readable(c[1], "m", 6, prefs=units))]
        if mesh.dim == 3:
            rows.append(("centre z", *readable(c[2], "m", 6, prefs=units)))
        rows.append(("volume per metre depth (= area)", *readable(mesh.cell_volumes[cell], "m²", prefs=units))
                    if mesh.dim == 2 else ("volume", f"{mesh.cell_volumes[cell]:.4g}", "m³"))
        rows += [(name, *readable(self.quality(name)[cell], unit, prefs=units))
                 for name, (_, unit) in colorings(mesh).items()]
        self.window.show_properties(f"Cell #{cell}", rows)

    def edge_picked(self, patch_index, face):
        mesh = self.window.mesh
        patch = mesh.patches[patch_index]
        c = mesh.face_centres[face]
        units = self.window.units
        rows = [("boundary", patch.name, ""), ("type", patch.type, ""), ("faces in boundary", f"{patch.count}", ""),
                ("face number", f"{face}", ""), ("centre x", *readable(c[0], "m", 6, prefs=units)),
                ("centre y", *readable(c[1], "m", 6, prefs=units))]
        if mesh.dim == 3:
            rows += [("centre z", *readable(c[2], "m", 6, prefs=units)),
                     ("face area", *readable(mesh.face_areas[face], "m²", prefs=units))]
        else:
            rows.append(("edge length", *readable(mesh.face_areas[face], "m", prefs=units)))
        self.window.show_properties(f"Boundary '{patch.name}'", rows)

    def export_mesh(self):
        project = self.window.project
        if project is None or not is_face_mesh(self.window.mesh):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export mesh", str(project.folder / "mesh.vtu"),
            "ParaView (*.vtu);;Gmsh 2.2 (*.msh);;SU2 (*.su2);;CGNS (*.cgns)")
        if path:
            self.export_to(path)

    def export_to(self, path):
        """Write the mesh to `path` in the format of its ending (the saved .vtu is copied as it is)."""
        from pathlib import Path

        from aeroflowsim.mesh_io import write_mesh
        source = self.window.project.mesh_dir / "mesh.vtu"
        try:
            if Path(path).suffix.lower() == ".vtu" and source.is_file():
                shutil.copy2(source, path)
            else:
                write_mesh(self.window.mesh, path)
        except (ValueError, OSError) as error:
            self.window.log(f"Mesh export failed: {error}", "error")
            return
        self.window.log(f"Mesh exported to {path}")


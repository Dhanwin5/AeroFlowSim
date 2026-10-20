# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Geometry step: the template's geometry drawn with its named boundaries, plus key dimensions.

For now the geometry comes from the template inputs (parametric nozzle, CSV profile or shape
library) via aeroflowsim/geometry_preview.py. Prompt 6d replaces the read-only drawing by the
geometry workspace (import, edit, sketch, enclosure, name boundaries by clicking); it plugs in
here by giving this page an editable geometry instead of a GeometryPreview.
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget

from aeroflowsim.geometry_preview import geometry_preview
from aeroflowsim.gui.theme import PATCH_COLOURS
from aeroflowsim.gui.vtk_view import MeshView
from aeroflowsim.gui.widgets import Banner, ValueTable


def _value_text(value, unit):
    if isinstance(value, str):
        return value
    return f"{value:.6g}"


class GeometryPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.banner = Banner()
        self.view = MeshView()
        self.summary = ValueTable(["Quantity", "Value", "Unit"])
        self.boundaries = ValueTable(["Boundary", "Type"])
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(QLabel("<b>Dimensions</b>"))
        side_layout.addWidget(self.summary, 2)
        side_layout.addWidget(QLabel("<b>Boundaries</b> (named as in the mesh)"))
        side_layout.addWidget(self.boundaries, 1)
        splitter = QSplitter()
        splitter.addWidget(self.view)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.banner)
        layout.addWidget(splitter, 1)
        self.preview = None

    def refresh(self):
        project = self.window.project
        self.preview = None
        self.summary.set_rows([])
        self.boundaries.set_rows([])
        if project is None:
            self.view.clear()
            return
        try:
            params = project.params_for(("geometry",))
            self.preview = geometry_preview(project.case, params)
        except ValueError as error:
            self.banner.show_message(f"Geometry problem: {error}", "error")
            self.view.clear("Fix the geometry inputs on the left.")
            return
        if self.preview is None:
            self.banner.show_message("This 1D template has no geometry drawing; its geometry inputs are on the left.")
            self.view.clear()
            return
        warnings = " ".join(self.preview.warnings)
        if warnings:
            self.banner.show_message(warnings, "warning")
        else:
            self.banner.hide_message()
        self.view.show_curves(self.preview)
        self.summary.set_rows([(label, _value_text(v, u), u) for label, (v, u) in self.preview.summary.items()])
        seen = []
        for curve in self.preview.curves:
            if (curve.name, curve.type) not in seen:
                seen.append((curve.name, curve.type))
        self.boundaries.set_rows(seen)
        for row, (_, kind) in enumerate(seen):
            self.boundaries.item(row, 0).setForeground(QColor(PATCH_COLOURS.get(kind, "gray")))

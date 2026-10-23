# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Results step: field plots against the reference, key numbers, colour pictures (shape view, x-t
diagram, 2D contour) and export. Out-of-date results carry an amber banner and are never shown as
current. Validity checks are in the Validity checks panel."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSplitter, QVBoxLayout, QWidget)

from aeroflowsim.gui.figures import PlotCanvas, field_figure
from aeroflowsim.gui.theme import paper_style
from aeroflowsim.gui.logic import (available_views, display_field, key_number_rows, key_result_tiles,
                                   run_status_text)
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
        top = QHBoxLayout()
        for w in (QLabel("Field"), self.field):
            top.addWidget(w)
        top.addStretch(1)
        for w in (csv, png, folder):
            top.addWidget(w)
        self.field.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        plot_area = QWidget()
        plot_layout = QVBoxLayout(plot_area)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.addLayout(top)
        plot_layout.addWidget(self.field_plot, 1)
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
        splitter = QSplitter(Qt.Vertical)      # field plot + key numbers above, colour pictures below
        splitter.addWidget(upper)
        splitter.addWidget(contour_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.banner)
        layout.addWidget(self.card)
        layout.addWidget(splitter, 1)
        self.splitter = splitter
        self._shown = None

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
            self.card.setVisible(False)
            return
        self.splitter.setVisible(True)
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

    def _fill(self):
        payload = self.window.results
        result = payload["result"]
        self.field.blockSignals(True)
        self.field.clear()
        units = self.window.units
        for key, f in result.fields.items():
            self.field.addItem(f"{f.label} [{units.label(f.unit)}]", key)
        self.field.blockSignals(False)
        self.numbers.set_rows(key_number_rows(result, payload.get("reference"), payload.get("run_s"), units))
        tiles = key_result_tiles(result, units)
        status = run_status_text(result, payload.get("run_s"))
        self.card.set_results(status if tiles else f"{status}. All numbers are in the Key numbers table.", tiles)
        self.draw_field()
        views = available_views(result, self.window.mesh)
        self.contour_box.setVisible(bool(views))
        self.view.blockSignals(True)
        self.view.clear()
        self.view.addItems(views)
        self.view.blockSignals(False)
        self._fill_contour_fields()

    def draw_field(self):
        payload = self.window.results
        key = self.field.currentData()
        if payload is None or key is None:
            return
        reference = payload.get("reference") or {}
        self.field_plot.set_figure(field_figure(self.window.mesh, payload["result"].fields[key], reference.get(key),
                                                self.window.units))

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
        if payload is None or key is None:
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
        path = self._ask("Save fields as CSV", f"{self.window.project.name}_fields.csv", "CSV files (*.csv)")
        if path:
            Path(path).write_text(fields_csv_text(self.window.mesh, payload["result"], payload.get("reference"),
                                                  self.window.units), encoding="utf-8")
            self.window.log(f"Fields saved to {path}")

    def save_png(self):
        payload = self.window.results
        key = self.field.currentData()
        path = self._ask("Save field plot", f"{self.window.project.name}_{key}.png", "PNG pictures (*.png)")
        if path:
            with paper_style():                  # saved pictures: light "paper" style in both themes, user's units
                reference = payload.get("reference") or {}
                field_figure(self.window.mesh, payload["result"].fields[key], reference.get(key),
                             self.window.units).savefig(path, dpi=150)
            self.window.log(f"Plot saved to {path}")

    def save_contour(self):
        view = self.view.currentText().split()[0].lower()
        path = self._ask("Save picture", f"{self.window.project.name}_{view}_{self.cfield.currentData()}.png",
                         "PNG pictures (*.png)")
        if path:
            with paper_style():                  # same picture, drawn again in the light style
                self.contour_figure().savefig(path, dpi=150)
            self.window.log(f"Picture saved to {path}")

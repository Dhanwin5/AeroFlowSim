# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The post-processing panels of the 2D Results step (Qt). Every number comes from aeroflowsim/post/; the panels only
collect choices, show results and store the user's definitions in the project.

    DisplayPanel    the scene of each view: field, colouring, contour lines, range, overlays, vectors, streamlines,
                    mirror / revolve, layout of 1, 2 or 4 views (each: current result, a snapshot, or a difference),
                    saved scenes, picture export, histogram
    SurfacesPanel   named surfaces: add by typing or by clicking in the view, rename, edit, delete, show / hide
    ReportsPanel    surface and volume integrals, flux balance, forces and moments, report definitions (monitors)
    XYPanel         XY plots along surfaces, with reference data and snapshot overlays; CSV / PNG / SVG / PDF
    SnapshotsPanel  save, rename, delete, restore, compare snapshots; project size
    FieldsPanel     custom field functions
Lengths are typed and shown in the user's length unit (View > Units); values of fields in their display units.
"""

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from aeroflowsim.gui.figures import PlotCanvas
from aeroflowsim.gui.results_logic import (BAR_POSITIONS, COLOURINGS, LAYOUTS, RANGE_MODES, RANGE_TYPED, Scene,
                                           VECTOR_FIELDS)
from aeroflowsim.gui.widgets import ValueTable
from aeroflowsim.post.definitions import FORCE_QUANTITIES, ReportDefinition, definitions_from
from aeroflowsim.post.integrals import CONSERVED, SURFACE_OPERATIONS, VOLUME_OPERATIONS
from aeroflowsim.post.surfaces import TYPE_LABELS, Surface, surfaces_from
from aeroflowsim.visualise import COLORMAPS

SOURCE_CURRENT = "Current result"


def _number(text, default=None):
    try:
        return float(str(text).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _scroll(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    area.setFrameShape(QScrollArea.NoFrame)
    return area


class _Base(QWidget):
    """Common helpers: the page (ResultsPage) owns the Solution, the project and the units."""

    def __init__(self, page):
        super().__init__()
        self.page = page

    @property
    def window(self):
        return self.page.window

    @property
    def project(self):
        return self.page.window.project

    def length(self):
        """(unit label, factor from metres) of the user's length unit."""
        unit = self.window.units.unit_for("m")
        if unit is None:
            return "m", 1.0
        return unit.name, float(unit.from_si(1.0))

    def field_combo(self, with_none=False):
        combo = QComboBox()
        combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        combo.setMinimumContentsLength(14)
        combo.with_none = with_none
        return combo

    def fill_fields(self, combo, keep=True):
        sol = self.page.solution()
        current = combo.currentData() if keep else None
        combo.blockSignals(True)
        combo.clear()
        if getattr(combo, "with_none", False):
            combo.addItem("(none)", "")
        if sol is not None:
            from aeroflowsim.gui.results_logic import field_choices
            for label, name in field_choices(sol):
                combo.addItem(label, name)
        if current is not None:
            i = combo.findData(current)
            if i >= 0:
                combo.setCurrentIndex(i)
        combo.blockSignals(False)


# ==================================================================================================== Display

class DisplayPanel(_Base):
    changed = Signal()

    def __init__(self, page):
        super().__init__(page)
        self.scenes = [Scene()]               # one Scene per view
        self.sources = [SOURCE_CURRENT]       # what each view shows: current, a snapshot name, or "A - B"
        self.view_index = 0
        self._loading = False
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.layout_choice = QComboBox()
        self.layout_choice.addItems(list(LAYOUTS))
        self.view_choice = QComboBox()
        self.source = QComboBox()
        self.field = self.field_combo()
        self.colouring = QComboBox()
        self.colouring.addItems(COLOURINGS)
        self.n_bands = QSpinBox(minimum=2, maximum=64, value=12)
        self.lines = QCheckBox("Contour lines")
        self.n_levels = QSpinBox(minimum=1, maximum=100, value=12)
        self.levels = QLineEdit()
        self.levels.setPlaceholderText("or typed levels: 0.5, 1, 1.5")
        self.labels = QCheckBox("Labels on the lines")
        self.cmap = QComboBox()
        self.cmap.addItems(list(COLORMAPS) + [c for c in ("coolwarm", "gray", "jet", "RdBu_r") if c not in COLORMAPS])
        self.range_mode = QComboBox()
        self.range_mode.addItems(RANGE_MODES)
        self.vmin, self.vmax = QLineEdit(), QLineEdit()
        self.log = QCheckBox("Log scale")
        self.bar = QComboBox()
        self.bar.addItems(BAR_POSITIONS)
        self.bar_format = QLineEdit("%.4g")
        self.edges = QCheckBox("Mesh edges")
        self.boundaries = QCheckBox("Boundaries", checked=True)
        self.vectors = QCheckBox("Vectors")
        self.vector_field = QComboBox()
        for key, (_, _, label, _) in VECTOR_FIELDS.items():
            self.vector_field.addItem(label, key)
        self.vector_scale = QDoubleSpinBox(minimum=0.05, maximum=50.0, value=1.0, singleStep=0.25)
        self.vector_skip = QSpinBox(minimum=1, maximum=50, value=1)
        self.vector_fixed = QCheckBox("Same length")
        self.vector_colour = self.field_combo(with_none=True)
        self.streams = QCheckBox("Streamlines")
        self.stream_seeds = QComboBox()
        self.stream_n = QSpinBox(minimum=1, maximum=500, value=20)
        self.stream_colour = self.field_combo(with_none=True)
        self.stream_arrows = QCheckBox("Arrow marks", checked=True)
        clear_seeds = QPushButton("Clear clicked seeds")
        clear_seeds.clicked.connect(self.clear_seeds)
        self.mirror = QCheckBox("Mirror about the axis / symmetry line")
        self.revolve = QCheckBox("3D revolved view (axisymmetric)")
        self.revolve_angle = QDoubleSpinBox(minimum=10.0, maximum=360.0, value=270.0, singleStep=30.0, suffix=" deg")
        self.problem = QLabel()
        self.problem.setObjectName("note")
        self.problem.setWordWrap(True)

        rows = [("Views", self.layout_choice), ("Settings of", self.view_choice), ("Shows", self.source),
                ("Field", self.field), ("Colouring", self.colouring), ("Bands", self.n_bands), ("", self.lines),
                ("Number of lines", self.n_levels), ("Levels", self.levels), ("", self.labels),
                ("Colour map", self.cmap), ("Range", self.range_mode), ("Minimum", self.vmin), ("Maximum", self.vmax),
                ("", self.log), ("Colour bar", self.bar), ("Number format", self.bar_format), ("", self.edges),
                ("", self.boundaries), ("", self.vectors), ("Vector", self.vector_field),
                ("Arrow size", self.vector_scale), ("Thin out (every n-th)", self.vector_skip), ("", self.vector_fixed),
                ("Colour arrows by", self.vector_colour), ("", self.streams), ("Seeds from surface", self.stream_seeds),
                ("Seeds along a line", self.stream_n), ("Colour by", self.stream_colour), ("", self.stream_arrows),
                ("", clear_seeds), ("", self.mirror), ("", self.revolve), ("Sweep angle", self.revolve_angle)]
        for label, w in rows:
            form.addRow(label, w)
        form.addRow(self.problem)

        # saved scenes
        self.saved = QComboBox()
        restore = QPushButton("Restore")
        restore.clicked.connect(self.restore_scene)
        save = QPushButton("Save scene...")
        save.clicked.connect(self.save_scene)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.delete_scene)
        scenes = QGroupBox("Saved scenes")
        sl = QGridLayout(scenes)
        sl.addWidget(self.saved, 0, 0, 1, 3)
        sl.addWidget(restore, 1, 0)
        sl.addWidget(save, 1, 1)
        sl.addWidget(delete, 1, 2)
        # pictures
        pictures = QGroupBox("Picture")
        pl = QGridLayout(pictures)
        self.scale = QSpinBox(minimum=1, maximum=8, value=2, suffix=" x window")
        self.transparent = QCheckBox("Transparent background")
        self.paper = QCheckBox("Paper style (light)", checked=True)
        save_png = QPushButton("Save PNG...")
        save_png.clicked.connect(self.save_picture)
        copy = QPushButton("Copy")
        copy.setToolTip("Copy the picture of the first view to the clipboard")
        copy.clicked.connect(self.copy_picture)
        hist = QPushButton("Histogram...")
        hist.clicked.connect(self.show_histogram)
        pl.addWidget(QLabel("Resolution"), 0, 0)
        pl.addWidget(self.scale, 0, 1)
        pl.addWidget(self.transparent, 1, 0, 1, 2)
        pl.addWidget(self.paper, 2, 0, 1, 2)
        pl.addWidget(save_png, 3, 0)
        pl.addWidget(copy, 3, 1)
        pl.addWidget(hist, 4, 0, 1, 2)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.addLayout(form)
        lay.addWidget(scenes)
        lay.addWidget(pictures)
        lay.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(inner))

        self.layout_choice.currentIndexChanged.connect(self._layout_changed)
        self.view_choice.currentIndexChanged.connect(self._view_changed)
        for w in (self.source, self.field, self.colouring, self.cmap, self.range_mode, self.bar, self.vector_field,
                  self.vector_colour, self.stream_seeds, self.stream_colour):
            w.currentIndexChanged.connect(self._edited)
        for w in (self.lines, self.labels, self.log, self.edges, self.boundaries, self.vectors, self.vector_fixed,
                  self.streams, self.stream_arrows, self.mirror, self.revolve):
            w.toggled.connect(self._edited)
        for w in (self.n_bands, self.n_levels, self.vector_skip, self.stream_n):
            w.valueChanged.connect(self._edited)
        for w in (self.vector_scale, self.revolve_angle):
            w.valueChanged.connect(self._edited)
        for w in (self.levels, self.vmin, self.vmax, self.bar_format):
            w.editingFinished.connect(self._edited)
        self._update_views_list()

    # ---- state <-> widgets -------------------------------------------------------------------

    def fill(self):
        """New solution or project: refill the choices and show the first view's scene."""
        for combo in (self.field, self.vector_colour, self.stream_colour):
            self.fill_fields(combo)
        self.fill_sources()
        self.fill_seed_surfaces()
        self.fill_saved()
        self._load(self.view_index)

    def fill_sources(self):
        from aeroflowsim.post.snapshots import list_snapshots
        names = [SOURCE_CURRENT] + ([s["name"] for s in list_snapshots(self.project)] if self.project else [])
        diffs = [f"Difference: {SOURCE_CURRENT} - {n}" for n in names[1:]]
        self.source.blockSignals(True)
        current = self.source.currentText()
        self.source.clear()
        self.source.addItems(names + diffs)
        i = self.source.findText(current)
        self.source.setCurrentIndex(max(i, 0))
        self.source.blockSignals(False)

    def fill_seed_surfaces(self):
        self.stream_seeds.blockSignals(True)
        current = self.stream_seeds.currentData()
        self.stream_seeds.clear()
        self.stream_seeds.addItem("(clicked points only)", "")
        for s in self.page.surfaces():
            if s.type in ("line", "rake", "x_line", "y_line", "point"):
                self.stream_seeds.addItem(s.name, s.name)
        i = self.stream_seeds.findData(current)
        self.stream_seeds.setCurrentIndex(max(i, 0))
        self.stream_seeds.blockSignals(False)

    def fill_saved(self):
        self.saved.clear()
        if self.project is not None:
            self.saved.addItems(sorted(self.project.post["scenes"]))

    def _update_views_list(self):
        n = LAYOUTS[self.layout_choice.currentText()]
        while len(self.scenes) < n:
            self.scenes.append(Scene.from_dict(self.scenes[0].to_dict()))
            self.sources.append(SOURCE_CURRENT)
        self.view_choice.blockSignals(True)
        self.view_choice.clear()
        self.view_choice.addItems([f"View {k + 1}" for k in range(n)])
        self.view_choice.setCurrentIndex(min(self.view_index, n - 1))
        self.view_choice.blockSignals(False)
        self.view_index = self.view_choice.currentIndex()

    def _layout_changed(self):
        self._update_views_list()
        self.page.set_view_count(LAYOUTS[self.layout_choice.currentText()])
        self._load(self.view_index)
        self.changed.emit()

    def _view_changed(self, index):
        if index >= 0:
            self.view_index = index
            self._load(index)

    def _load(self, k):
        s = self.scenes[k]
        self._loading = True
        try:
            i = self.source.findText(self.sources[k])
            self.source.setCurrentIndex(max(i, 0))
            i = self.field.findData(s.field)
            if i < 0 and self.field.count():
                i = 0
                s.field = self.field.itemData(0)
            self.field.setCurrentIndex(i)
            self.colouring.setCurrentText(s.colouring)
            self.n_bands.setValue(s.n_bands)
            self.lines.setChecked(s.contour_lines)
            self.n_levels.setValue(s.n_levels)
            self.levels.setText(", ".join(f"{v:g}" for v in s.levels))
            self.labels.setChecked(s.line_labels)
            self.cmap.setCurrentText(s.cmap)
            self.range_mode.setCurrentText(s.range_mode)
            self.vmin.setText("" if s.vmin is None else f"{s.vmin:g}")
            self.vmax.setText("" if s.vmax is None else f"{s.vmax:g}")
            self.log.setChecked(s.log_scale)
            self.bar.setCurrentText(s.bar_position)
            self.bar_format.setText(s.bar_format)
            self.edges.setChecked(s.edges)
            self.boundaries.setChecked(s.boundaries)
            self.vectors.setChecked(s.vectors)
            self.vector_field.setCurrentIndex(max(self.vector_field.findData(s.vector_field), 0))
            self.vector_scale.setValue(s.vector_scale)
            self.vector_skip.setValue(s.vector_skip)
            self.vector_fixed.setChecked(s.vector_fixed_length)
            self.vector_colour.setCurrentIndex(max(self.vector_colour.findData(s.vector_colour_by), 0))
            self.streams.setChecked(s.streamlines)
            self.stream_seeds.setCurrentIndex(max(self.stream_seeds.findData(s.stream_seeds), 0))
            self.stream_n.setValue(s.stream_n)
            self.stream_colour.setCurrentIndex(max(self.stream_colour.findData(s.stream_colour_by), 0))
            self.stream_arrows.setChecked(s.stream_arrows)
            self.mirror.setChecked(s.mirror)
            self.revolve.setChecked(s.revolve)
            self.revolve_angle.setValue(s.revolve_angle)
        finally:
            self._loading = False
        self._enable()

    def _enable(self):
        s = self.scenes[self.view_index]
        sol = self.page.solution()
        axi = sol is not None and sol.axisymmetric
        self.n_bands.setEnabled(s.colouring == COLOURINGS[2])
        for w in (self.n_levels, self.levels, self.labels):
            w.setEnabled(s.contour_lines)
        for w in (self.vmin, self.vmax):
            w.setEnabled(s.range_mode == RANGE_TYPED)
        for w in (self.vector_field, self.vector_scale, self.vector_skip, self.vector_fixed, self.vector_colour):
            w.setEnabled(s.vectors)
        for w in (self.stream_seeds, self.stream_n, self.stream_colour, self.stream_arrows):
            w.setEnabled(s.streamlines)
        self.revolve.setEnabled(axi)
        self.revolve_angle.setEnabled(axi and s.revolve)

    def _edited(self, *_):
        if self._loading:
            return
        s = self.scenes[self.view_index]
        self.sources[self.view_index] = self.source.currentText() or SOURCE_CURRENT
        s.field = self.field.currentData() or s.field
        s.colouring = self.colouring.currentText()
        s.n_bands = self.n_bands.value()
        s.contour_lines = self.lines.isChecked()
        s.n_levels = self.n_levels.value()
        s.levels = [v for v in (_number(t) for t in self.levels.text().replace(";", ",").split(",")) if v is not None]
        s.line_labels = self.labels.isChecked()
        s.cmap = self.cmap.currentText()
        s.range_mode = self.range_mode.currentText()
        s.vmin, s.vmax = _number(self.vmin.text()), _number(self.vmax.text())
        s.log_scale = self.log.isChecked()
        s.bar_position = self.bar.currentText()
        s.bar_format = self.bar_format.text() or "%.4g"
        s.edges = self.edges.isChecked()
        s.boundaries = self.boundaries.isChecked()
        s.vectors = self.vectors.isChecked()
        s.vector_field = self.vector_field.currentData()
        s.vector_scale = self.vector_scale.value()
        s.vector_skip = self.vector_skip.value()
        s.vector_fixed_length = self.vector_fixed.isChecked()
        s.vector_colour_by = self.vector_colour.currentData() or ""
        s.streamlines = self.streams.isChecked()
        s.stream_seeds = self.stream_seeds.currentData() or ""
        s.stream_n = self.stream_n.value()
        s.stream_colour_by = self.stream_colour.currentData() or ""
        s.stream_arrows = self.stream_arrows.isChecked()
        s.mirror = self.mirror.isChecked()
        s.revolve = self.revolve.isChecked() and self.revolve.isEnabled()
        s.revolve_angle = self.revolve_angle.value()
        self._enable()
        self.page.draw_view(self.view_index, keep_camera=not self.sender() is self.revolve)

    def set_problem(self, text):
        self.problem.setText(text)
        self.problem.setVisible(bool(text))

    # ---- seeds, scenes, pictures ---------------------------------------------------------------

    def add_seed(self, x, y):
        s = self.scenes[self.view_index]
        s.stream_points.append([x, y])
        s.streamlines = True
        self._load(self.view_index)
        self.page.draw_view(self.view_index)

    def clear_seeds(self):
        self.scenes[self.view_index].stream_points = []
        self.page.draw_view(self.view_index)

    def save_scene(self):
        name, ok = QInputDialog.getText(self, "Save scene", "Name of the scene:")
        if not ok or not name.strip():
            return
        s = self.scenes[self.view_index]
        view = self.page.grid.views[self.view_index]
        s.camera = [list(c) for c in view.plotter.camera_position]
        scenes = dict(self.project.post["scenes"])
        scenes[name.strip()] = {**s.to_dict(), "source": self.sources[self.view_index]}
        self.project.set_post("scenes", scenes)
        self.window.update_title()
        self.fill_saved()
        self.saved.setCurrentText(name.strip())
        self.window.log(f"Scene '{name.strip()}' saved in the project")

    def restore_scene(self, name=None):
        name = name or self.saved.currentText()
        data = self.project.post["scenes"].get(name) if self.project else None
        if not data:
            return
        self.scenes[self.view_index] = Scene.from_dict(data)
        self.sources[self.view_index] = data.get("source", SOURCE_CURRENT)
        self._load(self.view_index)
        self.page.draw_view(self.view_index, keep_camera=False)

    def delete_scene(self):
        name = self.saved.currentText()
        if not name:
            return
        scenes = dict(self.project.post["scenes"])
        scenes.pop(name, None)
        self.project.set_post("scenes", scenes)
        self.window.update_title()
        self.fill_saved()

    def save_picture(self):
        name = f"{self.project.name}_{self.scenes[self.view_index].field}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Save picture", str(self.project.results_dir / name),
                                              "PNG pictures (*.png)")
        if path:
            self.page.save_view_picture(self.view_index, path, self.scale.value(), self.transparent.isChecked(),
                                        self.paper.isChecked())

    def copy_picture(self):
        import tempfile
        from PySide6.QtGui import QGuiApplication, QImage
        tmp = Path(tempfile.mkdtemp()) / "picture.png"
        self.page.save_view_picture(self.view_index, tmp, self.scale.value(), False, self.paper.isChecked())
        QGuiApplication.clipboard().setImage(QImage(str(tmp)))
        self.window.log("Picture copied to the clipboard")

    def show_histogram(self):
        sol = self.page.view_solution(self.view_index)
        if sol is None:
            return
        HistogramDialog(self, sol, self.scenes[self.view_index].field, self.window.units).exec()


class HistogramDialog(QDialog):
    def __init__(self, parent, sol, name, prefs):
        super().__init__(parent)
        from aeroflowsim.gui.results_logic import histogram
        from aeroflowsim.post.fields import field_info
        self.setWindowTitle(f"Histogram of {field_info(sol, name).label}")
        self.weighted = QCheckBox("Weighted by cell volume")
        self.canvas = PlotCanvas()
        self.stats = QLabel()
        lay = QVBoxLayout(self)
        lay.addWidget(self.weighted)
        lay.addWidget(self.canvas, 1)
        lay.addWidget(self.stats)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.resize(640, 460)

        def draw():
            from matplotlib.figure import Figure
            counts, edges, st = histogram(sol, name, weighted=self.weighted.isChecked(), prefs=prefs)
            fig = Figure(figsize=(6, 3.5), layout="constrained")
            ax = fig.add_subplot()
            ax.bar(0.5 * (edges[:-1] + edges[1:]), counts, width=np.diff(edges), color="#4c78a8")
            ax.set_xlabel(f"{field_info(sol, name).label} [{st['unit']}]")
            ax.set_ylabel("volume fraction" if self.weighted.isChecked() else "cells")
            self.canvas.set_figure(fig)
            self.stats.setText(f"min {st['min']:.5g}   mean (volume-weighted) {st['mean']:.5g}   max {st['max']:.5g} "
                               f"{st['unit']}")
            self.figure, self.data = fig, (counts, edges, st)
        self.weighted.toggled.connect(lambda _: draw())
        draw()


# ==================================================================================================== Surfaces

class SurfaceDialog(QDialog):
    """Create or edit a surface by typing its values (lengths in the user's unit)."""

    def __init__(self, parent, panel, surface=None):
        super().__init__(parent)
        self.panel = panel
        unit, self.k = panel.length()
        self.setWindowTitle("Edit surface" if surface else "New surface")
        self.name = QLineEdit(surface.name if surface else "")
        self.type = QComboBox()
        for key, label in TYPE_LABELS.items():
            self.type.addItem(label, key)
        sol = panel.page.solution()
        self.patches = QListWidget()
        self.patches.setSelectionMode(QAbstractItemView.MultiSelection)
        for p in (sol.mesh.patches if sol else []):
            self.patches.addItem(p.name)
        self.x1, self.y1, self.x2, self.y2 = (QLineEdit() for _ in range(4))
        self.n = QSpinBox(minimum=1, maximum=1000, value=10)
        self.field = panel.field_combo()
        panel.fill_fields(self.field, keep=False)
        self.value = QLineEdit()
        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Type", self.type)
        form.addRow("Boundaries", self.patches)
        form.addRow(f"Point 1 x [{unit}]", self.x1)
        form.addRow(f"Point 1 y [{unit}]", self.y1)
        form.addRow(f"Point 2 x [{unit}]", self.x2)
        form.addRow(f"Point 2 y [{unit}]", self.y2)
        form.addRow("Seed points", self.n)
        form.addRow("Field", self.field)
        self.value_label = QLabel("Value")
        form.addRow(self.value_label, self.value)
        self.message = QLabel()
        self.message.setObjectName("note")
        self.message.setWordWrap(True)
        form.addRow(self.message)
        self.form = form
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.try_accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)
        self.type.currentIndexChanged.connect(self._shape)
        if surface:
            self.type.setCurrentIndex(self.type.findData(surface.type))
            for i in range(self.patches.count()):
                self.patches.item(i).setSelected(self.patches.item(i).text() in surface.patches)
            for box, v in zip((self.x1, self.y1, self.x2, self.y2), (*surface.start, *surface.end)):
                box.setText(f"{v * self.k:.6g}")
            self.n.setValue(surface.n_points)
            i = self.field.findData(surface.field)
            if i >= 0:
                self.field.setCurrentIndex(i)
            self.value.setText(f"{surface.value * (self.k if surface.type in ('x_line', 'y_line') else 1.0):.6g}")
        self._shape()

    def _shape(self):
        t = self.type.currentData()
        show = {"patches": t == "boundary", "p1": t in ("line", "rake", "point"), "p2": t in ("line", "rake"),
                "n": t == "rake", "field": t == "iso", "value": t in ("iso", "x_line", "y_line")}
        rows = {"patches": [self.patches], "p1": [self.x1, self.y1], "p2": [self.x2, self.y2], "n": [self.n],
                "field": [self.field], "value": [self.value]}
        for key, widgets in rows.items():
            for w in widgets:
                w.setVisible(show[key])
                label = self.form.labelForField(w)
                if label is not None:
                    label.setVisible(show[key])
        unit = self.panel.length()[0]
        self.value_label.setText({"iso": "Value (SI)", "x_line": f"x [{unit}]", "y_line": f"y [{unit}]"}.get(t, "Value"))

    def surface(self):
        t = self.type.currentData()
        k = self.k
        pt = lambda a, b: (_number(a.text(), 0.0) / k, _number(b.text(), 0.0) / k)
        value = _number(self.value.text(), 0.0)
        if t in ("x_line", "y_line"):
            value /= k
        return Surface(self.name.text().strip() or TYPE_LABELS[t], t,
                       patches=[i.text() for i in self.patches.selectedItems()], start=pt(self.x1, self.y1),
                       end=pt(self.x2, self.y2), n_points=self.n.value(), field=self.field.currentData() or "",
                       value=value)

    def try_accept(self):
        s = self.surface()
        sol = self.panel.page.solution()
        problem = s.problem(sol) if sol is not None else ""
        names = {x.name for x in self.panel.page.surfaces(project_only=True)} - {getattr(self, "old_name", None)}
        if s.name in names:
            problem = f"There is already a surface called '{s.name}'."
        if problem:
            self.message.setText(problem)
            return
        self.result_surface = s
        self.accept()


class SurfacesPanel(_Base):
    changed = Signal()

    def __init__(self, page):
        super().__init__(page)
        self.list = QListWidget()
        self.list.itemChanged.connect(self._toggled)
        self.list.itemDoubleClicked.connect(lambda _: self.edit())
        add = QPushButton("New...")
        add.clicked.connect(self.add)
        edit = QPushButton("Edit...")
        edit.clicked.connect(self.edit)
        rename = QPushButton("Rename...")
        rename.clicked.connect(self.rename)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.delete)
        click_line = QPushButton("Line by two clicks")
        click_line.setToolTip("Click the start and the end point in the view")
        click_line.clicked.connect(self.start_line)
        click_point = QPushButton("Point by one click")
        click_point.clicked.connect(self.start_point)
        self.hint = QLabel("Boundaries are always available as surfaces. Right-click in the view for more.")
        self.hint.setObjectName("note")
        self.hint.setWordWrap(True)
        grid = QGridLayout()
        for i, b in enumerate((add, edit, rename, delete)):
            grid.addWidget(b, i // 2, i % 2)
        grid.addWidget(click_line, 2, 0)
        grid.addWidget(click_point, 2, 1)
        lay = QVBoxLayout(self)
        lay.addWidget(self.list, 1)
        lay.addLayout(grid)
        lay.addWidget(self.hint)
        self.pending_point = False

    def fill(self):
        self.list.blockSignals(True)
        self.list.clear()
        unit, k = self.length()
        for s in self.page.surfaces(project_only=True):
            item = QListWidgetItem(f"{s.name}  -  {s.describe(unit, k)}")
            item.setData(Qt.UserRole, s.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if s.visible else Qt.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)

    def _store(self, surfaces):
        self.project.set_post("surfaces", [s.to_dict() for s in surfaces])
        self.window.update_title()
        self.fill()
        self.changed.emit()

    def _selected(self):
        item = self.list.currentItem()
        return None if item is None else item.data(Qt.UserRole)

    def add(self, surface=None):
        if surface is None:
            dialog = SurfaceDialog(self, self)
            if dialog.exec() != QDialog.Accepted:
                return
            surface = dialog.result_surface
        existing = self.page.surfaces(project_only=True)
        names = {s.name for s in existing}
        base, k = surface.name, 2
        while surface.name in names:
            surface.name = f"{base} {k}"
            k += 1
        self._store(existing + [surface])
        self.window.log(f"Surface '{surface.name}' created")
        return surface

    def edit(self):
        name = self._selected()
        surfaces = self.page.surfaces(project_only=True)
        old = next((s for s in surfaces if s.name == name), None)
        if old is None:
            return
        dialog = SurfaceDialog(self, self, old)
        dialog.old_name = old.name
        if dialog.exec() != QDialog.Accepted:
            return
        self._store([dialog.result_surface if s.name == name else s for s in surfaces])

    def rename(self):
        name = self._selected()
        if name is None:
            return
        new, ok = QInputDialog.getText(self, "Rename surface", "New name:", text=name)
        new = new.strip()
        surfaces = self.page.surfaces(project_only=True)
        if not ok or not new or new == name:
            return
        if any(s.name == new for s in surfaces):
            QMessageBox.warning(self, "Rename surface", f"There is already a surface called '{new}'.")
            return
        for s in surfaces:
            if s.name == name:
                s.name = new
        defs = definitions_from(self.project.post["report_definitions"])
        for d in defs:                                  # report definitions follow the new name
            if d.surface == name:
                d.surface = new
        self.project.set_post("report_definitions", [d.to_dict() for d in defs])
        self._store(surfaces)

    def delete(self):
        name = self._selected()
        if name is None:
            return
        used = [d.name for d in definitions_from(self.project.post["report_definitions"]) if d.surface == name]
        text = f"Delete the surface '{name}'?"
        if used:
            text += f"\n\nThese report definitions use it and will show 'cannot be evaluated': {', '.join(used)}."
        if QMessageBox.question(self, "Delete surface", text) != QMessageBox.Yes:
            return
        self._store([s for s in self.page.surfaces(project_only=True) if s.name != name])

    def _toggled(self, item):
        surfaces = self.page.surfaces(project_only=True)
        for s in surfaces:
            if s.name == item.data(Qt.UserRole):
                s.visible = item.checkState() == Qt.Checked
        self._store(surfaces)

    def start_line(self):
        for v in self.page.grid.active():
            v.line_start = None
        self.page.grid.views[0].line_start_pending = True
        self.page.awaiting = "line_1"
        self.window.log("Click the start point of the line in the view, then the end point")

    def start_point(self):
        self.page.awaiting = "point"
        self.window.log("Click the point in the view")


# ==================================================================================================== Reports

class ReportsPanel(_Base):
    def __init__(self, page):
        super().__init__(page)
        tabs = QTabWidget()
        tabs.addTab(self._surface_tab(), "Surface")
        tabs.addTab(self._volume_tab(), "Volume")
        tabs.addTab(self._flux_tab(), "Fluxes")
        tabs.addTab(self._force_tab(), "Forces")
        tabs.addTab(self._definitions_tab(), "Definitions")
        self.tabs = tabs
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(tabs)

    # -- surface integrals
    def _surface_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.s_surface = QComboBox()
        self.s_operation = QComboBox()
        for k, label in SURFACE_OPERATIONS.items():
            self.s_operation.addItem(label, k)
        self.s_field = self.field_combo()
        self.s_quantity = QComboBox()
        for k in CONSERVED:
            self.s_quantity.addItem(k.replace("_", " "), k)
        go = QPushButton("Compute")
        go.clicked.connect(self.compute_surface)
        self.s_result = QLabel()
        self.s_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.s_result.setWordWrap(True)
        as_def = QPushButton("Keep as report definition...")
        as_def.clicked.connect(lambda: self.keep_definition("surface"))
        form.addRow("Surface", self.s_surface)
        form.addRow("Operation", self.s_operation)
        form.addRow("Field", self.s_field)
        form.addRow("Quantity", self.s_quantity)
        form.addRow(go)
        form.addRow(self.s_result)
        form.addRow(as_def)
        self.s_operation.currentIndexChanged.connect(self._surface_enable)
        return w

    def _surface_enable(self):
        op = self.s_operation.currentData()
        self.s_field.setEnabled(op not in ("area", "mass_flow", "flux"))
        self.s_quantity.setEnabled(op == "flux")

    def compute_surface(self):
        from aeroflowsim.post.integrals import surface_integral
        sol = self.page.solution()
        surface = self.page.surface_by_name(self.s_surface.currentText())
        if sol is None or surface is None:
            return
        op = self.s_operation.currentData()
        try:
            value, unit = surface_integral(sol, surface, op, self.s_field.currentData(), self.s_quantity.currentData())
        except ValueError as exc:
            self.s_result.setText(f"Cannot compute: {exc}")
            return None
        shown = self._shown(value, unit)
        self.s_result.setText(f"<b>{shown}</b>")
        return value, unit

    def _shown(self, value, unit):
        from aeroflowsim.gui.logic import readable
        text, u = readable(value, unit, digits=6, prefs=self.window.units)
        return f"{text} {u}"

    # -- volume integrals
    def _volume_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.v_operation = QComboBox()
        for k, label in VOLUME_OPERATIONS.items():
            self.v_operation.addItem(label, k)
        self.v_field = self.field_combo()
        self.v_region = QComboBox()
        self.v_region.addItems(["Whole domain", "Box", "Circle"])
        self.v_values = QLineEdit()
        self.v_values.setPlaceholderText("box: x1, y1, x2, y2   circle: x, y, radius")
        go = QPushButton("Compute")
        go.clicked.connect(self.compute_volume)
        self.v_result = QLabel()
        self.v_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        as_def = QPushButton("Keep as report definition...")
        as_def.clicked.connect(lambda: self.keep_definition("volume"))
        form.addRow("Operation", self.v_operation)
        form.addRow("Field", self.v_field)
        form.addRow("Region", self.v_region)
        self.v_values_label = QLabel()
        form.addRow(self.v_values_label, self.v_values)
        form.addRow(go)
        form.addRow(self.v_result)
        form.addRow(as_def)
        self.v_region.currentIndexChanged.connect(self._region_label)
        self._region_label()
        return w

    def _region_label(self):
        unit = self.length()[0]
        self.v_values_label.setText(f"Values [{unit}]")
        self.v_values.setEnabled(self.v_region.currentIndex() > 0)

    def region(self):
        k = self.length()[1]
        values = [v / k for v in (_number(t) for t in self.v_values.text().split(",")) if v is not None]
        kind = self.v_region.currentIndex()
        if kind == 1 and len(values) == 4:
            return {"type": "box", "min": values[:2], "max": values[2:]}
        if kind == 2 and len(values) == 3:
            return {"type": "circle", "centre": values[:2], "radius": values[2]}
        if kind > 0:
            raise ValueError("type 4 numbers for a box (x1, y1, x2, y2) or 3 for a circle (x, y, radius)")
        return {}

    def compute_volume(self):
        from aeroflowsim.post.integrals import volume_integral
        sol = self.page.solution()
        if sol is None:
            return None
        try:
            value, unit = volume_integral(sol, self.v_operation.currentData(), self.v_field.currentData(),
                                          self.region() or None)
        except ValueError as exc:
            self.v_result.setText(f"Cannot compute: {exc}")
            return None
        self.v_result.setText(f"<b>{self._shown(value, unit)}</b>")
        return value, unit

    # -- flux balance
    def _flux_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        go = QPushButton("Compute the flux balance")
        go.clicked.connect(self.compute_fluxes)
        self.flux_table = ValueTable(["Boundary", "Type", "Mass", "x-momentum", "y-momentum", "Energy"])
        self.flux_note = QLabel()
        self.flux_note.setObjectName("note")
        self.flux_note.setWordWrap(True)
        save = QPushButton("Save CSV...")
        save.clicked.connect(self.save_fluxes)
        lay.addWidget(go)
        lay.addWidget(self.flux_table, 1)
        lay.addWidget(self.flux_note)
        lay.addWidget(save)
        return w

    def compute_fluxes(self):
        from aeroflowsim.post.integrals import flux_balance
        sol = self.page.solution()
        if sol is None:
            return None
        fb = flux_balance(sol)
        u = self.window.units

        def f(v, unit):
            return self._shown(v, unit)
        rows = [(n, t, f(m, "kg/s"), f(x, "N"), f(y, "N"), f(e, "W")) for n, t, m, x, y, e in fb["rows"]]
        net = fb["net"]
        rows.append(("Net (out - in)", "", f(net[0], "kg/s"), f(net[1], "N"), f(net[2], "N"), f(net[3], "W")))
        self.flux_table.set_rows(rows)
        note = (f"Imbalance: mass {100 * fb['relative']['mass']:.3g} % and energy {100 * fb['relative']['energy']:.3g} % "
                "of the inflow. Outward positive; momentum fluxes include the pressure force.")
        if fb["note"]:
            note += f" {fb['note']} Pressure source: {f(fb['pressure_source'], 'N')}."
        self.flux_note.setText(note)
        self.last_fluxes = fb
        return fb

    def save_fluxes(self):
        from aeroflowsim.post.export import table_csv
        fb = getattr(self, "last_fluxes", None) or self.compute_fluxes()
        if fb is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save flux balance", str(self.project.results_dir / "fluxes.csv"),
                                              "CSV files (*.csv)")
        if path:
            table_csv(path, list(fb["columns"]), list(fb["rows"]) + [("net", "", *fb["net"])],
                      "AeroFlowSim flux balance (SI, outward positive)")

    # -- forces
    def _force_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.f_walls = QListWidget()
        self.f_walls.setSelectionMode(QAbstractItemView.MultiSelection)
        self.f_walls.setMaximumHeight(90)
        self.f_point = QLineEdit("0, 0")
        self.f_aref = QLineEdit()
        self.f_lref = QLineEdit()
        self.f_angle = QLineEdit()
        go = QPushButton("Compute")
        go.clicked.connect(self.compute_forces)
        self.f_table = ValueTable(["Quantity", "Value", "Unit"])
        as_def = QPushButton("Keep Cd / Cl / Cm as report definitions")
        as_def.clicked.connect(self.keep_force_definitions)
        self.f_point_label = QLabel()
        form.addRow("Walls", self.f_walls)
        form.addRow(self.f_point_label, self.f_point)
        form.addRow("Reference area [m²]", self.f_aref)
        form.addRow("Reference length [m]", self.f_lref)
        form.addRow("Free-stream angle [deg]", self.f_angle)
        form.addRow(go)
        form.addRow(self.f_table)
        form.addRow(as_def)
        return w

    def compute_forces(self):
        from aeroflowsim.post.integrals import forces_and_moments
        sol = self.page.solution()
        walls = [i.text() for i in self.f_walls.selectedItems()]
        if sol is None:
            return None
        k = self.length()[1]
        point = [v / k for v in (_number(t, 0.0) for t in self.f_point.text().split(","))][:2] + [0.0, 0.0]
        a_ref = _number(self.f_aref.text(), sol.key_numbers.get("A_ref", (1.0,))[0])
        l_ref = _number(self.f_lref.text(), sol.key_numbers.get("L_ref", (1.0,))[0])
        angle = _number(self.f_angle.text(), None)
        try:
            out = forces_and_moments(sol, walls, point[:2], A_ref=a_ref, L_ref=l_ref, angle_deg=angle)
        except ValueError as exc:
            self.f_table.set_rows([("Cannot compute", str(exc), "")])
            return None
        from aeroflowsim.gui.logic import readable
        rows = []
        for key, label, unit in (("Fx", "Force x (body axes)", out["force_unit"]), ("Fy", "Force y", out["force_unit"]),
                                 ("D", "Drag (wind axes)", out["force_unit"]), ("L", "Lift", out["force_unit"]),
                                 ("M", "Moment (nose-up +)", out["moment_unit"]), ("Cd", "Cd", "-"), ("Cl", "Cl", "-"),
                                 ("Cm", "Cm", "-")):
            rows.append((label, *readable(float(out[key]), unit, digits=6, prefs=self.window.units)))
        if out["x_cp"] is not None:
            rows.append(("Centre of pressure x", *readable(out["x_cp"], "m", digits=5, prefs=self.window.units)))
        rows.append(("Reference area, length", f"{a_ref:g} m², {l_ref:g} m", ""))
        self.f_table.set_rows(rows)
        self.last_forces = out
        return out

    # -- report definitions
    def _definitions_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.d_table = ValueTable(["Name", "Definition", "Value", "Unit", "Monitor"])
        evaluate = QPushButton("Evaluate")
        evaluate.clicked.connect(self.evaluate_definitions)
        edit = QPushButton("Monitor settings...")
        edit.clicked.connect(self.edit_definition)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.delete_definition)
        save = QPushButton("Save CSV...")
        save.clicked.connect(self.save_definitions)
        row = QHBoxLayout()
        for b in (evaluate, edit, delete, save):
            row.addWidget(b)
        note = QLabel("Make a definition in the Surface, Volume or Forces tab ('Keep as report definition'). Marked "
                      "'monitor', it is plotted during the run and written to results/report_<name>.csv; marked "
                      "'converge', the run is converged only when it has settled.")
        note.setObjectName("note")
        note.setWordWrap(True)
        lay.addWidget(self.d_table, 1)
        lay.addLayout(row)
        lay.addWidget(note)
        return w

    def keep_definition(self, kind):
        name, ok = QInputDialog.getText(self, "Report definition", "Name of the report definition:")
        name = name.strip()
        if not ok or not name:
            return
        if kind == "surface":
            d = ReportDefinition(name, "surface", self.s_surface.currentText(), self.s_operation.currentData(),
                                 self.s_field.currentData() or "", self.s_quantity.currentData())
        else:
            try:
                region = self.region()
            except ValueError as exc:
                QMessageBox.warning(self, "Report definition", str(exc))
                return
            d = ReportDefinition(name, "volume", operation=self.v_operation.currentData(),
                                 field=self.v_field.currentData() or "", region=region)
        self._add(d)

    def keep_force_definitions(self):
        walls = [i.text() for i in self.f_walls.selectedItems()]
        if not walls:
            QMessageBox.information(self, "Report definitions", "Choose the walls first.")
            return
        k = self.length()[1]
        point = tuple([v / k for v in (_number(t, 0.0) for t in self.f_point.text().split(","))][:2])
        for q in ("Cd", "Cl", "Cm"):
            self._add(ReportDefinition(f"{q} ({', '.join(walls)})", "force", walls=walls, force=q,
                                       moment_point=point), quiet=True)
        self.evaluate_definitions()

    def _add(self, d, quiet=False):
        defs = [x for x in definitions_from(self.project.post["report_definitions"]) if x.name != d.name]
        defs.append(d)
        self.project.set_post("report_definitions", [x.to_dict() for x in defs])
        self.window.update_title()
        self.evaluate_definitions()
        self.tabs.setCurrentIndex(4)
        if not quiet:
            self.window.log(f"Report definition '{d.name}' added")

    def evaluate_definitions(self):
        from aeroflowsim.post.definitions import evaluate_definitions
        sol = self.page.solution()
        defs = definitions_from(self.project.post["report_definitions"]) if self.project else []
        values = evaluate_definitions(sol, defs, self.page.surfaces(project_only=True)) if sol is not None else {}
        rows = []
        from aeroflowsim.gui.logic import readable
        for d in defs:
            v, u = values.get(d.name, (float("nan"), ""))
            if np.isfinite(v):
                text, unit = readable(v, u, digits=6, prefs=self.window.units)
            else:
                text, unit = "-", u
            mon = ("monitor + converge" if d.converge else "monitor") if d.monitor else ""
            rows.append((d.name, d.describe(), text, unit, mon))
        self.d_table.set_rows(rows)
        self.last_values = values
        return values

    def edit_definition(self):
        row = self.d_table.currentRow()
        defs = definitions_from(self.project.post["report_definitions"])
        if row < 0 or row >= len(defs):
            return
        d = defs[row]
        dialog = MonitorDialog(self, d)
        if dialog.exec() == QDialog.Accepted:
            d.monitor, d.converge = dialog.monitor.isChecked(), dialog.converge.isChecked()
            d.tolerance, d.window = dialog.tolerance.value(), dialog.window.value()
            self.project.set_post("report_definitions", [x.to_dict() for x in defs])
            self.window.update_title()
            self.evaluate_definitions()

    def delete_definition(self):
        row = self.d_table.currentRow()
        defs = definitions_from(self.project.post["report_definitions"])
        if row < 0 or row >= len(defs):
            return
        if QMessageBox.question(self, "Delete report definition", f"Delete '{defs[row].name}'?") != QMessageBox.Yes:
            return
        del defs[row]
        self.project.set_post("report_definitions", [x.to_dict() for x in defs])
        self.window.update_title()
        self.evaluate_definitions()

    def save_definitions(self):
        from aeroflowsim.post.export import definitions_csv
        values = getattr(self, "last_values", None) or self.evaluate_definitions()
        path, _ = QFileDialog.getSaveFileName(self, "Save report definitions",
                                              str(self.project.results_dir / "report_definitions.csv"),
                                              "CSV files (*.csv)")
        if path:
            definitions_csv(values, path, definitions_from(self.project.post["report_definitions"]))

    def fill(self):
        sol = self.page.solution()
        self.s_surface.clear()
        for s in self.page.surfaces():
            if s.type != "point" or True:
                self.s_surface.addItem(s.name)
        for combo in (self.s_field, self.v_field):
            self.fill_fields(combo)
        self.f_walls.clear()
        if sol is not None:
            for name, bc in sol.conditions.items():
                if bc.type == "slip_wall":
                    item = QListWidgetItem(name)
                    self.f_walls.addItem(item)
                    item.setSelected(True)
        self.f_point_label.setText(f"Moment point x, y [{self.length()[0]}]")
        self._surface_enable()
        self.evaluate_definitions()


class MonitorDialog(QDialog):
    def __init__(self, parent, d):
        super().__init__(parent)
        self.setWindowTitle(f"Monitor: {d.name}")
        self.monitor = QCheckBox("Evaluate during the run (monitor)", checked=d.monitor)
        self.converge = QCheckBox("Use as a convergence criterion", checked=d.converge)
        self.tolerance = QDoubleSpinBox(decimals=8, minimum=1e-8, maximum=1.0, value=d.tolerance, singleStep=1e-4)
        self.window = QSpinBox(minimum=2, maximum=1_000_000, value=d.window)
        form = QFormLayout(self)
        form.addRow(self.monitor)
        form.addRow(self.converge)
        form.addRow("Settled within (relative)", self.tolerance)
        form.addRow("over iterations", self.window)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.converge.toggled.connect(lambda on: self.monitor.setChecked(True) if on else None)


# ==================================================================================================== XY plots

class XYPanel(_Base):
    def __init__(self, page):
        super().__init__(page)
        self.fields = QListWidget()
        self.fields.setSelectionMode(QAbstractItemView.MultiSelection)
        self.surfaces = QListWidget()
        self.surfaces.setSelectionMode(QAbstractItemView.MultiSelection)
        for w in (self.fields, self.surfaces):
            w.setMaximumHeight(120)
        self.x_axis = self.field_combo()
        self.log_x, self.log_y = QCheckBox("Log x"), QCheckBox("Log y")
        self.cells = QCheckBox("Cell values (steps)")
        self.reference = QLineEdit()
        self.reference.setPlaceholderText("CSV with two columns x, y (SI units)")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse)
        self.reference_label = QLineEdit("Reference")
        self.overlay = QListWidget()
        self.overlay.setSelectionMode(QAbstractItemView.MultiSelection)
        self.overlay.setMaximumHeight(80)
        plot = QPushButton("Plot")
        plot.clicked.connect(self.plot)
        save = QPushButton("Save picture...")
        save.clicked.connect(self.save_picture)
        csv = QPushButton("Save CSV...")
        csv.clicked.connect(self.save_csv)
        keep = QPushButton("Keep plot...")
        keep.clicked.connect(self.keep_plot)
        self.saved = QComboBox()
        self.saved.currentIndexChanged.connect(self.load_plot)
        self.message = QLabel()
        self.message.setObjectName("note")
        self.message.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Saved plots", self.saved)
        form.addRow("y: fields", self.fields)
        form.addRow("on surfaces", self.surfaces)
        form.addRow("x axis", self.x_axis)
        opts = QHBoxLayout()
        for w in (self.log_x, self.log_y, self.cells):
            opts.addWidget(w)
        form.addRow(opts)
        ref = QHBoxLayout()
        ref.addWidget(self.reference, 1)
        ref.addWidget(browse)
        form.addRow("Reference data", ref)
        form.addRow("Its legend", self.reference_label)
        form.addRow("Overlay snapshots", self.overlay)
        buttons = QGridLayout()
        for i, b in enumerate((plot, save, csv, keep)):
            buttons.addWidget(b, i // 2, i % 2)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.addLayout(form)
        lay.addLayout(buttons)
        lay.addWidget(self.message)
        note = QLabel("The plot is drawn in the Plots area under the view.")
        note.setObjectName("note")
        lay.addWidget(note)
        lay.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(inner))
        self.curves = []

    def fill(self):
        from aeroflowsim.gui.results_logic import field_choices
        from aeroflowsim.post.snapshots import list_snapshots
        from aeroflowsim.post.xy import X_CHOICES
        sol = self.page.solution()
        self.fields.clear()
        self.x_axis.clear()
        for key, label in X_CHOICES.items():
            self.x_axis.addItem(label, key)
        if sol is not None:
            for label, name in field_choices(sol):
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, name)
                self.fields.addItem(item)
                item.setSelected(name == "p")
                self.x_axis.addItem(label, name)
        self.surfaces.clear()
        for s in self.page.surfaces():
            if s.type != "point":
                item = QListWidgetItem(s.name)
                self.surfaces.addItem(item)
        if self.surfaces.count():
            walls = [i for i in range(self.surfaces.count()) if "wall" in self.surfaces.item(i).text()]
            self.surfaces.item(walls[0] if walls else 0).setSelected(True)
        self.overlay.clear()
        if self.project:
            for s in list_snapshots(self.project):
                self.overlay.addItem(s["name"])
        self.saved.blockSignals(True)
        self.saved.clear()
        self.saved.addItem("")
        if self.project:
            self.saved.addItems(sorted(self.project.post["xy_plots"]))
        self.saved.blockSignals(False)

    def settings(self):
        from aeroflowsim.post.xy import XYPlot
        return XYPlot("XY plot", [i.data(Qt.UserRole) for i in self.fields.selectedItems()],
                      [i.text() for i in self.surfaces.selectedItems()], self.x_axis.currentData() or "x",
                      self.log_x.isChecked(), self.log_y.isChecked(), self.reference.text().strip(),
                      self.reference_label.text().strip() or "Reference", "cell" if self.cells.isChecked() else "linear")

    def _labels(self, sol, plot):
        from aeroflowsim.post.xy import axis_label
        convert = None
        prefs = self.window.units

        def convert(values, unit):
            from aeroflowsim.gui.results_logic import display_values
            return display_values(values, unit, prefs)
        return axis_label(sol, plot.x_axis, convert), axis_label(sol, plot.fields[0], convert) if plot.fields else ""

    def build(self, style=None):
        from aeroflowsim.gui.results_logic import display_values
        from aeroflowsim.post.fields import field_info
        from aeroflowsim.post.snapshots import list_snapshots
        from aeroflowsim.post.solution import Solution
        from aeroflowsim.post.xy import X_CHOICES, Curve, curves, read_reference_csv, xy_figure
        sol = self.page.solution()
        plot = self.settings()
        if sol is None or not plot.fields or not plot.surfaces:
            self.message.setText("Choose at least one field and one surface.")
            return None
        surfaces = {s.name: s for s in self.page.surfaces()}
        try:
            out = curves(sol, plot, surfaces)
            for item in self.overlay.selectedItems():
                snap = Solution.from_project(self.project, snapshot=item.text())
                for c in curves(snap, plot, surfaces, label_prefix=f"{item.text()}: "):
                    c.style = "dashed"
                    out.append(c)
        except ValueError as exc:
            self.message.setText(str(exc))
            return None
        prefs = self.window.units
        x_unit = "m" if plot.x_axis in X_CHOICES else field_info(sol, plot.x_axis).unit
        y_unit = field_info(sol, plot.fields[0]).unit
        for c in out:
            c.x = display_values(c.x, x_unit, prefs)[0]
            c.y = display_values(c.y, y_unit, prefs)[0]
        if plot.reference_csv:
            try:
                rx, ry, _ = read_reference_csv(self._path(plot.reference_csv))
                out.append(Curve(display_values(rx, x_unit, prefs)[0], display_values(ry, y_unit, prefs)[0],
                                 plot.reference_label, "markers"))
            except (OSError, ValueError) as exc:
                self.message.setText(f"Reference data not read: {exc}")
        xlabel, ylabel = self._labels(sol, plot)
        from aeroflowsim.gui.theme import is_dark
        style = style or ("dark" if is_dark() else "paper")
        self.curves, self.xlabel, self.ylabel = out, xlabel, ylabel
        return xy_figure(out, xlabel, ylabel, plot.log_x, plot.log_y, style=style)

    def _path(self, text):
        p = Path(text)
        return p if p.is_absolute() else self.project.folder / p

    def plot(self):
        self.message.setText("")
        fig = self.build()
        if fig is not None:
            self.page.show_figure(fig, "XY plot")

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Reference data", str(self.project.folder), "CSV files (*.csv)")
        if path:
            try:
                path = str(Path(path).relative_to(self.project.folder))
            except ValueError:
                pass
            self.reference.setText(path)

    def save_picture(self):
        from aeroflowsim.post.xy import save_figure
        path, _ = QFileDialog.getSaveFileName(self, "Save XY plot", str(self.project.results_dir / "xy_plot.png"),
                                              "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if path:
            fig = self.build(style="paper")
            if fig is not None:
                save_figure(fig, path)
                self.window.log(f"XY plot saved to {path} (paper style)")

    def save_csv(self):
        from aeroflowsim.post.xy import curves_csv
        if not self.curves:
            self.plot()
        path, _ = QFileDialog.getSaveFileName(self, "Save XY data", str(self.project.results_dir / "xy_plot.csv"),
                                              "CSV files (*.csv)")
        if path and self.curves:
            curves_csv(self.curves, path, self.xlabel, self.ylabel)

    def keep_plot(self):
        name, ok = QInputDialog.getText(self, "Keep XY plot", "Name of the plot:")
        if ok and name.strip():
            plots = dict(self.project.post["xy_plots"])
            plots[name.strip()] = self.settings().to_dict()
            self.project.set_post("xy_plots", plots)
            self.window.update_title()
            self.fill()
            self.saved.setCurrentText(name.strip())

    def load_plot(self):
        from aeroflowsim.post.xy import XYPlot
        name = self.saved.currentText()
        data = self.project.post["xy_plots"].get(name) if self.project and name else None
        if not data:
            return
        p = XYPlot.from_dict(data)
        for i in range(self.fields.count()):
            self.fields.item(i).setSelected(self.fields.item(i).data(Qt.UserRole) in p.fields)
        for i in range(self.surfaces.count()):
            self.surfaces.item(i).setSelected(self.surfaces.item(i).text() in p.surfaces)
        self.x_axis.setCurrentIndex(max(self.x_axis.findData(p.x_axis), 0))
        self.log_x.setChecked(p.log_x)
        self.log_y.setChecked(p.log_y)
        self.cells.setChecked(p.mode == "cell")
        self.reference.setText(p.reference_csv)
        self.reference_label.setText(p.reference_label)
        self.plot()


# ==================================================================================================== Snapshots

class SnapshotsPanel(_Base):
    def __init__(self, page):
        super().__init__(page)
        self.table = ValueTable(["Name", "Saved", "Iterations", "Size"])
        save = QPushButton("Save current...")
        save.clicked.connect(self.save)
        rename = QPushButton("Rename...")
        rename.clicked.connect(self.rename)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.delete)
        restore = QPushButton("Restore as current")
        restore.clicked.connect(self.restore)
        compare = QPushButton("Compare with current")
        compare.clicked.connect(self.compare)
        self.size = QLabel()
        self.size.setObjectName("note")
        self.size.setWordWrap(True)
        self.numbers = ValueTable(["Key number", "Current", "Snapshot", "Unit", "Change %"])
        grid = QGridLayout()
        for i, b in enumerate((save, rename, delete, restore, compare)):
            grid.addWidget(b, i // 2, i % 2)
        lay = QVBoxLayout(self)
        lay.addWidget(self.table, 1)
        lay.addLayout(grid)
        lay.addWidget(self.size)
        lay.addWidget(QLabel("<b>Key numbers: current vs snapshot</b>"))
        lay.addWidget(self.numbers, 1)

    def fill(self):
        from aeroflowsim.post.snapshots import folder_size, list_snapshots, size_text, size_warning
        if self.project is None:
            return
        items = list_snapshots(self.project)
        self.table.set_rows([(s["name"], s["saved"], s["iterations"] or "", size_text(s["size"])) for s in items])
        warning = size_warning(self.project)
        self.size.setText(f"Project size: {size_text(folder_size(self.project.folder))}. {warning}")

    def _selected(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return None if item is None else item.text()

    def save(self):
        from aeroflowsim.post.snapshots import save_snapshot
        name, ok = QInputDialog.getText(self, "Save snapshot", "Name of the snapshot (e.g. baseline):")
        if not ok or not name.strip():
            return
        try:
            save_snapshot(self.project, name.strip())
        except ValueError as exc:
            if "already exists" in str(exc) and QMessageBox.question(
                    self, "Save snapshot", f"{exc} Replace it?") == QMessageBox.Yes:
                save_snapshot(self.project, name.strip(), overwrite=True)
            else:
                return
        self.window.log(f"Snapshot '{name.strip()}' saved")
        self.page.snapshots_changed()

    def rename(self):
        from aeroflowsim.post.snapshots import rename_snapshot
        old = self._selected()
        if old is None:
            return
        new, ok = QInputDialog.getText(self, "Rename snapshot", "New name:", text=old)
        if ok and new.strip() and new.strip() != old:
            try:
                rename_snapshot(self.project, old, new.strip())
            except ValueError as exc:
                QMessageBox.warning(self, "Rename snapshot", str(exc))
                return
            self.page.snapshots_changed()

    def delete(self):
        from aeroflowsim.post.snapshots import delete_snapshot
        name = self._selected()
        if name is None:
            return
        if QMessageBox.question(self, "Delete snapshot", f"Delete the snapshot '{name}'? This cannot be undone.") \
                != QMessageBox.Yes:
            return
        delete_snapshot(self.project, name)
        self.window.log(f"Snapshot '{name}' deleted")
        self.page.snapshots_changed()

    def restore(self):
        from aeroflowsim.post.snapshots import restore_snapshot, save_snapshot
        name = self._selected()
        if name is None or self.window.runner.busy:
            return
        answer = QMessageBox.question(
            self, "Restore snapshot", f"Make '{name}' the current result? The current result is replaced.\n\n"
            "Save the current result as a snapshot first?", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if answer == QMessageBox.Cancel:
            return
        if answer == QMessageBox.Yes:
            n, ok = QInputDialog.getText(self, "Save snapshot", "Name for the current result:")
            if not ok or not n.strip():
                return
            save_snapshot(self.project, n.strip(), overwrite=True)
        restore_snapshot(self.project, name)
        self.window.reload_project_results()
        self.window.log(f"Snapshot '{name}' restored as the current result")
        self.page.snapshots_changed()

    def compare(self):
        from aeroflowsim.post.compare import key_number_table
        from aeroflowsim.post.solution import Solution
        name = self._selected()
        sol = self.page.solution()
        if name is None or sol is None:
            return
        snap = Solution.from_project(self.project, snapshot=name)
        self.numbers.set_rows([(k, f"{a:.6g}", f"{b:.6g}", u, f"{c:+.3f}") for k, a, b, u, c in key_number_table(sol, snap)])
        self.page.compare_with(name)


# ==================================================================================================== Fields

class FieldsPanel(_Base):
    changed = Signal()

    def __init__(self, page):
        super().__init__(page)
        self.table = ValueTable(["Name", "Formula", "Label", "Unit"])
        self.name = QLineEdit()
        self.name.setPlaceholderText("name, e.g. p_bar")
        self.formula = QLineEdit()
        self.formula.setPlaceholderText("formula, e.g. p / 1e5   or   sqrt(u**2 + v**2)")
        self.label = QLineEdit()
        self.label.setPlaceholderText("label shown (optional)")
        self.message = QLabel()
        self.message.setObjectName("note")
        self.message.setWordWrap(True)
        add = QPushButton("Add / replace")
        add.clicked.connect(self.add)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.delete)
        self.formula.textChanged.connect(self.check)
        self.name.textChanged.connect(self.check)
        help_text = QLabel("Fields: rho, u, v, p, T, M, p0, T0, s, speed, h, h0, Cp, vorticity, divergence, x, y and "
                           "your own fields. Constants: pi, e, g0, gamma, R. Functions: sqrt, exp, log, log10, abs, sin, "
                           "cos, tan, minimum, maximum, ... Values in SI units.")
        help_text.setObjectName("note")
        help_text.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.name)
        lay.addWidget(self.formula)
        lay.addWidget(self.label)
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(delete)
        lay.addLayout(row)
        lay.addWidget(self.message)
        lay.addWidget(help_text)

    def fill(self):
        from aeroflowsim.post.fields import field_info
        sol = self.page.solution()
        rows = []
        for name, spec in (self.project.custom_fields if self.project else {}).items():
            unit = ""
            if sol is not None:
                try:
                    unit = field_info(sol, name).unit
                except ValueError:
                    unit = "?"
            rows.append((name, spec["formula"], spec.get("label", ""), unit))
        self.table.set_rows(rows)

    def check(self):
        from aeroflowsim.post.fields import custom_field_problem
        sol = self.page.solution()
        name, formula = self.name.text().strip(), self.formula.text().strip()
        if sol is None or not name or not formula:
            self.message.setText("")
            return "incomplete"
        existing = dict(sol.custom_fields)
        existing.pop(name, None)
        sol.custom_fields = existing
        problem = custom_field_problem(sol, name, formula)
        sol.custom_fields = dict(self.project.custom_fields)
        self.message.setText(problem or "OK")
        return problem

    def add(self):
        problem = self.check()
        if problem:
            return
        fields = dict(self.project.custom_fields)
        fields[self.name.text().strip()] = {"formula": self.formula.text().strip(),
                                           "label": self.label.text().strip() or self.name.text().strip()}
        self.project.set_post("custom_fields", fields)
        self.window.update_title()
        self.page.custom_fields_changed()

    def delete(self):
        row = self.table.currentRow()
        names = list(self.project.custom_fields)
        if row < 0 or row >= len(names):
            return
        fields = dict(self.project.custom_fields)
        fields.pop(names[row])
        self.project.set_post("custom_fields", fields)
        self.window.update_title()
        self.page.custom_fields_changed()


class InitialisationDialog(QDialog):
    """Patch regions for a fresh start, and the interpolation onto a new mesh (Run step)."""

    def __init__(self, parent, project, prefs):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Start of a run")
        unit = prefs.unit_for("m")
        self.k = float(unit.from_si(1.0)) if unit else 1.0
        lu = unit.name if unit else "m"
        self.interpolate = QCheckBox("On a new mesh, start from the previous solution interpolated onto it",
                                     checked=project.post.get("interpolate_new_mesh", True))
        self.table = ValueTable(["Region", "Values (SI)"])
        self.region = QComboBox()
        self.region.addItems(["Box", "Circle"])
        self.coords = QLineEdit()
        self.coords.setPlaceholderText(f"box: x1, y1, x2, y2   circle: x, y, radius  [{lu}]")
        self.p, self.T, self.u, self.v = (QLineEdit() for _ in range(4))
        for box, text in ((self.p, "p [Pa]"), (self.T, "T [K]"), (self.u, "u [m/s]"), (self.v, "v [m/s]")):
            box.setPlaceholderText(text + " (empty: keep)")
        add = QPushButton("Add region")
        add.clicked.connect(self.add)
        delete = QPushButton("Delete region")
        delete.clicked.connect(self.delete)
        self.message = QLabel("Patch regions are applied on top of the Initial solution when a run starts from scratch "
                              "(Start from scratch, or the first run).")
        self.message.setObjectName("note")
        self.message.setWordWrap(True)
        self.patches = [dict(p) for p in project.post.get("init_patches", [])]
        form = QFormLayout()
        form.addRow("Region", self.region)
        form.addRow("Corners / centre", self.coords)
        for box in (self.p, self.T, self.u, self.v):
            form.addRow(box.placeholderText().split(" ")[0], box)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.interpolate)
        lay.addWidget(self.table)
        lay.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(delete)
        lay.addLayout(row)
        lay.addWidget(self.message)
        lay.addWidget(buttons)
        self._show()

    def _show(self):
        rows = []
        for p in self.patches:
            r = p["region"]
            where = (f"box {r['min']} - {r['max']} m" if r["type"] == "box" else f"circle {r['centre']} m, r = {r['radius']} m")
            rows.append((where, ", ".join(f"{k} = {v:g}" for k, v in p["values"].items())))
        self.table.set_rows(rows)

    def add(self):
        nums = [v / self.k for v in (_number(t) for t in self.coords.text().split(",")) if v is not None]
        values = {k: _number(b.text()) for k, b in (("p", self.p), ("T", self.T), ("u", self.u), ("v", self.v))}
        values = {k: v for k, v in values.items() if v is not None}
        if self.region.currentText() == "Box" and len(nums) == 4:
            region = {"type": "box", "min": nums[:2], "max": nums[2:]}
        elif self.region.currentText() == "Circle" and len(nums) == 3:
            region = {"type": "circle", "centre": nums[:2], "radius": nums[2]}
        else:
            self.message.setText("Type 4 numbers for a box or 3 for a circle.")
            return
        if not values:
            self.message.setText("Give at least one value (p, T, u or v).")
            return
        if any(values.get(k, 1.0) <= 0 for k in ("p", "T")):
            self.message.setText("Pressure and temperature must be positive.")
            return
        self.patches.append({"region": region, "values": values})
        self._show()

    def delete(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.patches):
            del self.patches[row]
            self._show()

    def apply(self):
        self.project.set_post("init_patches", self.patches)
        self.project.set_post("interpolate_new_mesh", self.interpolate.isChecked())

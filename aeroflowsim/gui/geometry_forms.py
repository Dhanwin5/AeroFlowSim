# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Forms and dialogs of the geometry workspace.

    OperationForm     the editable settings of ONE operation, generated from gui/geometry_logic.FIELDS
                      (no per-operation GUI code: a new operation only needs a FIELDS entry)
    OperationDialog   that form in a dialog with OK / Cancel (to add a new operation)
    ImportDialog      unit, fluid/solid, healing tolerance, cutting plane - with a live preview
    PointTableDialog  the points of an outline in a table (mm): edit, insert, delete rows
    SuggestionsDialog the smart rule's suggested sizes, each with its reason and an Apply button
"""

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from aeroflowsim.geometry_model import GeometryDocument, operation_from_dict
from aeroflowsim.gui import geometry_logic as logic
from aeroflowsim.gui.widgets import ValueTable


class OperationForm(QWidget):
    """Editable settings of an operation. changed() is emitted on every edit; operation() reads it back."""

    changed = Signal()

    def __init__(self, op, parent=None):
        super().__init__(parent)
        self.op = operation_from_dict(op.to_dict())          # work on a copy
        self.fields = logic.fields_for(op)
        self.editors, self.labels = {}, {}
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for field in self.fields:
            value = self.op.params[field.key]
            if field.kind == "choice":
                editor = QComboBox()
                for key, label in field.options:
                    editor.addItem(label, key)
                editor.setCurrentIndex(max(0, [k for k, _ in field.options].index(value)
                                           if value in [k for k, _ in field.options] else 0))
                editor.currentIndexChanged.connect(self._edited)
            elif field.kind == "bool":
                editor = QCheckBox()
                editor.setChecked(bool(value))
                editor.toggled.connect(self._edited)
            else:
                editor = QLineEdit(logic.to_text(field, value))
                editor.textEdited.connect(self._edited)
            if field.help:
                editor.setToolTip(field.help)
            label = QLabel(f"{field.label}" + (f" [{field.unit}]" if field.unit else ""))
            layout.addRow(label, editor)
            self.editors[field.key], self.labels[field.key] = editor, label
        self.problem = QLabel(objectName="error", wordWrap=True)
        layout.addRow(self.problem)
        self._update_visible()

    def _read(self, field):
        editor = self.editors[field.key]
        if field.kind == "choice":
            return editor.currentData()
        if field.kind == "bool":
            return editor.isChecked()
        return logic.from_text(field, editor.text())

    def operation(self):
        """The operation with the typed settings; ValueError naming the first bad field."""
        op = operation_from_dict(self.op.to_dict())
        for field in self.fields:
            op.params[field.key] = self._read(field)
        return op

    def _edited(self, *_):
        try:
            self.operation()
            self.problem.setText("")
        except ValueError as error:
            self.problem.setText(str(error))
        self._update_visible()
        self.changed.emit()

    def _update_visible(self):
        params = dict(self.op.params)
        for field in self.fields:
            if field.kind == "choice":
                params[field.key] = self.editors[field.key].currentData()
        for field in self.fields:
            visible = logic.shown(field, params)
            self.editors[field.key].setVisible(visible)
            self.labels[field.key].setVisible(visible)


class OperationDialog(QDialog):
    """Add a new operation: its settings form, OK / Cancel."""

    def __init__(self, op, title, note="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.form = OperationForm(op)
        layout = QVBoxLayout(self)
        if note:
            layout.addWidget(QLabel(note, wordWrap=True))
        layout.addWidget(self.form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.result_op = None

    def accept(self):
        try:
            self.result_op = self.form.operation()
        except ValueError as error:
            self.form.problem.setText(str(error))
            return
        super().accept()


class ImportDialog(QDialog):
    """Settings of an import, with a preview of what the file gives (size, faces, area, messages)."""

    def __init__(self, op, context, has_template=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Import {op.params['source'] or op.params['file']}")
        self.context = context
        self.form = OperationForm(op)
        self.form.changed.connect(self.update_preview)
        self.replace = QCheckBox("Replace the template geometry (switch the template shape off)")
        self.replace.setChecked(has_template)
        self.replace.setVisible(has_template)
        self.summary = ValueTable(["Preview", "Value", "Unit"])
        self.summary.setMinimumHeight(170)
        self.notes = QLabel(wordWrap=True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.form)
        layout.addWidget(self.replace)
        layout.addWidget(self.summary)
        layout.addWidget(self.notes)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(520, 520)
        self.result_op = None
        self.update_preview()

    def update_preview(self):
        from aeroflowsim.geometry_model import replay
        try:
            op = self.form.operation()
        except ValueError as error:
            self.notes.setText(str(error))
            return
        built = replay(GeometryDocument([operation_from_dict({**op.to_dict(), "id": "op1"})]), self.context,
                       triangulate=False)
        box = built.bbox()
        rows = []
        if box is not None:
            rows += [("Width (x)", logic.mm(box[2] - box[0]), "mm"), ("Height (y)", logic.mm(box[3] - box[1]), "mm"),
                     ("x from", f"{logic.mm(box[0])} to {logic.mm(box[2])}", "mm"),
                     ("y from", f"{logic.mm(box[1])} to {logic.mm(box[3])}", "mm")]
        rows += [("Edges", str(len(built.edges)), "")]
        for face in built.faces.values():
            rows.append((f"Face ({face.role})", f"{face.area / logic.MM**2:.6g}", "mm²"))
        self.summary.set_rows(rows)
        self.notes.setText("\n".join(text for _, text in built.messages))

    def accept(self):
        try:
            self.result_op = self.form.operation()
        except ValueError as error:
            self.notes.setText(str(error))
            return
        super().accept()


class SuggestionsDialog(QDialog):
    """Suggested sizes (aeroflowsim/smart_rules.py): title, value, reason, Apply. Nothing is applied by itself."""

    def __init__(self, suggestions, apply, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Suggested sizes")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Suggestions from the geometry. Each one is applied only when you press its Apply "
                                "button (and can be undone); the validity checks then check the result.",
                                wordWrap=True))
        self.buttons = []
        if not suggestions:
            layout.addWidget(QLabel("<i>No suggestions: the sizes already follow the rules.</i>"))
        for suggestion in suggestions:
            box = QFormLayout()
            title = QLabel(f"<b>{suggestion.title}</b>: {suggestion.text}")
            reason = QLabel(suggestion.reason, wordWrap=True, objectName="hint")
            button = QPushButton("Apply")
            button.clicked.connect(lambda _=False, s=suggestion, b=button: (apply(s), b.setEnabled(False),
                                                                             b.setText("Applied")))
            row = QHBoxLayout()
            row.addWidget(title, 1)
            row.addWidget(button)
            box.addRow(row)
            box.addRow(reason)
            layout.addLayout(box)
            self.buttons.append(button)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.resize(560, 120 + 90 * len(suggestions))


class PointTableDialog(QDialog):
    """The points of an outline (x, y in mm): type new values, insert or delete rows."""

    def __init__(self, points_m, title="Points", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["x [mm]", "y [mm]"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for x, y in np.asarray(points_m) / logic.MM:
            self._append(x, y)
        insert, delete = QPushButton("Insert point after"), QPushButton("Delete point")
        insert.clicked.connect(self.insert_after)
        delete.clicked.connect(self.delete_rows)
        self.problem = QLabel(objectName="error", wordWrap=True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(insert)
        row.addWidget(delete)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(row)
        layout.addWidget(self.problem)
        layout.addWidget(buttons)
        self.resize(360, 520)
        self.result_points = None

    def _append(self, x, y, row=None):
        row = self.table.rowCount() if row is None else row
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(f"{x:.8g}"))
        self.table.setItem(row, 1, QTableWidgetItem(f"{y:.8g}"))

    def insert_after(self):
        row = self.table.currentRow()
        pts = self.points_mm()
        if pts is None or not len(pts):
            return
        row = len(pts) - 1 if row < 0 else row
        nxt = pts[row + 1] if row + 1 < len(pts) else pts[row]
        mid = 0.5 * (pts[row] + nxt)                       # halfway to the next point
        self._append(mid[0], mid[1], row + 1)

    def delete_rows(self):
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def points_mm(self):
        try:
            return np.array([[float(self.table.item(r, c).text().replace(",", ".")) for c in range(2)]
                             for r in range(self.table.rowCount())])
        except (ValueError, AttributeError):
            self.problem.setText("Every cell must hold a number.")
            return None

    def accept(self):
        pts = self.points_mm()
        if pts is None:
            return
        if len(pts) < 3:
            self.problem.setText("An outline needs at least three points.")
            return
        self.result_points = pts * logic.MM
        super().accept()

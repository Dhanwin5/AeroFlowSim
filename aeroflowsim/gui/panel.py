# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Qt input panel, drawn automatically from a case's schema.toml (zero GUI code per case).

What to show is decided by aeroflowsim/gui/panel_model.py (tested without a window); this module
only turns each WidgetSpec into a Qt widget:
    float / int  -> NumberEdit (a text box that accepts 2.8e-4; arrow keys and wheel step the value)
    bool         -> QCheckBox
    choice       -> QComboBox (options needing a missing package are greyed out, with the install hint)
    text         -> QLineEdit
    file         -> QLineEdit + "Browse..." button (a file dialog)
Every label and box shows the help text and allowed range as a tooltip (rest the mouse on it); a
red message appears under a bad value.
Groups are collapsible sections; inputs and sections hide and show with show_if.

Qt basics used here: a *signal* is an event a widget announces (e.g. "text edited"), a *slot* is
the function connected to it. The panel announces every change the user makes with its signal
value_changed(name, value); the main window decides what to do with it (store it, allow undo,
mark results out of date). Values set by the program (set_values) do not emit the signal.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QScrollArea, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from aeroflowsim.gui.panel_model import PanelModel, WidgetSpec, text_to_value, value_to_text

ERROR_STYLE = "color: #d32f2f;"          # readable on light and dark backgrounds
HINT_STYLE = "color: palette(mid); font-size: 90%;"


class NumberEdit(QLineEdit):
    """A text box for one number. Typed text is kept as typed until Enter or leaving the box.

    A spin box would silently clamp out-of-range values; this box keeps what the user typed and
    the panel shows why it is not allowed, as every other AeroFlowSim check does.
    Up/Down arrow keys and the mouse wheel (when the box has focus) add or subtract one step.
    """

    def __init__(self, spec: WidgetSpec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def _step(self, direction):
        value = text_to_value(self.spec, self.text())
        if isinstance(value, str):
            return
        value = value + direction * self.spec.step_size
        if self.spec.kind == "int":
            value = int(round(value))
        else:
            value = float(f"{value:.12g}")      # no 0.30000000000000004 from repeated steps
        value = min(max(value, self.spec.minimum), self.spec.maximum)
        self.setText(value_to_text(value))
        self.editingFinished.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Up, Qt.Key_Down):
            self._step(1 if event.key() == Qt.Key_Up else -1)
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        if self.hasFocus():                     # never change a value just by scrolling the panel
            self._step(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
        else:
            event.ignore()


class Section(QWidget):
    """A collapsible group: a bold header button with an arrow, and the inputs below it."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.header = QToolButton(text=title, checkable=True, checked=True)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.DownArrow)
        self.header.setStyleSheet("QToolButton { border: none; font-weight: bold; color: palette(window-text); }")
        self.header.toggled.connect(self._toggle)
        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(16, 0, 0, 6)
        self.grid.setColumnStretch(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.header)
        layout.addWidget(self.body)

    def _toggle(self, opened):
        self.header.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)
        self.body.setVisible(opened)


class InputRow:
    """The widgets of one input: label, editor, '?' button, hint and error message."""

    def __init__(self, panel, spec: WidgetSpec, section: Section):
        self.spec = spec
        self.panel = panel
        self.label = QLabel(spec.label if spec.kind != "bool" else "")
        self.label.setToolTip(spec.tooltip)
        self.editor, editor_widget = self._make_editor()
        self.editor.setToolTip(spec.tooltip)
        self.hint = QLabel("\n".join(spec.missing.values()), wordWrap=True, visible=bool(spec.missing))
        self.hint.setStyleSheet(HINT_STYLE)
        self.error = QLabel(wordWrap=True, visible=False)
        self.error.setStyleSheet(ERROR_STYLE)
        self.error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row = section.grid.rowCount()
        section.grid.addWidget(self.label, row, 0)
        section.grid.addWidget(editor_widget, row, 1)
        section.grid.addWidget(self.hint, row + 1, 1)
        section.grid.addWidget(self.error, row + 2, 1)
        self.widgets = [self.label, editor_widget]

    def _make_editor(self):
        """The editor widget for the input type, and the widget to put in the layout."""
        s = self.spec
        if s.kind in ("float", "int"):
            editor = NumberEdit(s)
            editor.editingFinished.connect(lambda: self.panel._edited(s.name, text_to_value(s, editor.text())))
            return editor, editor
        if s.kind == "bool":
            editor = QCheckBox(s.label)
            editor.toggled.connect(lambda checked: self.panel._edited(s.name, checked))
            return editor, editor
        if s.kind == "choice":
            editor = QComboBox()
            for option in s.options:
                editor.addItem(f"{option}  (not installed)" if option in s.missing else option, option)
                if option in s.missing:         # greyed out: cannot be chosen until the package is installed
                    editor.model().item(editor.count() - 1).setEnabled(False)
            editor.currentIndexChanged.connect(lambda i: self.panel._edited(s.name, editor.itemData(i)))
            return editor, editor
        editor = QLineEdit()
        editor.editingFinished.connect(lambda: self.panel._edited(s.name, editor.text()))
        if s.kind == "text":
            return editor, editor
        # file: a path box plus a Browse button
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse)
        layout.addWidget(editor, 1)
        layout.addWidget(browse)
        return editor, box

    def browse(self):
        start = str(Path(self.editor.text()).parent) if self.editor.text() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self.panel, f"Choose {self.spec.label.lower()}", start,
                                              self.spec.file_filter)
        if path:
            self.panel._edited(self.spec.name, self.panel.file_handler(self.spec.name, path))

    def display(self, value):
        """Show a value in the editor without announcing it as a user change."""
        self.editor.blockSignals(True)
        if self.spec.kind == "bool":
            self.editor.setChecked(bool(value))
        elif self.spec.kind == "choice":
            index = self.editor.findData(value)
            if index < 0:                       # a value not in the list (e.g. from an old project)
                self.editor.addItem(f"{value}  (unknown)", value)
                index = self.editor.count() - 1
            self.editor.setCurrentIndex(index)
        else:
            self.editor.setText(value_to_text(value))
        self.editor.blockSignals(False)

    def set_visible(self, shown):
        for w in self.widgets:
            w.setVisible(shown)
        self.hint.setVisible(shown and bool(self.spec.missing))
        if not shown:
            self.error.setVisible(False)

    def set_problem(self, message):
        self.error.setText(message or "")
        self.error.setVisible(bool(message))


class InputPanel(QScrollArea):
    """All inputs of a PanelModel, in collapsible groups. Emits value_changed(name, value) on user edits.

    file_handler(name, chosen_path) -> value to store: lets the owner copy a chosen file into the
    project folder and store a relative path (default: store the chosen path as it is).
    """

    value_changed = Signal(str, object)

    def __init__(self, model: PanelModel, values: dict, file_handler=None, parent=None):
        super().__init__(parent)
        self.model = model
        self._values = dict(values)
        self.file_handler = file_handler or (lambda name, path: path)
        self.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        self.sections, self.rows = {}, {}
        for group, specs in model.groups().items():
            section = Section(group)
            self.sections[group] = section
            layout.addWidget(section)
            for spec in specs:
                self.rows[spec.name] = InputRow(self, spec, section)
        layout.addStretch(1)
        content.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.setWidget(content)
        self.set_values(self._values)

    def values(self) -> dict:
        return dict(self._values)

    def problems(self) -> dict:
        return self.model.problems(self._values)

    def set_values(self, values):
        """Show these values (e.g. after Undo or Open); does not emit value_changed."""
        self._values.update(values)
        for name, row in self.rows.items():
            if name in self._values:
                row.display(self._values[name])
        self._refresh()

    def _edited(self, name, value):
        """Slot for every user edit: store, update visibility and messages, announce the change."""
        if self._values.get(name) == value and type(self._values.get(name)) is type(value):
            self._refresh()                     # e.g. Enter pressed without a change
            return
        self._values[name] = value
        self._refresh()
        self.value_changed.emit(name, value)

    def _refresh(self):
        shown = self.model.visible(self._values)
        problems = self.model.problems(self._values)
        for name, row in self.rows.items():
            row.set_visible(name in shown)
            row.set_problem(problems.get(name) if name in shown else None)
        groups = set(self.model.visible_groups(self._values))
        for group, section in self.sections.items():
            section.setVisible(group in groups)

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
    gas          -> QComboBox of the gas library (gui/gas_logic.py) + "Custom..." button (gui/gas_dialog.py)
Every label and box shows the help text and allowed range as a tooltip (rest the mouse on it), and
the Details area under the inputs shows the same facts for the input that was last clicked or
reached with the keyboard (Tab). A red message appears under a bad value.
Groups are collapsible sections; inputs and sections hide and show with show_if.

Qt basics used here: a *signal* is an event a widget announces (e.g. "text edited"), a *slot* is
the function connected to it. The panel announces every change the user makes with its signal
value_changed(name, value); the main window decides what to do with it (store it, allow undo,
mark results out of date). Values set by the program (set_values) do not emit the signal.
"""

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QScrollArea, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from aeroflowsim.gui.gas_logic import gas_choices
from aeroflowsim.gui.theme import colour
from aeroflowsim.gui.panel_model import PanelModel, WidgetSpec, details, text_to_value, value_to_text

INPUT_PROPERTY = "aeroflowsim_input"     # Qt property naming the input a widget belongs to (for Details)
DETAILS_PROMPT = "Click an input (or move to it with Tab) to see what it means, its unit and allowed range."
MIN_LABEL_WIDTH = 90     # px: narrowest label column (long labels wrap onto more lines below their full width)
MIN_EDITOR_WIDTH = 100   # px: narrowest input box (room for a number such as 2.8e-04 or 0.00028)
DETAILS_MAX_HEIGHT = 280 # px: tallest Details box (longer details scroll inside it)


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
        self.header.setObjectName("section")          # styled by the theme (aeroflowsim/gui/theme.py)
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
    """The widgets of one input: label, editor, hint and error message."""

    def __init__(self, panel, spec: WidgetSpec, section: Section):
        self.spec = spec
        self.panel = panel
        self.label = QLabel(spec.label if spec.kind != "bool" else "", wordWrap=True)   # long labels wrap
        self.label.setToolTip(spec.tooltip)
        self.editor, editor_widget = self._make_editor()
        self.editor.setToolTip(spec.tooltip)
        editor_widget.setMinimumWidth(MIN_EDITOR_WIDTH)
        self.hint = QLabel("\n".join(spec.missing.values()), wordWrap=True, visible=bool(spec.missing))
        self.hint.setObjectName("hint")
        self.error = QLabel(wordWrap=True, visible=False)
        self.error.setObjectName("error")
        self.error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row = section.grid.rowCount()
        section.grid.addWidget(self.label, row, 0)
        section.grid.addWidget(editor_widget, row, 1)
        section.grid.addWidget(self.hint, row + 1, 1)
        section.grid.addWidget(self.error, row + 2, 1)
        self.widgets = [self.label, editor_widget]
        # Clicking the label or any part of the editor (or reaching it with Tab) shows its Details.
        for widget in [self.label, editor_widget, *editor_widget.findChildren(QWidget)]:
            widget.setProperty(INPUT_PROPERTY, spec.name)
            widget.installEventFilter(panel)

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
            # Without this a combo box is never narrower than its longest option; now it can shrink
            # with the panel (a long option is then shortened with "..."; the open list shows it whole).
            editor.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            editor.setMinimumContentsLength(8)
            for option in s.options:
                editor.addItem(f"{option}  (not installed)" if option in s.missing else option, option)
                if option in s.missing:         # greyed out: cannot be chosen until the package is installed
                    editor.model().item(editor.count() - 1).setEnabled(False)
            editor.currentIndexChanged.connect(lambda i: self.panel._edited(s.name, editor.itemData(i)))
            return editor, editor
        if s.kind == "gas":
            editor = QComboBox()
            editor.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            editor.setMinimumContentsLength(8)
            editor.currentIndexChanged.connect(self._gas_chosen)
            custom = QPushButton("Custom...")
            custom.setToolTip("Make a custom gas (a copy of the chosen gas that you can edit), saved in your own "
                              "gas library and copied into this project.")
            custom.clicked.connect(lambda: self._new_gas())
            box = QWidget()
            layout = QHBoxLayout(box)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(editor, 1)
            layout.addWidget(custom)
            self._choices = []
            return editor, box
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

    def _gas_chosen(self, index):
        choice = self._choices[index]
        current = self.panel.values().get(self.spec.name)
        if choice.kind == "new":
            self._new_gas()
            return
        value = self.panel.gas_handler.choose(choice) if choice.kind == "user" else choice.data
        if value is None:
            self.display(current)
        else:
            self.panel._edited(self.spec.name, value)
            self.display(value)                     # a user gas is now the project's copy

    def _new_gas(self):
        current = self.panel.values().get(self.spec.name, self.spec.default)
        value = self.panel.gas_handler.new(current)
        if value is not None:
            self.panel._edited(self.spec.name, value)
        self.display(value if value is not None else current)

    def display(self, value):
        """Show a value in the editor without announcing it as a user change."""
        self.editor.blockSignals(True)
        if self.spec.kind == "gas":                 # the list depends on the value (a project gas) and the library
            self._choices = gas_choices(value, self.panel.gas_handler.base)
            self.editor.clear()
            for choice in self._choices:
                self.editor.addItem(choice.text, choice.data)
            index = self.editor.findData(str(value))
            self.editor.setCurrentIndex(max(index, 0))
        elif self.spec.kind == "bool":
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


class DetailsBox(QFrame):
    """The Details area under the inputs: help text and facts of the selected input."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("details")
        self.title = QLabel(wordWrap=True)
        self.help = QLabel(wordWrap=True)
        self.facts = QLabel(wordWrap=True)
        self.problem = QLabel(wordWrap=True)
        self.problem.setObjectName("error")
        self.facts.setObjectName("detailsfacts")
        for label in (self.help, self.facts, self.problem):
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        inner = QWidget()
        inner.setObjectName("detailsinner")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 6, 8, 6)
        for label in (self.title, self.help, self.facts, self.problem):
            layout.addWidget(label)
        layout.addStretch(1)
        # Long details (a gas with its sources) scroll inside the box instead of squeezing the inputs.
        self.scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        self.setMaximumHeight(DETAILS_MAX_HEIGHT)
        self.name = None
        self.clear()

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(min(DETAILS_MAX_HEIGHT, self.scroll.widget().sizeHint().height() + 4))
        return hint

    def clear(self):
        self.name = None
        self.title.setText("<b>Details</b>")
        self.help.setText(DETAILS_PROMPT)
        self.facts.setText("")
        self.problem.setVisible(False)

    def show_input(self, spec: WidgetSpec, problem=None, value=None, base=None):
        self.name = spec.name
        self.title.setText(f"<b>{spec.label}</b>")
        self.help.setText(spec.help or "No description given in the template.")
        muted = colour("muted")
        rows = "".join(f"<tr><td style='padding-right:10px; color:{muted}'>{label}</td><td>{text}</td></tr>"
                       for label, text in details(spec, value, base))
        self.facts.setText(f"<table>{rows}</table>")
        self.problem.setText(problem or "")
        self.problem.setVisible(bool(problem))


class GasHandler:
    """What a gas input asks of its owner (the main window gives one that knows the project):
        base            the project folder (relative custom-gas paths are read from it), or None
        choose(choice)  a gas of "My gases" was picked: copy it into the project, return the value to store
        new(current)    open the custom-gas form (filled from the current gas): the value to store, or None
    This default (no project) stores the user-library path and cannot make new gases."""

    base = None

    def choose(self, choice):
        return choice.data

    def new(self, current):
        return None


class InputPanel(QWidget):
    """All inputs of a PanelModel, in collapsible groups, with a Details area underneath.
    Emits value_changed(name, value) on user edits.

    file_handler(name, chosen_path) -> value to store: lets the owner copy a chosen file into the
    project folder and store a relative path (default: store the chosen path as it is).
    gas_handler: what a gas input needs from the owner (see GasHandler).
    """

    value_changed = Signal(str, object)

    def __init__(self, model: PanelModel, values: dict, file_handler=None, gas_handler=None, parent=None):
        super().__init__(parent)
        self.model = model
        self._values = dict(values)
        self.file_handler = file_handler or (lambda name, path: path)
        self.gas_handler = gas_handler or GasHandler()
        self.scroll = QScrollArea(widgetResizable=True)
        self.details = DetailsBox()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll, 1)
        outer.addWidget(self.details)
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
        self.scroll.setWidget(content)
        # The panel never scrolls sideways: when it is narrow, the labels wrap instead (see
        # _fit_labels). Everything left and right of the label column (margins, gaps, the widest box):
        grid = next(iter(self.sections.values())).grid if self.sections else None
        side = layout.contentsMargins().left() + layout.contentsMargins().right()
        if grid is not None:
            side += grid.contentsMargins().left() + grid.contentsMargins().right() + max(grid.horizontalSpacing(), 0)
        editor_width = max((row.widgets[1].minimumSizeHint().width() for row in self.rows.values()), default=0)
        self._label_full = max((row.label.fontMetrics().horizontalAdvance(row.label.text())
                                for row in self.rows.values()), default=0) + 2   # longest label on one line
        self._beside_labels = side + max(editor_width, MIN_EDITOR_WIDTH)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # So the dock cannot be made narrower than the narrowest label column + the narrowest box.
        frame = 2 * self.scroll.frameWidth() + self.scroll.verticalScrollBar().sizeHint().width()
        self.scroll.setMinimumWidth(self._beside_labels + MIN_LABEL_WIDTH + frame)
        self.scroll.viewport().installEventFilter(self)       # resizing the panel re-fits the labels
        self._fit_labels()
        self.set_values(self._values)

    def _fit_labels(self):
        """Give all labels one width: the longest label if it fits, else what is left beside the boxes.

        Every group has its own grid, so one width for all labels keeps all input boxes of the panel
        in one column, whatever group they are in. Labels narrower than their text wrap onto more lines.
        """
        room = self.scroll.viewport().width() - self._beside_labels
        label_width = max(MIN_LABEL_WIDTH, min(self._label_full, room))
        for row in self.rows.values():
            if row.label.maximumWidth() != label_width:      # (only on a change: avoids needless re-layouts)
                row.label.setFixedWidth(label_width)

    def eventFilter(self, watched, event):
        """Watches every input widget: a click or keyboard focus shows that input in Details.
        Also watches the visible area of the scroll area: a new width re-fits the labels."""
        if event.type() == QEvent.Resize and watched is self.scroll.viewport():
            self._fit_labels()
        elif event.type() in (QEvent.FocusIn, QEvent.MouseButtonPress):
            name = watched.property(INPUT_PROPERTY)
            if name in self.rows:
                self.show_details(name)
        return False                             # never swallow the event: the widget still gets it

    def restyle(self):
        """After a theme change: the Details text carries colours, so draw it again."""
        if self.details.name in self.rows:
            self.show_details(self.details.name)
        else:
            self.details.clear()

    def show_details(self, name):
        problem = self.model.shown_problems(self._values).get(name)
        self.details.show_input(self.rows[name].spec, problem, self._values.get(name), self.gas_handler.base)

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
        if self.details.name in self.rows:
            self.show_details(self.details.name)
        groups = set(self.model.visible_groups(self._values))
        for group, section in self.sections.items():
            section.setVisible(group in groups)

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Assistant panel of the Setup step: describe the case in words, review the proposed values, apply.

Optional and OFF by default: while the assistant is off this file imports nothing from
aeroflowsim.assistant (tests/test_assistant.py). The assistant can only propose values for inputs of the
template; every proposal is checked against the schema (aeroflowsim/assistant/review.py), shown in a table
with a tick box per row, and applied only when the user presses Apply - as ONE undo step.
This file has no network code: the providers (aeroflowsim/assistant/) do the talking.
"""

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from aeroflowsim.gui.logic import readable
from aeroflowsim.gui.widgets import Banner

EXAMPLE = "e.g.  Mach 2.4 nitrogen over a 10 degree wedge, 5 bar back pressure"
COLUMNS = ["", "Input", "Current", "Proposed", "Unit", "Reason"]


class _Bridge(QObject):
    """Carries the answer of the provider thread back to the GUI thread."""
    done = Signal(object, object)       # proposals, provider notes
    failed = Signal(str)


def read_settings(settings):
    """The saved assistant choices as an AssistantSettings (imports the assistant package: only call when it is on)."""
    from aeroflowsim.assistant.config import AssistantSettings
    return AssistantSettings.from_mapping(lambda name, default=None: settings.value(f"assistant/{name}", default))


def assistant_enabled(settings) -> bool:
    """True if the user turned the assistant on. Reads one saved flag; imports nothing."""
    return settings.value("assistant/enabled", False) in (True, "true", "True", 1, "1")


class AssistantPanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.provider_factory = None            # tests / scripts: callable(name) -> provider, instead of the settings
        self._project = None
        self._proposals, self._text, self._from_model, self._provider_notes = [], "", False, []
        self._bridge = _Bridge()
        self._bridge.done.connect(self._on_done)
        self._bridge.failed.connect(self._on_failed)

        self.toggle = QToolButton()
        self.toggle.setText("Assistant")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setStyleSheet("QToolButton { border: none; font-weight: 600; }")
        self.toggle.toggled.connect(self._set_open)
        self.status = QLabel()
        self.settings_button = QPushButton("Settings...")
        self.settings_button.clicked.connect(window.show_assistant_settings)
        self.banner = Banner()                  # shown for the online provider: the text leaves this computer
        header = QHBoxLayout()
        header.addWidget(self.toggle)
        header.addWidget(self.status, 1)
        header.addWidget(self.settings_button)

        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Describe the case in plain words, " + EXAMPLE)
        self.text.setFixedHeight(56)
        self.provider = QComboBox()
        self.provider.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.provider.setMinimumContentsLength(22)
        self.provider.setToolTip("Rules: keyword parser, no model. Local model: a server on this computer. "
                                 "Online: your own key; the text leaves this computer.")
        self.provider.currentIndexChanged.connect(self._update_status)
        self.propose_button = QPushButton("Propose")
        self.propose_button.setToolTip("Turn the description into proposed input values (nothing changes yet)")
        self.propose_button.clicked.connect(self.propose)
        row = QHBoxLayout()
        row.addWidget(QLabel("Provider"))
        row.addWidget(self.provider)
        row.addWidget(self.propose_button)
        row.addStretch(1)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.Stretch)
        self.table.setMinimumHeight(110)
        self.notes = QPlainTextEdit(readOnly=True)
        self.notes.setMaximumHeight(72)
        self.notes.setVisible(False)                # shown only when there is something to say
        self.apply_button = QPushButton("Apply ticked")
        self.apply_button.setToolTip("Change the ticked inputs as one step (Ctrl+Z undoes all of them)")
        self.apply_button.clicked.connect(self.apply)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        buttons = QHBoxLayout()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.text)
        body.addLayout(row)
        body.addWidget(self.table)
        body.addWidget(self.notes)
        body.addLayout(buttons)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self.banner)
        layout.addWidget(self.body)
        opened = window.settings.value("assistant/panel_open", False) in (True, "true", "True", 1, "1")
        self.toggle.setChecked(opened)
        self._set_open(opened, save=False)
        self.refresh()

    # ---------------------------------------------------------------------------------- state

    def _set_open(self, opened, save=True):
        self.toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)
        self._show_body()
        if save:
            self.window.settings.setValue("assistant/panel_open", bool(opened))

    def _show_body(self):
        """The body (text, table, ...) is shown only when the panel is open AND the assistant is on."""
        self.body.setVisible(self.toggle.isChecked() and assistant_enabled(self.window.settings))

    def refresh(self):
        """Called when the page is shown, the project changes or the Settings change."""
        project = self.window.project
        if project is not self._project:
            self._project = project
            self.clear()
        on = assistant_enabled(self.window.settings)
        self.provider.blockSignals(True)
        self.provider.clear()
        if on:
            settings = read_settings(self.window.settings)
            for name, label, allowed in settings.selectable():
                self.provider.addItem(label, name)
                if not allowed:
                    item = self.provider.model().item(self.provider.count() - 1)
                    item.setEnabled(False)
                    item.setToolTip("Turn it on explicitly in Tools > Assistant settings (it sends your text over the internet).")
            self.provider.setCurrentIndex(max(0, self.provider.findData(settings.provider)))
        self.provider.blockSignals(False)
        for widget in (self.text, self.provider, self.propose_button):
            widget.setEnabled(on and project is not None)
        self.settings_button.setText("Settings..." if on else "Turn on...")
        self._update_status()
        self._show_body()
        self.apply_button.setEnabled(self.table.rowCount() > 0)

    def _provider_name(self) -> str:
        return self.provider.currentData() or "rules"

    def _update_status(self):
        if not assistant_enabled(self.window.settings):
            self.status.setText("Assistant off - it changes nothing until you turn it on")
            self.banner.hide_message()
            return
        if self._provider_name() == "online":
            self.status.setText("Online - text leaves this computer")
            self.banner.show_message("Online provider: the description you type here is sent over the internet to the "
                                     "service you chose in the settings (never project files, geometry or results).",
                                     "warning")
        else:
            self.status.setText("Offline")
            self.banner.hide_message()

    # ---------------------------------------------------------------------------------- propose

    def _context(self):
        from aeroflowsim.assistant.context import SchemaContext
        project = self.window.project
        return SchemaContext(project.case.parameters(), dict(project.values))

    def _make_provider(self):
        if self.provider_factory is not None:
            return self.provider_factory(self._provider_name())
        from aeroflowsim.assistant.config import make_provider
        return make_provider(read_settings(self.window.settings), self._provider_name())

    def propose(self):
        """Slot of Propose: ask the provider (in a thread: a model can take a while), then review the answer."""
        text = self.text.toPlainText().strip()
        if self.window.project is None or not assistant_enabled(self.window.settings):
            return
        if not text:
            self._show_notes(["Type a description of the case first."])
            return
        from aeroflowsim.assistant.proposal import AssistantError
        try:
            provider = self._make_provider()
        except AssistantError as error:
            self._show_notes([str(error)])
            return
        context = self._context()
        self.propose_button.setEnabled(False)
        self.status.setText("Asking the assistant ...")
        self._text, self._from_model = text, provider.from_model

        def work():
            try:
                self._bridge.done.emit(provider.propose(text, context), list(provider.notes))
            except AssistantError as error:
                self._bridge.failed.emit(str(error))
            except Exception as error:               # a provider must never crash the application
                self._bridge.failed.emit(f"The assistant failed: {error}")

        threading.Thread(target=work, daemon=True).start()

    def _on_failed(self, message):
        self.propose_button.setEnabled(self.window.project is not None)
        self._update_status()
        self._show_notes([message])

    def _on_done(self, proposals, provider_notes):
        self.propose_button.setEnabled(self.window.project is not None)
        self._update_status()
        self._proposals, self._provider_notes = list(proposals), list(provider_notes)
        self._fill(self._review())

    def _review(self):
        from aeroflowsim.assistant.review import review_proposals
        return review_proposals(self._context(), self._proposals, from_model=self._from_model, text=self._text)

    # ---------------------------------------------------------------------------------- table

    def _show(self, value, unit):
        if value is None:
            return "", ""
        if isinstance(value, bool):
            return ("yes" if value else "no"), ""
        if isinstance(value, (int, float)):
            return readable(value, unit, 5, units=(), prefs=self.window.units)
        return str(value), ""

    def _fill(self, review):
        self.table.setRowCount(0)
        for r in review.rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked)
            check.setData(Qt.UserRole, r.name)
            old, _ = self._show(r.old, r.unit)
            new, unit = self._show(r.new, r.unit)
            reason = QTableWidgetItem(r.reason)
            reason.setToolTip(r.reason)
            for column, item in enumerate((check, QTableWidgetItem(r.label), QTableWidgetItem(old),
                                           QTableWidgetItem(new), QTableWidgetItem(unit), reason)):
                self.table.setItem(row, column, item)
        lines = [f"Rejected - {x.proposal.field}: {x.message}" for x in review.rejected]
        lines += [f"Already set: {name}" for name in review.unchanged]
        lines += list(self._provider_notes)
        if not review.rows and not lines:
            lines = ["Nothing to propose: the description names no input of this template."]
        self._show_notes(lines)
        self.apply_button.setEnabled(bool(review.rows))

    def _show_notes(self, lines):
        self.notes.setPlainText("\n".join(lines))
        self.notes.setVisible(bool(lines))

    def ticked(self) -> list[str]:
        """Input keys of the ticked rows."""
        return [self.table.item(row, 0).data(Qt.UserRole) for row in range(self.table.rowCount())
                if self.table.item(row, 0).checkState() == Qt.Checked]

    def clear(self):
        self._proposals, self._provider_notes = [], []
        self.table.setRowCount(0)
        self.notes.clear()
        self.notes.setVisible(False)
        self.apply_button.setEnabled(False)

    # ---------------------------------------------------------------------------------- apply

    def apply(self):
        """Apply the ticked rows as ONE undoable step (checked again against the current values first)."""
        if self.window.project is None:
            return
        wanted = set(self.ticked())
        rows = [r for r in self._review().rows if r.name in wanted]
        if not rows:
            self._show_notes(["Nothing ticked."])
            return
        self.window.set_inputs({r.name: r.new for r in rows},
                               "assistant: " + ", ".join(r.label for r in rows[:3]) + (" ..." if len(rows) > 3 else ""))
        self.clear()
        self._show_notes([f"Applied {len(rows)} input(s). Edit > Undo (Ctrl+Z) takes them all back."])

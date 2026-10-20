# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The workflow strip along the bottom of the window: Geometry -> Mesh -> Setup -> Run -> Results.

Each step is a chip coloured by its status (green up to date, amber needs update, grey not
started, red error; see aeroflowsim/project.py for how the status is decided). Clicking a chip
opens that step. While a job runs, its chip turns blue and shows the progress and a small x
button that cancels the job. The strip replaces both a status bar and a step tree.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QToolButton, QWidget

from aeroflowsim.gui.theme import STATUS_COLOURS, STATUS_TEXT
from aeroflowsim.project import WORKFLOW

TITLES = {"geometry": "Geometry", "mesh": "Mesh", "setup": "Setup", "run": "Run", "results": "Results"}
SHORTCUTS = {"geometry": "Ctrl+1", "mesh": "Ctrl+2", "setup": "Ctrl+3", "run": "Ctrl+4", "results": "Ctrl+5"}


class StepChip(QFrame):
    """One step: a round status dot, the title, and (while busy) a progress bar and a cancel button."""

    clicked = Signal(str)
    cancel = Signal()

    def __init__(self, step, parent=None):
        super().__init__(parent)
        self.step = step
        self.status = "none"
        self.current = False
        self.setObjectName("chip")
        self.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 8, 4)
        self.dot = QLabel("●")
        self.title = QPushButton(TITLES[step], flat=True)
        self.title.setCursor(Qt.PointingHandCursor)
        self.title.clicked.connect(lambda: self.clicked.emit(self.step))
        self.progress = QProgressBar(maximumWidth=110, maximumHeight=14, textVisible=True, visible=False)
        self.cancel_button = QToolButton(text="✕", autoRaise=True, visible=False, toolTip="Cancel this job")
        self.cancel_button.clicked.connect(self.cancel.emit)
        for w in (self.dot, self.title, self.progress, self.cancel_button):
            layout.addWidget(w)
        self.set_status("none")

    def mousePressEvent(self, event):
        self.clicked.emit(self.step)

    def set_status(self, status, detail=""):
        self.status = status
        fill, text = STATUS_COLOURS[status]
        self.dot.setStyleSheet(f"color: {fill}; font-size: 16px;")
        tip = f"{TITLES[self.step]}: {STATUS_TEXT[status]}" + (f"\n{detail}" if detail else "")
        self.setToolTip(f"{tip}\n({SHORTCUTS[self.step]})")
        self.title.setEnabled(status != "disabled")
        self._restyle()

    def set_current(self, current):
        self.current = current
        self._restyle()

    def _restyle(self):
        fill, _ = STATUS_COLOURS[self.status]
        border = f"2px solid {fill}" if self.current else "1px solid palette(mid)"
        weight = "bold" if self.current else "normal"
        self.setStyleSheet(f"#chip {{ border: {border}; border-radius: 14px; }}"
                           f"#chip QPushButton {{ font-weight: {weight}; border: none; padding: 0 2px; }}")

    def set_busy(self, fraction=None, text=""):
        """fraction: 0..1, or None for an 'unknown' (moving) bar. Call set_idle() when done."""
        self.dot.setStyleSheet(f"color: {STATUS_COLOURS['busy'][0]}; font-size: 16px;")
        self.progress.setVisible(True)
        self.cancel_button.setVisible(True)
        if fraction is None:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(1000 * min(max(fraction, 0.0), 1.0)))
        self.progress.setFormat(text or "%p%")
        self.progress.setToolTip(text)

    def set_idle(self):
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.set_status(self.status)


class WorkflowStrip(QWidget):
    """All step chips joined by arrows. Signals: step_clicked(step), cancel_requested()."""

    step_clicked = Signal(str)
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 6)
        layout.setSpacing(4)
        self.chips = {}
        for i, step in enumerate(WORKFLOW):
            if i:
                arrow = QLabel("━━▶")
                arrow.setStyleSheet("color: palette(mid);")
                layout.addWidget(arrow)
            chip = StepChip(step)
            chip.clicked.connect(self.step_clicked.emit)
            chip.cancel.connect(self.cancel_requested.emit)
            self.chips[step] = chip
            layout.addWidget(chip)
        layout.addStretch(1)
        self.message = QLabel()
        self.message.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.message)

    def set_statuses(self, statuses: dict, details=None):
        for step, status in statuses.items():
            self.chips[step].set_status(status, (details or {}).get(step, ""))

    def set_current(self, step):
        for name, chip in self.chips.items():
            chip.set_current(name == step)

    def set_busy(self, step, fraction=None, text=""):
        for name, chip in self.chips.items():
            if name == step:
                chip.set_busy(fraction, text)
            else:
                chip.set_idle()

    def set_idle(self):
        for chip in self.chips.values():
            chip.set_idle()

    def show_message(self, text):
        """A short note at the right end of the strip (e.g. 'Saved')."""
        self.message.setText(text)

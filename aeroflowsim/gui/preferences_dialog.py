# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tools > Preferences: settings of this computer that are not part of a project (now: solver CPU threads).

The thread count only changes how fast a run is, never its numbers (aeroflowsim/compute.py, gather face
sums), so it is a preference of the computer, not an input of the project."""

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox, QVBoxLayout

from aeroflowsim import compute

THREADS_KEY = "solver/threads"        # 0 = the default (physical cores minus one)


def threads_setting(settings) -> int:
    """The saved thread count, 0 = default."""
    try:
        return max(0, int(settings.value(THREADS_KEY, 0)))
    except (TypeError, ValueError):
        return 0


class PreferencesDialog(QDialog):
    """threads() -> the chosen thread count (0 = default) after OK."""

    def __init__(self, threads: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        layout = QVBoxLayout(self)
        default = compute.default_threads()
        note = QLabel(f"CPU threads used by the 2D solver. The default is the number of physical cores minus one "
                      f"({default} on this computer), so the window stays responsive. The thread count changes only "
                      "the speed, never the results. A new value applies from the next run.", wordWrap=True)
        note.setObjectName("hint")
        layout.addWidget(note)
        form = QFormLayout()
        self.use_default = QCheckBox(f"Default ({default})")
        self.spin = QSpinBox()
        self.spin.setRange(1, compute.max_threads())
        self.spin.setValue(threads or default)
        self.use_default.setChecked(threads == 0)
        self.spin.setEnabled(threads != 0)
        self.use_default.toggled.connect(lambda on: self.spin.setEnabled(not on))
        form.addRow("Solver threads", self.use_default)
        form.addRow("", self.spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def threads(self) -> int:
        return 0 if self.use_default.isChecked() else int(self.spin.value())

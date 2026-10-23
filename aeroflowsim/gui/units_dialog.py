# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""View > Units: the display unit of each quantity (length, pressure, temperature, mass flow, force,
area, velocity), with presets. Only how numbers are SHOWN and TYPED changes; projects and results stay
SI (aeroflowsim/units.py)."""

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from aeroflowsim.units import PRESETS, QUANTITIES, UnitPreferences


class UnitsDialog(QDialog):
    """preferences() -> the chosen UnitPreferences (after OK)."""

    def __init__(self, prefs: UnitPreferences, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Units")
        layout = QVBoxLayout(self)
        note = QLabel("Choose how numbers are shown and typed. Everything is still stored and computed in SI "
                      "units, so changing a unit never changes a result.", wordWrap=True)
        note.setObjectName("hint")
        layout.addWidget(note)
        presets = QHBoxLayout()
        for name, choices in PRESETS.items():
            button = QPushButton(name.split(" (")[0])
            button.setToolTip(name)
            button.clicked.connect(lambda _=False, c=choices: self.apply(c))
            presets.addWidget(button)
        presets.addStretch(1)
        layout.addLayout(presets)
        form = QFormLayout()
        self.boxes = {}
        for quantity, (_, units) in QUANTITIES.items():
            box = QComboBox()
            box.addItems(list(units))
            box.setCurrentText(prefs.choices[quantity])
            self.boxes[quantity] = box
            form.addRow(quantity.capitalize(), box)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self, choices):
        for quantity, name in choices.items():
            self.boxes[quantity].setCurrentText(name)

    def preferences(self) -> UnitPreferences:
        return UnitPreferences({quantity: box.currentText() for quantity, box in self.boxes.items()})

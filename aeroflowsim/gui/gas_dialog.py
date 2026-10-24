# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The custom-gas form (name, molar mass or R, gamma or cp, viscosity law, Prandtl number) and the
Tools > Gas library window.

All checking and the file text come from gui/gas_logic.py (form_to_toml, tested without a window);
this dialog only shows the fields, the problem of the current values, and OK when they are fine.
The result is saved to the user's own gas library by the caller (main window), and copied into the
project that uses it.
"""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPushButton, QScrollArea, QSplitter, QVBoxLayout)

from aeroflowsim.gases import save_user_gas, user_gas_dir
from aeroflowsim.gui.gas_logic import (HEAT, LAWS, SPECIFY, critical_units, form_from_gas, form_to_toml, gas_choices,
                                       gas_detail_rows)
from aeroflowsim.gui.theme import colour


class CustomGasDialog(QDialog):
    """form() -> the field values; result_toml -> (name, TOML text) after OK."""

    def __init__(self, form, parent=None, prefs=None):
        super().__init__(parent)
        self.prefs = prefs                         # the user's units (critical temperature and pressure)
        self.setWindowTitle("Custom gas")
        self.setMinimumWidth(460)
        self.result_toml = None
        layout = QVBoxLayout(self)
        intro = QLabel("A calorically perfect gas (constant cp and gamma). It is saved in your own gas library "
                       "and copied into this project, so the project stays reproducible.", wordWrap=True)
        intro.setObjectName("hint")
        layout.addWidget(intro)
        grid = QFormLayout()
        self.edits = {}
        self.combos = {}

        def edit(key, label):
            box = QLineEdit(str(form.get(key, "")))
            box.textChanged.connect(self._check)
            self.edits[key] = box
            grid.addRow(label, box)

        def combo(key, options, label):
            box = QComboBox()
            box.addItems(options)
            box.setCurrentText(form.get(key, options[0]))
            box.currentIndexChanged.connect(self._switch)
            self.combos[key] = box
            grid.addRow(label, box)

        edit("name", "Name")
        combo("specify", SPECIFY, "Give")
        edit("molar_mass", "Molar mass [g/mol]")
        edit("R", "Gas constant R [J/(kg K)]")
        combo("heat", HEAT, "Give")
        edit("gamma", "Ratio of specific heats gamma [-]")
        edit("cp", "Specific heat cp [J/(kg K)]")
        combo("law", LAWS, "Viscosity law")
        edit("mu_ref", "Viscosity at T_ref [Pa s]")
        edit("T_ref", "Reference temperature T_ref [K]")
        edit("S", "Sutherland temperature S [K]")
        edit("prandtl", "Prandtl number [-]")
        t_unit, p_unit = critical_units(prefs)
        critical = QLabel("Critical point (optional: needed by the ideal-gas validity check)")
        critical.setObjectName("hint")
        grid.addRow(critical)
        edit("T_c", f"Critical temperature [{t_unit.name}]")
        edit("p_c", f"Critical pressure [{p_unit.name}]")
        edit("omega", "Acentric factor [-]")
        self.grid = grid
        layout.addLayout(grid)
        self.problem = QLabel(wordWrap=True)
        self.problem.setObjectName("error")
        layout.addWidget(self.problem)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._switch()

    def form(self) -> dict:
        values = {key: box.text() for key, box in self.edits.items()}
        values.update({key: box.currentText() for key, box in self.combos.items()})
        return values

    def _switch(self, *_):
        """Show only the fields of the chosen options (molar mass or R, gamma or cp, S or n)."""
        f = self.form()
        shown = {"molar_mass": f["specify"] == SPECIFY[0], "R": f["specify"] == SPECIFY[1],
                 "gamma": f["heat"] == HEAT[0], "cp": f["heat"] == HEAT[1]}
        for key, visible in shown.items():
            self.grid.setRowVisible(self.edits[key], visible)
        self.grid.labelForField(self.edits["S"]).setText(
            "Sutherland temperature S [K]" if f["law"] == LAWS[0] else "Exponent n [-]")
        self._check()

    def _check(self, *_):
        try:
            form_to_toml(self.form(), self.prefs)
            problem = ""
        except ValueError as error:
            problem = str(error)
        self.problem.setText(problem)
        self.problem.setVisible(bool(problem))
        self.buttons.button(QDialogButtonBox.Save).setEnabled(not problem)

    def _save(self):
        self.result_toml = form_to_toml(self.form(), self.prefs)
        self.accept()


class GasLibraryDialog(QDialog):
    """Tools > Gas library: every built-in and custom gas with its values and sources (read-only), and
    "New custom gas..." to add one to the user's own library (no project needed)."""

    def __init__(self, parent=None, prefs=None):
        super().__init__(parent)
        self.prefs = prefs
        self.setWindowTitle("Gas library")
        self.resize(900, 560)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show)
        self.facts = QLabel(wordWrap=True)
        self.facts.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.facts.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll = QScrollArea(widgetResizable=True)
        scroll.setWidget(self.facts)
        split = QSplitter()
        split.addWidget(self.list)
        split.addWidget(scroll)
        split.setSizes([330, 570])
        new = QPushButton("New custom gas...")
        new.clicked.connect(self.new_gas)
        folder = QPushButton("Open my gas folder")
        folder.setToolTip(str(user_gas_dir()))
        folder.clicked.connect(self.open_folder)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        buttons = QHBoxLayout()
        for w in (new, folder):
            buttons.addWidget(w)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(split, 1)
        layout.addLayout(buttons)
        self.fill()

    def fill(self, select=None):
        self.choices = [c for c in gas_choices() if c.kind in ("builtin", "user")]
        self.list.clear()
        for c in self.choices:
            self.list.addItem(c.text)
        index = next((i for i, c in enumerate(self.choices) if c.data == select), 0)
        self.list.setCurrentRow(index)

    def _show(self, row):
        if 0 <= row < len(self.choices):
            muted = colour("muted")
            rows = "".join(f"<tr><td style='padding-right:10px; color:{muted}; vertical-align:top'>{label}</td>"
                           f"<td>{text}</td></tr>" for label, text in gas_detail_rows(self.choices[row].data))
            self.facts.setText(f"<table>{rows}</table>")

    def new_gas(self):
        row = self.list.currentRow()
        dialog = CustomGasDialog(form_from_gas(self.choices[row].data if row >= 0 else "N2", prefs=self.prefs), self,
                                 self.prefs)
        if dialog.exec() and dialog.result_toml:
            name, text = dialog.result_toml
            path = save_user_gas(text, name)
            self.fill(select=str(path))

    def open_folder(self):
        folder = user_gas_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

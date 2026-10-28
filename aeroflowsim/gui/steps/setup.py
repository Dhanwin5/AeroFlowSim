# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Setup step: the physics inputs (in the Inputs panel), derived numbers, and the template's README."""

from pathlib import Path

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget

from aeroflowsim.case import get_derived
from aeroflowsim.gui.assistant_panel import AssistantPanel
from aeroflowsim.gui.logic import readable
from aeroflowsim.gui.widgets import Banner, ValueTable


class SetupPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.banner = Banner()
        self.assistant = AssistantPanel(window)      # optional, off by default; collapsed
        self.derived = ValueTable(["Derived quantity", "Value", "Unit"])
        reset = QPushButton("Reset all inputs to defaults")
        reset.setToolTip("Every input of every step back to the template's default (Ctrl+Z undoes it).")
        reset.clicked.connect(window.reset_inputs)
        self.readme = QTextBrowser(openExternalLinks=False)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("<b>Derived from the inputs</b> (read-only)"))
        left_layout.addWidget(self.derived, 1)
        row = QHBoxLayout()
        row.addWidget(reset)
        row.addStretch(1)
        left_layout.addLayout(row)
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.readme)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.banner)
        layout.addWidget(self.assistant)
        layout.addWidget(splitter, 1)

    def refresh(self):
        self.assistant.refresh()
        project = self.window.project
        if project is None:
            return
        case = project.case
        self.title.setText(f"<h3>{case.title}</h3>{case.description}")
        readme = Path(case.folder) / "README.md"
        self.readme.setMarkdown(readme.read_text(encoding="utf-8") if readme.is_file() else "")
        problems = project.problems()
        if problems:
            names = {p.name: p.label for p in case.parameters()}
            self.banner.show_message("Inputs to fix: " + "; ".join(f"{names[k]}" for k in problems), "error")
            self.derived.set_rows([])
            return
        self.banner.hide_message()
        try:
            derived = get_derived(case, project.params())
        except ValueError as error:
            self.banner.show_message(str(error), "error")
            derived = {}
        self.derived.set_rows([(label, *readable(value, unit, 5, prefs=self.window.units))
                               for label, (value, unit) in derived.items()])

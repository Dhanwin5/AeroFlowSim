# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The start page (no project open): new project from a template, open, example projects, recent projects."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

from aeroflowsim.gui.app_info import LOGO
from aeroflowsim.project import old_settings_files


class WelcomePage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        logo = QLabel()
        logo.setPixmap(QPixmap(str(LOGO)).scaledToWidth(520, Qt.SmoothTransformation))
        new = QPushButton("New project...")
        new.setToolTip("Choose a template, a name and a place (the template highlighted below is preselected)")
        new.clicked.connect(lambda: window.new_project(self.selected_template()))
        open_ = QPushButton("Open project...")
        open_.clicked.connect(lambda: window.open_project())
        self.import_old = QPushButton("Import old settings...")
        self.import_old.clicked.connect(window.import_old_settings)
        buttons = QHBoxLayout()
        for b in (new, open_, self.import_old):
            buttons.addWidget(b)
        buttons.addStretch(1)
        self.templates = QListWidget()
        self.templates.setObjectName("templates")
        self.templates.setWordWrap(True)        # long descriptions wrap instead of being cut off
        self.templates.setToolTip("Double-click (or Enter) to create a project from a template right away")
        # Double-click or Enter ("activated") creates a project from the template at once.
        self.templates.itemActivated.connect(lambda item: window.create_from_template(item.data(Qt.UserRole)))
        self.recent = QListWidget()
        self.recent.setObjectName("recent")
        self.recent.setWordWrap(True)
        self.recent.itemActivated.connect(lambda item: window.open_project(item.data(Qt.UserRole)))
        self.examples = QListWidget()
        self.examples.setObjectName("examples")
        self.examples.setWordWrap(True)
        self.examples.setToolTip("Double-click to open a copy of the example (saved in your projects folder)")
        self.examples.itemActivated.connect(lambda item: window.open_example(item.data(Qt.UserRole)))
        lists = QHBoxLayout()
        for title, widget in (("Start from a template (double-click)", self.templates),
                              ("Example projects (double-click)", self.examples),
                              ("Recent projects (double-click)", self.recent)):
            column = QVBoxLayout()
            column.addWidget(QLabel(f"<b>{title}</b>"))
            column.addWidget(widget)
            lists.addLayout(column)
        layout = QVBoxLayout(self)
        layout.addWidget(logo)
        layout.addWidget(QLabel("Free, open-source CFD for nozzle aerodynamics and propulsion."))
        layout.addLayout(buttons)
        layout.addLayout(lists, 1)

    def selected_template(self):
        """Key of the highlighted template, or None."""
        item = self.templates.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def refresh(self):
        previous = self.selected_template()
        self.templates.clear()
        for name, case in self.window.templates().items():
            item = QListWidgetItem(f"{case.title}\n    {case.description}")
            item.setData(Qt.UserRole, name)
            item.setToolTip(case.description)
            self.templates.addItem(item)
            if name == previous:
                self.templates.setCurrentItem(item)
        self.examples.clear()
        from aeroflowsim.examples import list_examples
        for folder, title in list_examples():
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, str(folder))
            self.examples.addItem(item)
        self.recent.clear()
        for path in self.window.recent_projects():
            folder = Path(path)
            item = QListWidgetItem(f"{folder.stem}\n    {folder.parent}")   # name first, then where it is
            item.setToolTip(path)
            item.setData(Qt.UserRole, path)
            self.recent.addItem(item)
        self.import_old.setVisible(bool(old_settings_files()))

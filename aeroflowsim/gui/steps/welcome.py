# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The start page (no project open): new project from a template, open, recent projects."""

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
        new.clicked.connect(lambda: window.new_project())
        open_ = QPushButton("Open project...")
        open_.clicked.connect(lambda: window.open_project())
        self.import_old = QPushButton("Import old settings...")
        self.import_old.clicked.connect(window.import_old_settings)
        buttons = QHBoxLayout()
        for b in (new, open_, self.import_old):
            buttons.addWidget(b)
        buttons.addStretch(1)
        self.templates = QListWidget()
        self.templates.itemActivated.connect(lambda item: window.new_project(item.data(Qt.UserRole)))
        self.recent = QListWidget()
        self.recent.itemActivated.connect(lambda item: window.open_project(item.data(Qt.UserRole)))
        lists = QHBoxLayout()
        for title, widget in (("Start from a template (double-click)", self.templates),
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

    def refresh(self):
        self.templates.clear()
        for name, case in self.window.templates().items():
            item = QListWidgetItem(f"{case.title}\n    {case.description}")
            item.setData(Qt.UserRole, name)
            item.setToolTip(case.description)
            self.templates.addItem(item)
        self.recent.clear()
        for path in self.window.recent_projects():
            item = QListWidgetItem(path)
            item.setData(Qt.UserRole, path)
            self.recent.addItem(item)
        self.import_old.setVisible(bool(old_settings_files()))

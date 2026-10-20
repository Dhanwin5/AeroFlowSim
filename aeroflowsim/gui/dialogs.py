# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Dialog windows: New project (template, name, location) and the project-name question of Save as."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from aeroflowsim.project import default_projects_dir, folder_for


class ProjectPlaceDialog(QDialog):
    """Ask for a project name and the folder it goes in; result: folder (…/<name>.afsproj)."""

    def __init__(self, title, name="", parent=None, templates=None, template=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 480 if templates else 160)
        self.templates = None
        layout = QVBoxLayout(self)
        if templates:
            layout.addWidget(QLabel("<b>Template</b> (the physics; you can change every input later)"))
            self.templates = QListWidget()
            self.templates.setWordWrap(True)
            for key, case in templates.items():
                item = QListWidgetItem(f"{case.title}\n    {case.description}")
                item.setData(Qt.UserRole, key)
                self.templates.addItem(item)
                if key == template:
                    self.templates.setCurrentItem(item)
            if self.templates.currentItem() is None:
                self.templates.setCurrentRow(0)
            self.templates.currentItemChanged.connect(self._template_changed)
            layout.addWidget(self.templates, 1)
        form = QFormLayout()
        self.name = QLineEdit(name or (self._suggested_name() if templates else ""))
        self.location = QLineEdit(str(default_projects_dir()))
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.location, 1)
        row.addWidget(browse)
        place = QWidget()
        place.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        form.addRow("Project name", self.name)
        form.addRow("Location", place)
        layout.addLayout(form)
        self.message = QLabel()
        self.message.setObjectName("error")
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.folder = None

    def _suggested_name(self):
        item = self.templates.currentItem() if self.templates else None
        return f"My {item.text().splitlines()[0]}" if item else "My project"

    def _template_changed(self, *_):
        self.name.setText(self._suggested_name())

    def template(self):
        return self.templates.currentItem().data(Qt.UserRole) if self.templates else None

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Where should the project folder go?", self.location.text())
        if folder:
            self.location.setText(folder)

    def _accept(self):
        try:
            folder = folder_for(self.name.text(), Path(self.location.text()))
        except ValueError as error:
            self.message.setText(str(error))
            return
        if folder.exists():
            self.message.setText(f"{folder.name} already exists in that location; choose another name.")
            return
        self.folder = folder
        self.accept()

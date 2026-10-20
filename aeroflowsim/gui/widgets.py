# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Small widgets shared by the step pages."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QLabel, QListWidget, QListWidgetItem, QTableWidget,
                               QTableWidgetItem)

from aeroflowsim.gui.theme import CHECK_COLOURS, CHECK_ICONS

BANNER_STYLES = {
    "info": "background: #e3f2fd; color: #0d47a1; border: 1px solid #90caf9;",
    "warning": "background: #fff8e1; color: #5d4037; border: 1px solid #f9a825;",
    "error": "background: #ffebee; color: #b71c1c; border: 1px solid #ef9a9a;",
}


class Banner(QLabel):
    """A coloured message bar (e.g. 'These results come from older inputs'). Hidden when empty."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setVisible(False)

    def show_message(self, text, level="info"):
        self.setText(text)
        self.setStyleSheet(f"QLabel {{ {BANNER_STYLES[level]} border-radius: 4px; padding: 6px 10px; }}")
        self.setVisible(bool(text))

    def hide_message(self):
        self.setText("")
        self.setVisible(False)


class ValueTable(QTableWidget):
    """A read-only table of rows (e.g. quantity, value, unit)."""

    def __init__(self, headers, parent=None):
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setAlternatingRowColors(True)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.verticalHeader().setDefaultSectionSize(22)

    def set_rows(self, rows):
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                if c > 0:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.setItem(r, c, item)

    def rows(self):
        return [tuple(self.item(r, c).text() for c in range(self.columnCount())) for r in range(self.rowCount())]


class CheckList(QListWidget):
    """Validity checks, one coloured line each, under optional section headings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.NoSelection)

    def set_sections(self, sections):
        """sections: [(heading, [CheckResult])]."""
        self.clear()
        for heading, checks in sections:
            item = QListWidgetItem(heading)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            self.addItem(item)
            if not checks:
                self.addItem(QListWidgetItem("    No checks apply."))
            for check in checks:
                line = QListWidgetItem(f"{CHECK_ICONS[check.level]}  {check.name}: {check.message}")
                line.setForeground(QColor(CHECK_COLOURS[check.level]))
                line.setToolTip(f"{check.level}: {check.message}")
                self.addItem(line)
        if not sections:
            self.addItem(QListWidgetItem("No checks yet: generate a mesh or run the case."))

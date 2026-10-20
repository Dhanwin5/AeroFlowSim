# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Small widgets shared by the step pages."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout, QHeaderView, QLabel, QListWidget,
                               QListWidgetItem, QTableWidget, QTableWidgetItem, QVBoxLayout)

from aeroflowsim.gui.theme import CHECK_ICONS, check_colour, colour, repolish



class Banner(QLabel):
    """A coloured message bar (e.g. 'These results come from older inputs'). Hidden when empty."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("banner")             # colours come from the theme, by the "level" property
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setVisible(False)

    def show_message(self, text, level="info"):
        self.setText(text)
        self.setProperty("level", level)
        repolish(self)
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
                line.setForeground(QColor(check_colour(check.level)))
                line.setToolTip(f"{check.level}: {check.message}")
                self.addItem(line)
        if not sections:
            self.addItem(QListWidgetItem("No checks yet: generate a mesh or run the case."))


class SummaryCard(QFrame):
    """The key-results card at the top of the Results step: a status line and one tile per number."""

    COLUMNS = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.status = QLabel()
        self.status.setWordWrap(True)
        self._content = ("", [])
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.addWidget(self.status)
        layout.addLayout(self.grid)
        self.tiles = []
        self.set_outdated(False)

    def set_results(self, status_text, tiles):
        """tiles: [(title, value text, unit)]."""
        self._content = (status_text, tiles)
        self.status.setText(f"<b>Key results</b> &nbsp;·&nbsp; {status_text}")
        for tile in self.tiles:                   # hide and detach at once (see PlotCanvas.set_figure)
            self.grid.removeWidget(tile)
            tile.hide()
            tile.setParent(None)
            tile.deleteLater()
        self.tiles = []
        muted = colour("muted")
        for i, (title, value, unit) in enumerate(tiles):
            tile = QLabel(f"<div style='font-size:18pt; font-weight:600'>{value}"
                          f"<span style='font-size:10pt; font-weight:normal'>&nbsp;{unit}</span></div>"
                          f"<div style='color:{muted}'>{title}</div>")
            tile.setObjectName("tile")
            tile.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.grid.addWidget(tile, i // self.COLUMNS, i % self.COLUMNS)
            self.tiles.append(tile)

    def set_outdated(self, outdated):
        """Amber border and a note when the results come from older inputs."""
        self.setProperty("outdated", bool(outdated))
        repolish(self)
        self.setToolTip("These results come from older inputs: run again to update them." if outdated else "")

    def restyle(self):
        """Redraw the tiles after a theme change (their caption colour is part of their text)."""
        self.set_results(*self._content)

    def tile_texts(self):
        """Plain text of every tile (for tests)."""
        return [tile.text() for tile in self.tiles]

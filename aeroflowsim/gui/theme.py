# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Light and dark theme: Qt's Fusion style with its light or dark colour scheme, plus matching
colours for the VTK view and the workflow strip. Plots stay white ("paper" look) in both themes,
so exported pictures look the same as the command line's."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

STATUS_COLOURS = {          # workflow-strip chip colours: (fill, text)
    "ok": ("#2e7d32", "white"),        # green: up to date
    "outdated": ("#f9a825", "black"),  # amber: needs update
    "none": ("#9e9e9e", "white"),      # grey: not started
    "error": ("#c62828", "white"),     # red: error
    "disabled": ("#d6d6d6", "#8a8a8a"),
    "busy": ("#1565c0", "white"),      # blue: a job is running for this step
}
STATUS_TEXT = {"ok": "up to date", "outdated": "needs update", "none": "not started", "error": "error",
               "disabled": "not available for this template", "busy": "working"}
PATCH_COLOURS = {"wall": "#d62728", "inlet": "#1f77b4", "outlet": "#2ca02c", "axis": "#9467bd",
                 "farfield": "#17becf", "symmetry": "#ff7f0e"}
CHECK_ICONS = {"info": "✔", "warning": "⚠", "error": "✖"}
CHECK_COLOURS = {"info": "#2e7d32", "warning": "#b26a00", "error": "#c62828"}


def apply_theme(dark: bool):
    app = QApplication.instance()
    app.setStyle("Fusion")
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)


def view_colours(dark: bool) -> dict:
    """Colours of the VTK view for the theme."""
    if dark:
        return {"background": "#202124", "text": "white", "edges": "#5f6368", "outline": "#e8eaed"}
    return {"background": "white", "text": "black", "edges": "#3c4043", "outline": "#202124"}

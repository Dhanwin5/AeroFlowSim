# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Light and dark theme for the whole GUI.

One place decides every colour:
  - Qt widgets: Fusion style with Qt's light/dark colour scheme, plus ONE application-wide style
    sheet built from the colour tokens below (stylesheet()). Widgets never set their own colours;
    they get an objectName (e.g. "chip", "details") or a property (e.g. level="warning") and the
    sheet styles them. Switching theme = installing the other sheet, so every widget restyles at
    once with readable contrast.
  - matplotlib plots in the window: mpl_rc(dark) (backgrounds, text, ticks, legend). Pictures
    that are SAVED always use the light "paper" style (paper_style()), like the command line's.
  - the VTK view: view_colours(dark).
"""

from contextlib import contextmanager

import matplotlib
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

# Colour tokens. Contrast of text on its background is at least 4.5:1 (WCAG AA) in both themes.
TOKENS = {
    False: {   # light
        "text": "#1f1f1f", "muted": "#5f6368", "border": "#c4c7c5", "base": "#ffffff", "panel": "#f3f5f7",
        "error": "#c62828", "ok": "#2e7d32", "warning": "#8a5300",
        "info_bg": "#e3f2fd", "info_fg": "#0d47a1", "info_border": "#90caf9",
        "warn_bg": "#fff8e1", "warn_fg": "#5d4037", "warn_border": "#f9a825",
        "err_bg": "#ffebee", "err_fg": "#b71c1c", "err_border": "#ef9a9a",
        "plot_bg": "#ffffff", "plot_text": "#1f1f1f",
    },
    True: {    # dark
        "text": "#e8eaed", "muted": "#a8adb3", "border": "#5f6368", "base": "#28292c", "panel": "#303134",
        "error": "#f28b82", "ok": "#81c995", "warning": "#fdd663",
        "info_bg": "#1d2f45", "info_fg": "#a8c7fa", "info_border": "#3b6ea5",
        "warn_bg": "#3a3220", "warn_fg": "#fdd663", "warn_border": "#b38600",
        "err_bg": "#3c1f1f", "err_fg": "#f6aea9", "err_border": "#8c3a3a",
        "plot_bg": "#28292c", "plot_text": "#e8eaed",
    },
}

STATUS_COLOURS = {          # workflow-strip status dots (the same in both themes, all readable on both)
    "ok": "#34a853", "outdated": "#f9ab00", "none": "#9aa0a6", "error": "#ea4335", "disabled": "#9aa0a6",
    "busy": "#4285f4",
}
STATUS_TEXT = {"ok": "up to date", "outdated": "needs update", "none": "not started", "error": "error",
               "disabled": "not available for this template", "busy": "working"}
PATCH_COLOURS = {"wall": "#d62728", "inlet": "#1f77b4", "outlet": "#2ca02c", "axis": "#9467bd",
                 "farfield": "#17becf", "symmetry": "#ff7f0e"}
CHECK_ICONS = {"info": "✔", "warning": "⚠", "error": "✖"}

_state = {"dark": False}


def is_dark() -> bool:
    return _state["dark"]


def colour(name, dark=None) -> str:
    """A colour token of the current (or given) theme, e.g. colour('error')."""
    return TOKENS[is_dark() if dark is None else dark][name]


def check_colour(level) -> str:
    """Text colour of a validity check of this level ('info', 'warning', 'error')."""
    return colour({"info": "ok", "warning": "warning", "error": "error"}[level])


def stylesheet(dark: bool) -> str:
    """The application-wide style sheet of a theme."""
    t = TOKENS[dark]
    chips = "".join(f'#chip[status="{s}"] #dot {{ color: {c}; }}\n' for s, c in STATUS_COLOURS.items())
    return f"""
QToolButton#section {{ border: none; font-weight: bold; color: {t['text']}; padding: 2px 0; }}
QLabel#hint {{ color: {t['muted']}; font-size: 90%; }}
QLabel#error {{ color: {t['error']}; }}
QFrame#details {{ background: {t['base']}; border: 1px solid {t['border']}; border-radius: 4px; }}
QFrame#details QLabel {{ color: {t['text']}; background: transparent; border: none; }}
QFrame#details QLabel#detailsfacts {{ color: {t['text']}; }}
QFrame#details QLabel#error {{ color: {t['error']}; }}
QLabel#banner {{ border-radius: 4px; padding: 6px 10px; }}
QLabel#banner[level="info"] {{ background: {t['info_bg']}; color: {t['info_fg']}; border: 1px solid {t['info_border']}; }}
QLabel#banner[level="warning"] {{ background: {t['warn_bg']}; color: {t['warn_fg']}; border: 1px solid {t['warn_border']}; }}
QLabel#banner[level="error"] {{ background: {t['err_bg']}; color: {t['err_fg']}; border: 1px solid {t['err_border']}; }}
QFrame#chip {{ border: 1px solid {t['border']}; border-radius: 14px; background: {t['base']}; }}
QFrame#chip[current="true"] {{ border: 2px solid {t['text']}; }}
QFrame#chip QPushButton {{ border: none; padding: 0 2px; color: {t['text']}; background: transparent; }}
QFrame#chip[current="true"] QPushButton {{ font-weight: bold; }}
QFrame#chip QPushButton:disabled {{ color: {t['muted']}; }}
QFrame#chip QLabel#dot {{ font-size: 16px; }}
{chips}QFrame#chip[busy="true"] #dot {{ color: {STATUS_COLOURS['busy']}; }}
QLabel#arrow, QLabel#stripmessage {{ color: {t['muted']}; }}
QFrame#card {{ border: 2px solid {t['border']}; border-radius: 8px; }}
QFrame#card[outdated="true"] {{ border: 2px solid {t['warn_border']}; }}
QFrame#card QLabel {{ color: {t['text']}; }}
QLabel#tile {{ background: {t['base']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 6px 10px; }}
QLabel#note {{ color: {t['warning']}; }}
QLineEdit {{ background: {t['base']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 3px;
             padding: 2px 4px; }}
QLineEdit:focus {{ border: 1px solid {STATUS_COLOURS['busy']}; }}
QLineEdit:disabled {{ color: {t['muted']}; }}
QListWidget#templates::item, QListWidget#recent::item {{ padding: 6px 4px; border-bottom: 1px solid {t['border']}; }}
QListWidget#templates::item:selected, QListWidget#recent::item:selected {{
    background: {t['info_bg']}; color: {t['info_fg']}; }}
QTableWidget {{ alternate-background-color: {t['panel']}; background: {t['base']}; color: {t['text']}; }}
"""


def repolish(widget):
    """Re-apply the style sheet after a dynamic property (e.g. status) changed."""
    for w in [widget, *widget.findChildren(QWidget)]:
        w.style().unpolish(w)
        w.style().polish(w)


def mpl_rc(dark: bool) -> dict:
    """matplotlib settings for plots shown in the window."""
    t = TOKENS[dark]
    return {"figure.facecolor": t["plot_bg"], "axes.facecolor": t["plot_bg"], "savefig.facecolor": t["plot_bg"],
            "text.color": t["plot_text"], "axes.labelcolor": t["plot_text"], "axes.titlecolor": t["plot_text"],
            "xtick.color": t["plot_text"], "ytick.color": t["plot_text"], "axes.edgecolor": t["muted"],
            "legend.facecolor": t["base"], "legend.edgecolor": t["border"], "legend.labelcolor": t["plot_text"]}


@contextmanager
def paper_style():
    """Use the light plot style inside this block (for pictures that are saved to files)."""
    with matplotlib.rc_context(mpl_rc(False)):
        yield


def apply_theme(dark: bool):
    """Switch the whole application to the light or dark theme."""
    _state["dark"] = dark
    app = QApplication.instance()
    app.setStyle("Fusion")
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    app.setStyleSheet(stylesheet(dark))
    matplotlib.rcParams.update(mpl_rc(dark))


def view_colours(dark: bool) -> dict:
    """Colours of the VTK view for the theme."""
    if dark:
        return {"background": "#202124", "text": "white", "edges": "#5f6368", "outline": "#e8eaed"}
    return {"background": "white", "text": "black", "edges": "#3c4043", "outline": "#202124"}

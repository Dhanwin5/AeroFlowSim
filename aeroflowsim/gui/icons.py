# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""AeroFlowSim's own icon set: simple line drawings on a 24 x 24 grid, coloured for the theme.

Each icon is a few SVG shapes (paths, lines, circles) written below. INK is replaced by the
theme's text colour and ACCENT by a blue, so one drawing works in light and dark themes.
The drawings are made for AeroFlowSim (not copied from any other program) and kept here as text,
so there are no image files to install. icon(name) returns a QIcon; unknown names give an empty icon.
"""

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from aeroflowsim.gui.theme import colour, is_dark

ACCENT = {False: "#1a73e8", True: "#8ab4f8"}
SIZES = (16, 24, 32, 48)

# name: SVG shapes; "INK" = text colour, "ACCENT" = blue. Stroke width 1.6 unless set.
DRAWINGS = {
    # ---- main tool bar ----
    "new": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M12 11v6M9 14h6" stroke="ACCENT"/>',
    "open": '<path d="M3 7h6l2 2h10v10H3z"/><path d="M3 11h18" stroke="ACCENT"/>',
    "save": '<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4"/><rect x="8" y="13" width="8" height="5" stroke="ACCENT"/>',
    "undo": '<path d="M9 7L4 11l5 4"/><path d="M4 11h10a5 5 0 0 1 0 10h-3"/>',
    "redo": '<path d="M15 7l5 4-5 4"/><path d="M20 11H10a5 5 0 0 0 0 10h3"/>',
    "mesh": '<path d="M4 20L12 4l8 16z"/><path d="M8 12h8M12 20l-4-8M12 20l4-8M6 16h12" stroke="ACCENT"/>',
    "run": '<path d="M7 4l12 8-12 8z" fill="ACCENT" stroke="ACCENT"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" fill="INK"/>',
    "fit": '<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/><rect x="8" y="9" width="8" height="6" stroke="ACCENT"/>',
    "theme": '<circle cx="12" cy="12" r="7"/><path d="M12 5a7 7 0 0 1 0 14z" fill="INK"/>',
    # ---- workspace modes and tools ----
    "select": '<path d="M6 3l11 9-5 1 3 6-2 1-3-6-4 4z" fill="ACCENT" stroke="INK"/>',
    "move": '<path d="M12 3v18M3 12h18"/><path d="M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3" stroke="ACCENT"/>',
    "points": '<path d="M4 18L10 8l5 6 5-9"/><circle cx="4" cy="18" r="1.8" fill="ACCENT" stroke="ACCENT"/>'
              '<circle cx="10" cy="8" r="1.8" fill="ACCENT" stroke="ACCENT"/><circle cx="15" cy="14" r="1.8" '
              'fill="ACCENT" stroke="ACCENT"/><circle cx="20" cy="5" r="1.8" fill="ACCENT" stroke="ACCENT"/>',
    "import": '<path d="M5 14v6h14v-6"/><path d="M12 3v11M8 10l4 4 4-4" stroke="ACCENT"/>',
    "export": '<path d="M5 14v6h14v-6"/><path d="M12 14V3M8 7l4-4 4 4" stroke="ACCENT"/>',
    "table": '<rect x="4" y="4" width="16" height="16"/><path d="M4 9h16M4 14h16M12 4v16"/>',
    "sketch": '<path d="M4 20l3-1 11-11-2-2L5 17z"/><path d="M14 6l2 2" stroke="ACCENT"/><path d="M15 20h5" stroke="ACCENT"/>',
    "line": '<path d="M5 19L19 5"/><circle cx="5" cy="19" r="1.8" fill="ACCENT" stroke="ACCENT"/>'
            '<circle cx="19" cy="5" r="1.8" fill="ACCENT" stroke="ACCENT"/>',
    "polyline": '<path d="M4 18l5-9 6 6 5-10"/>',
    "arc3": '<path d="M4 18a10 10 0 0 1 16 0"/><circle cx="4" cy="18" r="1.6" fill="ACCENT" stroke="ACCENT"/>'
            '<circle cx="12" cy="10" r="1.6" fill="ACCENT" stroke="ACCENT"/><circle cx="20" cy="18" r="1.6" '
            'fill="ACCENT" stroke="ACCENT"/>',
    "arc": '<path d="M19 12a7 7 0 0 1-7 7"/><path d="M12 12h7M12 12v7" stroke="ACCENT" stroke-dasharray="2 2"/>'
           '<circle cx="12" cy="12" r="1.6" fill="ACCENT" stroke="ACCENT"/>',
    "tangent_arc": '<path d="M3 17h8a6 6 0 0 0 6-6V5"/><path d="M3 17h8" stroke="ACCENT"/>',
    "spline": '<path d="M3 17c4-12 8 8 12-2s4-6 6-6"/>',
    "rectangle": '<rect x="4" y="6" width="16" height="12"/>',
    "rectangle3": '<path d="M4 15l9-9 7 7-9 9z"/>',
    "circle": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="1.4" fill="ACCENT" stroke="ACCENT"/>',
    "construction": '<path d="M3 21L21 3" stroke-dasharray="3 2"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13 7l4 4" stroke="ACCENT"/>',
    "transform": '<rect x="4" y="10" width="10" height="10"/><path d="M10 4h10v10" stroke="ACCENT" '
                 'stroke-dasharray="2 2"/><path d="M14 10l4-4" stroke="ACCENT"/>',
    "fillet": '<path d="M5 4v8a8 8 0 0 0 8 8h7"/><path d="M5 12a8 8 0 0 0 8 8" stroke="ACCENT"/>',
    "chamfer": '<path d="M5 4v9l7 7h8"/><path d="M5 13l7 7" stroke="ACCENT"/>',
    "delete": '<path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13"/>',
    "role": '<rect x="3" y="5" width="18" height="14"/><circle cx="12" cy="12" r="3.5" fill="INK"/>'
            '<path d="M3 9h3M3 15h3M18 9h3M18 15h3" stroke="ACCENT"/>',
    "boolean": '<circle cx="9" cy="12" r="6"/><circle cx="15" cy="12" r="6" stroke="ACCENT"/>',
    "split": '<rect x="4" y="4" width="16" height="16"/><path d="M8 21L16 3" stroke="ACCENT"/>',
    "split_edge": '<path d="M3 12h18"/><path d="M12 7v10" stroke="ACCENT"/>',
    "trim": '<path d="M3 12h18M12 3v18"/><path d="M14 12h7" stroke="ACCENT" stroke-dasharray="2 2"/>'
            '<path d="M16 7l4 10M20 7l-4 10" stroke="ACCENT"/>',
    "extend": '<path d="M3 12h10M19 4v16"/><path d="M13 12h6" stroke="ACCENT" stroke-dasharray="2 2"/>',
    "offset": '<path d="M4 18c3-8 7-8 16-12"/><path d="M4 13c2-6 6-6 13-10" stroke="ACCENT"/>',
    "pattern": '<rect x="3" y="9" width="5" height="5"/><rect x="10" y="9" width="5" height="5" stroke="ACCENT"/>'
               '<rect x="17" y="9" width="5" height="5" stroke="ACCENT"/>',
    "fill": '<path d="M5 18L9 6l10 4-3 9z" fill="ACCENT" fill-opacity="0.35"/>',
    "merge": '<rect x="3" y="7" width="9" height="10"/><rect x="12" y="7" width="9" height="10"/>'
             '<path d="M12 7v10" stroke="ACCENT" stroke-dasharray="2 2"/>',
    "enclosure": '<rect x="2.5" y="4" width="19" height="16" rx="2"/><path d="M7 12c3-3 7-3 10 0-3 2-7 2-10 0z" '
                 'fill="ACCENT" stroke="ACCENT"/>',
    "name": '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.6" fill="ACCENT" stroke="ACCENT"/>',
    "refinement": '<rect x="4" y="4" width="16" height="16" stroke-dasharray="3 2"/><path d="M8 8h8v8H8zM12 8v8M8 12h8" '
                  'stroke="ACCENT" stroke-width="1.2"/>',
    "axisymmetric": '<path d="M3 18h18" stroke="ACCENT" stroke-dasharray="3 2"/><path d="M5 18V9c4-4 10-4 14 0v9"/>',
    "suggestions": '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c1 1 1 2 1 3h6c0-1 0-2 1-3A6 6 0 0 0 12 3z" '
                   'stroke="ACCENT"/>',
    "more": '<circle cx="5" cy="12" r="1.6" fill="INK"/><circle cx="12" cy="12" r="1.6" fill="INK"/>'
            '<circle cx="19" cy="12" r="1.6" fill="INK"/>',
    "revert": '<path d="M4 4v6h6"/><path d="M5 10a8 8 0 1 1 1 6"/>',
    "constrain": '<path d="M4 20h16M4 20V6"/><path d="M4 20L18 6" stroke="ACCENT"/><path d="M4 15a5 5 0 0 1 5 5" '
                 'stroke="ACCENT"/>',
    "dimension": '<path d="M4 6v12M20 6v12"/><path d="M4 12h16M7 9l-3 3 3 3M17 9l3 3-3 3" stroke="ACCENT"/>',
    "measure": '<path d="M3 17L17 3l4 4L7 21z"/><path d="M7 13l2 2M10 10l2 2M13 7l2 2" stroke="ACCENT"/>',
    "grid": '<path d="M4 4v16M10 4v16M16 4v16M4 4h16M4 10h16M4 16h16" stroke-width="1"/>'
            '<path d="M20 4v16M4 20h16" stroke-width="1"/>',
    "view3d": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" stroke="ACCENT"/>',
    "revolve": '<ellipse cx="12" cy="12" rx="9" ry="4"/><path d="M3 12h18" stroke="ACCENT" stroke-dasharray="3 2"/>'
               '<path d="M12 6v-3l3 1.5" stroke="ACCENT"/>',
}


def _svg(name, dark) -> str:
    ink, accent = colour("text", dark), ACCENT[dark]
    body = DRAWINGS[name].replace("INK", ink).replace("ACCENT", accent)
    # No xmlns attribute: Qt draws the SVG without it, and the GUI must contain no web addresses.
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="' + ink +
            '" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' + body + "</svg>")


@lru_cache(maxsize=None)
def _icon(name, dark) -> QIcon:
    if name not in DRAWINGS:
        return QIcon()
    renderer = QSvgRenderer(QByteArray(_svg(name, dark).encode()))
    result = QIcon()
    for size in SIZES:
        image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        result.addPixmap(QPixmap.fromImage(image))
    return result


def icon(name, dark=None) -> QIcon:
    """The icon `name` in the colours of the current (or given) theme."""
    return _icon(name, is_dark() if dark is None else dark)

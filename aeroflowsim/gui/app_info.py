# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Where the GUI finds its pictures and documents, and what the About box says (all local files)."""

from pathlib import Path

from aeroflowsim import __version__
from aeroflowsim.discovery import PROJECT_DIR

ASSETS = PROJECT_DIR / "assets"
LOGO = ASSETS / "logo.png"
ICON = ASSETS / "icon.png"
DOCS = PROJECT_DIR / "docs"
THEORY_MANUAL = DOCS / "theory_manual.md"
DEVELOPER_GUIDE = DOCS / "developer_guide.md"
VALIDATION_REPORT = PROJECT_DIR / "validation" / "report.md"
VALIDATION_SCRIPT = PROJECT_DIR / "validation" / "run_all.py"

ORGANISATION = "AeroFlowSim"
APPLICATION = "AeroFlowSim"


def about_html() -> str:
    """Text of Help > About: version, licence, how to cite."""
    return (f"<h2>AeroFlowSim {__version__}</h2>"
            "<p>A GUI-first, open-source CFD solver for nozzle and propulsion aerodynamics, with built-in "
            "validity checks and published validation.</p>"
            "<p>Copyright © 2026 Dhanwin Mehta.<br>Licence: <b>GPL-3.0-or-later</b> (see the LICENSE file). "
            "You may use, study, share and improve this software; improved versions you share must stay free.</p>"
            "<p><b>How to cite:</b> Mehta, D. <i>AeroFlowSim</i>, version "
            f"{__version__}, 2026. (Full details in CITATION.cff.)</p>"
            "<p>The desktop GUI uses Qt (PySide6, LGPL) and VTK / PyVista (BSD/MIT).<br>"
            "AeroFlowSim makes no network connections and collects no usage statistics.</p>")


def local_path(path: Path) -> Path | None:
    return path if path.is_file() else None

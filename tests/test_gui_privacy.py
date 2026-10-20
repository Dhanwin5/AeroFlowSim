# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Privacy of the desktop GUI (CLAUDE.md rule 12): no network access and no usage statistics.

The GUI code may not use any networking module, may not contain web addresses, and may only open
LOCAL files with the system viewer (QUrl.fromLocalFile). (The old Streamlit GUI is covered by
tests/test_streamlit_config.py.)
"""

import re
from pathlib import Path

GUI_DIR = Path(__file__).resolve().parent.parent / "aeroflowsim" / "gui"
NETWORK = re.compile(r"^\s*(import|from)\s+(socket|ssl|http|urllib|requests|httpx|aiohttp|ftplib|smtplib|"
                     r"PySide6\.QtNetwork|PySide6\.QtWebEngine\w*|PySide6\.QtWebSockets)\b", re.MULTILINE)
QT_NETWORK = re.compile(r"QtNetwork|QtWebEngine|QNetworkAccessManager|QWebEngineView")
WEB_ADDRESS = re.compile(r"https?://|www\.")
REMOTE_URL = re.compile(r"openUrl\((?!QUrl\.fromLocalFile)")


def _gui_files():
    return sorted(p for p in GUI_DIR.rglob("*.py") if p.name != "streamlit_panel.py")


def test_gui_has_no_network_code():
    offenders = []
    for path in _gui_files():
        text = path.read_text(encoding="utf-8")
        for pattern in (NETWORK, QT_NETWORK, WEB_ADDRESS, REMOTE_URL):
            if pattern.search(text):
                offenders.append(f"{path.name}: {pattern.pattern[:40]}")
    assert not offenders, offenders


def test_the_desktop_gui_files_are_checked():
    names = {p.name for p in _gui_files()}
    assert {"main_window.py", "app.py", "panel.py", "vtk_view.py"} <= names

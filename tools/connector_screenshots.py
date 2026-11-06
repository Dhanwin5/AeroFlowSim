# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Screenshots of Tools > Use with AI assistants in the light and the dark theme (docs/screenshots/connector/).

Uses a temporary settings file, so the real connector settings of this computer are not touched.

    .venv\\Scripts\\python.exe tools/connector_screenshots.py
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    folder = Path(tempfile.mkdtemp())
    os.environ["AEROFLOWSIM_CONNECTOR_SETTINGS"] = str(folder / "connector.json")
    from PySide6.QtWidgets import QApplication

    from aeroflowsim.gui.connector_page import ConnectorDialog
    from aeroflowsim.gui.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    out = ROOT / "docs" / "screenshots" / "connector"
    out.mkdir(parents=True, exist_ok=True)
    for dark in (False, True):
        apply_theme(dark)
        dialog = ConnectorDialog()
        dialog.allow.setChecked(True)
        dialog.result.setText("The server works: 25 tools (list_templates, describe_template, list_gases, ...).")
        dialog.resize(760, 640)
        dialog.show()
        app.processEvents()
        path = out / f"connector_{'dark' if dark else 'light'}.png"
        dialog.grab().save(str(path))
        dialog.close()
        print(path)


if __name__ == "__main__":
    main()

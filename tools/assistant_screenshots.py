# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Screenshots of the Assistant panel (Setup step) in the light and the dark theme.

    python tools/assistant_screenshots.py            writes docs/screenshots/assistant/*.png

Shows: the assistant off (default), and on with a reviewed proposal (rules provider, nothing contacted).
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEXT = "Helium, 300 bar chamber pressure, 5 bar back pressure, throat diameter 2 mm, 350 K"


def main():
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from aeroflowsim.gui.main_window import MainWindow
    from aeroflowsim.project import Project

    app = QApplication.instance() or QApplication([])
    out = ROOT / "docs" / "screenshots" / "assistant"
    out.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp())
    window = MainWindow(QSettings(str(folder / "s.ini"), QSettings.IniFormat))
    window.resize(1500, 900)
    window.show()
    window.load_project(Project.create("quasi1d_nozzle", folder / "Shot.afsproj"))
    window.go_to("setup")
    panel = window.pages["setup"].assistant
    panel.toggle.setChecked(True)
    for dark in (False, True):
        theme = "dark" if dark else "light"
        window.settings.setValue("assistant/enabled", False)
        panel.refresh()
        panel.clear()
        window.set_dark(dark, save=False)
        app.processEvents()
        window.grab().save(str(out / f"assistant_off_{theme}.png"))
        window.settings.setValue("assistant/enabled", True)
        panel.refresh()
        panel.text.setPlainText(TEXT)
        panel.propose()
        for _ in range(200):                      # wait for the provider thread (a few ms for the rules provider)
            app.processEvents()
            if panel.table.rowCount():
                break
        app.processEvents()
        window.grab().save(str(out / f"assistant_review_{theme}.png"))
        window.settings.setValue("assistant/online_opt_in", True)
        window.settings.setValue("assistant/provider", "online")
        panel.refresh()
        app.processEvents()
        window.grab().save(str(out / f"assistant_online_{theme}.png"))
        window.settings.setValue("assistant/provider", "rules")
        window.settings.setValue("assistant/online_opt_in", False)
    window.runner.shutdown()
    print("Screenshots in", out)


if __name__ == "__main__":
    main()

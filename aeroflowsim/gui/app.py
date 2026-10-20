# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Start the desktop GUI:  python -m aeroflowsim gui  [project folder]

Creates the Qt application (one per program), shows the splash screen with the logo, applies the
remembered theme, opens the main window and hands control to Qt's event loop: from then on Qt
waits for clicks and key presses and calls the connected functions (slots).
"""

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from aeroflowsim.gui import app_info
from aeroflowsim.gui.main_window import MainWindow, make_settings
from aeroflowsim.gui.theme import apply_theme


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(app_info.APPLICATION)
    app.setOrganizationName(app_info.ORGANISATION)
    app.setWindowIcon(QIcon(str(app_info.ICON)))
    settings = make_settings()
    apply_theme(settings.value("theme", "light") == "dark")
    splash = QSplashScreen(QPixmap(str(app_info.LOGO)).scaledToWidth(560, Qt.SmoothTransformation))
    splash.show()
    splash.showMessage("Starting AeroFlowSim ...", Qt.AlignBottom | Qt.AlignHCenter)
    app.processEvents()
    window = MainWindow(settings)
    window.show()
    splash.finish(window)
    project = next((a for a in argv[1:] if not a.startswith("-") and a != "gui"), None)
    if project:
        QTimer.singleShot(0, lambda: window.open_project(project))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

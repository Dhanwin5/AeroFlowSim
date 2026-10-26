# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Start the desktop GUI:  python -m aeroflowsim gui  [project folder]

Creates the Qt application (one per program), shows the splash screen with the logo, applies the
remembered theme, opens the main window and hands control to Qt's event loop: from then on Qt
waits for clicks and key presses and calls the connected functions (slots).
"""

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from aeroflowsim.gui import app_info
from aeroflowsim.gui.main_window import MainWindow, make_settings
from aeroflowsim.gui.theme import apply_theme


def _install_error_dialog():
    """Unexpected errors go to the log file and a dialog with 'Copy details' instead of closing the program."""
    import logging
    import traceback
    from PySide6.QtWidgets import QMessageBox
    from aeroflowsim.diagnostics import anonymise, start_logging
    start_logging()
    log = logging.getLogger("aeroflowsim")

    def hook(kind, value, tb):
        text = "".join(traceback.format_exception(kind, value, tb))
        log.error("Unexpected error:\n%s", text)
        box = QMessageBox(QMessageBox.Critical, "Unexpected error",
                          f"Something went wrong: {value}\n\nYour project is not affected unless you were saving it. "
                          "Please report this with Help > Copy diagnostic info.")
        box.setDetailedText(anonymise(text))
        copy = box.addButton("Copy details", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is copy:
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(anonymise(text))
    sys.excepthook = hook


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
    _install_error_dialog()
    window = MainWindow(settings)
    window.show()
    splash.finish(window)
    project = next((a for a in argv[1:] if not a.startswith("-") and a != "gui"), None)
    if project:
        QTimer.singleShot(0, lambda: window.open_project(project))
    quit_after = os.environ.get("AEROFLOWSIM_QUIT_AFTER_MS")    # smoke test of the installed program
    if quit_after:
        QTimer.singleShot(int(quit_after), window.close)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Screenshots of every GUI page, in the light and the dark theme, at a chosen display scaling.

    python tools/screenshots.py                          the N2 nozzle example (made and run if needed)
    python tools/screenshots.py --project "path/My.afsproj" --scale 1.5 --theme dark
    python tools/screenshots.py --template external_2d   a NACA 0012 C-domain-free quick external case

Pictures go to docs/screenshots/<project>/<page>_<theme>_<scale>.png (or --out). The window is grabbed from the
screen, so the VTK views (OpenGL) appear as they are drawn. Used to look at every page after a GUI change
(Post-processing and alpha release stage quality gate: light and dark, 100 % and 150 % scaling).
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PAGES = ["geometry", "mesh", "setup", "run", "results"]
RESULT_TABS = ["Display", "Surfaces", "Reports", "XY plot", "Snapshots", "Fields"]


def make_example(template, folder):
    """A small example project with a result (made and solved here)."""
    from aeroflowsim.project import Project, run_project
    if (folder / "project.yaml").is_file():
        project = Project.open(folder)
    elif template == "nozzle_axi":
        project = Project.create("nozzle_axi", folder, {"mesh_preset": "Coarse"})
    else:
        project = Project.create("external_2d", folder, {"shape": "NACA 4-digit airfoil", "mach": 0.8, "alpha": 1.25,
                                                         "surface_size": 0.01, "farfield_size": 2.0,
                                                         "max_iter": 4000})
    if project.load_results() is None:
        print(f"Solving {folder.name} ...", flush=True)
        run_project(project)
    return project.folder


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=None)
    parser.add_argument("--template", default="nozzle_axi", choices=("nozzle_axi", "external_2d"))
    parser.add_argument("--scale", type=float, default=1.0, help="display scaling (1.0, 1.25, 1.5)")
    parser.add_argument("--theme", default="both", choices=("light", "dark", "both"))
    parser.add_argument("--out", default=None)
    parser.add_argument("--setup", default=None, help="python file with a function setup(window) run before grabbing")
    args = parser.parse_args(argv)
    os.environ["QT_SCALE_FACTOR"] = f"{args.scale:g}"
    folder = Path(args.project) if args.project else ROOT / "docs" / "screenshots" / "_projects" / (
        "N2 nozzle.afsproj" if args.template == "nozzle_axi" else "NACA 0012.afsproj")
    folder = make_example(args.template, folder) if not args.project else folder

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox
    from aeroflowsim.gui.main_window import MainWindow
    from aeroflowsim.project import Project
    app = QApplication.instance() or QApplication(["aeroflowsim"])
    for name in ("question", "information", "warning"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Yes))
    settings = QSettings(str(Path(tempfile.mkdtemp()) / "s.ini"), QSettings.IniFormat)
    w = MainWindow(settings)
    w.resize(1600, 1000)
    w.show()
    w.load_project(Project.open(folder))
    out = Path(args.out) if args.out else ROOT / "docs" / "screenshots" / folder.stem.replace(" ", "_")
    out.mkdir(parents=True, exist_ok=True)
    if args.setup:
        namespace = {}
        exec(Path(args.setup).read_text(encoding="utf-8"), namespace)      # developer tool: a local script
        namespace["setup"](w)

    def settle(ms=1500):
        from PySide6.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def grab(name):
        """Render the window's widgets, then paste every visible VTK view's own picture on top (OpenGL views are
        not part of QWidget.grab)."""
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QImage, QPainter
        from pyvistaqt import QtInteractor
        settle()
        shot = w.grab()
        painter = QPainter(shot)
        ratio = shot.devicePixelRatio()
        for view in w.findChildren(QtInteractor):
            if not view.isVisible() or view.width() < 10:
                continue
            image = view.screenshot(return_img=True)
            h, wd = image.shape[:2]
            qimg = QImage(image.copy().data, wd, h, 3 * wd, QImage.Format_RGB888).copy()
            qimg.setDevicePixelRatio(ratio)
            top_left = view.mapTo(w, QPoint(0, 0))
            painter.drawImage(top_left, qimg.scaled(int(view.width() * ratio), int(view.height() * ratio)))
        painter.end()
        path = out / f"{name}_{theme}_{int(round(args.scale * 100))}.png"
        shot.save(str(path))
        print(path)

    themes = ["light", "dark"] if args.theme == "both" else [args.theme]
    for theme in themes:
        w.set_dark(theme == "dark", save=False)
        for page in PAGES:
            w.go_to(page)
            grab(page)
        if w.pages["results"].post_area.isVisible():
            tabs = w.pages["results"].post_tabs
            for i, tab in enumerate(RESULT_TABS):
                tabs.setCurrentIndex(i)
                grab("results_" + tab.lower().replace(" ", "_"))
    w.runner.shutdown()
    w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

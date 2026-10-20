# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The solver side must never depend on the GUI: only app.py and aeroflowsim/gui/ may import a GUI
library (streamlit, Qt / PySide6, PyVista, VTK).

This keeps every case runnable from the command line and from scripts, and lets the GUI be
swapped or improved without touching any solver.
"""

import subprocess
import sys
from pathlib import Path

import re

import aeroflowsim

PROJECT_DIR = Path(__file__).resolve().parent.parent
GUI_LIBRARIES = ("streamlit", "PySide6", "pyvistaqt", "pyvista", "vtk", "vtkmodules", "qtpy")
IMPORTS_GUI = re.compile(r"^\s*(import|from)\s+(" + "|".join(GUI_LIBRARIES) + r")\b", re.MULTILINE)


def test_only_the_gui_layer_imports_gui_libraries():
    folders = [PROJECT_DIR / "aeroflowsim", PROJECT_DIR / "cases", PROJECT_DIR / "validation"]
    gui = PROJECT_DIR / "aeroflowsim" / "gui"
    offenders = []
    for folder in folders:
        for path in folder.rglob("*.py"):
            if gui in path.parents:
                continue
            match = IMPORTS_GUI.search(path.read_text(encoding="utf-8"))
            if match:
                offenders.append(f"{path.relative_to(PROJECT_DIR)} ({match.group(2)})")
    assert not offenders, f"GUI library imported outside the GUI layer: {offenders}"


def test_command_line_and_projects_work_without_qt():
    """Import everything outside aeroflowsim/gui/ with Qt and PyVista made unimportable."""
    code = (
        "import sys\n"
        "for name in ('PySide6', 'pyvista', 'pyvistaqt', 'vtk', 'vtkmodules'):\n"
        "    sys.modules[name] = None\n"
        "import aeroflowsim, aeroflowsim.cli, aeroflowsim.project, aeroflowsim.tasks, aeroflowsim.result_io\n"
        "import aeroflowsim.geometry_preview, aeroflowsim.gui.panel_model, aeroflowsim.gui.logic\n"
        "print('ok')\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=PROJECT_DIR)
    assert out.stdout.strip() == "ok", out.stderr


def test_version_is_the_same_everywhere():
    pyproject = (PROJECT_DIR / "pyproject.toml").read_text(encoding="utf-8")
    citation = (PROJECT_DIR / "CITATION.cff").read_text(encoding="utf-8")
    assert f'version = "{aeroflowsim.__version__}"' in pyproject
    assert f"version: {aeroflowsim.__version__}" in citation

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The solver side must never depend on the GUI: only app.py and aeroflowsim/gui/ may import streamlit.

This keeps every case runnable from the command line, and lets the GUI be swapped later
(e.g. for a Qt desktop GUI) without touching any solver.
"""

import re
from pathlib import Path

import aeroflowsim

PROJECT_DIR = Path(__file__).resolve().parent.parent
IMPORTS_STREAMLIT = re.compile(r"^\s*(import|from)\s+streamlit\b", re.MULTILINE)


def test_only_the_gui_layer_imports_streamlit():
    folders = [PROJECT_DIR / "aeroflowsim", PROJECT_DIR / "cases", PROJECT_DIR / "validation"]
    gui = PROJECT_DIR / "aeroflowsim" / "gui"
    offenders = []
    for folder in folders:
        for path in folder.rglob("*.py"):
            if gui in path.parents:
                continue
            if IMPORTS_STREAMLIT.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(PROJECT_DIR)))
    assert not offenders, f"streamlit imported outside the GUI layer: {offenders}"


def test_version_is_the_same_everywhere():
    pyproject = (PROJECT_DIR / "pyproject.toml").read_text(encoding="utf-8")
    citation = (PROJECT_DIR / "CITATION.cff").read_text(encoding="utf-8")
    assert f'version = "{aeroflowsim.__version__}"' in pyproject
    assert f"version: {aeroflowsim.__version__}" in citation

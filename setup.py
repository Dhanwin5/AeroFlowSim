# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Data files of a pip install (everything else is in pyproject.toml).

The templates (cases/), example projects (examples/), icons (assets/), user documentation and validation report live
next to the aeroflowsim package in the source folder. A wheel installs them to <prefix>/share/aeroflowsim/, where
aeroflowsim/discovery.py finds them (DATA_DIR). Generated files (meshes, caches, saved Streamlit settings) are left out.
"""

import os
from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).resolve().parent
TARGET = "share/aeroflowsim"
SKIP_DIRS = {"__pycache__", "mesh", "settings", "uploads", ".pytest_cache"}


def tree(folder):
    """[(install folder, [files])] for every folder below ROOT/folder (skipping generated files)."""
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT / folder):
        rel = Path(dirpath).relative_to(ROOT)
        # cases/<name>/mesh and settings are generated; an example project's own mesh/ is kept (it is its data)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS or (rel.parts[0] == "examples" and d == "mesh")]
        files = [str(Path(dirpath, f).relative_to(ROOT)).replace("\\", "/") for f in filenames
                 if not f.endswith((".pyc", ".pyo"))]
        if files:
            out.append((f"{TARGET}/{rel.as_posix()}", files))
    return out


def data_files():
    out = tree("cases") + tree("examples") + tree("assets") + tree("docs/tutorials")
    out.append((f"{TARGET}/docs", [f"docs/{f.name}" for f in sorted((ROOT / "docs").glob("*.md"))]))
    out.append((f"{TARGET}/validation", ["validation/report.md"]))
    out.append((TARGET, [f for f in ("LICENSE", "README.md", "CITATION.cff") if (ROOT / f).is_file()]))
    return out


setup(data_files=data_files())

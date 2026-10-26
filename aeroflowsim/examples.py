# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Example projects shipped with AeroFlowSim (folder examples/, made by tools/make_examples.py).

The start page lists them; opening one copies it into the user's projects folder first (a new name if that copy
exists already), so the shipped example is never changed.
"""

import shutil
from pathlib import Path

from aeroflowsim.discovery import PROJECT_DIR

EXAMPLES_DIR = PROJECT_DIR / "examples"
TITLES = {"N2 nozzle": "N2 nozzle (2D axisymmetric, with its result)",
          "NACA 0012 transonic": "NACA 0012, Mach 0.8, alpha 1.25 deg",
          "Mach 2 wedge": "Mach 2 flow over a 10 deg wedge",
          "Sod shock tube": "Sod shock tube (1D, exact solution)"}


def list_examples():
    """[(folder, title)] of the example projects that are present."""
    if not EXAMPLES_DIR.is_dir():
        return []
    out = []
    for folder in sorted(EXAMPLES_DIR.glob("*.afsproj")):
        out.append((folder, TITLES.get(folder.stem, folder.stem)))
    return out


def copy_example(folder, target_parent=None) -> Path:
    """Copy an example project into the projects folder; returns the copy."""
    from aeroflowsim.project import default_projects_dir
    folder = Path(folder)
    parent = Path(target_parent) if target_parent else default_projects_dir()
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / folder.name
    k = 2
    while target.exists():
        target = parent / f"{folder.stem} ({k}){folder.suffix}"
        k += 1
    shutil.copytree(folder, target)
    return target

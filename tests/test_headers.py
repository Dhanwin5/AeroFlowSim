# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every Python file must start with the AeroFlowSim licence header (GPL-3.0-or-later)."""

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
HEADER = ("# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion\n"
          "# Copyright (C) 2026 Dhanwin Mehta\n"
          "# SPDX-License-Identifier: GPL-3.0-or-later\n")
SKIP = {".venv", "venv", ".git", "results", "build", "dist", "__pycache__", "uploads"}


def python_files():
    """All .py files of the project, outside virtual environments, caches and output folders."""
    for path in PROJECT_DIR.rglob("*.py"):
        if not SKIP.intersection(path.relative_to(PROJECT_DIR).parts):
            yield path


def test_every_python_file_has_the_licence_header():
    missing = [str(p.relative_to(PROJECT_DIR)) for p in python_files()
               if not p.read_text(encoding="utf-8").replace("\r\n", "\n").startswith(HEADER)]
    assert not missing, f"Files without the licence header: {missing}"

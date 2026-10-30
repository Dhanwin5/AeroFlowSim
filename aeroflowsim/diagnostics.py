# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Diagnostic information for bug reports and the log file (no personal data, no network).

diagnostic_text() lists the AeroFlowSim version, the operating system, Python and package versions, the display
scaling (given by the GUI) and the last lines of the log file. User names in paths are replaced by "<user>".
The log file is <app data>/AeroFlowSim/aeroflowsim.log (Windows: %APPDATA%), at most about 1 MB (rotated).
"""

import logging
import logging.handlers
import os
import platform
import sys
from importlib import metadata
from pathlib import Path

from aeroflowsim import __version__

PACKAGES = ("numpy", "numba", "scipy", "matplotlib", "PySide6-Essentials", "vtk", "pyvista", "pyvistaqt", "gmsh", "ezdxf",
            "pyyaml")


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "AeroFlowSim"


def log_path() -> Path:
    return app_data_dir() / "aeroflowsim.log"


def start_logging() -> Path:
    """Send log records (and unexpected errors) to the rotating log file."""
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("aeroflowsim")
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    return path


def anonymise(text) -> str:
    """Replace the user's home folder and user name in a text."""
    home = str(Path.home())
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    text = str(text).replace(home, "<home>").replace(home.replace("\\", "/"), "<home>")
    if len(user) > 2:
        text = text.replace(user, "<user>")
    return text


def diagnostic_text(scaling=None, log_lines=40) -> str:
    lines = [f"AeroFlowSim {__version__}",
             f"Operating system: {platform.system()} {platform.release()} ({platform.version()}), {platform.machine()}",
             f"Python {sys.version.split()[0]} ({'installed program' if getattr(sys, 'frozen', False) else 'source'})"]
    from aeroflowsim import compute
    lines.append(f"CPU: {compute.physical_cores()} physical cores, {compute.max_threads()} logical; solver threads "
                 f"{compute.threads()} (default {compute.default_threads()})")
    if scaling is not None:
        lines.append(f"Display scaling: {100 * scaling:.0f} %")
    for name in PACKAGES:
        try:
            lines.append(f"{name} {metadata.version(name)}")
        except metadata.PackageNotFoundError:
            lines.append(f"{name}: not installed")
    path = log_path()
    if path.is_file():
        tail = path.read_text(encoding="utf-8", errors="replace").splitlines()[-log_lines:]
        lines += ["", f"Last {len(tail)} log lines:"] + tail
    return anonymise("\n".join(lines))

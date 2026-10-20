# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Settings for the GUI tests (skipped if Qt is not installed).

The VTK view needs OpenGL, which Qt's "offscreen" platform does not have (the render window would
be 0 x 0 pixels). So the tests use the normal platform: on Windows and macOS the test windows
appear briefly; on Linux they need a display (GitHub Actions starts a virtual one, Xvfb). Only
without any display does Qt fall back to "offscreen", and the tests that need a rendered view skip.
"""

import os
import sys

import pytest

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


def needs_rendering(view):
    """Skip a test that clicks in the VTK view when there is no OpenGL (offscreen platform)."""
    if view.plotter.ren_win.GetSize()[0] == 0:
        pytest.skip("No OpenGL display available for the VTK view.")

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Settings for the GUI tests: no window on screen (Qt "offscreen"), skipped if Qt is not installed."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # must be set before the QApplication exists
pytest.importorskip("PySide6")

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The light per-push CI set (marker "smoke", a few minutes): 2D Sod and wedge (quick meshes) against their
references, an MMS-lite order check on 32 x 32 / 16 x 16 quads, plus tests/test_kernels.py and the free-stream /
well-balanced tests of tests/test_euler_core.py (selected in .github/workflows/tests.yml)."""

import os

import numpy as np
import pytest

from validation.common import Comparison, _module, read_references

pytestmark = pytest.mark.smoke
VALIDATION = os.path.join(os.path.dirname(__file__), "..", "validation")


@pytest.mark.parametrize("name", ["euler2d_sod", "euler2d_wedge"])
def test_quick_validation_case(name, monkeypatch):
    monkeypatch.setenv("AEROFLOWSIM_VALIDATION_SET", "quick")
    if name == "euler2d_wedge":
        pytest.importorskip("gmsh")
    from pathlib import Path
    folder = Path(VALIDATION) / name
    _header, references = read_references(folder)
    measured = _module(folder).measure()
    failed = [r.quantity for r in references if not Comparison(r, float(measured[r.id])).passed]
    assert not failed


def test_mms_lite_second_order():
    from aeroflowsim.mms import observed_orders, run_level
    runs = [run_level("triangles", n, residual_drop=8.0) for n in (16, 32)]
    order = observed_orders(runs)[0]
    assert np.all(order > 1.8), order

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The GUI path (RunJob in a background thread) and the script path (aeroflowsim.run_case) must
give IDENTICAL results, because both go through the same engine function."""

import numpy as np
import pytest

import aeroflowsim
from aeroflowsim.discovery import load_case
from aeroflowsim.job import RunJob
from aeroflowsim.parameters import defaults, validate


def gui_path(name, changes):
    """Run like the GUI does: validated Setup values, mesh from the Mesh tab, RunJob thread."""
    case = load_case(name)
    params = validate(case.parameters(), {**defaults(case.parameters()), **changes})
    job = RunJob()
    job.start(case, params, case.build_mesh(params))
    job.wait(timeout=300)
    assert job.status == "finished", job.error
    return job


def assert_identical(job, out):
    assert job.result.iterations == out.result.iterations
    assert job.result.key_numbers == out.result.key_numbers
    for key, f in out.result.fields.items():
        assert np.array_equal(job.result.fields[key].values, f.values), key
    assert [c.as_dict() for c in job.checks] == [c.as_dict() for c in out.checks]


@pytest.mark.parametrize("name, changes", [("demo_heat1d", {}), ("sod_shock_tube", {"n_cells": 200})])
def test_gui_and_script_give_identical_results(name, changes):
    assert_identical(gui_path(name, changes), aeroflowsim.run_case(f"cases/{name}", changes))


@pytest.mark.validation
def test_nozzle_gui_and_script_give_identical_results():
    assert_identical(gui_path("quasi1d_nozzle", {}), aeroflowsim.run_case("cases/quasi1d_nozzle"))

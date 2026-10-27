# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for imported_mesh (start from an existing mesh): the example file loads, the boundary map is applied and reported,
wrong input gives a clear message, and a short run keeps a uniform supersonic stream uniform."""

import numpy as np
import pytest

import aeroflowsim
from aeroflowsim.checks import run_mesh_checks
from aeroflowsim.discovery import load_case
from aeroflowsim.parameters import defaults

case = load_case("imported_mesh")
DEFAULTS = defaults(case.parameters())


def params(**changes):
    return {**DEFAULTS, **changes}


def test_example_mesh_loads_with_the_boundary_map_and_passes_the_mesh_checks():
    mesh = case.build_mesh(DEFAULTS)
    assert mesh.n_cells == 18 == case.estimated_cells(DEFAULTS)
    assert {p.name: p.type for p in mesh.patches} == {"left": "inlet", "right": "outlet", "bottom": "symmetry", "top": "wall"}
    assert mesh.cell_volumes.sum() == pytest.approx(0.04 * 0.02)
    assert all(c.level != "error" for c in run_mesh_checks(case, DEFAULTS, mesh))


def test_derived_numbers_list_the_boundary_names_and_types():
    numbers = case.derived(DEFAULTS)
    assert numbers["Boundary 'top'"][0].startswith("wall") and numbers["File format"][0] == "Gmsh"
    assert "x 0 to 40" in numbers["Size in the file's unit"][0]
    assert "NOT SET" in case.derived(params(boundary_map=""))["Boundary 'left'"][0]


def test_wrong_inputs_give_clear_messages():
    with pytest.raises(ValueError, match="Choose a boundary type"):
        case.build_mesh(params(boundary_map=""))
    with pytest.raises(ValueError, match="not found"):
        case.build_mesh(params(mesh_file="nowhere.msh"))
    with pytest.raises(ValueError, match="not a boundary type"):
        case.build_mesh(params(boundary_map="left: floor"))


def test_uniform_supersonic_stream_through_the_example_stays_uniform():
    """Inflow at the free stream, supersonic outflow, a symmetry floor and a slip ceiling: the exact solution is uniform."""
    out = aeroflowsim.run_case(case, params(max_iter=200))
    assert np.allclose(out.result.fields["p"].values, 101325.0, rtol=1e-9)
    assert out.result.key_numbers["Cd"][0] == pytest.approx(0.0, abs=1e-9)

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for external_2d (body in a free stream): the shape inputs are added automatically, the domain
geometry is exact, the default mesh passes every check, and short solver runs give sensible forces.
Mesh tests need Gmsh and are skipped without it."""

import math

import pytest

import aeroflowsim
from aeroflowsim.checks import run_mesh_checks
from aeroflowsim.discovery import load_case
from aeroflowsim.mesh import DEPTH_2D
from aeroflowsim.parameters import defaults

case = load_case("external_2d")
DEFAULTS = defaults(case.parameters())


def params(**changes):
    return {**DEFAULTS, **changes}


def test_shape_dropdown_and_shape_inputs_come_from_the_shape_library():
    names = [p.name for p in case.parameters()]
    assert names[0] == "shape" and "naca4.digits" in names and "domain_shape" in names
    assert case.requires == ["gmsh"] and case.has_solver


def test_derived_numbers_show_reference_values_without_gmsh():
    numbers = case.derived(params(shape="Conical nose cone"))
    assert numbers["Reference area"][0] == pytest.approx(math.pi * math.tan(math.radians(15.0)) ** 2)
    assert case.estimated_cells(DEFAULTS) > 1000


def test_default_mesh_passes_every_mesh_check():
    pytest.importorskip("gmsh")
    mesh = case.build_mesh(DEFAULTS)
    checks = run_mesh_checks(case, DEFAULTS, mesh)
    assert all(c.level == "info" for c in checks), [c.message for c in checks]
    assert {c.name for c in checks} >= {"Smallest angle", "Skewness"}


def test_cylinder_wall_length_and_domain_area_are_exact():
    pytest.importorskip("gmsh")
    mesh = case.build_mesh(params(shape="Circular cylinder"))
    wall = mesh.face_areas[mesh.patch("wall").faces].sum() / DEPTH_2D          # [m]
    assert wall == pytest.approx(math.pi * 1.0, rel=1e-4)
    exact = math.pi * (20.0**2 - 0.5**2)                                       # circle minus cylinder [m²]
    assert mesh.cell_volumes.sum() / DEPTH_2D == pytest.approx(exact, rel=1e-3)


def test_symmetric_body_at_zero_incidence_has_no_lift_and_positive_drag():
    """A short run (supersonic diamond, half domain): drag from the wave pressure, no lift by symmetry."""
    pytest.importorskip("gmsh")
    out = aeroflowsim.run_case(case, params(shape="Diamond airfoil", half_domain=True, domain_shape="Rectangle",
                                            upstream=1.0, downstream=2.0, height=3.0, surface_size=0.05,
                                            farfield_size=0.5, max_iter=150))
    k = out.result.key_numbers
    assert k["Cd"][0] > 0.0 and k["Cl"][0] == 0.0 and k["Cm"][0] == 0.0
    assert out.result.info["boundaries"]["farfield"]["type"] == "far_field"
    assert "wall_Cp" in out.result.series

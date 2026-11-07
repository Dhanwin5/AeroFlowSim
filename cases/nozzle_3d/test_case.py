# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the 3D nozzle template: discovery, the geometry (quarter / full, exact nozzle volume), the plume region as a
second cell zone, and short runs (mass flow near the 1D choked value, the two thrusts agree, the plume region's exit
numbers equal the plain nozzle's)."""

import math

import numpy as np
import pytest

pytest.importorskip("gmsh")

from aeroflowsim.discovery import load_case  # noqa: E402
from aeroflowsim.geometry_model import template_document  # noqa: E402
from aeroflowsim.parameters import defaults, validate  # noqa: E402

CASE = load_case("cases/nozzle_3d")


def params(**values):
    return validate(CASE.parameters(), {**defaults(CASE.parameters()), **values})


def _volume_of_revolution(wall):
    """Exact volume of the conical nozzle: int pi r(x)^2 dx of the piecewise-linear wall (cones: frusta)."""
    x, r = np.asarray(wall.x), np.asarray(wall.r)
    return float(np.sum(math.pi * np.diff(x) * (r[:-1] ** 2 + r[:-1] * r[1:] + r[1:] ** 2) / 3.0))


def test_template_is_found_with_the_3d_solver_defaults():
    assert CASE.has_solver
    p = params()
    assert p["gradient"] == "Green-Gauss (node values)" and p["quarter_domain"] and not p["plume"]
    assert p["d_throat"] == 0.00028 and p["p0"] == 500000.0                 # the nozzle_axi defaults
    assert [op.type for op in template_document(CASE).operations] == ["template_body", "template_enclosure_3d"]


@pytest.mark.parametrize("quarter", [True, False])
def test_mesh_volume_patches_and_symmetry(quarter):
    p = params(quarter_domain=quarter, surface_size=0.4, farfield_size=1.5)
    mesh = CASE.build_mesh(p)
    names = {q.name: q.type for q in mesh.patches}
    assert {"inlet", "outlet", "wall"} <= set(names) and ("symmetry" in names) == quarter
    exact = _volume_of_revolution(CASE.geometry(p)) / (4.0 if quarter else 1.0)
    assert mesh.cell_volumes.sum() == pytest.approx(exact, rel=2e-2)         # tetrahedra approximate the cone walls
    assert mesh.cell_zones == {}


def test_plume_region_is_a_second_zone():
    p = params(plume=True, surface_size=0.4, farfield_size=1.5)
    mesh = CASE.build_mesh(p)
    assert sorted(mesh.zone_names) == ["nozzle", "plume"]
    names = {q.name: q.type for q in mesh.patches}
    assert names["plume_outlet"] == "outlet" and names["plume_base"] == "wall" and "outlet" not in names
    wall = CASE.geometry(p)
    d_e = 2.0 * wall.r[-1]
    plume = math.pi * (2.0 * d_e) ** 2 * 5.0 * d_e / 4.0                   # quarter cylinder
    assert mesh.cell_volumes[mesh.zone_cells("plume")].sum() == pytest.approx(plume, rel=2e-2)


def test_short_runs_mass_flow_thrust_and_plume_exit_numbers():
    import aeroflowsim
    plain = aeroflowsim.run_case("cases/nozzle_3d", {"max_iter": 40})
    k = plain.result.key_numbers
    assert k["symmetry_factor"][0] == 4.0
    assert k["mdot"][0] == pytest.approx(k["mdot_1D"][0], rel=0.05)
    assert k["F_vacuum"][0] == pytest.approx(k["F_vacuum_wall"][0], rel=0.03)
    plume = aeroflowsim.run_case("cases/nozzle_3d", {"max_iter": 40, "plume": True})
    kp = plume.result.key_numbers
    assert kp["mdot"][0] == pytest.approx(k["mdot"][0], rel=0.02)          # measured on the nozzle -> plume interface
    assert kp["F_vacuum"][0] == pytest.approx(k["F_vacuum"][0], rel=0.02)

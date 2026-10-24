# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of every boundary-condition type of the Euler solver (aeroflowsim/euler/boundary.py): the
ghost states themselves, and small steady runs that must reach the exact uniform solution."""

import math

import numpy as np
import pytest

from aeroflowsim import gasdynamics as gd
from aeroflowsim.euler.boundary import (BC_TYPES, DEFAULT_FOR_KIND, BoundaryCondition, PatchInfo,
                                        boundary_problems, ghost_state)
from aeroflowsim.euler.flux import hllc_flux, normal_velocity
from aeroflowsim.euler.solver import EulerSolver, Numerics
from aeroflowsim.euler.state import (mach_number, state_from_mach, total_pressure, total_temperature,
                                     uniform_state)
from aeroflowsim.gases import gas_model
from aeroflowsim.mesh import PATCH_TYPES
from aeroflowsim.simple_meshes import rectangle_mesh

AIR = gas_model("air")
PATCH = PatchInfo("test", 2.0)       # total flux area 2 m² (for the mass-flow inlet)
N = np.array([[1.0, 0.0], [0.6, 0.8], [0.0, -1.0]])   # outward normals of three faces


def _inside(mach=0.5, angle=0.0, p=1e5, T=300.0, n=3):
    rho, vel = state_from_mach(AIR, mach, p, T, (math.cos(math.radians(angle)), math.sin(math.radians(angle))))
    return uniform_state(n, rho, vel, p)


def test_every_patch_kind_has_a_default_and_every_type_a_label_and_inputs():
    assert set(DEFAULT_FOR_KIND) == set(PATCH_TYPES)
    for kind, bc_type in DEFAULT_FOR_KIND.items():
        assert kind in BC_TYPES[bc_type].suits
    for t in BC_TYPES.values():
        assert t.label and t.help
        for p in t.inputs:
            assert p.label and p.help


@pytest.mark.parametrize("kind", ["slip_wall", "symmetry", "axis"])
def test_mirror_conditions_give_zero_mass_flux_and_keep_the_pressure(kind):
    Wi = _inside(0.6, 35.0)
    Wg = ghost_state(BoundaryCondition(kind), Wi, N, AIR, PATCH)
    assert np.allclose(normal_velocity(Wg, N), -normal_velocity(Wi, N))
    assert np.allclose(Wg[[0, -1]], Wi[[0, -1]])
    F = hllc_flux(Wi, Wg, N, AIR)
    assert np.allclose(F[0], 0.0, atol=1e-10) and np.allclose(F[-1], 0.0, atol=1e-6)


def test_supersonic_inlet_imposes_everything_and_supersonic_outlet_copies():
    values = {"mach": 3.0, "p": 2e4, "T": 220.0, "flow_angle": 10.0}
    Wg = ghost_state(BoundaryCondition("supersonic_inlet", values), _inside(), N, AIR, PATCH)
    assert np.allclose(mach_number(Wg, AIR), 3.0) and np.allclose(Wg[-1], 2e4)
    assert np.allclose(np.degrees(np.arctan2(Wg[2], Wg[1])), 10.0)
    Wi = _inside(2.5)
    assert np.array_equal(ghost_state(BoundaryCondition("supersonic_outlet"), Wi, N, AIR, PATCH), Wi)


@pytest.mark.parametrize("mach", [0.3, 0.8, 2.5])
def test_far_field_with_the_free_stream_inside_returns_the_free_stream(mach):
    values = {"mach": mach, "p": 5e4, "T": 250.0, "flow_angle": 20.0}
    Wi = _inside(mach, 20.0, 5e4, 250.0)
    Wg = ghost_state(BoundaryCondition("far_field", values), Wi, N, AIR, PATCH)
    assert np.allclose(Wg, Wi, rtol=1e-12)


def test_total_pressure_inlet_ghost_has_the_imposed_total_state():
    values = {"p0": 3e5, "T0": 400.0}
    Wi = _inside(0.4, 180.0)          # moving in -x: into the domain through faces with n = +x
    Wg = ghost_state(BoundaryCondition("total_pressure_inlet", values), Wi, N[:1], AIR, PATCH)[:, :1]
    assert np.allclose(total_pressure(Wg, AIR), 3e5) and np.allclose(total_temperature(Wg, AIR), 400.0)
    assert Wg[1, 0] < 0.0 and abs(Wg[2, 0]) < 1e-12          # flow normal to the boundary, inwards
    # Angle option: the inflow follows the given angle
    values = {"p0": 3e5, "T0": 400.0, "direction": "Angle to the x axis", "flow_angle": 30.0}
    Wg = ghost_state(BoundaryCondition("total_pressure_inlet", values), _inside(0.3, 30.0), -N[:1], AIR, PATCH)
    assert np.allclose(np.degrees(np.arctan2(Wg[2], Wg[1])), 30.0)


def test_mass_flow_inlet_ghost_carries_the_mass_flux_and_total_temperature():
    values = {"mass_flow": 50.0, "T0": 350.0}
    Wg = ghost_state(BoundaryCondition("mass_flow_inlet", values), _inside(0.2), N, AIR, PATCH)
    G = -Wg[0] * normal_velocity(Wg, N)                    # inflow mass flux [kg/(m² s)]
    assert np.allclose(G, 50.0 / PATCH.total_area)
    assert np.allclose(total_temperature(Wg, AIR), 350.0)


def test_pressure_outlet_imposes_the_back_pressure_only_where_the_outflow_is_subsonic():
    bc = BoundaryCondition("pressure_outlet", {"p": 8e4})
    sub = _inside(0.5)
    assert np.allclose(ghost_state(bc, sub, N[:1], AIR, PATCH)[-1, :1], 8e4)
    sup = _inside(1.8)
    assert np.array_equal(ghost_state(bc, sup, N[:1], AIR, PATCH)[:, :1], sup[:, :1])


def test_boundary_problems_name_missing_and_unknown_patches_and_bad_values():
    bcs = {"inlet": BoundaryCondition("total_pressure_inlet", {"p0": -1.0}), "ghost": BoundaryCondition("slip_wall")}
    problems = " ".join(boundary_problems(bcs, ["inlet", "wall"]))
    assert "'wall' has no boundary condition" in problems
    assert "'ghost'" in problems and "Total pressure" in problems
    with pytest.raises(ValueError, match="not a boundary-condition type"):
        BoundaryCondition("vortex")


def test_condition_round_trip_through_a_plain_dict_ignores_unknown_keys():
    bc = BoundaryCondition("far_field", {"mach": 0.8})
    again = BoundaryCondition.from_dict({**bc.to_dict(), "old_key": 3})
    assert again == bc and again.values["p"] == 101325.0


# ---- small steady runs that must reach the exact uniform solution ---------------------------------

def _channel(inlet, outlet, W0):
    mesh = rectangle_mesh(16, 3, x1=0.2, y1=0.03, distort=0.2,
                          kinds={"bottom": "wall", "top": "wall"})
    bcs = {"left": inlet, "right": outlet, "bottom": BoundaryCondition("slip_wall"),
           "top": BoundaryCondition("slip_wall")}
    solver = EulerSolver(mesh, AIR, bcs, Numerics(max_iterations=6000, residual_drop=9.0), L_ref=0.2,
                         scales=(1.0, 100.0, 100.0, 1e5))
    return solver.solve(uniform_state(mesh.n_cells, *W0)), mesh


def test_total_pressure_inlet_and_pressure_outlet_give_the_isentropic_channel_flow():
    p0, T0, p_back = 1.3e5, 320.0, 1e5
    out, _ = _channel(BoundaryCondition("total_pressure_inlet", {"p0": p0, "T0": T0}),
                      BoundaryCondition("pressure_outlet", {"p": p_back}), (1.0, (50.0, 0.0), 1.1e5))
    assert out.status == "converged"
    gamma = AIR.gamma_value
    M_exact = gd.mach_from_p0_over_p(p0 / p_back, gamma)
    assert np.allclose(mach_number(out.W, AIR), M_exact, rtol=1e-6)
    assert np.allclose(out.W[-1], p_back, rtol=1e-6)
    assert np.allclose(total_temperature(out.W, AIR), T0, rtol=1e-9)


def test_mass_flow_inlet_delivers_its_mass_flow():
    mdot, T0 = 3.5, 300.0                     # kg/s per metre of depth through a 0.03 m high inlet (M about 0.3)
    out, mesh = _channel(BoundaryCondition("mass_flow_inlet", {"mass_flow": mdot, "T0": T0}),
                         BoundaryCondition("pressure_outlet", {"p": 1e5}), (1.0, (90.0, 0.0), 1e5))
    assert out.status == "converged"
    assert np.allclose(out.W[0] * out.W[1] * 0.03, mdot, rtol=1e-6)
    assert np.allclose(total_temperature(out.W, AIR), T0, rtol=1e-9)


def test_disturbed_flow_returns_to_the_free_stream_through_a_far_field():
    mesh = rectangle_mesh(10, 10, distort=0.25)
    fs = {"mach": 0.5, "p": 1e5, "T": 300.0, "flow_angle": 15.0}
    bcs = {p.name: BoundaryCondition("far_field", fs) for p in mesh.patches}
    rho, vel = state_from_mach(AIR, 0.5, 1e5, 300.0, (math.cos(math.radians(15)), math.sin(math.radians(15))))
    W0 = uniform_state(mesh.n_cells, rho, vel, 1e5)
    bump = np.exp(-((mesh.cell_centres[:, 0] - 0.5) ** 2 + (mesh.cell_centres[:, 1] - 0.5) ** 2) / 0.02)
    W0[-1] *= 1.0 + 0.05 * bump
    out = EulerSolver(mesh, AIR, bcs, Numerics(max_iterations=3000, residual_drop=8.0)).solve(W0)
    assert out.status == "converged"
    assert np.allclose(out.W[-1], 1e5, rtol=1e-6) and np.allclose(mach_number(out.W, AIR), 0.5, rtol=1e-6)

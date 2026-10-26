# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Post-processing (aeroflowsim/post/): derived fields, custom formulas, sampling, surfaces, integrals,
flux balance, forces, report definitions; on known fields and on a converged nozzle run."""

import math

import numpy as np
import pytest

import aeroflowsim
from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.gases import gas_model
from aeroflowsim.post import (FieldError, ReportDefinition, Solution, Surface, available_fields,
                              custom_field_problem, evaluate_definitions, field_values, flux_balance,
                              forces_and_moments, node_values, surface_integral, volume_integral)
from aeroflowsim.post.definitions import MonitorEvaluator
from aeroflowsim.post.sampling import interpolate_cells, locate, sample_line, values_at
from aeroflowsim.post.surfaces import evaluate_surface
from aeroflowsim.simple_meshes import rectangle_mesh

AIR = gas_model("air")
KINDS = {"left": "inlet", "right": "outlet", "bottom": "wall", "top": "wall"}


def _interior(mesh):
    """Cells that touch no boundary face."""
    touch = np.zeros(mesh.n_cells, dtype=bool)
    touch[mesh.owner[mesh.n_interior_faces:]] = True
    return ~touch


def _linear_solution(triangles=True, axisymmetric=False, y0=0.0):
    m = rectangle_mesh(16, 8, 0.0, 2.0, y0, y0 + 1.0, triangles=triangles, kinds=KINDS, axisymmetric=axisymmetric)
    c = m.cell_centres
    fields = {"rho": 1.2 + 0.1 * c[:, 0] - 0.05 * c[:, 1], "u": 600.0 + 20.0 * c[:, 1], "v": 10.0 * c[:, 0],
              "p": 1e5 + 1000.0 * c[:, 0] + 500.0 * c[:, 1]}
    return Solution(m, fields, AIR, {}, {"mach": 2.0, "p_inf": 1e5, "T_inf": 300.0}, {"kind": "external"})


# ---- fields -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("triangles", [False, True])
def test_gradients_of_linear_fields_are_exact_in_interior_cells(triangles):
    sol = _linear_solution(triangles)
    inner = _interior(sol.mesh)
    g = sol.gradients
    assert np.allclose(g[0, 0, inner], 0.1) and np.allclose(g[0, 1, inner], -0.05)
    assert np.allclose(g[3, 0, inner], 1000.0) and np.allclose(g[3, 1, inner], 500.0)


def test_vorticity_of_solid_body_rotation_is_twice_omega():
    m = rectangle_mesh(12, 12, -1, 1, -1, 1, triangles=True, distort=0.2, kinds=KINDS)
    omega = 37.0   # [1/s]
    c = m.cell_centres
    sol = Solution(m, {"rho": np.ones(m.n_cells), "u": -omega * c[:, 1], "v": omega * c[:, 0],
                       "p": np.full(m.n_cells, 1e5)}, AIR)
    inner = _interior(m)
    assert np.allclose(field_values(sol, "vorticity")[inner], 2.0 * omega)
    assert np.allclose(field_values(sol, "divergence")[inner], 0.0, atol=1e-9)


def test_cp_external_and_internal_and_other_derived_fields():
    sol = _linear_solution()
    q = 0.5 * 1.4 * 1e5 * 4.0
    assert np.allclose(field_values(sol, "Cp"), (sol.fields["p"] - 1e5) / q)
    inner = Solution(sol.mesh, sol.fields, AIR, {"inlet": BoundaryCondition("total_pressure_inlet", {"p0": 2e5})},
                     {}, {"kind": "nozzle"})
    assert np.allclose(field_values(inner, "Cp"), sol.fields["p"] / 2e5)
    rho, u, v, p = sol.W
    T = p / (rho * AIR.R)
    assert np.allclose(field_values(sol, "speed"), np.hypot(u, v))
    assert np.allclose(field_values(sol, "h0"), AIR.cp(T) * T + 0.5 * (u * u + v * v))
    assert np.allclose(field_values(sol, "M"), np.hypot(u, v) / np.sqrt(1.4 * AIR.R * T))
    sch = field_values(sol, "schlieren")
    assert sch.min() >= 0.0 and sch.max() <= 1.0
    names = [f.name for f in available_fields(sol)]
    for n in ("rho", "Cp", "vorticity", "schlieren", "mach_normal", "aspect_ratio", "residual_density"):
        assert n in names


def test_normal_mach_number_is_mach_along_the_pressure_gradient():
    sol = _linear_solution()
    inner = _interior(sol.mesh)
    rho, u, v, p = sol.W
    c = np.sqrt(1.4 * p / rho)
    gp = np.array([1000.0, 500.0]) / math.hypot(1000.0, 500.0)
    expected = (u * gp[0] + v * gp[1]) / c
    assert np.allclose(field_values(sol, "mach_normal")[inner], expected[inner])


def test_custom_field_functions_good_input():
    sol = _linear_solution()
    sol.custom_fields = {"p_atm": {"formula": "p / 101325"}, "mflux": {"formula": "rho * u"},
                         "vmag": {"formula": "sqrt(u**2 + v**2)"}, "twice": {"formula": "2 * mflux"}}
    assert np.allclose(field_values(sol, "p_atm"), sol.fields["p"] / 101325)
    assert np.allclose(field_values(sol, "vmag"), np.hypot(sol.fields["u"], sol.fields["v"]))
    assert np.allclose(field_values(sol, "twice"), 2 * sol.fields["rho"] * sol.fields["u"])
    from aeroflowsim.post.fields import field_info
    assert field_info(sol, "vmag").unit == "m/s"
    assert field_info(sol, "mflux").unit == "kg m^-2 s^-1"
    assert custom_field_problem(sol, "ok_name", "p * gamma / (rho * R)") == ""


@pytest.mark.parametrize("formula,words", [
    ("__import__('os').system('echo hi')", "not allowed"),
    ("p.__class__", "not allowed"),
    ("(lambda: 1)()", "not allowed"),
    ("open('x')", "not allowed"),
    ("p[0]", "not allowed"),
    ("sqrt(x=p)", "plain values"),
    ("p +", "not valid"),
    ("pressure * 2", "Unknown name"),
    ("p + u", "different units"),
    ("'text'", "Only numbers"),
    ("eval('1')", "not allowed"),
])
def test_custom_field_functions_refuse_bad_or_malicious_input(formula, words):
    sol = _linear_solution()
    problem = custom_field_problem(sol, "f", formula)
    assert words in problem, problem


def test_custom_field_name_rules_and_self_reference():
    sol = _linear_solution()
    assert "already the name" in custom_field_problem(sol, "Cp", "p")
    assert "letter" in custom_field_problem(sol, "2x", "p")
    sol.custom_fields = {"a": {"formula": "b + 1"}, "b": {"formula": "a * 2"}}
    with pytest.raises(FieldError, match="uses itself"):
        field_values(sol, "a")


# ---- sampling and node values ---------------------------------------------------------------------

def test_point_values_and_line_samples_reproduce_linear_fields_inside():
    sol = _linear_solution()
    sol.conditions = {}
    pts = np.array([[0.73, 0.41], [1.5, 0.5], [3.0, 3.0]])
    assert locate(sol, pts)[2] == -1
    v = values_at(sol, "p", pts)
    inner = _interior(sol.mesh)
    exact = 1e5 + 1000 * pts[:, 0] + 500 * pts[:, 1]
    assert inner[locate(sol, pts[:2])].all()
    assert np.allclose(v[:2], exact[:2]) and np.isnan(v[2])
    t, xy, values = sample_line(sol, "p", (0.4, 0.3), (1.6, 0.7))
    assert len(t) >= 2 * 10                         # two samples per cell crossed
    assert np.all(np.diff(t) >= 0.0)


def test_node_values_are_exact_for_linear_fields_at_interior_nodes():
    sol = _linear_solution(triangles=False)
    nv = node_values(sol, "p")
    x, y = sol.mesh.nodes[:, 0], sol.mesh.nodes[:, 1]
    inner = (x > 1e-9) & (x < 2 - 1e-9) & (y > 1e-9) & (y < 1 - 1e-9)
    assert np.allclose(nv[inner], (1e5 + 1000 * x + 500 * y)[inner])


def test_interpolation_onto_another_mesh_is_exact_where_centres_coincide():
    a = rectangle_mesh(8, 4, 0, 2, 0, 1)
    vals = np.vstack([a.cell_centres[:, 0], a.cell_centres[:, 1]])
    out = interpolate_cells(a.cell_centres, vals, a.cell_centres)
    assert np.allclose(out, vals)
    b = rectangle_mesh(16, 8, 0, 2, 0, 1)
    fine = interpolate_cells(a.cell_centres, vals, b.cell_centres)
    assert np.abs(fine[0] - b.cell_centres[:, 0]).max() < 0.25


# ---- surfaces and integrals -----------------------------------------------------------------------

def test_line_integrals_are_exact_for_linear_fields():
    sol = _linear_solution()
    line = Surface.line((1.0, 0.25), (1.0, 0.75))     # inside the interior cells
    assert surface_integral(sol, line, "area")[0] == pytest.approx(0.5)
    # int p dy = int (1e5 + 1000 + 500 y) dy over [0.25, 0.75]
    expected = (1e5 + 1000.0) * 0.5 + 250.0 * (0.75**2 - 0.25**2)
    assert surface_integral(sol, line, "integral", "p")[0] == pytest.approx(expected, rel=1e-12)
    assert surface_integral(sol, line, "area_weighted", "p")[0] == pytest.approx(expected / 0.5, rel=1e-12)


def test_axisymmetric_areas_are_full_circle():
    m = rectangle_mesh(8, 8, 0.0, 1.0, 0.0, 1.0, axisymmetric=True, kinds={**KINDS, "bottom": "axis"})
    sol = Solution(m, {"rho": np.ones(64), "u": np.ones(64), "v": np.zeros(64), "p": np.ones(64)}, AIR)
    disc = Surface.line((0.5, 0.0), (0.5, 1.0))
    assert surface_integral(sol, disc, "area")[0] == pytest.approx(math.pi, rel=1e-12)
    assert surface_integral(sol, Surface.boundary("top"), "area")[0] == pytest.approx(2 * math.pi, rel=1e-12)
    assert volume_integral(sol, "volume")[0] == pytest.approx(math.pi, rel=1e-12)
    assert volume_integral(sol, "volume", region={"type": "box", "min": (0, 0), "max": (0.5, 1)})[0] == \
        pytest.approx(math.pi / 2, rel=1e-12)


def test_surface_types_evaluate_and_survive_a_round_trip():
    sol = _linear_solution()
    for s in (Surface.boundary("bottom", "top"), Surface.line((0.1, 0.1), (1.9, 0.9)), Surface.rake((0.5, 0.1),
              (0.5, 0.9), 5), Surface.point((1.0, 0.5)), Surface.iso("p", 101200.0), Surface.x_line(1.0),
              Surface.y_line(0.5)):
        assert Surface.from_dict(s.to_dict()) == s
        d = evaluate_surface(sol, s)
        assert d.n >= 1, s.type
    iso = evaluate_surface(sol, Surface.iso("p", 101200.0))
    xy = 0.5 * (iso.a + iso.b)
    xy = xy[(xy[:, 0] > 0.2) & (xy[:, 0] < 1.8) & (xy[:, 1] > 0.2) & (xy[:, 1] < 0.8)]   # away from the boundary nodes
    assert len(xy) and np.allclose(1000 * xy[:, 0] + 500 * xy[:, 1], 1200.0, atol=1.0)
    assert "no boundary" in Surface.boundary("nope").problem(sol)


# ---- a converged nozzle run -----------------------------------------------------------------------

@pytest.fixture(scope="module")
def nozzle():
    out = aeroflowsim.run_case("cases/nozzle_axi", {"mesh_preset": "Custom", "nx": 40, "nr": 8})
    assert out.result.converged
    return out, Solution.from_result(out.mesh, out.result, out.params, case=out.case)


def test_mass_flow_report_equals_the_solver_boundary_flux(nozzle):
    out, sol = nozzle
    mdot = out.result.key_numbers["mdot_exit"][0]
    assert surface_integral(sol, Surface.boundary("outlet"), "mass_flow")[0] == pytest.approx(mdot, rel=1e-12)
    # a line across the nozzle (not a boundary) gives the same mass flow to the accuracy of the reconstruction
    x_mid = 0.5 * (sol.mesh.nodes[:, 0].min() + sol.mesh.nodes[:, 0].max())
    across = surface_integral(sol, Surface.x_line(x_mid), "mass_flow")[0]
    assert across == pytest.approx(mdot, rel=0.02)


def test_flux_balance_closes_on_the_converged_run(nozzle):
    out, sol = nozzle
    fb = flux_balance(sol)
    assert fb["relative"]["mass"] < 1e-4 and fb["relative"]["energy"] < 1e-4
    names = [r[0] for r in fb["rows"]]
    assert {"inlet", "outlet"} <= set(names)
    assert fb["pressure_source"] > 0.0 and "Axisymmetric" in fb["note"]


def test_mass_weighted_total_pressure_and_report_definitions(nozzle):
    out, sol = nozzle
    p0_exit = out.result.key_numbers["p0_exit"][0]
    assert surface_integral(sol, Surface.boundary("outlet"), "mass_weighted", "p0")[0] == pytest.approx(p0_exit,
                                                                                                         rel=2e-3)
    defs = [ReportDefinition("p0 out", "surface", "outlet", "mass_weighted", "p0"),
            ReportDefinition("mdot", "surface", "outlet", "mass_flow", monitor=True),
            ReportDefinition("mass", "volume", operation="mass"),
            ReportDefinition("bad", "surface", "nope", "area")]
    values = evaluate_definitions(sol, defs)
    assert values["mdot"][0] == pytest.approx(out.result.key_numbers["mdot_exit"][0])
    assert values["mass"][1] == "kg" and values["mass"][0] > 0
    assert math.isnan(values["bad"][0]) and "no surface" in values["bad"][1].lower()
    for d in defs:
        assert ReportDefinition.from_dict(d.to_dict()) == d


def test_monitor_evaluator_matches_post_processing(nozzle):
    out, sol = nozzle
    from aeroflowsim.euler.state import primitive_to_conserved
    s = sol._solver                  # the run's numerics, reference scales and frozen limiter
    s.residual(primitive_to_conserved(sol.W, sol.gas), True, sol.W)
    s.stage0_boundary_flux = s.boundary_flux
    ev = MonitorEvaluator(sol.mesh, sol.gas, sol.conditions, sol.params,
                          [ReportDefinition("mdot", "surface", "outlet", "mass_flow", monitor=True)])
    assert ev(s, sol.W)["user_mdot"] == pytest.approx(out.result.key_numbers["mdot_exit"][0], rel=1e-12)


def test_forces_on_the_nozzle_wall(nozzle):
    out, sol = nozzle
    f = forces_and_moments(sol, ["wall"])
    k = out.result.key_numbers
    # the x-force of the gas on the wall equals F_wall + inlet momentum (see euler/forces.py), sign as body force
    assert f["Fy"] == 0.0 and f["force_unit"] == "N"
    fb = flux_balance(sol)
    wall_row = next(r for r in fb["rows"] if r[0] == "wall")
    assert f["Fx"] == pytest.approx(wall_row[3], rel=1e-12)
    assert k["F_vacuum"][0] > 0

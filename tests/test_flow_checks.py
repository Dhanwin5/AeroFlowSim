# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validity checks and smart rules of the 2D Euler solver: run status, monitors, positivity, CFL, thrust
two ways, total-pressure loss; numerics suggestions, first-layer height and failure diagnosis."""

import math

import numpy as np
import pytest

import aeroflowsim
from aeroflowsim import checks, smart_rules
from aeroflowsim.discovery import load_case
from aeroflowsim.parameters import defaults
from aeroflowsim.results import Field, Result

NOZZLE = load_case("nozzle_axi")


class Steady:
    steady = True


def _result(info=None, series=None, key_numbers=None, fields=None):
    return Result(fields=fields or {}, residuals=[1.0, 1e-7], key_numbers=key_numbers or {}, iterations=2,
                  converged=True, series=series or {}, info=info or {})


def test_run_status_is_an_error_after_a_divergence():
    assert checks.run_status(Steady, {}, None, _result({"status": "diverged", "message": "Bad."})).level == "error"
    assert checks.run_status(Steady, {}, None, _result({"status": "converged"})).level == "info"
    assert checks.run_status(Steady, {}, None, _result({})) is None


def test_monitors_settled_compares_the_change_over_the_window_with_the_tolerance():
    info = {"converge_on": ["thrust"], "monitor_window": 10, "monitor_tol": 1e-4,
            "monitor_labels": {"thrust": ["Thrust", "N"]}}
    flat = _result(info, {"monitor_thrust": np.full(20, 0.05)})
    moving = _result(info, {"monitor_thrust": np.linspace(0.05, 0.051, 20)})
    short = _result(info, {"monitor_thrust": np.full(5, 0.05)})
    assert checks.monitors_settled(Steady, {}, None, flat).level == "info"
    assert checks.monitors_settled(Steady, {}, None, moving).level == "warning"
    assert "shorter than the monitor window" in checks.monitors_settled(Steady, {}, None, short).message


def test_positivity_and_cfl_checks():
    assert checks.positivity_events(Steady, {}, None, _result({"positivity_events": 0})).level == "info"
    assert checks.positivity_events(Steady, {}, None, _result({"positivity_events": 40, "positivity_last": 0})).level == "info"
    assert checks.positivity_events(Steady, {}, None, _result({"positivity_events": 40, "positivity_last": 3})).level == "warning"
    assert checks.cfl_reductions(Steady, {}, None, _result({"cfl_reductions": 0, "cfl_final": 0.8})).level == "info"
    found = checks.cfl_reductions(Steady, {}, None, _result({"cfl_reductions": 2, "cfl": 1.2, "cfl_final": 0.3}))
    assert found.level == "warning" and "0.3" in found.message


def test_thrust_two_ways_and_total_pressure_loss():
    assert checks.thrust_two_ways(Steady, {}, None, _result(key_numbers={"thrust_difference": (0.1, "%")})).level == "info"
    assert checks.thrust_two_ways(Steady, {}, None, _result(key_numbers={"thrust_difference": (2.0, "%")})).level == "warning"
    info = {"kind": "nozzle", "boundaries": {"inlet": {"type": "total_pressure_inlet", "p0": 5e5}}}
    fields = {"p0": Field(np.full(3, 5e5), "Pa", "Total pressure")}
    good = _result(info, key_numbers={"p0_exit": (4.99e5, "Pa")}, fields=fields)
    lossy = _result(info, key_numbers={"p0_exit": (4.8e5, "Pa")}, fields=fields)
    assert checks.total_pressure_loss(Steady, {}, None, good).level == "info"
    assert checks.total_pressure_loss(Steady, {}, None, lossy).level == "warning"
    external = {"kind": "external"}
    shocky = _result(external, fields={**fields, "M": Field(np.array([0.5, 2.0, 1.0]), "-", "Mach")})
    assert "may contain shocks" in checks.total_pressure_loss(Steady, {}, None, shocky).message


def test_flow_scales_and_first_layer_height_for_the_nozzle_throat():
    params = defaults(NOZZLE.parameters())
    flow = smart_rules.flow_scales(NOZZLE, params)
    assert flow["where"] == "throat" and flow["L"] == pytest.approx(0.28e-3)
    assert flow["U"] == pytest.approx(math.sqrt(1.4 * NOZZLE.gas(params).R * 293.15 / 1.2), rel=1e-6)
    h = smart_rules.first_layer_height(flow)
    cf = 0.026 * flow["Re"] ** (-1 / 7)
    assert h == pytest.approx(flow["mu"] / (flow["rho"] * flow["U"] * math.sqrt(cf / 2)))
    assert 1e-8 < h < 1e-5


def test_numerics_suggestions_follow_the_mach_number_and_the_start():
    class Body:
        @staticmethod
        def gas(params):
            from aeroflowsim.gases import gas_model
            return gas_model("air")
    strong = smart_rules.numerics_suggestions(Body, {"mach": 6.0, "T_inf": 220.0, "cfl": 0.8})
    assert strong[0].inputs == {"cfl": 0.5, "first_order_iterations": 500, "carbuncle_fix": True}
    assert "41.8" in strong[0].reason                              # normal-shock pressure ratio at Mach 6
    assert smart_rules.numerics_suggestions(Body, {"mach": 0.1})[0].kind == "advice"
    nozzle = smart_rules.numerics_suggestions(NOZZLE, {"initialisation": "Uniform (free stream)", "p0": 5e5,
                                                       "time_scheme": "SSP-RK3", "cfl": 2.0})
    assert {s.title for s in nozzle} == {"Initial solution", "CFL number"}


def test_a_diverged_run_stops_cleanly_and_is_diagnosed(monkeypatch):
    import aeroflowsim.euler.solver as solver
    monkeypatch.setattr(solver, "MAX_CFL_REDUCTIONS", 0)
    out = aeroflowsim.run_case(NOZZLE, {"mesh_preset": "Coarse", "max_iter": 50, "cfl": 5.0, "time_scheme": "SSP-RK3",
                                        "initialisation": "Uniform (free stream)"})
    info = out.result.info
    assert info["status"] == "diverged" and not out.result.converged and info["diverged_at"] is not None
    assert all(np.isfinite(f.values).all() for f in out.result.fields.values())   # the last good state
    assert next(c for c in out.checks if c.name == "Run status").level == "error"
    titles = [s.title for s in smart_rules.diagnose(NOZZLE, out.params, out.result)]
    assert titles[:3] == ["Lower CFL", "First-order start", "Initial solution"] and "Where it failed" in titles


def test_a_stopped_run_returns_the_flow_of_that_moment_and_can_be_continued():
    """progress() returning True (the user pressed Stop) ends the run cleanly with status 'stopped'."""
    out = aeroflowsim.run_case(NOZZLE, {"mesh_preset": "Coarse", "max_iter": 100000},
                               progress=lambda it, res, info=None: it >= 25)
    r = out.result
    assert r.info["status"] == "stopped" and r.iterations == 25 and not r.converged
    check = next(c for c in out.checks if c.name == "Run status")
    assert check.level == "warning" and "carry on from iteration 26" in check.message
    from aeroflowsim.result_io import continuation_data
    again = aeroflowsim.run_case(NOZZLE, {"mesh_preset": "Coarse", "max_iter": 26}, mesh=out.mesh,
                                 restart=continuation_data(r))
    assert again.result.iterations == 26              # one more iteration, numbered on
    assert abs(again.result.key_numbers["mdot"][0] / r.key_numbers["mdot"][0] - 1.0) < 0.01


def test_an_angle_of_attack_on_an_axisymmetric_mesh_is_refused_before_the_run():
    pytest.importorskip("gmsh")
    from aeroflowsim.engine import SetupError
    body = load_case("external_2d")
    cone = {"shape": "Conical nose cone", "domain_shape": "Rectangle", "upstream": 1.0, "downstream": 1.0,
            "height": 2.0, "surface_size": 0.05, "farfield_size": 0.5, "max_iter": 3}
    with pytest.raises(SetupError, match="cannot have an angle of attack"):
        aeroflowsim.run_case(body, {**cone, "alpha": 10.0})
    with pytest.raises(SetupError, match="boundary 'farfield' at 5"):
        aeroflowsim.run_case(body, {**cone, "boundaries": {"farfield": {"type": "far_field", "mach": 2.0,
                                                                         "flow_angle": 5.0}}})
    out = aeroflowsim.run_case(body, cone)          # zero angle: runs, and the check says it is fine
    assert next(c for c in out.checks if c.name == "Axisymmetric free stream").level == "info"
    # Planar bodies may have an angle of attack; nozzles (no alpha input) are not checked
    assert checks.axisymmetric_incidence(body, {"alpha": 10.0}, load_case("nozzle_axi").build_mesh(
        {**defaults(NOZZLE.parameters()), "mesh_preset": "Coarse"}), None).level == "error"
    assert checks.axisymmetric_incidence(NOZZLE, defaults(NOZZLE.parameters()), out.mesh, None) is None


def test_a_cfl_reduction_keeps_the_run_going(monkeypatch):
    out = aeroflowsim.run_case(NOZZLE, {"mesh_preset": "Coarse", "max_iter": 60, "cfl": 5.0, "time_scheme": "SSP-RK3"})
    info = out.result.info
    assert info["status"] != "diverged" and info["cfl_reductions"] >= 1 and info["cfl_final"] < 5.0
    assert smart_rules.diagnose(NOZZLE, out.params, out.result)[0].title == "Lower CFL"

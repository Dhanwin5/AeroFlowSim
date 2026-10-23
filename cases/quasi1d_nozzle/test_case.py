# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validation tests for quasi1d_nozzle (default N2 thruster, p0 = 5 bar, T0 = 293.15 K).

Reference values: isentropic area-Mach theory and normal-shock relations (aeroflowsim/gasdynamics.py),
computed by hand for the default conical nozzle (A_exit/A_throat = 10.59).
"""

from functools import lru_cache

import numpy as np
import pytest

from aeroflowsim.discovery import load_case
from aeroflowsim.job import RunJob
from aeroflowsim.parameters import defaults

case = load_case("quasi1d_nozzle")


@lru_cache(maxsize=None)
def solve(**changes):
    """Run with default parameters, optionally changed; cached so each setup runs only once."""
    params = defaults(case.parameters())
    params.update(changes)
    mesh = case.build_mesh(params)
    result = case.run(params, mesh, lambda it, res: None)
    return params, mesh, result


def value(result, name):
    return result.key_numbers[name][0]


def relative(a, b):
    return abs(a - b) / abs(b)


def test_1_vacuum_like_back_pressure_matches_theory():
    _, _, result = solve()                     # back pressure 1 kPa
    k = {name: value(result, name) for name in ("M_exit", "p_exit", "mdot", "F_vacuum", "M_throat")}
    print(f"  M_exit {k['M_exit']:.4f}  p_exit {k['p_exit']:.1f} Pa  mdot {k['mdot'] * 1e6:.3f} mg/s  "
          f"F_vac {k['F_vacuum'] * 1e3:.3f} mN  M_throat {k['M_throat']:.4f}")
    assert result.converged
    assert relative(k["M_exit"], 3.99) < 0.02
    assert relative(k["p_exit"], 3.36e3) < 0.05
    assert relative(k["mdot"], 71.5e-6) < 0.02
    assert relative(k["F_vacuum"], 50.8e-3) < 0.02
    assert relative(k["M_throat"], 1.0) < 0.03


def test_2_mass_flow_is_conserved():
    _, _, result = solve()
    flows = [value(result, f"mdot_{where}") for where in ("inlet", "throat", "exit")]
    print(f"  mdot inlet / throat / exit: {[f'{m * 1e6:.5f}' for m in flows]} mg/s")
    assert max(flows) - min(flows) < 0.005 * np.mean(flows)


def test_3_gas_at_rest_stays_at_rest():
    params, _, result = solve(p_back=5.0e5)    # back pressure = p0: no flow
    u = result.fields["u"].values
    print(f"  max |u| = {np.abs(u).max():.3e} m/s")
    assert np.all(np.abs(u) < 1e-8)
    assert np.allclose(result.fields["p"].values, params["p0"], rtol=1e-12)


def test_4_normal_shock_position():
    # The residual stalls at ~1e-3 once the shock has settled (the limiter keeps switching at the
    # shock, see README), so a limited number of iterations is enough.
    _, mesh, result = solve(p_back=2.5e5, max_iter=30000)
    x_t, x_s, x_exact = value(result, "x_throat"), value(result, "x_shock"), value(result, "x_shock_exact")
    dx_local = mesh.dx[np.searchsorted(mesh.x, x_exact) - 1]          # cell width at the shock [m]
    print(f"  shock {(x_s - x_t) * 1e3:.4f} mm after the throat (theory {(x_exact - x_t) * 1e3:.4f} mm), "
          f"error {abs(x_s - x_exact) / dx_local:.2f} cells, M1 = {value(result, 'M_before_shock_exact'):.3f}")
    assert relative(x_exact - x_t, 0.32e-3) < 0.02                    # theory: 0.32 mm
    assert relative(value(result, "M_before_shock_exact"), 2.49) < 0.01
    assert abs(x_s - x_exact) < 2.0 * dx_local


def test_5_csv_profile_gives_same_answer_as_parametric():
    _, _, cone = solve()
    _, _, csv = solve(geometry_source="Custom profile (CSV)")         # examples/n2_conical_nozzle.csv
    for name in ("M_exit", "mdot", "F_vacuum"):
        print(f"  {name}: parametric {value(cone, name):.6g}, CSV {value(csv, name):.6g}")
        assert relative(value(csv, name), value(cone, name)) < 0.01


def test_6_residual_drops_six_orders():
    _, _, result = solve()
    print(f"  residual after {result.iterations} iterations: {result.residuals[-1]:.2e}")
    assert result.residuals[-1] <= 1e-6


def test_reference_matches_solution_in_supersonic_part():
    params, mesh, result = solve()
    exact = case.reference(params, mesh)["M"].values
    after = mesh.xc > value(result, "x_throat") + 0.2e-3              # away from the sharp throat
    error = np.abs(result.fields["M"].values[after] - exact[after]) / exact[after]
    print(f"  max relative Mach error downstream of the throat: {error.max():.3%}")
    assert error.max() < 0.02


def test_stop_signal_ends_run_cleanly():
    params = defaults(case.parameters())
    job = RunJob()
    job.stop()                      # Stop pressed: the run must end at its first progress call
    job.start(case, params, case.build_mesh(params))
    job.wait(timeout=30)
    assert job.status == "stopped"
    assert job.iterations == [1]


def test_derived_design_numbers_match_the_theory_references():
    """The read-only numbers under the inputs (case.derived) agree with validation/quasi1d_nozzle."""
    d = case.derived(defaults(case.parameters()))
    assert np.isclose(d["Area ratio A_exit/A_throat"][0], 10.59, rtol=1e-3)
    assert np.isclose(d["Design exit Mach number"][0], 3.99, rtol=3e-3)
    assert np.isclose(d["Design exit pressure"][0], 3.36e3, rtol=5e-3)
    assert np.isclose(d["Choked mass flow"][0], 71.5e-6, rtol=3e-3)
    assert np.isclose(d["Ideal vacuum thrust"][0], 50.8e-3, rtol=3e-3)
    assert d["Flow at this back pressure"][0] == "supersonic exit"
    p_b1, p_b2 = d["Back pressure: choking limit p_b1"][0], d["Back pressure: shock at exit p_b2"][0]
    assert d["Design exit pressure"][0] < p_b2 < p_b1 < 5e5        # supersonic < shock in nozzle < subsonic
    shock = case.derived({**defaults(case.parameters()), "p_back": 2.5e5})
    assert shock["Flow at this back pressure"][0] == "shock in nozzle"


@pytest.mark.parametrize("n", [300, 450, 1000, 5000, 20000])
def test_mesh_at_any_cell_count(n):
    """The throat grading once overflowed (10**n) for about 450 cells or more."""
    params = {**defaults(case.parameters()), "n_cells": n}
    mesh = case.build_mesh(params)
    profile = case.geometry(params)
    dx = np.diff(mesh.x)
    assert len(dx) == n and np.all(dx > 0.0)
    assert mesh.x[0] == profile.x[0] and mesh.x[-1] == profile.x[-1]
    i_t = int(np.argmin(np.abs(mesh.x - profile.x_throat)))
    assert mesh.x[i_t] == profile.x_throat                              # a face exactly at the throat
    assert np.isclose(dx[i_t - 1], dx[i_t], rtol=1e-9) and dx.min() == pytest.approx(dx[i_t], rel=1e-9)


# More cells need more iterations, and on fine meshes the minmod limiter falls into a limit cycle in the
# smallest cells at the sonic throat (see README): the residual stalls near 1e-7 from about 450 cells and
# near 1e-2 at 5 000 cells, while the solution itself is steady (mass balance, exit values). So the runs
# stop at 6 orders, and each mesh has the residual drop it reliably reaches.
RUNS = [pytest.param(300, 60000, 6.0, id="300"), pytest.param(450, 80000, 6.0, id="450"),
        pytest.param(1000, 150000, 5.5, id="1000", marks=pytest.mark.validation),
        pytest.param(5000, 120000, 1.5, id="5000", marks=pytest.mark.validation)]


@pytest.mark.parametrize("n, max_iter, orders", RUNS)
def test_runs_at_more_cells(n, max_iter, orders):
    params, _, result = solve(n_cells=n, tol=1e-6, max_iter=max_iter)
    k = {name: value(result, name) for name in ("M_exit", "mdot", "mdot_inlet", "mdot_exit", "F_vacuum")}
    drop = -np.log10(min(result.residuals))
    print(f"  {n} cells: {result.iterations} iterations, residual drop {drop:.1f} orders, M_exit {k['M_exit']:.5f}, "
          f"mdot {k['mdot'] * 1e6:.4f} mg/s, inlet/exit {k['mdot_inlet'] * 1e6:.5f}/{k['mdot_exit'] * 1e6:.5f}")
    assert drop >= orders
    assert relative(k["M_exit"], 3.99) < 0.01
    assert relative(k["mdot"], 71.5e-6) < 0.01 and relative(k["F_vacuum"], 50.8e-3) < 0.01
    assert abs(k["mdot_inlet"] - k["mdot_exit"]) < 0.005 * k["mdot"]

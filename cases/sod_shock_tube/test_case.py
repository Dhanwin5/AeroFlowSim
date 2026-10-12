"""Validation tests for sod_shock_tube against the exact Riemann solution (Toro ch. 4)."""

import math

import numpy as np

from core.discovery import load_case
from core.euler1d import euler_flux, primitive_to_conserved
from core.job import RunJob
from core.parameters import defaults

case = load_case("sod_shock_tube")


def solve(**changes):
    """Run with default (Sod) parameters, optionally changed; return params, mesh, result."""
    params = defaults(case.parameters())
    params.update(changes)
    mesh = case.build_mesh(params)
    result = case.run(params, mesh, lambda it, res: None)
    return params, mesh, result


def density_l1_error(n_cells):
    """L1 norm of the density error, sum |rho - rho_exact| dx  [kg/m²]."""
    params, mesh, result = solve(n_cells=n_cells)
    exact = case.reference(params, mesh)["rho"].values
    return float(np.sum(np.abs(result.fields["rho"].values - exact) * mesh.dx))


def test_density_error_decreases_with_observed_order():
    cells = [100, 200, 400]
    errors = [density_l1_error(n) for n in cells]
    orders = [math.log2(errors[k] / errors[k + 1]) for k in range(2)]
    for n, e in zip(cells, errors):
        print(f"  N = {n:4d}   L1(rho) = {e:.4e} kg/m²")
    print(f"  observed order: {orders[0]:.3f} (100->200), {orders[1]:.3f} (200->400)")
    assert errors[0] > errors[1] > errors[2]
    assert min(orders) > 0.6


def test_mass_momentum_energy_conserved():
    params, mesh, result = solve()
    gamma, t, dx = params["gamma"], params["t_end"], mesh.dx[0]
    f = result.fields
    W_end = np.array([f["rho"].values, f["u"].values, f["p"].values])
    W_start = case.initial_state(params, mesh)

    # Waves must not have reached the ends: end cells still hold their initial state.
    assert np.allclose(W_end[:, [0, -1]], W_start[:, [0, -1]], rtol=1e-12, atol=0.0)

    # Totals change only by what flows through the two ends. With u = 0 there the end
    # fluxes are (0, p, 0): mass and energy stay constant, momentum grows by (p_L - p_R) t.
    total_start = np.sum(primitive_to_conserved(W_start, gamma), axis=1) * dx
    end_flux = euler_flux(W_start[:, [0, -1]], gamma)          # flux at x = 0 and x = L
    expected = total_start + t * (end_flux[:, 0] - end_flux[:, 1])
    total_end = np.sum(primitive_to_conserved(W_end, gamma), axis=1) * dx
    relative_error = np.abs(total_end - expected) / np.abs(expected)
    print(f"  relative error mass, momentum, energy: {relative_error}")
    assert np.all(relative_error < 1e-10)


def test_density_and_pressure_stay_positive():
    _, _, result = solve()
    assert result.fields["rho"].values.min() > 0.0
    assert result.fields["p"].values.min() > 0.0


def test_shock_and_contact_positions():
    params, mesh, result = solve()
    dx = mesh.dx[0]
    k = result.key_numbers
    print(f"  shock:   {k['x_shock'][0]:.5f} m (exact {k['x_shock_exact'][0]:.5f} m)")
    print(f"  contact: {k['x_contact'][0]:.5f} m (exact {k['x_contact_exact'][0]:.5f} m)")
    assert abs(k["x_shock"][0] - k["x_shock_exact"][0]) < 2.0 * dx
    assert abs(k["x_contact"][0] - k["x_contact_exact"][0]) < 2.0 * dx


def test_progress_every_step_and_reaches_end_time():
    params = defaults(case.parameters())
    mesh = case.build_mesh(params)
    calls = []
    result = case.run(params, mesh, lambda it, res: calls.append(it))
    assert calls == list(range(1, result.iterations + 1))
    assert abs(result.key_numbers["t_final"][0] - params["t_end"]) < 1e-12


def test_stop_signal_ends_run_cleanly():
    params = defaults(case.parameters())
    job = RunJob()
    job.stop()                      # Stop pressed: the run must end at its first progress call
    job.start(case, params, case.build_mesh(params))
    job.wait(timeout=30)
    assert job.status == "stopped"
    assert job.iterations == [1]

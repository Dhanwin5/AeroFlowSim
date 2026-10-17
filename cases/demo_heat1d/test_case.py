"""Validation test for demo_heat1d: compare with the exact parabolic temperature profile."""

import numpy as np
from matplotlib.figure import Figure

from aeroflowsim.discovery import load_case
from aeroflowsim.parameters import defaults
from aeroflowsim.visualise import shape_view

case = load_case("demo_heat1d")


def solve():
    """Run the case with default parameters; return params, mesh, result and progress calls."""
    params = defaults(case.parameters())
    mesh = case.build_mesh(params)
    calls = []
    result = case.run(params, mesh, lambda it, res: calls.append((it, res)))
    return params, mesh, result, calls


def test_matches_exact_solution():
    params, mesh, result, _ = solve()
    exact = case.reference(params, mesh)["T"].values   # [K]
    error = np.max(np.abs(result.fields["T"].values - exact))  # [K]
    assert result.converged
    assert error < 1e-6


def test_energy_balance():
    params, _, result, _ = solve()
    q_out = result.key_numbers["q_left"][0] + result.key_numbers["q_right"][0]  # [W/m²]
    q_generated = params["q_gen"] * params["L"]                                # [W/m²]
    assert abs(q_out - q_generated) / q_generated < 1e-3


def test_progress_reported_and_residual_falls():
    params, _, result, calls = solve()
    assert len(calls) == result.iterations == len(result.residuals)
    assert result.residuals[0] == 1.0
    assert result.residuals[-1] < params["tol"]


def test_shape_view_of_rod():
    params, mesh, result, _ = solve()
    assert result.shape is not None                       # constant-height rod outline
    assert np.allclose(result.shape.r, 0.05 * params["L"])
    T = result.fields["T"]
    fig = shape_view(mesh.x, result.shape.radius_at(mesh.x), T.values, T.label, T.unit)
    assert isinstance(fig, Figure)

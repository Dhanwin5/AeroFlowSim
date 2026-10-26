# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""MMS order of accuracy on small meshes (the full study is validation/mms_euler2d) and the GCI tool."""

import math

import numpy as np
import pytest

from aeroflowsim import gci, mms
from aeroflowsim.euler.geometry import FVGeometry
from aeroflowsim.euler.limiters import NO_LIMITER, limiter_factors
from aeroflowsim.gases import gas_model
from aeroflowsim.simple_meshes import rectangle_mesh

AIR = gas_model("air")


def test_source_term_matches_finite_differences_of_the_fluxes():
    """The hand-written derivatives agree with central differences of the exact fluxes."""
    x, y, d = np.array([0.31, 0.77]), np.array([0.62, 0.18]) + 0.5, 1e-6

    def fluxes(x, y):
        rho, u, v, p = mms.exact_state(x, y)
        E = rho * AIR.internal_energy(p / (rho * AIR.R)) + 0.5 * rho * (u * u + v * v)
        F = np.array([rho * u, rho * u * u + p, rho * u * v, u * (E + p)])
        G = np.array([rho * v, rho * u * v, rho * v * v + p, v * (E + p)])
        return F, G, p

    Fx = (fluxes(x + d, y)[0] - fluxes(x - d, y)[0]) / (2 * d)
    Gy = (fluxes(x, y + d)[1] - fluxes(x, y - d)[1]) / (2 * d)
    planar = mms.source(x, y, AIR)
    assert np.allclose(planar, Fx + Gy, rtol=1e-6)
    # axisymmetric: d(rF)/dx + d(rG)/dr - p e_r
    rGy = (((y + d) * fluxes(x, y + d)[1]) - ((y - d) * fluxes(x, y - d)[1])) / (2 * d)
    expected = y * Fx + rGy
    expected[2] -= fluxes(x, y)[2]
    assert np.allclose(mms.source(x, y, AIR, axisymmetric=True), expected, rtol=1e-6)


def test_manufactured_flow_is_mixed_subsonic_and_supersonic():
    X, Y = np.meshgrid(np.linspace(0, 1, 41), np.linspace(0, 1.5, 61))
    rho, u, v, p = mms.exact_state(X.ravel(), Y.ravel())
    M = np.hypot(u, v) / np.sqrt(1.4 * p / rho)
    assert rho.min() > 0 and p.min() > 0
    assert M.min() < 0.9 and M.max() > 1.1


def test_no_limiter_gives_psi_one():
    g = FVGeometry(rectangle_mesh(4, 4))
    W = np.random.default_rng(0).uniform(1, 2, (4, g.n_cells))
    grad = np.random.default_rng(1).normal(size=(4, 2, g.n_cells))
    assert np.all(limiter_factors(g, grad, W, np.ones((4, g.n_boundary)), NO_LIMITER) == 1.0)


@pytest.mark.parametrize("kind,axi", [("quads", False), ("triangles", False), ("quads", True)])
def test_second_order_on_small_meshes(kind, axi):
    runs = mms.study(kind, levels=(8, 16), axisymmetric=axi, residual_drop=7.0)
    p = mms.observed_orders(runs)[0]
    assert p.min() > 1.8, p


def test_first_order_scheme_is_first_order():
    runs = mms.study("triangles", levels=(8, 16), order=1, residual_drop=7.0)
    p = mms.observed_orders(runs)[0]
    assert 0.7 < p.min() and p.max() < 1.3, p


# ---- GCI ------------------------------------------------------------------------------------------

def test_gci_recovers_order_and_limit_of_an_exact_power_law():
    h = (0.01, 0.02, 0.04)
    phi = [1.0 + 0.3 * hi**2 for hi in h]
    g = gci.three_mesh(h, phi)
    assert abs(g.p - 2.0) < 1e-9
    assert abs(g.extrapolated - 1.0) < 1e-12
    assert abs(g.asymptotic_ratio - 1.0) < 1e-3 and g.in_asymptotic_range   # = phi1/phi2 for an exact power law
    assert g.gci_fine == pytest.approx(1.25 * abs(phi[1] - phi[0]) / phi[0] / 3.0)


def test_gci_with_non_constant_refinement_ratio():
    h = (1.0, 1.5, 2.7)
    phi = [5.0 - 0.2 * hi**1.6 for hi in h]
    g = gci.three_mesh(h, phi)
    assert g.p == pytest.approx(1.6, abs=1e-8)
    assert g.extrapolated == pytest.approx(5.0, abs=1e-8)


def test_gci_flags_oscillatory_convergence_and_bad_input():
    g = gci.three_mesh((1, 2, 4), (1.0, 1.1, 0.95))
    assert g.oscillatory and not g.in_asymptotic_range
    with pytest.raises(ValueError):
        gci.three_mesh((4, 2, 1), (1, 2, 3))
    with pytest.raises(ValueError):
        gci.three_mesh((1, 2, 4), (1.0, 1.0, 2.0))


def test_two_mesh_gci_and_observed_order_from_known_errors():
    g = gci.two_mesh((0.5, 1.0), (1.0 + 0.25, 1.0 + 1.0), p=2.0)
    assert g.extrapolated == pytest.approx(1.0)
    assert gci.observed_order([4, 2, 1], [16.0, 4.0, 1.0]) == pytest.approx([2.0, 2.0])
    assert "observed order" in g.summary()
    assert math.isfinite(g.gci_fine)

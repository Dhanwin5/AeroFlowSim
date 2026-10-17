"""Tests for aeroflowsim/euler1d.py on its own (no case involved)."""

import numpy as np

from aeroflowsim.euler1d import (cfl_time_step, conserved_to_primitive, euler_flux, flux_divergence,
                          hllc_flux, minmod, primitive_to_conserved, ssp_rk2_step)

GAMMA = 1.4  # [-]


def test_uniform_flow_stays_exactly_uniform():
    # Air-like uniform flow: rho = 1.2 kg/m³, u = 50 m/s, p = 1e5 Pa, on 50 cells of 1 cm.
    n, dx = 50, 0.01                                   # [-], [m]
    W = np.array([np.full(n, 1.2), np.full(n, 50.0), np.full(n, 1.0e5)])
    U0 = primitive_to_conserved(W, GAMMA)
    U = U0.copy()
    rhs = lambda V: flux_divergence(V, dx, GAMMA)
    for _ in range(20):
        U = ssp_rk2_step(U, cfl_time_step(U, dx, GAMMA, 0.5), rhs)
    # Every face sees identical states, so every face flux is the same number and the
    # flux differences are exactly zero: no change at all, not even round-off.
    assert np.array_equal(U, U0)


def test_primitive_conserved_round_trip():
    W = np.array([[1.0, 0.125, 2.5], [0.0, -30.0, 400.0], [1.0e5, 1.0e4, 3.0e5]])
    assert np.allclose(conserved_to_primitive(primitive_to_conserved(W, GAMMA), GAMMA), W,
                       rtol=1e-14, atol=1e-10)


def test_hllc_is_consistent_with_physical_flux():
    # Same state on both sides -> numerical flux equals the physical flux.
    # Includes subsonic, supersonic right-moving and supersonic left-moving states.
    W = np.array([[1.2, 1.2, 1.2], [50.0, 600.0, -600.0], [1.0e5, 1.0e5, 1.0e5]])
    assert np.allclose(hllc_flux(W, W, GAMMA), euler_flux(W, GAMMA), rtol=1e-12)


def test_minmod():
    a = np.array([1.0, -1.0, 2.0, 1.0, 0.0])
    b = np.array([2.0, -3.0, -1.0, 0.5, 1.0])
    assert np.array_equal(minmod(a, b), [1.0, -1.0, 0.0, 0.5, 0.0])

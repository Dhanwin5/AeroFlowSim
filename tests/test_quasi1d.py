"""Tests of the quasi-1D finite-volume operator and the nozzle boundary conditions."""

import numpy as np
import pytest

from aeroflowsim.euler1d import N_GHOST, flux_divergence, primitive_to_conserved, transmissive_ghosts
from aeroflowsim.gasdynamics import p0_over_p, t0_over_t
from aeroflowsim.quasi1d import inlet_state, local_time_steps, nozzle_boundary, quasi1d_rhs

G, R = 1.4, 296.8   # N2


def cone(n=50):
    x = np.linspace(0.0, 1e-2, n + 1)          # faces [m]
    A = np.pi * (1e-3 + 0.3 * x) ** 2          # face areas [m²]
    volumes = 0.5 * (A[1:] + A[:-1]) * np.diff(x)
    return x, A, volumes


def test_gas_at_rest_in_a_cone_stays_exactly_at_rest():
    x, A, V = cone()
    p0, T0 = 5e5, 293.15
    W = np.array([np.full(50, p0 / (R * T0)), np.zeros(50), np.full(50, p0)])
    U = primitive_to_conserved(W, G)
    rhs = quasi1d_rhs(U, A, V, G, nozzle_boundary(p0, T0, p0, G, R))
    assert np.all(rhs == 0.0)   # exactly, not approximately


def test_constant_area_reduces_to_plain_euler():
    rng = np.random.default_rng(1)
    n, dx = 40, 1e-3
    W = np.array([1.0 + 0.1 * rng.random(n), 50 * rng.random(n), 1e5 * (1 + 0.1 * rng.random(n))])
    U = primitive_to_conserved(W, G)
    A = np.full(n + 1, 2e-6)
    rhs = quasi1d_rhs(U, A, A[:-1] * dx, G, transmissive_ghosts)
    assert np.allclose(rhs, flux_divergence(U, dx, G), rtol=1e-12, atol=1e-6)


def test_inlet_state_keeps_total_conditions():
    rho, u, p = inlet_state(100.0, 5e5, 293.15, G, R)
    T = p / (rho * R)
    M = u / np.sqrt(G * R * T)
    assert T * t0_over_t(M, G) == pytest.approx(293.15, rel=1e-12)
    assert p * p0_over_p(M, G) == pytest.approx(5e5, rel=1e-12)


def test_outlet_switches_between_back_pressure_and_extrapolation():
    bc = nozzle_boundary(5e5, 293.15, 1e3, G, R)
    c = np.sqrt(G * 1e4 / 0.1)
    for u, expect_p in ((0.5 * c, 1e3), (2.0 * c, 1e4)):
        W = np.array([[0.1, 0.1], [u, u], [1e4, 1e4]])
        Wg = bc(W)
        assert Wg.shape == (3, 2 + 2 * N_GHOST)
        assert Wg[2, -1] == expect_p and Wg[1, -1] == u


def test_local_time_steps_one_per_cell():
    W = np.array([[1.0, 1.0], [0.0, 300.0], [1e5, 1e5]])
    dt = local_time_steps(primitive_to_conserved(W, 1.4), np.array([1e-3, 2e-3]), 1.4, 0.5)
    c = np.sqrt(1.4e5)
    assert dt == pytest.approx([0.5e-3 / c, 0.5 * 2e-3 / (300 + c)])

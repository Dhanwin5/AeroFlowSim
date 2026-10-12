"""Tests for core/riemann_exact.py against the published values in Toro, Table 4.2."""

import numpy as np
import pytest

from core.riemann_exact import exact_solution, star_state, wave_structure

GAMMA = 1.4  # [-]


@pytest.mark.parametrize("left, right, p_star, u_star, rho_star_l, rho_star_r", [
    # Test 1 (Sod)
    ((1.0, 0.0, 1.0), (0.125, 0.0, 0.1), 0.30313, 0.92745, 0.42632, 0.26557),
    # Test 2 ("123 problem": two strong rarefactions)
    ((1.0, -2.0, 0.4), (1.0, 2.0, 0.4), 0.00189, 0.0, 0.02185, 0.02185),
    # Test 3 (strong shock)
    ((1.0, 0.0, 1000.0), (1.0, 0.0, 0.01), 460.894, 19.5975, 0.57506, 5.99924),
])
def test_star_values_match_toro_table(left, right, p_star, u_star, rho_star_l, rho_star_r):
    w = wave_structure(left, right, GAMMA)
    # Toro prints 3-6 significant digits; allow half a unit in the last printed digit.
    assert w["p_star"] == pytest.approx(p_star, rel=2e-5, abs=5e-6)
    assert w["u_star"] == pytest.approx(u_star, abs=5e-5)
    assert w["rho_star_L"] == pytest.approx(rho_star_l, abs=5e-6)
    assert w["rho_star_R"] == pytest.approx(rho_star_r, abs=5e-6)


def test_sod_wave_types_and_far_field():
    left, right = (1.0, 0.0, 1.0), (0.125, 0.0, 0.1)
    w = wave_structure(left, right, GAMMA)
    assert w["left_wave"] == "rarefaction" and w["right_wave"] == "shock"
    rho, u, p = exact_solution(left, right, GAMMA, [0.0, 1.0], 0.5, 0.2)
    assert np.allclose([rho[0], u[0], p[0]], left)
    assert np.allclose([rho[1], u[1], p[1]], right)


def test_identical_states_give_no_waves():
    p, u = star_state((1.2, 50.0, 1e5), (1.2, 50.0, 1e5), GAMMA)
    assert p == pytest.approx(1e5, rel=1e-12)
    assert u == pytest.approx(50.0, rel=1e-12)


def test_vacuum_is_rejected():
    with pytest.raises(ValueError):
        star_state((1.0, -20.0, 0.4), (1.0, 20.0, 0.4), GAMMA)

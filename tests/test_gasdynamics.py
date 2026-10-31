# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the isentropic and normal-shock relations against textbook tables (gamma = 1.4)."""

import math

import pytest

from aeroflowsim import gasdynamics as gd

G = 1.4


def test_isentropic_ratios_at_mach_2():
    assert gd.t0_over_t(2.0, G) == pytest.approx(1.8)
    assert gd.p0_over_p(2.0, G) == pytest.approx(7.824, rel=1e-4)
    assert gd.rho0_over_rho(2.0, G) == pytest.approx(4.347, rel=1e-3)
    assert gd.area_ratio(2.0, G) == pytest.approx(1.6875, rel=1e-4)
    assert gd.area_ratio(1.0, G) == pytest.approx(1.0)


@pytest.mark.parametrize("M", [0.05, 0.3, 0.9, 1.5, 2.49, 4.0])
def test_mach_from_area_ratio_round_trip(M):
    ratio = gd.area_ratio(M, G)
    assert gd.mach_from_area_ratio(ratio, G, supersonic=M > 1.0) == pytest.approx(M, rel=1e-10)


def test_mach_from_p0_over_p_round_trip():
    assert gd.mach_from_p0_over_p(gd.p0_over_p(3.0, G), G) == pytest.approx(3.0, rel=1e-12)
    assert gd.mach_from_p0_over_p(1.0, G) == 0.0


def test_normal_shock_at_mach_2():
    s = gd.normal_shock(2.0, G)
    assert s["M2"] == pytest.approx(0.5774, rel=1e-4)
    assert s["p2_p1"] == pytest.approx(4.5)
    assert s["rho2_rho1"] == pytest.approx(2.6667, rel=1e-4)
    assert s["T2_T1"] == pytest.approx(1.6875, rel=1e-4)
    assert s["p02_p01"] == pytest.approx(0.7209, rel=1e-4)
    with pytest.raises(ValueError):
        gd.normal_shock(0.8, G)


def test_choked_mass_flow_of_default_thruster():
    A_star = math.pi * 0.14e-3 ** 2                      # [m²]
    mdot = gd.choked_mass_flow(5e5, 293.15, A_star, G, 296.8)
    assert mdot == pytest.approx(71.5e-6, rel=2e-3)


def test_nozzle_regimes_for_default_thruster():
    ae = (0.911 / 0.280) ** 2
    assert gd.nozzle_flow_regime(5e5, 1e3, ae, G)["regime"] == "supersonic exit"
    assert gd.nozzle_flow_regime(5e5, 5e5, ae, G)["regime"] == "subsonic"
    shock = gd.nozzle_flow_regime(5e5, 2.5e5, ae, G)
    assert shock["regime"] == "shock in nozzle"
    assert shock["area_shock"] == pytest.approx(2.61, rel=5e-3)
    M1 = gd.mach_from_area_ratio(shock["area_shock"], G, supersonic=True)
    assert M1 == pytest.approx(2.49, rel=5e-3)


# ---- oblique shocks, Prandtl-Meyer, shock-expansion, Taylor-Maccoll (Post-processing and alpha release stage) ----------------------------

def test_oblique_shock_matches_the_wedge_reference():
    s = gd.oblique_shock(2.0, math.radians(10.0), 1.4)
    assert math.degrees(s["beta"]) == pytest.approx(39.314, abs=1e-3)
    assert s["p2_p1"] == pytest.approx(1.7066, abs=1e-4) and s["M2"] == pytest.approx(1.6405, abs=1e-4)
    with pytest.raises(ValueError, match="detaches"):
        gd.oblique_shock_angle(2.0, math.radians(30.0), 1.4)


def test_prandtl_meyer_function_and_expansion():
    # nu(2) = 26.38 deg (Anderson 2003, Table A.5); nu(1) = 0; the inverse is exact
    assert math.degrees(gd.prandtl_meyer(2.0, 1.4)) == pytest.approx(26.3798, abs=1e-3)
    assert gd.prandtl_meyer(1.0, 1.4) == 0.0
    assert gd.mach_from_prandtl_meyer(gd.prandtl_meyer(3.1, 1.4), 1.4) == pytest.approx(3.1, rel=1e-12)
    e = gd.expansion(2.0, math.radians(10.0), 1.4)
    assert e["p2_p1"] == pytest.approx(gd.p0_over_p(2.0, 1.4) / gd.p0_over_p(e["M2"], 1.4))


def test_diamond_airfoil_symmetry_and_linear_theory_limit():
    d0 = gd.diamond_airfoil(2.0, 0.1, 0.0, 1.4)
    assert d0["Cl"] == pytest.approx(0.0, abs=1e-14)
    assert d0["p"]["upper_front"] == d0["p"]["lower_front"]
    # thin airfoil: Ackeret theory Cl = 4 alpha / sqrt(M² - 1), Cd = 4 (alpha² + (t/c)²) / sqrt(M² - 1)
    thin = gd.diamond_airfoil(3.0, 0.01, 1.0, 1.4)
    a, b = math.radians(1.0), math.sqrt(8.0)
    assert thin["Cl"] == pytest.approx(4 * a / b, rel=0.03)
    assert thin["Cd"] == pytest.approx(4 * (a * a + 0.01**2) / b, rel=0.05)


@pytest.mark.parametrize("theta_s,mach,cp,theta_w", [
    # Sims (1964), NASA SP-3004: Table 9 (surface Cp) and Table 11 (shock angle [rad])
    (15.0, 2.0, 0.2022339, 0.59192180),
    (10.0, 2.0, 0.1044583, 0.54464827),
    (20.0, 2.0, 0.3255312, 0.65966167),
    (15.0, 3.0, 0.17310135, 0.44085123),
    (15.0, 1.5, 0.2400313, 0.78592365),
])
def test_taylor_maccoll_against_the_tables_of_sims(theta_s, mach, cp, theta_w):
    r = gd.taylor_maccoll(mach, math.radians(theta_s), 1.4)
    assert r["Cp"] == pytest.approx(cp, rel=1e-3)
    assert r["beta"] == pytest.approx(theta_w, abs=2e-5)

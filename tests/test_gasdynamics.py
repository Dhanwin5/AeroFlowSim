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

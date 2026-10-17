# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Classical 1D gas-dynamics relations (calorically perfect gas): isentropic flow and normal shocks.

Used as the "theory" for nozzle cases (and their tests). Pure functions, nothing here imports the GUI.
All ratios are dimensionless; M is the Mach number, gamma = cp/cv.

    isentropic:   T0/T = 1 + (gamma-1)/2 M²,   p0/p = (T0/T)^(gamma/(gamma-1)),   rho0/rho = (T0/T)^(1/(gamma-1))
    area-Mach:    A/A* = (1/M) [ (2/(gamma+1)) (1 + (gamma-1)/2 M²) ]^((gamma+1)/(2(gamma-1)))
    normal shock: M2² = (1 + (gamma-1)/2 M1²) / (gamma M1² - (gamma-1)/2), etc. (Anderson, ch. 3)
"""

import math

from scipy.optimize import brentq


# ---- isentropic flow ---------------------------------------------------------------------

def t0_over_t(M, gamma):
    """Total-to-static temperature ratio T0/T [-]."""
    return 1.0 + 0.5 * (gamma - 1.0) * M**2


def p0_over_p(M, gamma):
    """Total-to-static pressure ratio p0/p [-]."""
    return t0_over_t(M, gamma) ** (gamma / (gamma - 1.0))


def rho0_over_rho(M, gamma):
    """Total-to-static density ratio rho0/rho [-]."""
    return t0_over_t(M, gamma) ** (1.0 / (gamma - 1.0))


def area_ratio(M, gamma):
    """Isentropic area ratio A/A* [-] for Mach number M (A* = sonic throat area)."""
    exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))
    return (2.0 / (gamma + 1.0) * t0_over_t(M, gamma)) ** exponent / M


def mach_from_area_ratio(ratio, gamma, supersonic):
    """Mach number for a given A/A* >= 1: the supersonic or the subsonic solution."""
    if ratio < 1.0:
        raise ValueError(f"A/A* = {ratio} is below 1: no isentropic solution exists.")
    if ratio == 1.0:
        return 1.0
    f = lambda M: area_ratio(M, gamma) - ratio
    if supersonic:
        return brentq(f, 1.0, 100.0, xtol=1e-14, rtol=1e-14)
    return brentq(f, 1e-12, 1.0, xtol=1e-16, rtol=1e-14)


def mach_from_p0_over_p(ratio, gamma):
    """Mach number from p0/p >= 1 (inverse of p0_over_p)."""
    return math.sqrt(2.0 / (gamma - 1.0) * (max(ratio, 1.0) ** ((gamma - 1.0) / gamma) - 1.0))


def choked_mass_flow(p0, T0, A_star, gamma, R):
    """Mass flow [kg/s] through a sonic throat A_star [m²] from total p0 [Pa] and T0 [K]."""
    exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))
    return p0 * A_star / math.sqrt(R * T0) * math.sqrt(gamma) * (2.0 / (gamma + 1.0)) ** exponent


# ---- normal shock ------------------------------------------------------------------------

def normal_shock(M1, gamma):
    """Jump conditions across a normal shock with upstream Mach M1 > 1.

    Returns a dict: M2, p2_p1, T2_T1, rho2_rho1, p02_p01 (all dimensionless).
    """
    if M1 <= 1.0:
        raise ValueError(f"A normal shock needs a supersonic upstream Mach number (got {M1}).")
    g = gamma
    M2 = math.sqrt((1.0 + 0.5 * (g - 1.0) * M1**2) / (g * M1**2 - 0.5 * (g - 1.0)))
    p2_p1 = 1.0 + 2.0 * g / (g + 1.0) * (M1**2 - 1.0)
    rho2_rho1 = (g + 1.0) * M1**2 / (2.0 + (g - 1.0) * M1**2)
    T2_T1 = p2_p1 / rho2_rho1
    p02_p01 = p2_p1 * p0_over_p(M2, g) / p0_over_p(M1, g)   # = (p02/p2)(p2/p1)(p1/p01)
    return {"M2": M2, "p2_p1": p2_p1, "T2_T1": T2_T1, "rho2_rho1": rho2_rho1, "p02_p01": p02_p01}


# ---- which flow does a nozzle with a given back pressure have? -------------------------------

def exit_pressure_with_shock(p0, area_shock, area_exit, gamma):
    """Exit pressure [Pa] when a normal shock stands where A/A* = area_shock (A* = throat area).

    Upstream of the shock: supersonic isentropic flow. Across it the total pressure drops by
    p02/p01, so downstream the flow behaves as if it came through a larger sonic throat
    A*2 = A* / (p02/p01); the exit is on the subsonic branch of that new area ratio.
    """
    M1 = mach_from_area_ratio(area_shock, gamma, supersonic=True)
    p02 = p0 * normal_shock(M1, gamma)["p02_p01"]
    M_exit = mach_from_area_ratio(area_exit * p02 / p0, gamma, supersonic=False)
    return p02 / p0_over_p(M_exit, gamma)


def nozzle_flow_regime(p0, p_back, area_exit, gamma):
    """Classify the flow in a converging-diverging nozzle with exit area ratio A_e/A* = area_exit.

    Returns a dict with "regime":
      "subsonic"         back pressure too high to choke: subsonic everywhere (no shock)
      "shock in nozzle"  choked, normal shock inside the divergent part; also "area_shock" = A_s/A*
      "supersonic exit"  choked, supersonic all the way to the exit (any shocks/expansions are outside)
    """
    p_subsonic = p0 / p0_over_p(mach_from_area_ratio(area_exit, gamma, False), gamma)  # choked, subsonic exit
    p_shock_at_exit = exit_pressure_with_shock(p0, area_exit, area_exit, gamma)
    if p_back >= p_subsonic:
        return {"regime": "subsonic"}
    if p_back > p_shock_at_exit:
        # Exit pressure falls from p_subsonic (shock at the throat) to p_shock_at_exit (shock at the
        # exit) as the shock moves downstream, so there is exactly one shock position.
        f = lambda a: exit_pressure_with_shock(p0, a, area_exit, gamma) - p_back
        area_shock = brentq(f, 1.0 + 1e-12, area_exit, xtol=1e-13, rtol=1e-13)
        return {"regime": "shock in nozzle", "area_shock": area_shock}
    return {"regime": "supersonic exit"}

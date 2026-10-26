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


# ---- oblique shocks, Prandtl-Meyer expansions, shock-expansion theory, Taylor-Maccoll cones -----------------

def oblique_shock_angle(M1, theta, gamma, weak=True):
    """Shock angle beta [rad] of an attached oblique shock turning the flow by theta [rad] (theta-beta-M relation,
    tan(theta) = 2 cot(beta) (M1² sin²beta - 1) / (M1² (gamma + cos 2 beta) + 2); Anderson 2003, eq. 4.17).
    Weak solution by default. Raises ValueError if the shock would detach (theta above the maximum)."""
    from scipy.optimize import brentq

    def f(beta):
        return (2.0 / math.tan(beta) * (M1**2 * math.sin(beta)**2 - 1.0) / (M1**2 * (gamma + math.cos(2 * beta)) + 2.0)
                - math.tan(theta))
    mu = math.asin(1.0 / M1)
    if theta == 0.0:
        return mu
    betas = [mu + (math.pi / 2 - mu) * k / 2000 for k in range(1, 2000)]
    values = [f(b) for b in betas]
    k_max = max(range(len(values)), key=lambda k: values[k])
    if values[k_max] < 0.0:
        raise ValueError(f"The shock detaches: {math.degrees(theta):.2f} deg is more than the largest turning angle "
                         f"at Mach {M1:g}.")
    if weak:
        return brentq(f, mu + 1e-12, betas[k_max], xtol=1e-14)
    return brentq(f, betas[k_max], math.pi / 2 - 1e-12, xtol=1e-14)


def oblique_shock(M1, theta, gamma):
    """{beta [rad], M2, p2_p1} of the weak oblique shock turning the flow by theta [rad] (compression)."""
    if theta <= 0.0:
        return {"beta": math.asin(1.0 / M1), "M2": M1, "p2_p1": 1.0}
    beta = oblique_shock_angle(M1, theta, gamma)
    ns = normal_shock(M1 * math.sin(beta), gamma)
    return {"beta": beta, "M2": ns["M2"] / math.sin(beta - theta), "p2_p1": ns["p2_p1"]}


def prandtl_meyer(M, gamma):
    """Prandtl-Meyer function nu(M) [rad] (Anderson 2003, eq. 4.44)."""
    a = math.sqrt((gamma + 1.0) / (gamma - 1.0))
    return a * math.atan(math.sqrt(M * M - 1.0) / a) - math.atan(math.sqrt(M * M - 1.0))


def mach_from_prandtl_meyer(nu, gamma):
    """Mach number with Prandtl-Meyer angle nu [rad]."""
    from scipy.optimize import brentq
    return brentq(lambda M: prandtl_meyer(M, gamma) - nu, 1.0 + 1e-12, 100.0, xtol=1e-14)


def expansion(M1, turn, gamma):
    """{M2, p2_p1} after an isentropic Prandtl-Meyer expansion by turn [rad] > 0."""
    M2 = mach_from_prandtl_meyer(prandtl_meyer(M1, gamma) + turn, gamma)
    return {"M2": M2, "p2_p1": p0_over_p(M1, gamma) / p0_over_p(M2, gamma)}


def _turn(M, p_ratio, delta, gamma):
    """Flow turned by delta [rad] (> 0 compression, < 0 expansion): new (M, cumulative p ratio)."""
    if delta > 0.0:
        s = oblique_shock(M, delta, gamma)
        return s["M2"], p_ratio * s["p2_p1"]
    if delta < 0.0:
        e = expansion(M, -delta, gamma)
        return e["M2"], p_ratio * e["p2_p1"]
    return M, p_ratio


def diamond_airfoil(M, thickness_ratio, alpha_deg, gamma, x_max=0.5):
    """Shock-expansion theory of a diamond (double-wedge) airfoil of chord 1 (Anderson 2003, sec. 4.15; Liepmann
    and Roshko 1957, sec. 4.17): oblique shock or expansion at the leading edge and a Prandtl-Meyer expansion at
    the shoulder, on each surface; the trailing-edge waves do not act on the airfoil.

    Returns {p: {upper_front, upper_rear, lower_front, lower_rear: p/p_inf}, Cl, Cd, Cm_le (about the leading
    edge, nose-up positive)}, coefficients based on the chord (q_inf = gamma p M² / 2)."""
    t = thickness_ratio
    a = math.radians(alpha_deg)
    e1 = math.atan(t / 2 / x_max)                 # front face angle to the chord
    e2 = math.atan(t / 2 / (1.0 - x_max))         # rear face angle
    p = {}
    M_u, p_u = _turn(M, 1.0, e1 - a, gamma)       # upper front face: turned by (e1 - alpha)
    p["upper_front"] = p_u
    M_u, p_u = _turn(M_u, p_u, -(e1 + e2), gamma)
    p["upper_rear"] = p_u
    M_l, p_l = _turn(M, 1.0, e1 + a, gamma)
    p["lower_front"] = p_l
    M_l, p_l = _turn(M_l, p_l, -(e1 + e2), gamma)
    p["lower_rear"] = p_l
    q_over_p = 0.5 * gamma * M * M
    faces = {"upper_front": ((0.0, 0.0), (x_max, t / 2)), "upper_rear": ((x_max, t / 2), (1.0, 0.0)),
             "lower_front": ((0.0, 0.0), (x_max, -t / 2)), "lower_rear": ((x_max, -t / 2), (1.0, 0.0))}
    Fx = Fy = Mz = 0.0
    for name, ((x0, y0), (x1, y1)) in faces.items():
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        n = (-dy / L, dx / L) if name.startswith("upper") else (dy / L, -dx / L)   # outward normal of the body
        f = (p[name] - 1.0) * L                   # (p - p_inf) / p_inf x face length; force on the body = -f n
        fx, fy = -f * n[0], -f * n[1]
        xm, ym = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        Fx, Fy = Fx + fx, Fy + fy
        Mz += xm * fy - ym * fx
    D = Fx * math.cos(a) + Fy * math.sin(a)
    Lf = -Fx * math.sin(a) + Fy * math.cos(a)
    return {"p": p, "Cl": Lf / q_over_p, "Cd": D / q_over_p, "Cm_le": -Mz / q_over_p}


def taylor_maccoll(M, cone_half_angle, gamma):
    """Supersonic flow round a circular cone at zero incidence (Taylor and Maccoll 1933; Anderson 2003, sec. 10.4).

    Behind the attached conical shock the flow depends on the polar angle theta only. With the velocity scaled by
    the maximum speed (V' = V / V_max), radial and normal components Vr and Vt = dVr/dtheta satisfy

        (g-1)/2 (1 - Vr² - Vt²) (2 Vr + Vt cot(theta) + dVt/dtheta) - Vt (Vr Vt + Vt dVt/dtheta) = 0.

    Shooting: for a trial shock angle beta the oblique-shock relations give the state just behind the shock; the
    equation is integrated from theta = beta towards the cone until Vt = 0, which is the cone surface. beta is found
    by root finding so that this happens at the given half-angle [rad].
    Returns {beta [rad], Mc (surface Mach number), pc_pinf, Cp = (pc - p_inf) / q_inf}.
    """
    from scipy.integrate import solve_ivp
    from scipy.optimize import brentq
    g = gamma

    def rhs(theta, y):
        vr, vt = y
        a = 0.5 * (g - 1.0) * (1.0 - vr * vr - vt * vt)
        dvt = (vt * vt * vr - a * (2.0 * vr + vt / math.tan(theta))) / (a - vt * vt)
        return [vt, dvt]

    def surface(beta):
        Mn1 = M * math.sin(beta)
        ns = normal_shock(Mn1, g)
        delta = math.atan(2.0 / math.tan(beta) * (Mn1**2 - 1.0) / (M**2 * (g + math.cos(2 * beta)) + 2.0))
        M2 = ns["M2"] / math.sin(beta - delta)
        V = (2.0 / ((g - 1.0) * M2 * M2) + 1.0) ** -0.5          # V / V_max
        y0 = [V * math.cos(beta - delta), -V * math.sin(beta - delta)]

        def wall(th, y):
            return y[1]
        wall.terminal, wall.direction = True, 1
        sol = solve_ivp(rhs, (beta, 1e-4), y0, events=wall, rtol=1e-12, atol=1e-14, max_step=1e-3)
        if not sol.t_events[0].size:
            return -1.0, None, Mn1
        return float(sol.t_events[0][0]), float(sol.y_events[0][0][0]), Mn1

    mu = math.asin(1.0 / M)
    # weak solution: between the Mach angle and the shock angle of the largest cone that keeps the shock attached
    trial = [mu + (math.radians(89.0) - mu) * k / 60 for k in range(1, 61)]
    angles = [surface(t)[0] for t in trial]
    k_max = max(range(len(angles)), key=lambda k: angles[k])
    if angles[k_max] < cone_half_angle:
        raise ValueError(f"The shock detaches from a {math.degrees(cone_half_angle):.1f} deg cone at Mach {M:g}.")
    beta = brentq(lambda b: surface(b)[0] - cone_half_angle, mu + 1e-6, trial[k_max], xtol=1e-14)
    _, vc, Mn1 = surface(beta)
    Mc = math.sqrt(2.0 / ((g - 1.0) * (1.0 / (vc * vc) - 1.0)))
    p02_p01 = (((g + 1) * Mn1**2 / ((g - 1) * Mn1**2 + 2)) ** (g / (g - 1))
               * ((g + 1) / (2 * g * Mn1**2 - (g - 1))) ** (1 / (g - 1)))       # total-pressure ratio of the shock
    pc_pinf = p0_over_p(M, g) * p02_p01 / p0_over_p(Mc, g)
    return {"beta": beta, "Mc": Mc, "pc_pinf": pc_pinf, "Cp": (pc_pinf - 1.0) / (0.5 * g * M * M)}

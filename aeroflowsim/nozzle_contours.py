# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Nozzle wall contours from the literature: the Rao bell (thrust-optimised parabola) and the planar
minimum-length nozzle by the Method of Characteristics.

Both return a WallProfile (aeroflowsim/geometry.py: wall radius or half-height r(x), SI metres), the same object
every other geometry source gives, so the nozzle cases and the shape library use them without caring where
they came from.

1. Rao bell (Rao 1960, "Approximation of optimum thrust nozzle contour"; chart angles from Huzel and Huang, "Modern Engineering for Design of
   Liquid-Propellant Rocket Engines", AIAA 1992, plot 4-16). Contour, from upstream to the exit:
       upstream throat arc      radius RU_RATIO x Rt   (1.5 Rt: Seitzman, Georgia Tech AE 6450 notes)
       downstream throat arc    radius RD_RATIO x Rt   (0.382 Rt: same), ends at point N where the wall angle
                                is theta_n
       parabola N -> E          written as a quadratic Bezier curve: P0 = N, P2 = E (the exit), and the control
                                point P1 is where the tangent at N (angle theta_n) meets the tangent at E
                                (angle theta_e). It leaves N with slope tan(theta_n) and arrives at E with
                                slope tan(theta_e).
   The length is a fraction Lf of a 15 degree half-angle cone with the same throat and exit radius:
       L15 = Rt (sqrt(eps) - 1) / tan(15 deg)   (axisymmetric; eps = (r_e / Rt)²)
   theta_n and theta_e come from the digitised chart (below) unless the user gives them.

2. Minimum-length nozzle by the Method of Characteristics (Anderson, "Modern Compressible Flow", 3rd ed.,
   chapter 11, planar flow). A sharp corner at the sonic throat turns the flow by theta_max = nu(M_e) / 2 in a
   centred expansion fan, which the wall then straightens (turns back to axial) at the exit. With the fan cut
   into n characteristics of angle theta_k = k theta_max / n (k = 1 ... n) the Riemann invariants give every
   node by algebra (nu = Prandtl-Meyer angle, theta = flow angle):
       K- = theta + nu is constant along a left-running characteristic C- (slope theta - mu),
       K+ = theta - nu is constant along a right-running characteristic C+ (slope theta + mu).
   Node (k, m) is where C- number k meets C+ number m (which is the reflection of C- number m off the axis):
       theta = theta_k - theta_m,   nu = theta_k + theta_m          (m = 0: the corner, m = k: on the axis).
   Positions follow from intersecting the two straight-line characteristic segments with the slopes averaged
   between their end points (second order). The wall point m is where C+ number m, continued past the last
   C-, reaches the wall; the wall angle there is the flow angle of its node (n, m).
"""

import math

import numpy as np

from aeroflowsim import gasdynamics as gd
from aeroflowsim.geometry import WallProfile

RU_RATIO = 1.5      # radius of the upstream throat arc / throat radius [-] (Seitzman, Georgia Tech AE 6450)
RD_RATIO = 0.382    # radius of the downstream throat arc / throat radius [-] (same source)
CONE_REFERENCE_DEG = 15.0   # the length fraction of a bell refers to a cone of this half-angle [deg]

# ---- Rao angles: theta_n (end of the downstream throat arc) and theta_e (exit) [deg] ----------------------------
# Digitised from Huzel and Huang, plot 4-16 (p. 77 of the 1992 edition), by D. Sd (pygasflow, plot-4-16-data/*.csv,
# fetched 27 Oct 2026): every second digitised point, rounded to 0.01. They are READ OFF A CHART, so good to roughly
# +-0.5 deg. Rows: (area ratio eps = exit area / throat area, angle in degrees); one table per length fraction Lf.
RAO_THETA_N = {
    0.6: ((4.66, 31.18), (6.24, 32.33), (7.74, 33.33), (9.85, 34.15), (12.48, 35.09), (15.64, 35.81), (18.80, 36.42),
          (22.03, 36.86), (25.41, 37.24), (28.87, 37.63), (32.93, 37.96), (37.52, 38.35), (42.78, 38.51),
          (50.38, 38.84)),
    0.7: ((5.11, 29.14), (7.29, 29.91), (9.77, 30.96), (13.23, 32.11), (16.69, 33.16), (20.15, 33.93), (24.14, 34.54),
          (28.87, 35.09), (34.59, 35.59), (40.53, 35.81), (46.69, 36.14), (50.38, 36.19)),
    0.8: ((5.11, 27.04), (8.35, 28.36), (12.18, 29.74), (16.62, 31.07), (20.75, 31.84), (25.19, 32.56), (29.32, 33.05),
          (34.44, 33.44), (40.90, 33.71), (48.05, 34.04), (50.38, 34.04)),
    0.9: ((5.19, 25.88), (8.35, 27.15), (12.63, 28.64), (17.67, 29.96), (22.78, 30.90), (27.59, 31.62), (33.31, 32.06),
          (38.72, 32.39), (45.79, 32.83), (50.38, 32.89)),
    1.0: ((5.19, 25.00), (8.12, 26.10), (12.33, 27.37), (16.77, 28.47), (21.65, 29.47), (27.59, 30.29), (33.31, 30.96),
          (39.17, 31.45), (46.84, 31.89), (50.30, 31.95)),
}
RAO_THETA_E = {
    0.6: ((4.74, 17.39), (8.80, 15.62), (14.81, 14.25), (20.68, 13.36), (25.71, 12.92), (32.26, 12.48),
          (38.80, 12.26), (50.53, 12.10)),
    0.7: ((4.74, 14.91), (8.80, 13.31), (13.23, 12.32), (18.05, 11.54), (23.76, 10.94), (30.00, 10.50),
          (36.02, 10.22), (45.04, 10.00), (50.53, 10.00)),
    0.8: ((4.74, 12.65), (8.95, 10.88), (14.59, 9.72), (20.53, 9.28), (27.44, 8.95), (34.14, 8.73), (41.43, 8.57),
          (48.12, 8.40), (50.38, 8.35)),
    0.9: ((4.74, 10.99), (8.72, 9.39), (12.93, 8.40), (17.67, 8.12), (22.56, 7.96), (28.12, 7.85), (34.81, 7.63),
          (43.01, 7.46), (50.53, 7.30)),
    1.0: ((4.81, 9.01), (8.57, 7.74), (13.01, 6.91), (18.05, 6.69), (23.46, 6.58), (31.65, 6.36), (38.95, 6.31),
          (48.20, 6.03), (50.53, 5.97)),
}
RAO_EPS_RANGE = (5.2, 50.3)         # area ratios covered by all five tables [-]
RAO_LF_RANGE = (0.6, 1.0)           # length fractions covered [-]


def rao_angles(area_ratio, length_fraction):
    """(theta_n, theta_e) [deg] from the digitised Huzel-Huang chart, linear in the area ratio and in Lf.

    Raises ValueError outside the charted range (no extrapolation): give theta_n and theta_e yourself there."""
    lo, hi = RAO_EPS_RANGE
    if not lo <= area_ratio <= hi:
        raise ValueError(f"The Rao chart covers area ratios {lo:g} to {hi:g}; yours is {area_ratio:g}. Type the "
                         "initial angle theta_n and the exit angle theta_e yourself.")
    if not RAO_LF_RANGE[0] <= length_fraction <= RAO_LF_RANGE[1]:
        raise ValueError(f"The Rao chart covers lengths of {RAO_LF_RANGE[0] * 100:.0f} to {RAO_LF_RANGE[1] * 100:.0f} % "
                         f"of a 15 degree cone; yours is {length_fraction * 100:g} %. Type theta_n and theta_e yourself.")
    fractions = sorted(RAO_THETA_N)
    out = []
    for table in (RAO_THETA_N, RAO_THETA_E):
        at_eps = [float(np.interp(area_ratio, *zip(*table[f]))) for f in fractions]
        out.append(float(np.interp(length_fraction, fractions, at_eps)))
    return out[0], out[1]


def bell_nozzle(r_throat, area_ratio, length_fraction=0.8, theta_n=None, theta_e=None, planar=False,
                upstream_ratio=RU_RATIO, downstream_ratio=RD_RATIO, inlet_arc_angle=30.0, n_points=60):
    """Rao bell nozzle as a WallProfile [m]; its throat is at x = 0.

    r_throat       throat radius (axisymmetric) or half-height (planar) [m]
    area_ratio     exit area / throat area (planar: exit height / throat height) [-]
    length_fraction  length of the diverging part as a fraction of a 15 degree cone with the same area ratio [-]
    theta_n, theta_e  wall angles at the start of the parabola and at the exit [deg]; None: the chart values
    inlet_arc_angle   how far the upstream throat arc is drawn [deg] (a design choice, not part of Rao's method)
    The profile gets marks "throat", "N" (start of the parabola) and "exit".
    """
    if r_throat <= 0.0 or area_ratio <= 1.0:
        raise ValueError("A bell nozzle needs a positive throat radius and an area ratio above 1.")
    if theta_n is None or theta_e is None:
        chart_n, chart_e = rao_angles(area_ratio, length_fraction)
        theta_n = chart_n if theta_n is None else theta_n
        theta_e = chart_e if theta_e is None else theta_e
    if not 0.0 < theta_e < theta_n < 89.0:
        raise ValueError(f"The angles must satisfy 0 < theta_e < theta_n < 89 deg (theta_n = {theta_n:g}, "
                         f"theta_e = {theta_e:g}).")
    ratio = area_ratio if planar else math.sqrt(area_ratio)      # exit radius / throat radius
    r_e = r_throat * ratio                                        # [m]
    L_cone = r_throat * (ratio - 1.0) / math.tan(math.radians(CONE_REFERENCE_DEG))   # 15 degree cone length [m]
    x_e = length_fraction * L_cone                                # [m]
    tn, te = math.radians(theta_n), math.radians(theta_e)
    R_u, R_d = upstream_ratio * r_throat, downstream_ratio * r_throat
    # upstream arc: circle centre (0, Rt + R_u); angle phi from the throat (0) back to -inlet_arc_angle
    phi = np.linspace(-math.radians(inlet_arc_angle), 0.0, max(n_points // 3, 8))[:-1]
    up = np.column_stack([R_u * np.sin(phi), r_throat + R_u * (1.0 - np.cos(phi))])
    # downstream arc: centre (0, Rt + R_d), from the throat to angle theta_n
    phi = np.linspace(0.0, tn, max(n_points // 3, 8))
    down = np.column_stack([R_d * np.sin(phi), r_throat + R_d * (1.0 - np.cos(phi))])
    N = down[-1]
    if x_e <= N[0] + 1e-9 * x_e:
        raise ValueError("The nozzle is too short for its throat arc: raise the length fraction or lower theta_n.")
    # quadratic Bezier N -> E with end slopes tan(theta_n), tan(theta_e)
    x1 = (r_e - N[1] + N[0] * math.tan(tn) - x_e * math.tan(te)) / (math.tan(tn) - math.tan(te))
    P0, P1, P2 = N, np.array([x1, N[1] + (x1 - N[0]) * math.tan(tn)]), np.array([x_e, r_e])
    if not N[0] < x1 < x_e:
        raise ValueError("These angles do not give a smooth parabola (the control point is outside the nozzle): "
                         "change theta_n, theta_e or the length fraction.")
    t = np.linspace(0.0, 1.0, n_points)[1:, None]
    bez = (1 - t)**2 * P0 + 2 * (1 - t) * t * P1 + t**2 * P2
    xy = np.vstack([up, down, bez])
    marks = [("throat", 0.0, r_throat), ("N", float(N[0]), float(N[1])), ("exit", x_e, r_e)]
    return WallProfile(xy[:, 0], xy[:, 1], interpolation="linear", marks=marks)


# ---- minimum-length nozzle by the Method of Characteristics --------------------------------------------------

def moc_min_length_nozzle(mach_exit, gamma, h_throat=1.0, n_chars=40):
    """Planar minimum-length nozzle: WallProfile of the half-height y(x) [m]; the sharp-corner throat is at x = 0.

    mach_exit  design exit Mach number (> 1) [-];  gamma  ratio of specific heats [-]
    h_throat   throat half-height [m] (the full throat height is twice this)
    n_chars    number of characteristics of the expansion fan: the wall has n_chars + 1 points. More is more exact
               (second order in 1 / n_chars).
    The wall starts at the throat corner (0, h) with the angle theta_max = nu(M_e) / 2.
    """
    if mach_exit <= 1.0:
        raise ValueError("The design exit Mach number must be above 1.")
    if gamma <= 1.0:
        raise ValueError("gamma must be above 1.")
    if n_chars < 3:
        raise ValueError("Use at least 3 characteristics.")
    nu_exit = gd.prandtl_meyer(mach_exit, gamma)
    theta_max = 0.5 * nu_exit
    n = int(n_chars)
    step = theta_max / n
    # Mach number and Mach angle for nu = j step (j = 0 ... 2 n): every node has nu = (k + m) step
    nu_table = np.arange(2 * n + 1) * step
    mach = np.array([1.0] + [gd.mach_from_prandtl_meyer(v, gamma) for v in nu_table[1:]])
    mu = np.arcsin(1.0 / mach)

    # node (k, m), 0 <= m <= k <= n, k >= 1: theta = (k - m) step, nu = (k + m) step; row k is the C- number k
    x = np.zeros((n + 1, n + 1))
    y = np.zeros((n + 1, n + 1))
    th = lambda k, m: (k - m) * step                       # flow angle [rad]
    for k in range(1, n + 1):
        x[k, 0], y[k, 0] = 0.0, h_throat                   # every C- of the fan starts at the corner
        for m in range(1, k + 1):
            # C- from node (k, m-1): slope tan(theta - mu) averaged over both ends
            a_minus = 0.5 * ((th(k, m - 1) - mu[k + m - 1]) + (th(k, m) - mu[k + m]))
            if m == k:                                      # axis node: theta = 0, y = 0
                x[k, m] = x[k, m - 1] + (0.0 - y[k, m - 1]) / math.tan(a_minus)
                y[k, m] = 0.0
                continue
            # C+ from node (k-1, m): slope tan(theta + mu) averaged over both ends
            a_plus = 0.5 * ((th(k - 1, m) + mu[k - 1 + m]) + (th(k, m) + mu[k + m]))
            s_minus, s_plus = math.tan(a_minus), math.tan(a_plus)
            x0, y0 = x[k, m - 1], y[k, m - 1]
            x1, y1 = x[k - 1, m], y[k - 1, m]
            x[k, m] = (y1 - y0 + s_minus * x0 - s_plus * x1) / (s_minus - s_plus)
            y[k, m] = y0 + s_minus * (x[k, m] - x0)
    # wall points: C+ number m continued from node (n, m) up to the wall
    wx, wy = [0.0], [h_throat]
    wall_angle = theta_max
    for m in range(1, n + 1):
        angle = th(n, m)                                    # wall angle at wall point m (= flow angle of node (n, m))
        slope_wall = math.tan(0.5 * (wall_angle + angle))   # from wall point m-1
        a_plus = th(n, m) + mu[n + m]                       # C+ leaves node (n, m) with this angle
        s_plus = math.tan(a_plus)
        xa, ya = x[n, m], y[n, m]
        xw, yw = wx[-1], wy[-1]
        x_new = (ya - yw + slope_wall * xw - s_plus * xa) / (slope_wall - s_plus)
        wx.append(x_new)
        wy.append(yw + slope_wall * (x_new - xw))
        wall_angle = angle
    marks = [("throat", 0.0, h_throat), ("exit", wx[-1], wy[-1])]
    return WallProfile(wx, wy, interpolation="linear", marks=marks)


def moc_area_ratio_error(profile, mach_exit, gamma, h_throat):
    """Relative difference between the nozzle's exit height ratio and the isentropic A / A* of the design Mach."""
    ratio = float(profile.r[-1]) / h_throat
    return ratio / gd.area_ratio(mach_exit, gamma) - 1.0

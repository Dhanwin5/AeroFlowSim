# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""NACA 4-digit airfoil "MPTT" (Abbott & von Doenhoff 1959, section 6.4).

Thickness (half of it, perpendicular to the camber line), x = position / chord:
    y_t = 5 t (0.2969 sqrt(x) - 0.1260 x - 0.3516 x² + 0.2843 x³ + a4 x⁴)
    a4 = -0.1015 (original, blunt trailing edge) or -0.1036 (closed trailing edge)
Camber line (m = M/100, p = P/10):
    y_c = m / p² (2 p x - x²)                    for x < p
    y_c = m / (1 - p)² ((1 - 2p) + 2 p x - x²)   for x >= p
Surfaces: the thickness is put on perpendicular to the camber line (slope angle phi):
    upper x_u = x - y_t sin(phi), y_u = y_c + y_t cos(phi);  lower with the signs swapped.
Points: cosine spacing x = (1 - cos beta) / 2, dense at both edges.
"""

import numpy as np

from aeroflowsim.shapes.profile import ShapeProfile

A4_OPEN, A4_CLOSED = -0.1015, -0.1036


def naca4_surfaces(digits, n, closed_te=True):
    """(upper, lower) surfaces, each (n + 1, 2) from the leading edge to the trailing edge, chord 1."""
    m, p, t = int(digits[0]) / 100.0, int(digits[1]) / 10.0, int(digits[2:]) / 100.0
    if t <= 0.0 or t > 0.40:
        raise ValueError(f"NACA {digits}: the thickness (last two digits) must be 01 to 40 % of the chord.")
    if (m == 0.0) != (p == 0.0):
        raise ValueError(f"NACA {digits}: the camber M and its position P must both be 0 (symmetric) "
                         "or both non-zero.")
    x = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n + 1)))     # cosine spacing, 0 ... 1
    a4 = A4_CLOSED if closed_te else A4_OPEN
    yt = 5.0 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 + a4 * x**4)
    if m == 0.0:
        yc, slope = np.zeros_like(x), np.zeros_like(x)
    else:
        front = x < p
        yc = np.where(front, m / p**2 * (2 * p * x - x**2), m / (1 - p)**2 * ((1 - 2 * p) + 2 * p * x - x**2))
        slope = np.where(front, 2 * m / p**2 * (p - x), 2 * m / (1 - p)**2 * (p - x))
    phi = np.arctan(slope)
    upper = np.column_stack([x - yt * np.sin(phi), yc + yt * np.cos(phi)])
    lower = np.column_stack([x + yt * np.sin(phi), yc - yt * np.cos(phi)])
    if closed_te:
        upper[-1] = lower[-1] = [1.0, yc[-1]]                     # exactly one trailing-edge point
    return upper, lower


def profile(inputs):
    digits, c, closed = inputs["digits"], inputs["chord"], inputs["closed_te"]
    n = inputs["points_per_side"]
    upper, lower = naca4_surfaces(digits, n, closed)
    # counter-clockwise: trailing edge -> upper surface -> leading edge -> lower surface (-> back)
    points = np.vstack([upper[::-1], lower[1:-1] if closed else lower[1:]]) * c
    le = n                                                        # index of the leading edge point
    corners = [0] if closed else [0, len(points) - 1]             # sharp TE, or the two blunt-TE corners
    return ShapeProfile(points, reference_length=c, reference_area=c * 1.0, corners=corners,
                        refine=[le], name=f"NACA {digits}")

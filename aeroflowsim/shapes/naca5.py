# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""NACA 5-digit airfoil "LPSTT" (standard S = 0 and reflex S = 1 camber lines).

Digits (Abbott and von Doenhoff 1959; Jacobs and Pinkerton NACA TR-537, 1936; tabulated constants as printed on
Wikipedia "NACA airfoil", checked here against the thin-airfoil design lift, see tests/test_shapes_new.py):
    L    design lift coefficient c_li = 0.15 L (the ideal lift of the camber line)
    P    position of the maximum camber of the standard line: x_m = 0.05 P (of the chord)
    S    0: standard camber line, 1: reflex camber line (the trailing edge curves back up)
    TT   maximum thickness in % of the chord (the same thickness distribution as the 4-digit series)
Camber line (x, y_c as fractions of the chord), constants r, k1 [, k2/k1] from the table below, for c_li = 0.3 (L = 2):
    standard  0 < x < r :  y_c = k1/6 (x³ - 3 r x² + r² (3 - r) x)         r < x < 1 :  y_c = k1 r³/6 (1 - x)
    reflex    0 < x < r :  y_c = k1/6 [(x - r)³ - (k2/k1)(1 - r)³ x - r³ x + r³]
              r < x < 1 :  y_c = k1/6 [(k2/k1)(x - r)³ - (k2/k1)(1 - r)³ x - r³ x + r³]
For another L the camber line is linear in k1, so k1 is scaled by L / 2 (r and k2/k1 stay): the lift of a camber line
is proportional to its camber. The thickness is put on perpendicular to the camber line exactly as for the NACA 4-digit
series (aeroflowsim/shapes/naca4.py), with the closed-trailing-edge coefficient -0.1036 or the original -0.1015.
"""

import numpy as np

from aeroflowsim.shapes.naca4 import A4_CLOSED, A4_OPEN
from aeroflowsim.shapes.profile import ShapeProfile

# (LPS digits for L = 2) -> (r, k1, k2/k1 or None). Source: Wikipedia, "NACA airfoil", five-digit series tables.
CAMBER_TABLE = {
    "210": (0.0580, 361.40, None), "220": (0.1260, 51.640, None), "230": (0.2025, 15.957, None),
    "240": (0.2900, 6.643, None), "250": (0.3910, 3.230, None),
    "221": (0.1300, 51.990, 0.000764), "231": (0.2170, 15.793, 0.00677),
    "241": (0.3180, 6.520, 0.0303), "251": (0.4410, 3.191, 0.1355),
}


def camber_constants(digits):
    """(r, k1, k2_over_k1) of the camber line of the 5 digits (k2_over_k1 is None for the standard line)."""
    key = f"2{digits[1:3]}"
    if key not in CAMBER_TABLE:
        known = ", ".join(sorted(f"x{k[1:]}" for k in CAMBER_TABLE))
        raise ValueError(f"NACA {digits}: the camber line '{digits[:3]}' is not tabulated. The second and third digits "
                         f"must be one of: {known} (x = the first digit, 1 to 9).")
    r, k1, ratio = CAMBER_TABLE[key]
    return r, k1 * int(digits[0]) / 2.0, ratio


def camber_line(digits, x):
    """(y_c, dy_c/dx) of the camber line at x (fractions of the chord, arrays allowed)."""
    r, k1, k2 = camber_constants(digits)
    x = np.asarray(x, dtype=float)
    if k2 is None:
        front = x < r
        y = np.where(front, k1 / 6 * (x**3 - 3 * r * x**2 + r**2 * (3 - r) * x), k1 * r**3 / 6 * (1 - x))
        slope = np.where(front, k1 / 6 * (3 * x**2 - 6 * r * x + r**2 * (3 - r)), -k1 * r**3 / 6)
    else:
        front = x < r
        common = -k2 * (1 - r)**3 * x - r**3 * x + r**3
        y = np.where(front, k1 / 6 * ((x - r)**3 + common), k1 / 6 * (k2 * (x - r)**3 + common))
        slope = np.where(front, k1 / 6 * (3 * (x - r)**2 - k2 * (1 - r)**3 - r**3),
                         k1 / 6 * (3 * k2 * (x - r)**2 - k2 * (1 - r)**3 - r**3))
    return y, slope


def naca5_surfaces(digits, n, closed_te=True):
    """(upper, lower) surfaces, each (n + 1, 2) from the leading edge to the trailing edge, chord 1."""
    if len(digits) != 5 or not digits.isdigit():
        raise ValueError(f"NACA {digits}: five digits are needed (LPSTT).")
    t = int(digits[3:]) / 100.0
    if t <= 0.0 or t > 0.40:
        raise ValueError(f"NACA {digits}: the thickness (last two digits) must be 01 to 40 % of the chord.")
    x = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n + 1)))
    a4 = A4_CLOSED if closed_te else A4_OPEN
    yt = 5.0 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 + a4 * x**4)
    yc, slope = camber_line(digits, x)
    phi = np.arctan(slope)
    upper = np.column_stack([x - yt * np.sin(phi), yc + yt * np.cos(phi)])
    lower = np.column_stack([x + yt * np.sin(phi), yc - yt * np.cos(phi)])
    upper[0] = lower[0] = [0.0, 0.0]                              # the camber line starts at the origin
    if closed_te:
        upper[-1] = lower[-1] = [1.0, yc[-1]]
    return upper, lower


def profile(inputs):
    digits, c, closed = inputs["digits"], inputs["chord"], inputs["closed_te"]
    n = inputs["points_per_side"]
    upper, lower = naca5_surfaces(digits, n, closed)
    points = np.vstack([upper[::-1], lower[1:-1] if closed else lower[1:]]) * c
    corners = [0] if closed else [0, len(points) - 1]
    return ShapeProfile(points, reference_length=c, reference_area=c * 1.0, corners=corners, refine=[n],
                        name=f"NACA {digits}")

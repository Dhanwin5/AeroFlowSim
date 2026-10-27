# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Biconvex (circular-arc) airfoil: two equal circular arcs, sharp leading and trailing edges.

Chord c along x, thickness ratio t = (maximum thickness) / c. Each surface is a circular arc through the leading edge
(0, 0) and the trailing edge (c, 0) with the sagitta s = t c / 2 (the height of the arc at mid-chord):
    R = (a² + s²) / (2 s) with a = c / 2,       y(x) = sqrt(R² - (x - a)²) - (R - s)     (upper surface; lower = -y)
Each surface leaves the chord at the edges with the angle asin(a / R), so the edges are sharp wedges of
twice that angle.
Used in supersonic airfoil theory (Anderson, Modern Compressible Flow, shock-expansion theory). Points: cosine spacing.
"""

import numpy as np

from aeroflowsim.shapes.profile import ShapeProfile


def surface(c, t, n):
    """Upper surface (n + 1, 2) from the leading edge to the trailing edge."""
    a, s = 0.5 * c, 0.5 * t * c
    R = (a * a + s * s) / (2.0 * s)
    x = 0.5 * c * (1.0 - np.cos(np.linspace(0.0, np.pi, n + 1)))
    y = np.sqrt(np.maximum(R * R - (x - a) ** 2, 0.0)) - (R - s)
    y[0] = y[-1] = 0.0
    return np.column_stack([x, y])


def profile(inputs):
    c, t, n = inputs["chord"], inputs["thickness_ratio"], inputs["points_per_side"]
    upper = surface(c, t, n)
    lower = upper * [1.0, -1.0]
    points = np.vstack([upper[::-1], lower[1:-1]])         # counter-clockwise: TE -> upper -> LE -> lower
    return ShapeProfile(points, reference_length=c, reference_area=c * 1.0, corners=[0, n], refine=[0, n],
                        name=f"Biconvex t/c = {t:g}")

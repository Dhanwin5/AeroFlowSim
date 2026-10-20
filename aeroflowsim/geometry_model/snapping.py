# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Snapping while sketching: a clicked point jumps to a nearby "special" point (no window needed).

Within the tolerance (a few pixels, converted to metres by the view), in this order:
    1. a corner of the geometry, or a point already placed in the current sketch (to close it);
    2. the midpoint of an edge;
    3. the nearest grid point (when the grid is on: then always).
Otherwise the point stays where it was clicked. Exact values can always be typed instead.
"""

import math

import numpy as np


def grid_step(size) -> float:
    """A round grid spacing [m] for a geometry of this size: 1, 2 or 5 x 10^n, about size / 20."""
    if not size > 0.0:
        return 1.0
    raw = size / 20.0
    power = 10.0 ** math.floor(math.log10(raw))
    return min((step * power for step in (1.0, 2.0, 5.0, 10.0)), key=lambda s: abs(math.log(s / raw)))


def snap(built, xy, tolerance, sketch_points=(), grid=None):
    """(point (2,), what) - what is "corner", "sketch point", "midpoint", "grid" or "" (no snap)."""
    p = np.asarray(xy, dtype=float)
    candidates = []
    if built is not None:
        candidates += [(v.xy, "corner") for v in built.vertices.values() if v.corner]
    candidates += [(np.asarray(q, dtype=float), "sketch point") for q in sketch_points]
    for point, what in candidates:
        if np.linalg.norm(point - p) <= tolerance:
            return np.array(point, dtype=float), what
    if built is not None:
        for edge in built.edges.values():
            mid = edge.midpoint
            if np.linalg.norm(mid - p) <= tolerance:
                return mid, "midpoint"
    if grid:                                          # with the grid on, every other click lands on it
        return np.round(p / grid) * grid, "grid"
    return p, ""

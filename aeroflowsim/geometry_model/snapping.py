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


MAJOR_EVERY = 5     # every fifth grid line is drawn stronger [-]


def visible_grid(x0, x1, y0, y1):
    """Grid lines for the visible box [m]: (step, xs, ys, x_major, y_major).

    The step is grid_step() of the visible height (about 20 lines across), so the grid follows the
    zoom; lines at multiples of the step, every MAJOR_EVERY-th one marked "major".
    """
    step = grid_step(max(y1 - y0, 1e-300))
    xs = np.arange(math.floor(x0 / step), math.ceil(x1 / step) + 1) * step
    ys = np.arange(math.floor(y0 / step), math.ceil(y1 / step) + 1) * step
    major = lambda v: np.isclose(np.mod(np.round(v / step), MAJOR_EVERY), 0.0)
    return step, xs, ys, major(xs), major(ys)


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

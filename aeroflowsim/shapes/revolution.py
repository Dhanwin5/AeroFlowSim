# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Helpers for bodies of revolution (nose cones, blunt bodies, intakes): not a shape itself (it has no .toml).

A body of revolution is described by its UPPER chain: points (x, r) from the nose on the axis (r = 0) over the
top to the rear end. `silhouette` mirrors it into the full outline a ShapeProfile needs (symmetric about y = 0).
"""

import numpy as np

from aeroflowsim.shapes.profile import ShapeProfile, turning_corners

CORNER_ANGLE = 30.0     # the outline turns by more than this at a "corner" [deg]


def silhouette(chain, close_on_axis=False, corner_angle=CORNER_ANGLE, name="", refine=None, **profile_args):
    """Full outline of the body of revolution with upper chain `chain` (N, 2), r >= 0.

    chain[0] must lie on the axis (r = 0). close_on_axis=False: the last point is the rear edge of the body at
    r = R (a flat base closes it). close_on_axis=True: the last point is on the axis too (a body that closes to
    a point or that has its rear wall on the axis).
    Extra keyword arguments go to ShapeProfile (reference_length, reference_area, ...)."""
    chain = np.asarray(chain, dtype=float)
    if abs(chain[0, 1]) > 1e-12 * max(float(np.ptp(chain[:, 0])), 1e-300):
        raise ValueError("The first point of a body of revolution must lie on the axis (r = 0).")
    lower = chain * [1.0, -1.0]
    # counter-clockwise: nose -> lower surface -> base -> upper surface back to the point after the nose
    if close_on_axis:
        points = np.vstack([lower[:-1], chain[::-1][:-1]])
    else:
        points = np.vstack([lower, chain[::-1][:-1]])
    corners = turning_corners(points, corner_angle)
    corners[0] = True                               # the nose point: always a refinement point
    refine_mask = np.zeros(len(points), dtype=bool)
    refine_mask[0] = True
    return ShapeProfile(points, axisymmetric=True, corners=corners, refine=refine_mask, name=name, **profile_args)


def channel_outline(x, r, axisymmetric, reference_area, corners_at=(), name=""):
    """Closed outline of a nozzle flow path: the wall r(x) and its mirror image about y = 0, closed at both ends.

    Counter-clockwise: lower wall (x increasing), exit plane up, upper wall (x decreasing), inlet plane down. The
    four end points are corners, plus the wall points whose index is in corners_at. (For a planar nozzle r is the
    half-height; for an axisymmetric one the radius: the outline is then the nozzle's silhouette.)"""
    x, r = np.asarray(x, dtype=float), np.asarray(r, dtype=float)
    n = len(x)
    points = np.vstack([np.column_stack([x, -r]), np.column_stack([x[::-1], r[::-1]])])
    corners = np.zeros(len(points), dtype=bool)
    for i in (0, n - 1, n, 2 * n - 1):
        corners[i] = True
    for i in corners_at:
        corners[i] = corners[2 * n - 1 - i] = True
    return ShapeProfile(points, reference_length=float(x[-1] - x[0]), reference_area=reference_area,
                        axisymmetric=axisymmetric, corners=corners, name=name)

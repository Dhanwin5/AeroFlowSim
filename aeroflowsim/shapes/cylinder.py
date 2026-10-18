# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Circular cylinder of diameter D, centre (D/2, 0), as N_POINTS points on the circle.

The mesher draws a smooth spline through the points (there are no corners), so the mesh nodes lie
on the circle to within about 1e-10 D; the points include the front and back (y = 0) exactly.
"""

import numpy as np

from aeroflowsim.shapes.profile import ShapeProfile

N_POINTS = 360   # points on the circle (one per degree)


def profile(inputs):
    D = inputs["diameter"]                                   # [m]
    angle = 2.0 * np.pi * np.arange(N_POINTS) / N_POINTS     # counter-clockwise from the back point [rad]
    points = np.column_stack([0.5 * D * (1.0 + np.cos(angle)), 0.5 * D * np.sin(angle)])
    points[N_POINTS // 2, 1] = 0.0                           # exactly on y = 0 at the front
    return ShapeProfile(points, reference_length=D, reference_area=D * 1.0,
                        refine=[0, N_POINTS // 2], name=f"Cylinder D = {D:g} m")

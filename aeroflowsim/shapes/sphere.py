# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sphere of diameter D (axisymmetric: the silhouette is a circle of diameter D centred at (D/2, 0)).

Reference length = D; reference area = the frontal area pi D² / 4 (so the drag coefficient is the usual sphere Cd).
The outline is N_POINTS points on the circle, including the front and the back point exactly on the axis.
"""

import math

import numpy as np

from aeroflowsim.shapes.profile import ShapeProfile

N_POINTS = 360   # points on the circle (one per degree)


def profile(inputs):
    D = inputs["diameter"]                                   # [m]
    angle = 2.0 * np.pi * np.arange(N_POINTS) / N_POINTS     # counter-clockwise from the back point [rad]
    points = np.column_stack([0.5 * D * (1.0 + np.cos(angle)), 0.5 * D * np.sin(angle)])
    points[N_POINTS // 2, 1] = 0.0                           # exactly on the axis at the front
    return ShapeProfile(points, reference_length=D, reference_area=math.pi * D**2 / 4.0, axisymmetric=True,
                        refine=[0, N_POINTS // 2], name=f"Sphere D = {D:g} m")

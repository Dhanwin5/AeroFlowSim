# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Diamond airfoil: leading edge (0, 0), shoulders at (xm c, +-t/2), trailing edge (c, 0)."""

from aeroflowsim.shapes.profile import ShapeProfile


def profile(inputs):
    c = inputs["chord"]                                      # [m]
    t = inputs["thickness_ratio"] * c                        # largest thickness [m]
    xm = inputs["x_max_thickness"] * c                       # shoulder position [m]
    points = [(0.0, 0.0), (xm, -0.5 * t), (c, 0.0), (xm, 0.5 * t)]   # counter-clockwise
    return ShapeProfile(points, reference_length=c, reference_area=c * 1.0, corners=[0, 1, 2, 3],
                        name=f"Diamond airfoil t/c = {inputs['thickness_ratio']:g}")

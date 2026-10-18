# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Wedge: tip at (0, 0), flat base at x = L from y = -L tan(theta) to +L tan(theta)."""

import math

from aeroflowsim.shapes.profile import ShapeProfile


def profile(inputs):
    L = inputs["length"]                                     # [m]
    h = L * math.tan(math.radians(inputs["half_angle"]))     # base half-height [m]
    points = [(0.0, 0.0), (L, -h), (L, h)]                   # counter-clockwise
    return ShapeProfile(points, reference_length=L, reference_area=L * 1.0,   # [m], [m²] per metre depth
                        corners=[0, 1, 2], name=f"Wedge {inputs['half_angle']:g}°")

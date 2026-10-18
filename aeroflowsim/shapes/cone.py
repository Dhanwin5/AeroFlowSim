# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Conical nose cone: tip (0, 0), base radius R = L tan(theta), optional cylindrical afterbody.

The outline is the full silhouette (symmetric about the axis y = 0); meshes use its upper half
with an axis patch. Reference length = total body length; reference area = base area pi R².
"""

import math

from aeroflowsim.shapes.profile import ShapeProfile


def profile(inputs):
    L = inputs["length"]                                     # cone length [m]
    R = L * math.tan(math.radians(inputs["half_angle"]))     # base radius [m]
    end = L + (inputs["afterbody_length"] if inputs["base"] == "Cone-cylinder" else 0.0)   # body end [m]
    if end > L:
        points = [(0.0, 0.0), (L, -R), (end, -R), (end, R), (L, R)]   # counter-clockwise
    else:
        points = [(0.0, 0.0), (L, -R), (L, R)]
    return ShapeProfile(points, reference_length=end, reference_area=math.pi * R**2, axisymmetric=True,
                        corners=list(range(len(points))), name=f"Cone {inputs['half_angle']:g}°")

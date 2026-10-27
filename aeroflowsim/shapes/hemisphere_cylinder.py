# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Hemisphere-cylinder: a hemispherical nose of radius R = D/2 on a cylinder of length L_c, flat base.

The nose tip is at x = 0. Reference length = total length R + L_c... measured as the overall body length
(R + L_c); reference area = base area pi R².
"""

import math

import numpy as np

from aeroflowsim.shapes.revolution import silhouette


def profile(inputs):
    R = 0.5 * inputs["diameter"]                            # [m]
    Lc = inputs["cylinder_length"]                          # [m]
    a = np.linspace(0.0, 0.5 * math.pi, inputs["points"])
    nose = np.column_stack([R * (1.0 - np.cos(a)), R * np.sin(a)])
    chain = np.vstack([nose, [R + Lc, R]]) if Lc > 0.0 else nose
    return silhouette(chain, reference_length=R + Lc, reference_area=math.pi * R**2,
                      name=f"Hemisphere-cylinder D = {2 * R:g} m")

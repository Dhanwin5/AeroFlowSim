# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Rao bell nozzle (thrust-optimised parabola) as a closed flow-path outline.

The wall comes from aeroflowsim/nozzle_contours.py (bell_nozzle: equations, chart data and sources are there); this
file only closes it into an outline (the wall and its mirror image) for the geometry workspace. The same wall as a
WallProfile feeds the nozzle templates. Reference length = nozzle length; reference area = throat area.
"""

import math

from aeroflowsim.nozzle_contours import bell_nozzle
from aeroflowsim.shapes.revolution import channel_outline


def wall_profile(inputs):
    """The wall (WallProfile) for these inputs; theta_n / theta_e of 0 mean 'take them from the chart'."""
    return bell_nozzle(0.5 * inputs["throat_diameter"], inputs["area_ratio"], inputs["length_percent"] / 100.0,
                       inputs["theta_n"] or None, inputs["theta_e"] or None, inputs["body_type"] == "Planar",
                       inputs["upstream_ratio"], inputs["downstream_ratio"], inputs["inlet_arc_angle"])


def profile(inputs):
    wall = wall_profile(inputs)
    axisymmetric = inputs["body_type"] == "Axisymmetric"
    rt = 0.5 * inputs["throat_diameter"]
    area = math.pi * rt**2 if axisymmetric else 2.0 * rt * 1.0
    return channel_outline(wall.x, wall.r, axisymmetric, area, name="Bell nozzle")

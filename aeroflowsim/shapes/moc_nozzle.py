# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Planar minimum-length nozzle by the Method of Characteristics, as a closed flow-path outline.

The wall comes from aeroflowsim/nozzle_contours.py (moc_min_length_nozzle: equations and checks are there); this file
only closes it (wall + mirror image + throat plane + exit plane). Reference length = nozzle length; reference
area = throat area (throat height x 1 m).
"""

from aeroflowsim.nozzle_contours import moc_min_length_nozzle
from aeroflowsim.shapes.revolution import channel_outline


def wall_profile(inputs):
    """The wall (WallProfile of the half-height) for these inputs."""
    return moc_min_length_nozzle(inputs["mach_exit"], inputs["gamma"], 0.5 * inputs["throat_height"],
                                 inputs["n_characteristics"])


def profile(inputs):
    wall = wall_profile(inputs)
    return channel_outline(wall.x, wall.r, False, inputs["throat_height"] * 1.0, corners_at=(0,),
                           name=f"MOC nozzle M = {inputs['mach_exit']:g}")

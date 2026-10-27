# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spherically blunted cone: a sphere of radius r_n tangent to a cone of half-angle theta, up to the base radius R_b.

Geometry (tip of the sharp cone at x = 0 before blunting): the sphere's centre is on the axis at
    x_c = r_n / sin(theta),
the sphere touches the cone at P = (x_c - r_n sin(theta), r_n cos(theta)), and the nose point is at x_c - r_n (this is then
moved to x = 0). The cone continues from P to the base radius R_b, where a flat base (or a cylindrical afterbody) follows.
Reference length = total length; reference area = base area pi R_b².
"""

import math

import numpy as np

from aeroflowsim.shapes.revolution import silhouette


def profile(inputs):
    theta = math.radians(inputs["half_angle"])              # cone half-angle [rad]
    Rb = 0.5 * inputs["base_diameter"]                      # base radius [m]
    rn = 0.5 * inputs["nose_diameter"]                      # nose radius [m]
    if rn * math.cos(theta) >= Rb:
        raise ValueError("The nose sphere is as big as the base: lower the nose diameter or raise the base diameter.")
    xc = rn / math.sin(theta)                               # sphere centre [m]
    P = np.array([xc - rn * math.sin(theta), rn * math.cos(theta)])    # tangent point [m]
    a = np.linspace(0.0, 0.5 * math.pi - theta, inputs["points"])      # polar angle of the cap, 0 ... tangent point
    cap = np.column_stack([xc - rn * np.cos(a), rn * np.sin(a)])
    end = np.array([P[0] + (Rb - P[1]) / math.tan(theta), Rb])         # cone end at the base radius
    pieces = [cap, [end]]
    after = inputs["afterbody_length"]
    if after > 0.0:
        pieces.append([[end[0] + after, Rb]])
    chain = np.vstack(pieces)
    chain[:, 0] -= chain[0, 0]                              # the nose point is at x = 0
    return silhouette(chain, reference_length=chain[-1, 0], reference_area=math.pi * Rb**2,
                      name=f"Blunted cone {inputs['half_angle']:g}°")

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sphere-cone capsule (re-entry capsule): spherical heat-shield forebody, rounded shoulder, conical afterbody.

Tip (the front of the spherical forebody) at x = 0, axis along x, the capsule flies forward (towards -x of the body).
    forebody   spherical cap of radius R_n, centre C = (R_n, 0)
    shoulder   a torus of radius r_s (a circular arc in the outline), tangent to the sphere from inside: its centre T
               is at distance R_n - r_s from C and at height R_b - r_s, where R_b is the largest radius:
                   sin(alpha) = (R_b - r_s) / (R_n - r_s),   T = (R_n - (R_n - r_s) cos(alpha), R_b - r_s)
    afterbody  a cone narrowing backwards with half-angle theta_c, tangent to the shoulder arc, of axial length L_a
    back       a flat back face
With psi the angle of the outward normal measured from +y towards +x, the shoulder arc runs from psi = alpha - 90 deg
(the tangent point with the sphere) to psi = theta_c (the tangent point with the cone), point = T + r_s (sin psi, cos psi).
Reference length = total length; reference area = pi R_b².
"""

import math

import numpy as np

from aeroflowsim.shapes.revolution import silhouette


def profile(inputs):
    Rn = inputs["nose_radius"]                              # forebody sphere radius [m]
    Rb = 0.5 * inputs["diameter"]                           # largest radius [m]
    rs = inputs["shoulder_radius"]                          # shoulder radius [m]
    tc = math.radians(inputs["afterbody_angle"])            # afterbody half-angle [rad]
    La = inputs["afterbody_length"]                         # afterbody axial length [m]
    if not Rn > Rb:
        raise ValueError("The forebody sphere radius must be larger than the capsule radius (diameter / 2).")
    if not 0.0 < rs < Rb:
        raise ValueError("The shoulder radius must be positive and smaller than the capsule radius.")
    sin_alpha = (Rb - rs) / (Rn - rs)
    alpha = math.asin(sin_alpha)
    T = np.array([Rn - (Rn - rs) * math.cos(alpha), Rb - rs])           # shoulder centre [m]
    n = inputs["points"]
    a = np.linspace(0.0, alpha, n)                                      # forebody: polar angle from the tip
    fore = np.column_stack([Rn * (1.0 - np.cos(a)), Rn * np.sin(a)])
    psi = np.linspace(alpha - 0.5 * math.pi, tc, max(n // 3, 8))
    shoulder = np.column_stack([T[0] + rs * np.sin(psi), T[1] + rs * np.cos(psi)])[1:]
    E = shoulder[-1]                                                    # where the cone starts
    back = np.array([E[0] + La, E[1] - La * math.tan(tc)])
    if back[1] <= 0.0:
        raise ValueError("The afterbody cone closes before its end: shorten the afterbody or lower its angle.")
    chain = np.vstack([fore, shoulder, [back]])
    return silhouette(chain, reference_length=float(chain[-1, 0]), reference_area=math.pi * Rb**2,
                      name="Capsule")

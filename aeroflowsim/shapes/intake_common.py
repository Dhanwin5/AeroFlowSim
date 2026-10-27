# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Outline of an external-compression intake (ramp or spike) shared by ramp_intake.py and spike_intake.py.

A ShapeProfile is ONE closed outline, but an intake is a centre body plus a cowl, which in a plane are two separate
solids. So the two are joined by a solid rear block behind the duct: the duct is a dead-end pocket (closed at the back,
open at the front). This is right for the shock system, the capture and the spillage in front of the lip; it is not a
through-flow duct (a shape with two bodies is a gap register item).

The chain (x, y) runs along the upper boundary of the solid, from the leading edge / spike tip on y = 0:
    nose points ... end of the last ramp E = (x_E, y_E)   (the surface of the centre body, corners at each ramp end)
    duct floor to (x_d, y_E), up the end of the duct to (x_d, y_c), back along the cowl's inner surface (height y_c, from
    x_d to the bend at x_b = max(x_E, x_lip)), up the inner surface to the lip (x_lip, y_lip) (descending at the cowl
    angle from the lip), the cowl's outer surface to (x_end, y_o), and down to the axis at (x_end, 0).
    y_c = y_lip - max(x_E - x_lip, 0) tan(cowl angle): the duct height at the end of the centre body is y_c - y_E.
"""

import math

from aeroflowsim.shapes.profile import count_self_intersections


def intake_chain(nose_points, x_lip, y_lip, cowl_angle_deg, outer_angle_deg, duct_length, rear_wall):
    """The chain described in the module docstring; ValueError if the cowl and the centre body collide."""
    xe, ye = nose_points[-1]
    tan_c, tan_o = math.tan(math.radians(cowl_angle_deg)), math.tan(math.radians(outer_angle_deg))
    y_c = y_lip - max(xe - x_lip, 0.0) * tan_c                     # ceiling of the duct [m]
    if y_c - ye <= 1e-3 * max(xe, 1e-9):
        raise ValueError("The cowl lip is too low: the duct would have no height at the end of the centre body. "
                         "Raise the lip or lower the cowl angle.")
    x_d = xe + duct_length                                          # end of the duct [m]
    x_end = x_d + rear_wall                                         # rear of the body [m]
    x_b = max(xe, x_lip)                                            # bend between the sloping and the flat inner surface
    y_o = y_lip + (x_end - x_lip) * tan_o                           # height of the outer surface at the rear [m]
    chain = [tuple(p) for p in nose_points] + [(x_d, ye), (x_d, y_c)]
    if x_lip >= x_d:
        raise ValueError("The cowl lip is behind the end of the duct: move it forward or lengthen the duct.")
    if x_lip < xe:                                                  # flat part of the ceiling from x_d back to the bend
        chain.append((x_b, y_c))
    chain += [(x_lip, y_lip), (x_end, y_o), (x_end, 0.0)]
    if count_self_intersections(chain) > 0:
        raise ValueError("The cowl crosses the centre body or itself: raise the lip, move it forward, or change the angles.")
    return chain

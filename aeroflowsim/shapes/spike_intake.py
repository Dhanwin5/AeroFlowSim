# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Axisymmetric spike (centre-body) intake: a conical spike, an annular duct and a cowl (see intake_common.py).

The spike is a cone of half-angle delta with its tip at the origin, length L_s, ending at the radius r_s = L_s tan(delta);
behind it the centre body continues as a cylinder. The cowl lip is at (lip_x, lip_r). The smart rule "shock on lip" suggests
the radius where the conical (Taylor-Maccoll) shock reaches the lip. Reference length = body length; reference area = capture
area pi lip_r².
"""

import math

from aeroflowsim.shapes.intake_common import intake_chain
from aeroflowsim.shapes.revolution import silhouette


def profile(inputs):
    delta = math.radians(inputs["cone_half_angle"])
    Ls = inputs["spike_length"]
    nose = [(0.0, 0.0), (Ls, Ls * math.tan(delta))]
    chain = intake_chain(nose, inputs["lip_x"], inputs["lip_r"], inputs["cowl_angle"], inputs["cowl_outer_angle"],
                         inputs["duct_length"], inputs["rear_wall"])
    outline = silhouette(chain, close_on_axis=True, corner_angle=1.0, reference_length=chain[-1][0],
                         reference_area=math.pi * inputs["lip_r"]**2, name="Spike intake")
    outline.warnings.append("The annular duct is closed at its rear (a one-piece outline cannot hold a through duct): use "
                            "it for the shock system and the capture, not for the duct flow.")
    return outline

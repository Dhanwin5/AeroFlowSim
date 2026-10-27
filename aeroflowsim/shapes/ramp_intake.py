# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Planar external-compression ramp intake: 1 to 3 ramps, a duct and a cowl (see intake_common.py for the outline).

The ramp surface starts at the leading edge (0, 0) with ramp 1 at angle delta_1 to the free stream; ramp i ends where its
length (along the surface) is used up. The cowl lip is at (lip_x, lip_y). The smart rule "shock on lip" suggests the lip
that sits on the ramp shocks (aeroflowsim/intake_theory.py, aeroflowsim/smart_rules.py). Reference length = body length;
reference area = the capture height lip_y x 1 m.
"""

from aeroflowsim.intake_theory import ramp_corners
from aeroflowsim.shapes.intake_common import intake_chain
from aeroflowsim.shapes.profile import ShapeProfile


def ramps(inputs):
    """(angles [deg], lengths [m]) of the ramps in use."""
    n = int(inputs["n_ramps"])
    return ([inputs[f"angle{i}"] for i in range(1, n + 1)], [inputs[f"length{i}"] for i in range(1, n + 1)])


def profile(inputs):
    angles, lengths = ramps(inputs)
    if any(b <= a for a, b in zip(angles, angles[1:])):
        raise ValueError("The ramp angles must increase from ramp to ramp (each ramp turns the flow further).")
    nose = ramp_corners(angles, lengths)
    chain = intake_chain(nose, inputs["lip_x"], inputs["lip_y"], inputs["cowl_angle"], inputs["cowl_outer_angle"],
                         inputs["duct_length"], inputs["rear_wall"])
    outline = ShapeProfile(chain, reference_length=chain[-1][0], reference_area=inputs["lip_y"] * 1.0,
                           corners=list(range(len(chain))), refine=[0, len(chain) - 3],
                           name=f"Ramp intake, {len(angles)} ramp(s)")
    outline.warnings.append("The duct is closed at its rear (a one-piece outline cannot hold a through duct): use it for "
                            "the shock system and the capture, not for the duct flow.")
    return outline

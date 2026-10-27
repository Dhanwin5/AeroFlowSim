# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shock geometry of supersonic intakes with external compression: where the shocks run, and where the cowl lip
must be so that they meet on the lip ("shock on lip", the design point of an external-compression intake: all
the compression happens outside, nothing spills, and no shock enters the duct).

Ramp intake (planar): ramp i turns the flow from the angle of the previous ramp (delta_{i-1}, 0 for the free
stream) to delta_i. The oblique-shock relation (Anderson, Modern Compressible Flow, theta-beta-M, eq. 4.17,
aeroflowsim.gasdynamics.oblique_shock_angle) gives the shock angle beta_i from the flow direction in front of it, so the
shock leaves the ramp corner i - 1 at the absolute angle eps_i = delta_{i-1} + beta_i from the free-stream direction.
Spike intake (axisymmetric): the conical shock of the spike's cone (Taylor-Maccoll, gasdynamics.taylor_maccoll)
is a straight cone from the tip at the angle beta.
"""

import math

from aeroflowsim import gasdynamics as gd


def ramp_shocks(mach, gamma, ramp_angles_deg):
    """Shocks of a sequence of ramps with absolute surface angles delta_i [deg] (increasing, first from the free stream).

    Returns a list, one entry per ramp: {turn [deg], beta [deg] (from the flow in front), angle [deg] (absolute
    inclination of the shock), mach_before, mach_after, p_ratio (static pressure behind / in front)}.
    Raises ValueError if the angles do not increase or a shock would detach."""
    out, previous, M = [], 0.0, mach
    for i, delta in enumerate(ramp_angles_deg, start=1):
        turn = delta - previous
        if turn <= 0.0:
            raise ValueError(f"Ramp {i}: its angle ({delta:g} deg) must be larger than the one before ({previous:g} deg).")
        shock = gd.oblique_shock(M, math.radians(turn), gamma)      # may raise: shock detaches
        out.append({"turn": turn, "beta": math.degrees(shock["beta"]), "angle": previous + math.degrees(shock["beta"]),
                    "mach_before": M, "mach_after": shock["M2"], "p_ratio": shock["p2_p1"]})
        previous, M = delta, shock["M2"]
    return out


def ramp_corners(ramp_angles_deg, ramp_lengths):
    """Points [(x, y)] of the ramp surface from the leading edge (0, 0): one per ramp end. Lengths are along the surface."""
    points, x, y = [(0.0, 0.0)], 0.0, 0.0
    for delta, length in zip(ramp_angles_deg, ramp_lengths):
        x += length * math.cos(math.radians(delta))
        y += length * math.sin(math.radians(delta))
        points.append((x, y))
    return points


def _line_distance(point, origin, angle_deg):
    """Distance [m] of `point` from the straight line through `origin` with the given inclination [deg]."""
    a = math.radians(angle_deg)
    return abs(-(point[0] - origin[0]) * math.sin(a) + (point[1] - origin[1]) * math.cos(a))


def ramp_lip(mach, gamma, ramp_angles_deg, ramp_lengths, lip_x=None):
    """Cowl lip position that puts the ramp shocks on the lip.

    With one ramp the shock is one straight line from the leading edge, so the lip is on it at the height
    y = lip_x tan(eps_1) (lip_x must be given). With two or more ramps the lip is where shock 1 (from the leading edge) and
    shock 2 (from the first ramp corner) cross; the later shocks then miss the lip by the distances returned.
    Returns {lip: (x, y), shocks: ramp_shocks(), miss: [distance of the lip from each shock line, m]}."""
    shocks = ramp_shocks(mach, gamma, ramp_angles_deg)
    corners = ramp_corners(ramp_angles_deg, ramp_lengths)
    e1 = math.radians(shocks[0]["angle"])
    if len(shocks) == 1:
        if lip_x is None:
            raise ValueError("With one ramp the lip position along the shock is a free choice: give the lip's x.")
        lip = (lip_x, lip_x * math.tan(e1))
    else:
        e2 = math.radians(shocks[1]["angle"])
        (x1, y1) = corners[1]
        # shock 1: y = x tan e1;  shock 2: y = y1 + (x - x1) tan e2
        if math.isclose(e1, e2):
            raise ValueError("The first two shocks are parallel: they never meet.")
        x = (y1 - x1 * math.tan(e2)) / (math.tan(e1) - math.tan(e2))
        lip = (x, x * math.tan(e1))
    miss = [_line_distance(lip, corners[i], s["angle"]) for i, s in enumerate(shocks)]
    return {"lip": lip, "shocks": shocks, "miss": miss}


def cone_shock_angle(mach, gamma, cone_half_angle_deg):
    """Shock angle [deg] of the conical shock of a cone (Taylor-Maccoll) in a stream of Mach `mach`."""
    return math.degrees(gd.taylor_maccoll(mach, math.radians(cone_half_angle_deg), gamma)["beta"])


def spike_lip(mach, gamma, cone_half_angle_deg, lip_x):
    """Cowl lip (x, r) on the conical shock of the spike: r = x tan(beta). Returns {lip, beta [deg]}."""
    beta = cone_shock_angle(mach, gamma, cone_half_angle_deg)
    return {"lip": (lip_x, lip_x * math.tan(math.radians(beta))), "beta": beta}

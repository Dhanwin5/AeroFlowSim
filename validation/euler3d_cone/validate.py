# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""10 deg cone at Mach 2 in 3D (external_3d "Nose cone": a sharp cone, tip at x = 0; quarter domain, tetrahedra, the
template's 3D defaults) against Taylor-Maccoll.

Shock angle: the pressure on a slice just inside the symmetry plane z = 0 (aeroflowsim.post.view3d, node values),
searched along lines y = const at 6 heights; where it crosses half-way between p_inf and the pressure behind the conical
shock, a line through the tip gives beta. Cp: the mean over the wall faces on the cone surface between 30 % and 80 % of
its length (the flat base excluded).
"""

import math

import numpy as np
from scipy.interpolate import LinearNDInterpolator

import aeroflowsim
from aeroflowsim.gasdynamics import normal_shock, taylor_maccoll
from validation.common import is_quick

HALF_ANGLE = 10.0                                      # [deg]
D = 0.1                                                # base diameter [m]
LENGTH = 0.5 * D / math.tan(math.radians(HALF_ANGLE))  # [m] cone length for the half-angle
BASE = {"body_shape": "Nose cone", "diameter": D, "length": LENGTH, "mach": 2.0, "half_domain": True,
        "quarter_domain": True, "upstream": 0.2, "downstream": 0.3, "lateral": 0.6, "max_iter": 20000}
RUNS = {}


def _sizes():
    return {"surface_size": 0.03, "farfield_size": 0.12} if is_quick() else {"surface_size": 0.015, "farfield_size": 0.06}


def _measure(out):
    from aeroflowsim.post.fields import node_values
    from aeroflowsim.post.solution import Solution
    from aeroflowsim.post.view3d import slice_plane
    mesh, r = out.mesh, out.result
    tm = taylor_maccoll(2.0, math.radians(HALF_ANGLE), 1.4)
    p_inf = out.params["p_inf"]
    level = 0.5 * (p_inf + normal_shock(2.0 * math.sin(tm["beta"]), 1.4)["p2_p1"] * p_inf)
    sol = Solution.from_result(mesh, r, out.params)
    s = slice_plane(mesh, node_values(sol, "p"), (0.0, 0.0, 1e-6 * D), (0.0, 0.0, 1.0))
    interp = LinearNDInterpolator(s.points[:, :2], s.values)
    t = math.tan(math.radians(HALF_ANGLE))
    xs, ys = [], []
    for yk in np.linspace(0.10, 0.35, 6) * LENGTH:    # away from the tip (as the 2D cone case): the shock is resolved
        x = np.linspace(0.0, 1.2 * LENGTH, 4000)
        pk = interp(x, np.full_like(x, yk))
        ok = np.isfinite(pk)
        i = np.flatnonzero(ok[:-1] & ok[1:] & (pk[:-1] < level) & (pk[1:] >= level))
        if len(i):
            k = i[0]
            xs.append(x[k] + (level - pk[k]) * (x[k + 1] - x[k]) / (pk[k + 1] - pk[k]))
            ys.append(yk)
    xs, ys = np.array(xs), np.array(ys)
    beta = math.degrees(math.atan(float(np.sum(xs * ys) / np.sum(xs * xs)))) if len(xs) else float("nan")
    wx, wp = r.series["wall_x"], r.series["wall_p"]
    wr = np.hypot(r.series["wall_y"], r.series["wall_z"])
    on_cone = (np.abs(wr - wx * t) < 0.03 * D) & (wx > 0.3 * LENGTH) & (wx < 0.8 * LENGTH)
    cp = float(np.mean((wp[on_cone] - p_inf) / r.key_numbers["q_inf"][0]))
    return {"beta": beta, "Cp": cp, "stations": len(xs), "cells": mesh.n_cells, "iterations": r.iterations,
            "converged": r.converged, "time": r.key_numbers["wall_time"][0], "theory": tm}


def measure():
    RUNS["cone"] = _measure(aeroflowsim.run_case("cases/external_3d", {**BASE, **_sizes()}))
    if not is_quick():      # reported only (not scored): cells / sqrt(2) on the wall and in the field
        RUNS["finer"] = _measure(aeroflowsim.run_case("cases/external_3d", {**BASE, "surface_size": 0.0106,
                                                                           "farfield_size": 0.0424}))
    return {"beta": RUNS["cone"]["beta"], "Cp": RUNS["cone"]["Cp"]}


def study():
    tm = RUNS["cone"]["theory"]
    rows = [[name, f"{m['cells']:,}", f"{m['iterations']:,}", "yes" if m["converged"] else "NO", f"{m['time']:.0f}",
             str(m["stations"]), f"{m['beta']:.3f}", f"{math.degrees(tm['beta']):.3f}", f"{m['Cp']:.4f}",
             f"{tm['Cp']:.4f}"] for name, m in RUNS.items()]
    return {"title": "Runs (the scored run is 'cone'; 'finer' is reported only)",
            "columns": ["Run", "Cells", "Iterations", "Converged", "Time [s]", "Shock stations", "beta [deg]",
                        "beta Taylor-Maccoll [deg]", "Cp", "Cp Taylor-Maccoll"],
            "rows": rows,
            "notes": ["3D quarter domain with two symmetry planes, tetrahedra, the external_3d defaults."]}

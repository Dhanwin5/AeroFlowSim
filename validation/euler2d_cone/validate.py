# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""15 deg half-angle cone at Mach 2 (axisymmetric) with the external_2d template, against the Taylor-Maccoll
solution (aeroflowsim.gasdynamics.taylor_maccoll, checked against the tables of Sims 1964, NASA SP-3004).

Rectangle domain around the cone (axis = symmetry line), Gmsh triangles. The shock angle is fitted through the
shock position on six lines parallel to the axis, a straight line through the tip. The shock position on a line is
where the density gradient along it is largest (parabola through the largest sample and its neighbours). The
half-level crossing used for the wedge is NOT used here: behind a conical shock the pressure keeps rising towards
the cone (isentropic compression), so the level half-way between p_inf and the value just behind the shock is not
the middle of the smeared shock (found in Prompt 7b: it gave 35.05 deg on the coarse mesh while Cp agreed to 0.1 %); the surface Cp is the mean over the wall cells between 30 %
and 80 % of the cone length (away from the tip, where the conical flow needs a few cells to establish, and from
the base corner).
"""

import math

import numpy as np
from scipy.interpolate import LinearNDInterpolator

import aeroflowsim
from aeroflowsim.gasdynamics import taylor_maccoll
from validation.common import is_quick

CASE = "cases/external_2d"
HALF_ANGLE = 15.0          # [deg]
BASE = {"shape": "Conical nose cone", "cone.half_angle": HALF_ANGLE, "cone.length": 1.0, "domain_shape": "Rectangle",
        "upstream": 0.5, "downstream": 0.5, "height": 1.5, "mach": 2.0, "first_order_iterations": 200,
        "max_iter": 30000}
RUNS = {}


def _sizes():
    return {"surface_size": 0.02, "farfield_size": 0.08} if is_quick() else {"surface_size": 0.01, "farfield_size": 0.04}


def _measure(out):
    mesh, r = out.mesh, out.result
    tm = taylor_maccoll(2.0, math.radians(HALF_ANGLE), 1.4)
    p_inf = out.params["p_inf"]
    xc, yc = mesh.cell_centres[:, 0], mesh.cell_centres[:, 1]
    interp = LinearNDInterpolator(np.column_stack([xc, yc]), r.fields["rho"].values)
    xs, ys = [], []
    L = 1.0
    t = math.tan(math.radians(HALF_ANGLE))
    for yk in np.linspace(0.15, 0.45, 6) * L:      # away from the tip, where the shock is only a few cells long
        x = np.linspace(-0.2, yk / math.tan(math.radians(25.0)), 3000)   # between the free stream and the cone, before the base
        rk = interp(x, np.full_like(x, yk))
        ok = np.isfinite(rk)
        x, rk = x[ok], rk[ok]
        g = np.gradient(rk, x)
        k = int(np.argmax(g))
        if 0 < k < len(x) - 1:
            a, b, c = g[k - 1], g[k], g[k + 1]
            shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
            xs.append(x[k] + shift * (x[1] - x[0]))
            ys.append(yk)
    xs, ys = np.array(xs), np.array(ys)
    beta = math.degrees(math.atan(float(np.sum(xs * ys) / np.sum(xs * xs))))
    wx, wy, wp = r.series["wall_x"], r.series["wall_y"], r.series["wall_p"]
    on_cone = (np.abs(wy - wx * t) < 0.02 * L) & (wx > 0.3 * L) & (wx < 0.8 * L)
    q = 0.5 * 1.4 * p_inf * 4.0
    cp = float(np.mean((wp[on_cone] - p_inf) / q))
    return {"beta": beta, "Cp": cp, "cells": mesh.n_cells, "iterations": r.iterations, "converged": r.converged,
            "time": r.key_numbers["wall_time"][0], "theory": tm}


def measure():
    out = aeroflowsim.run_case(CASE, {**BASE, **_sizes()})
    RUNS["cone"] = _measure(out)
    return {"beta": RUNS["cone"]["beta"], "Cp": RUNS["cone"]["Cp"]}


def study():
    m = RUNS["cone"]
    tm = m["theory"]
    return {"title": "Run", "columns": ["Cells", "Iterations", "Converged", "Time [s]", "beta [deg]",
                                        "beta Taylor-Maccoll [deg]", "Cp", "Cp Taylor-Maccoll"],
            "rows": [[f"{m['cells']:,}", f"{m['iterations']:,}", "yes" if m["converged"] else "NO", f"{m['time']:.0f}",
                      f"{m['beta']:.3f}", f"{math.degrees(tm['beta']):.3f}", f"{m['Cp']:.4f}", f"{tm['Cp']:.4f}"]],
            "notes": ["Taylor-Maccoll (aeroflowsim.gasdynamics.taylor_maccoll) agrees with Sims (1964, NASA SP-3004, "
                      "Tables 9 and 11) to 7e-5 in Cp and 2e-6 rad in the shock angle (tests/test_gasdynamics.py)."]}

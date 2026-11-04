# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Circular cylinder (D = 1 m, front at x = 0) at Mach 3 on the default Gmsh triangle mesh of external_2d (full circle
domain), with the numerics the smart rule suggests for triangle meshes: Green-Gauss with node values and the implicit
update limit 0.2 (everything else the 2D defaults). Stand-off: the cells within 0.01 D of the stagnation line ahead of
the cylinder, ordered by x; where their pressure crosses half-way between p_inf and the pressure behind a normal Mach 3
shock (linear interpolation). A diverged run scores no value. Quick and full sets are the same mesh."""

import math

import numpy as np

import aeroflowsim
from aeroflowsim.gasdynamics import normal_shock

MACH = 3.0
INPUTS = {"shape": "Circular cylinder", "mach": MACH, "gradient": "Green-Gauss (node values)", "update_limit": 0.2,
          "max_iter": 20000}
RUNS = {}


def billig():
    return 0.386 * math.exp(4.67 / MACH**2)


def _standoff(out):
    """Stand-off / R from the pressure FIELD sampled along the stagnation line y = 0 (linear interpolation between the
    cell centres, 4,000 points from 1.5 D upstream to the nose): the last crossing of the half-way level. (A first
    version used only the cells whose centre lies within 0.01 D of the line: in the coarse cells ahead of the shock
    there were none between x = -0.74 and -0.28, so it interpolated across the gap: the first scoring gave 1.042 (FAIL);
    found by printing the samples, fixed, scored again.)"""
    from scipy.interpolate import LinearNDInterpolator
    mesh, r = out.mesh, out.result
    c = mesh.cell_centres
    box = (c[:, 0] < 0.05) & (c[:, 0] > -1.6) & (np.abs(c[:, 1]) < 0.4)
    interp = LinearNDInterpolator(c[box, :2], r.fields["p"].values[box])
    x = np.linspace(-1.5, -1e-3, 4000)
    p = interp(x, np.zeros_like(x))
    level = 0.5 * (1.0 + normal_shock(MACH, 1.4)["p2_p1"]) * out.params["p_inf"]
    ok = np.isfinite(p)
    i = np.flatnonzero(ok[:-1] & ok[1:] & (p[:-1] < level) & (p[1:] >= level))
    if not len(i):
        return float("nan")
    k = i[-1]
    return -float(x[k] + (level - p[k]) * (x[k + 1] - x[k]) / (p[k + 1] - p[k])) / 0.5


def measure():
    out = aeroflowsim.run_case("cases/external_2d", INPUTS)
    r = out.result
    standoff = float("nan") if r.info["status"] == "diverged" else _standoff(out)
    cd = np.asarray(r.series.get("monitor_Cd", [np.nan]))
    RUNS["cylinder"] = {"cells": out.mesh.n_cells, "iterations": r.iterations, "converged": r.converged,
                        "status": r.info["status"], "time": r.key_numbers["wall_time"][0], "standoff": standoff,
                        "Cd": r.key_numbers["Cd"][0], "Cd_range": float(np.ptp(cd[-1000:]) / abs(cd[-1])),
                        "residual": r.residuals[-1], "limited": r.info.get("limited_updates", 0)}
    return {"standoff": standoff}


def study():
    m = RUNS["cylinder"]
    return {"title": "Run", "columns": ["Cells", "Iterations", "Status", "Final residual", "Time [s]", "Stand-off / R",
                                        "Billig", "Cd", "Cd range, last 1,000 it", "Limited updates"],
            "rows": [[f"{m['cells']:,}", f"{m['iterations']:,}", m["status"], f"{m['residual']:.1e}", f"{m['time']:.0f}",
                      f"{m['standoff']:.4f}", f"{billig():.4f}", f"{m['Cd']:.4f}", f"{100 * m['Cd_range']:.3f} %",
                      f"{m['limited']:,}"]],
            "notes": ["The residual of an inviscid blunt-body wake on triangles does not reach 1e-6 (the wake keeps "
                      "moving); the forebody quantities settle (Cd range in the table)."]}

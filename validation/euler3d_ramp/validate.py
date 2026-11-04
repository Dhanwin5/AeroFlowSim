# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""30 deg ramp at Mach 2 in a box (detached shock), tetrahedra against hexahedra on the same box, with the 3D defaults
of external_3d (node-value gradients, Venkatakrishnan K = 1, update limit 0.2, implicit LU-SGS, 100 first-order
iterations). Mesh and flow: tools/robustness_cases.py (ramp).

Stand-off: along the first row of cells over the bottom wall upstream of the corner (x = 0.3), the pressure (binned in
x, mean over the cells of a bin) crosses half-way between p_inf and the pressure behind a normal Mach 2 shock; the
stand-off is 0.3 - x of that crossing. Full and quick sets are the same (the box is small)."""

import importlib.util
from pathlib import Path

import numpy as np

from aeroflowsim.gasdynamics import normal_shock

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_3D = {"gradient": "Green-Gauss (node values)", "venkat_k": 1.0, "update_limit": 0.2,
               "first_order_iterations": 100, "max_iterations": 20000}
RUNS = {}


def _tool():
    spec = importlib.util.spec_from_file_location("robustness_cases", ROOT / "tools" / "robustness_cases.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _standoff(mesh, W):
    c = mesh.cell_centres
    row = (c[:, 1] < 1.0 / 16.0) & (c[:, 0] < 0.3)
    edges = np.linspace(0.0, 0.3, 49)
    which = np.clip(np.digitize(c[row, 0], edges) - 1, 0, 47)
    p = np.bincount(which, W[-1, row], minlength=48) / np.maximum(np.bincount(which, minlength=48), 1)
    x = 0.5 * (edges[:-1] + edges[1:])
    level = 0.5 * (1e5 + normal_shock(2.0, 1.4)["p2_p1"] * 1e5)
    i = np.flatnonzero((p[:-1] < level) & (p[1:] >= level))
    if not len(i):
        return float("nan")
    k = i[0]
    return float(0.3 - (x[k] + (level - p[k]) * (x[k + 1] - x[k]) / (p[k + 1] - p[k])))


def measure():
    tool = _tool()
    for kind in ("tetrahedra", "hexahedra"):
        mesh, r, _p, _n = tool.ramp(kind, DEFAULTS_3D)
        RUNS[kind] = {"cells": mesh.n_cells, "iterations": r.iterations, "converged": r.converged,
                      "time": r.key_numbers["wall_time"][0], "standoff": _standoff(mesh, r.W),
                      "limited": r.info.get("limited_updates", 0)}
    t, h = RUNS["tetrahedra"], RUNS["hexahedra"]
    return {"standoff_ratio": t["standoff"] / h["standoff"], "converged": 1.0 if t["converged"] else 0.0}


def study():
    rows = [[k, f"{m['cells']:,}", f"{m['iterations']:,}", "yes" if m["converged"] else "NO", f"{m['time']:.0f}",
             f"{m['standoff']:.4f}", f"{m['limited']:,}"] for k, m in RUNS.items()]
    return {"title": "Runs",
            "columns": ["Kind", "Cells", "Iterations", "Converged", "Time [s]", "Stand-off [m]", "Limited updates"],
            "rows": rows,
            "notes": ["Before the robust-second-order stage the tetrahedral run stalled at a residual of 0.26."]}

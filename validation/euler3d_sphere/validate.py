# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sphere at Mach 3 in 3D (external_3d, quarter domain, tetrahedra): bow-shock stand-off vs Billig; the same sphere as a
2D axisymmetric run (external_2d, structured O-grid) for the 2D / 3D consistency check; and a Mach 6 run on tetrahedra
for the positivity fallback and carbuncle behaviour (reported). The template's 3D defaults (LU-SGS, Green-Gauss, K = 1).

Stand-off: in the 3D run the cells within 0.1 R of the x axis upstream of the nose, in the 2D run the cells along the
axis; the shock is where their pressure, ordered by x, crosses half-way between p_inf and the pressure behind a normal
shock (linear interpolation), and Delta = (x of the nose) - (x of that crossing).
Carbuncle indicator: the spread of the shock position over the cells near the axis (a carbuncle shows as a bulge that
moves the shock forward on the axis); and whether the residual converged.
"""

import math

import numpy as np

import aeroflowsim
from aeroflowsim.gasdynamics import normal_shock
from validation.common import is_quick

D = 0.1                      # sphere diameter [m]
R = 0.5 * D
SPHERE_3D = {"body_shape": "Sphere", "diameter": D, "half_domain": True, "quarter_domain": True, "upstream": 1.0,
             "downstream": 1.5, "lateral": 1.5, "max_iter": 20000}
RUNS = {}


def _sizes_3d():
    return {"surface_size": 0.04, "farfield_size": 0.25} if is_quick() else {"surface_size": 0.02, "farfield_size": 0.12}


def billig(mach):
    """Billig (1967) stand-off distance of a sphere / R."""
    return 0.143 * math.exp(3.24 / mach**2)


def _level(mach, p_inf):
    return 0.5 * (p_inf + normal_shock(mach, 1.4)["p2_p1"] * p_inf)


def _crossing(x, p, level):
    o = np.argsort(x)
    x, p = x[o], p[o]
    i = np.flatnonzero((p[:-1] < level) & (p[1:] >= level))
    if not len(i):
        return float("nan")
    k = i[-1]                                  # the last rise before the nose
    return float(x[k] + (level - p[k]) * (x[k + 1] - x[k]) / (p[k + 1] - p[k]))


def standoff_3d(out, mach):
    """Stand-off / R from the pressure field on a slice just inside the symmetry plane z = 0, sampled along the
    stagnation line y = 0+ (node values, linear interpolation, 4,000 points). (Until the robust-second-order stage only
    the cells within 0.1 R of the axis were used; on the coarse cells ahead of the shock that interpolated across gaps
    of several cells: the same flaw as found in the 2D cylinder-on-triangles case. `standoff_3d_cells` keeps the old
    method for the record.)"""
    from scipy.interpolate import LinearNDInterpolator
    from aeroflowsim.post.fields import node_values
    from aeroflowsim.post.solution import Solution
    from aeroflowsim.post.view3d import slice_plane
    mesh, r = out.mesh, out.result
    sol = Solution.from_result(mesh, r, out.params)
    s = slice_plane(mesh, node_values(sol, "p"), (0.0, 0.0, 1e-6 * D), (0.0, 0.0, 1.0))
    near = (s.points[:, 0] < 0.0) & (s.points[:, 1] < 0.5 * D)
    interp = LinearNDInterpolator(s.points[near, :2], s.values[near])
    x = np.linspace(-R - 1.5 * D, -R - 1e-6, 4000)
    p = interp(x, np.full_like(x, 1e-6 * D))
    level = _level(mach, out.params["p_inf"])
    ok = np.isfinite(p)
    i = np.flatnonzero(ok[:-1] & ok[1:] & (p[:-1] < level) & (p[1:] >= level))
    if not len(i):
        return float("nan")
    k = i[-1]
    return (-R - float(x[k] + (level - p[k]) * (x[k + 1] - x[k]) / (p[k + 1] - p[k]))) / R


def standoff_3d_cells(out, mach):
    """The first method (cells within 0.1 R of the axis), kept to report what it gave."""
    mesh, r = out.mesh, out.result
    c = mesh.cell_centres
    near = (np.hypot(c[:, 1], c[:, 2]) < 0.1 * R) & (c[:, 0] < -R)
    x_shock = _crossing(c[near, 0], r.fields["p"].values[near], _level(mach, out.params["p_inf"]))
    return (-R - x_shock) / R


def standoff_2d(out, mach):
    mesh, r = out.mesh, out.result
    cells = mesh.owner[mesh.patch("axis").faces] if any(p.name == "axis" for p in mesh.patches) else \
        np.flatnonzero(mesh.cell_centres[:, 1] < 0.02 * D)
    nose = float(min(mesh.face_centres[mesh.patch(p.name).faces, 0].min() for p in mesh.patches if p.type == "wall"))
    c = mesh.cell_centres[cells]
    up = c[:, 0] < nose
    x_shock = _crossing(c[up, 0], r.fields["p"].values[cells][up], _level(mach, out.params["p_inf"]))
    return (nose - x_shock) / R


def _run3d(mach, extra=None):
    out = aeroflowsim.run_case("cases/external_3d", {**SPHERE_3D, **_sizes_3d(), "mach": mach, **(extra or {})})
    r = out.result
    # a diverged run has no valid flow: no stand-off is read from it (it fails instead of passing by chance)
    standoff = float("nan") if r.info["status"] == "diverged" else standoff_3d(out, mach)
    old = float("nan") if r.info["status"] == "diverged" else standoff_3d_cells(out, mach)
    return {"standoff": standoff, "standoff_cells": old, "cells": out.mesh.n_cells, "iterations": r.iterations,
            "converged": r.converged, "time": r.key_numbers["wall_time"][0], "Cd": r.key_numbers["Cd"][0],
            "positivity": r.info["positivity_events"], "cfl_reductions": r.info["cfl_reductions"]}


def _run2d(mach):
    inputs = {"shape": "Sphere", "sphere.diameter": D, "mesh_type": "Structured C/O-grid", "mach": mach,
              "first_order_iterations": 200, "max_iter": 20000}
    out = aeroflowsim.run_case("cases/external_2d", inputs)
    r = out.result
    return {"standoff": standoff_2d(out, mach), "cells": out.mesh.n_cells, "iterations": r.iterations,
            "converged": r.converged, "time": r.key_numbers["wall_time"][0], "Cd": r.key_numbers["Cd"][0],
            "positivity": r.info["positivity_events"], "cfl_reductions": r.info["cfl_reductions"]}


def measure():
    RUNS["3D Mach 3"] = _run3d(3.0)
    RUNS["2D axisymmetric Mach 3"] = _run2d(3.0)
    if not is_quick():
        RUNS["3D Mach 6"] = _run3d(6.0)
    return {"standoff": RUNS["3D Mach 3"]["standoff"], "standoff_2d": RUNS["2D axisymmetric Mach 3"]["standoff"]}


def study():
    rows = []
    for name, m in RUNS.items():
        mach = 6.0 if "6" in name else 3.0
        rows.append([name, f"{m['cells']:,}", f"{m['iterations']:,}", "yes" if m["converged"] else "NO",
                     f"{m['time']:.0f}", f"{m['standoff']:.4f}", f"{m.get('standoff_cells', float('nan')):.4f}",
                     f"{billig(mach):.4f}", f"{m['Cd']:.4f}",
                     f"{m['positivity']:,}", f"{m['cfl_reductions']}"])
    return {"title": "Runs", "columns": ["Run", "Cells", "Iterations", "Converged", "Time [s]", "Stand-off / R",
                                         "Stand-off / R (old cell method)", "Billig", "Cd", "Positivity fallbacks", "CFL reductions"],
            "rows": rows,
            "notes": ["Mach 6 on tetrahedra (full set): reported for the positivity fallback and the carbuncle; a "
                      "converged run with a stand-off near Billig means no carbuncle bulge on the stagnation line."]}

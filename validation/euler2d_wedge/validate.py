# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mach 2 flow over a 10 deg wedge with the external_2d template: shock angle, surface pressure, M2.

Domain: half domain (symmetry plane y = 0), rectangle 0.5 L upstream, 0.5 L downstream, 1.5 L high; Gmsh
triangles with wall cells of 0.02 L. The template's default numerics; only the Mach number (2) and a short
first-order start (the smart rule's suggestion for supersonic flow) are set.

Measured: the shock position at six heights above the wedge surface (where the pressure, interpolated
linearly between the cell centres, crosses half-way between p1 and p2 along horizontal lines), a straight
line through them and the tip gives beta; p2/p1 and M2
are the means over the wedge-surface cells between 20 % and 80 % of the length (away from the tip and the
base corner, where the flow is not uniform).
"""

import math

import numpy as np
from scipy.interpolate import LinearNDInterpolator

import aeroflowsim
from aeroflowsim.gasdynamics import normal_shock

CASE = "cases/external_2d"
INPUTS = {"shape": "Wedge", "wedge.half_angle": 10.0, "half_domain": True, "domain_shape": "Rectangle",
          "upstream": 0.5, "downstream": 0.5, "height": 1.5, "surface_size": 0.02, "farfield_size": 0.05,
          "mach": 2.0, "first_order_iterations": 200, "max_iter": 30000}
FINER = {"surface_size": 0.01, "farfield_size": 0.025}
RUNS = {}
THETA = 10.0     # [deg]


def _measure(out):
    mesh, r = out.mesh, out.result
    xc, yc = mesh.cell_centres[:, 0], mesh.cell_centres[:, 1]
    p, M = r.fields["p"].values, r.fields["M"].values
    p1 = out.params["p_inf"]
    p2_theory = 1.7066 * p1
    level = 0.5 * (p1 + p2_theory)
    t = math.tan(math.radians(THETA))
    # Shock position on horizontal lines y = yk above the wedge, from the pressure along the line
    xs, ys = [], []
    interpolate = LinearNDInterpolator(np.column_stack([xc, yc]), p)   # p between the cell centres
    for yk in np.linspace(0.15, 0.6, 6):
        x = np.linspace(-0.3, yk / t, 2000)                    # the line y = yk, from upstream to the wedge
        pk = interpolate(x, np.full_like(x, yk))
        i = np.flatnonzero((pk[:-1] < level) & (pk[1:] >= level))
        if len(i):
            k = i[0]
            xs.append(x[k] + (level - pk[k]) * (x[k + 1] - x[k]) / (pk[k + 1] - pk[k]))
            ys.append(yk)
    xs, ys = np.array(xs), np.array(ys)
    slope = float(np.sum(xs * ys) / np.sum(xs * xs))           # line through the tip (0, 0)
    beta = math.degrees(math.atan(slope))
    # Surface cells: next to the wall, between 20 % and 80 % of the length
    wall = mesh.patch("wall")
    cells = mesh.owner[wall.faces]
    fx = mesh.face_centres[wall.faces, 0]
    fy = mesh.face_centres[wall.faces, 1]
    front = (fy > 0.0) & (fx > 0.2) & (fx < 0.8) & (mesh.face_normals[wall.faces, 0] > 0.0)
    return {"beta": beta, "p_ratio": float(np.mean(p[cells[front]]) / p1), "M2": float(np.mean(M[cells[front]])),
            "cells": mesh.n_cells, "iterations": r.iterations, "converged": r.converged,
            "time": r.key_numbers["wall_time"][0], "Cd": r.key_numbers["Cd"][0]}


def measure():
    RUNS["wall 0.02 L"] = _measure(aeroflowsim.run_case(CASE, INPUTS))
    RUNS["wall 0.01 L"] = _measure(aeroflowsim.run_case(CASE, {**INPUTS, **FINER}))
    return {k: RUNS["wall 0.02 L"][k] for k in ("beta", "p_ratio", "M2")}


def study():
    rows = [[name, f"{m['cells']:,}", f"{m['iterations']:,}", "yes" if m["converged"] else "NO", f"{m['time']:.0f}",
             f"{m['beta']:.3f}", f"{m['p_ratio']:.4f}", f"{m['M2']:.4f}", f"{m['Cd']:.4f}"] for name, m in RUNS.items()]
    shock = normal_shock(2.0 * math.sin(math.radians(39.314)), 1.4)
    return {"title": "Two meshes", "columns": ["Mesh", "Cells", "Iterations", "Converged", "Time [s]", "beta [deg]",
                                               "p2/p1", "M2", "Cd (incl. base)"], "rows": rows,
            "notes": [f"Theory: beta = 39.314 deg, p2/p1 = {shock['p2_p1']:.4f}, M2 = 1.6405.",
                      "Cd includes the base drag of the flat base (the base pressure is not part of the oblique-shock "
                      "theory)."]}

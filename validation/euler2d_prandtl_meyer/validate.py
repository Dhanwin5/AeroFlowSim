# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Prandtl-Meyer expansion round a 10 deg convex corner at Mach 2 (planar), with the geometry_2d template.

The geometry is drawn in the workspace (a closed polyline, the fluid domain): the wall runs along y = 0 from
x = -0.5 m to the corner at the origin and then 10 deg downwards to x = 1 m; the inlet (left) is a supersonic
inlet, the outlet (right) a supersonic outlet, the top (y = 1 m) a slip wall that the expansion fan does not
reach inside the domain (its first Mach line leaves the corner at 30 deg and meets y = 1 m at x = 1.73 m).
Measured: the mean Mach number and pressure of the wall cells downstream of the corner, between x = 0.4 m and
0.9 m (where the whole fan has passed: its last Mach line, at 24.8 deg to the turned wall, leaves the wall at once).
"""

import math

import numpy as np

import aeroflowsim
from aeroflowsim.discovery import load_case
from aeroflowsim.geometry_model import GeometryDocument
from aeroflowsim.geometry_model.operations import NameBoundary, Sketch
from aeroflowsim.parameters import defaults, validate
from aeroflowsim.workspace_mesh import mesh_for
from validation.common import is_quick

CASE = "cases/geometry_2d"
TURN = 10.0       # [deg]
FREE = {"mach": 2.0, "p": 101325.0, "T": 288.15, "flow_angle": 0.0}
RUNS = {}


def geometry():
    drop = 1.0 * math.tan(math.radians(TURN))
    pts = [[-0.5, 0.0], [0.0, 0.0], [1.0, -drop], [1.0, 1.0], [-0.5, 1.0]]
    return GeometryDocument([Sketch("op1", kind="polyline", points=pts, closed=True, role="fluid"),
                             NameBoundary("op2", edges=["op1:e1", "op1:e2"], name="wall", kind="wall"),
                             NameBoundary("op3", edges=["op1:e3"], name="outlet", kind="outlet"),
                             NameBoundary("op4", edges=["op1:e4"], name="top", kind="wall"),
                             NameBoundary("op5", edges=["op1:e5"], name="inlet", kind="inlet")])


def measure():
    case = load_case(CASE)
    size = 0.02 if is_quick() else 0.01
    params = validate(case.parameters(), {**defaults(case.parameters()), "flow_type": "External (body in a free stream)",
                                          "gas": "air", "mach": 2.0, "p_inf": 101325.0, "T_inf": 288.15,
                                          "surface_size": size, "max_size": 2 * size, "first_order_iterations": 200,
                                          "max_iter": 30000,
                                          "boundaries": {"inlet": {"type": "supersonic_inlet", **FREE},
                                                         "outlet": {"type": "supersonic_outlet"},
                                                         "wall": {"type": "slip_wall"}, "top": {"type": "slip_wall"}}})
    mesh = mesh_for(case, params, geometry())
    out = aeroflowsim.run_case(case, params, mesh=mesh)
    r = out.result
    wall = mesh.patch("wall")
    cells = mesh.owner[wall.faces]
    fx = mesh.face_centres[wall.faces, 0]
    keep = (fx > 0.4) & (fx < 0.9)
    M = float(np.mean(r.fields["M"].values[cells[keep]]))
    p = float(np.mean(r.fields["p"].values[cells[keep]]) / 101325.0)
    RUNS["corner"] = {"cells": mesh.n_cells, "iterations": r.iterations, "converged": r.converged,
                      "time": r.key_numbers["wall_time"][0], "M": M, "p": p}
    return {"M2": M, "p2_p1": p}


def study():
    m = RUNS["corner"]
    return {"title": "Run", "columns": ["Cells", "Iterations", "Converged", "Time [s]", "M2", "p2/p1"],
            "rows": [[f"{m['cells']:,}", f"{m['iterations']:,}", "yes" if m["converged"] else "NO", f"{m['time']:.0f}",
                      f"{m['M']:.4f}", f"{m['p']:.4f}"]],
            "notes": ["Wall cells next to a centred expansion: the first-cell values lag the exact fan slightly on coarse "
                      "meshes (the fan is smeared over a few cells at the corner)."]}

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sod shock tube with the 2D Euler solver: along x on quads, and along the diagonal of a triangle mesh.

The 2D solver must reproduce the 1D exact solution (aeroflowsim/riemann_exact.py) whatever the
direction of the flow relative to the mesh. Waves are located where the pressure (shock) or density
(contact) crosses half-way between the two plateaus next to it.
"""

import math

import numpy as np

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import EulerSolver, Numerics
from aeroflowsim.gases import gas_model
from aeroflowsim.simple_meshes import rectangle_mesh

LEFT, RIGHT = (1.0, 0.0, 1.0), (0.125, 0.0, 0.1)       # rho [kg/m³], u [m/s], p [Pa]
T_END = 0.2                                           # [s]
P_STAR, RHO_STAR_L, RHO_STAR_R = 0.30313, 0.42632, 0.26557
TIMES = {}


def solve(mesh, direction, origin, select=None):
    """Run the shock tube on `mesh`; the tube runs along the unit vector `direction` through `origin`.

    Returns (s, rho, speed along the tube, p) of the selected cells, sorted by s (the distance from the
    diaphragm, which is the line through `origin` normal to `direction`).
    """
    gas = gas_model("air")                            # gamma = 1.4, as in Toro's test 1
    bcs = {p.name: BoundaryCondition("supersonic_outlet") for p in mesh.patches}   # no wave reaches them
    xy = mesh.cell_centres[:, :2]
    s = (xy - origin) @ np.asarray(direction)
    W0 = np.zeros((4, mesh.n_cells))
    left = s <= 0.0
    W0[0] = np.where(left, LEFT[0], RIGHT[0])
    W0[3] = np.where(left, LEFT[2], RIGHT[2])
    solver = EulerSolver(mesh, gas, bcs, Numerics(cfl=0.8, end_time=T_END, max_iterations=100000),
                         L_ref=1.0, scales=(1.0, 1.0, 1.0, 1.0))
    out = solver.solve(W0)
    if out.status != "end_time":
        raise RuntimeError(f"Sod 2D run ended with status {out.status}: {out.message}")
    speed = out.W[1] * direction[0] + out.W[2] * direction[1]
    keep = np.ones(mesh.n_cells, bool) if select is None else select(xy)
    order = np.argsort(s[keep])
    return (s[keep][order], out.W[0][keep][order], speed[keep][order], out.W[3][keep][order],
            out.wall_time_s)


def plateau(s, f, start, end):
    """Mean of f over the cells with start <= s <= end: the level of a flat plateau [unit of f].

    On a triangle mesh the plateaus carry small 2D ripples (about +-2 % behind the contact at 45 degrees
    to the edges); a mean over the plateau measures its level, a single point would measure a ripple.
    """
    inside = (s >= start) & (s <= end)
    return float(f[inside].mean())


def crossing(s, f, level, after):
    """First s > after where f falls below `level` (linear interpolation) [m]."""
    i = np.flatnonzero((s[:-1] > after) & (f[:-1] >= level) & (f[1:] < level))[0]
    return float(s[i] + (level - f[i]) * (s[i + 1] - s[i]) / (f[i + 1] - f[i]))


def measure():
    out = {}
    # Along x: 400 x 2 quads, the tube from -0.5 to 0.5 m
    mesh = rectangle_mesh(400, 2, x0=-0.5, x1=0.5, y0=0.0, y1=0.005)
    s, rho, u, p, wall = solve(mesh, (1.0, 0.0), (0.0, 0.0))
    TIMES["along x, quads"] = (mesh.n_cells, wall)
    # Exact wave positions: rarefaction tail -0.014 m, contact 0.185 m, shock 0.350 m. The plateaus are
    # averaged away from the smeared waves: p and u over [0.03, 0.31] m (both sides of the contact, where
    # they are equal), rho*L over [0.03, 0.15] m, rho*R over [0.22, 0.31] m.
    out["p_star_x"] = plateau(s, p, 0.03, 0.31)
    out["u_star_x"] = plateau(s, u, 0.03, 0.31)
    out["rho_star_L_x"] = plateau(s, rho, 0.03, 0.15)
    out["rho_star_R_x"] = plateau(s, rho, 0.22, 0.31)
    out["shock_travel_x"] = crossing(s, p, 0.5 * (P_STAR + RIGHT[2]), 0.2)
    out["contact_travel_x"] = crossing(s, rho, 0.5 * (RHO_STAR_L + RHO_STAR_R), 0.0)

    # Diagonal: 100 x 100 squares split into triangles; the tube along (1, 1)/sqrt(2) through (0.5, 0.5),
    # read in the cells within 0.02 m of the diagonal x = y
    mesh = rectangle_mesh(100, 100, triangles=True)
    d = (1.0 / math.sqrt(2.0), 1.0 / math.sqrt(2.0))
    s, rho, u, p, wall = solve(mesh, d, (0.5, 0.5), select=lambda xy: np.abs(xy[:, 0] - xy[:, 1]) < 0.02)
    TIMES["diagonal, triangles"] = (mesh.n_cells, wall)
    out["p_star_diag"] = plateau(s, p, 0.03, 0.31)
    out["u_star_diag"] = plateau(s, u, 0.03, 0.31)
    out["rho_star_L_diag"] = plateau(s, rho, 0.03, 0.15)
    out["shock_travel_diag"] = crossing(s, p, 0.5 * (P_STAR + RIGHT[2]), 0.2)
    return out


def study():
    """Mesh size and wall-clock time of the two runs (CLAUDE.md rule 14)."""
    rows = [[name, f"{n:,}", f"{wall:.1f}"] for name, (n, wall) in TIMES.items()]
    return {"title": "Runs", "columns": ["Run", "Cells", "Wall-clock time [s]"], "rows": rows,
            "notes": ["Second order (least-squares gradients, Venkatakrishnan limiter), SSP-RK3, CFL 0.8, "
                      "one global time step; time-accurate to t = 0.2 s."]}

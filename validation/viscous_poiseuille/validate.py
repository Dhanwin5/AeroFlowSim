# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Hagen-Poiseuille flow in a tube, axisymmetric laminar Navier-Stokes (set-up and tolerances in reference.toml)."""

import time

import numpy as np

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import LUSGS, EulerSolver, Numerics
from aeroflowsim.euler.state import primitive_to_conserved, uniform_state
from aeroflowsim.euler.viscous import LAMINAR, ViscousSettings
from aeroflowsim.euler.wall_fields import wall_data
from aeroflowsim.simple_meshes import graded_rectangle
from validation.viscous_couette.validate import MU, gas

R, D = 0.5e-3, 1e-3
P0, P_OUT, T0 = 5100.0, 4600.0, 300.0
TIMING = {}


def section(mesh, W, x):
    """(u_m, u_centre, rho_bulk) of the column of cells nearest to x."""
    cc = mesh.cell_centres
    xs = np.unique(np.round(cc[:, 0], 12))
    xc = xs[np.argmin(np.abs(xs - x))]
    col = np.flatnonzero(np.abs(cc[:, 0] - xc) < 1e-12)
    r, u, rho = cc[col, 1], W[1, col], W[0, col]
    A = mesh.cell_volumes[col] * r                         # r dr (per radian)
    u_m = float(np.sum(u * A) / np.sum(A))
    near = np.argsort(r)[:4]
    c = np.polyfit(r[near] ** 2, u[near], 1)             # u = a + b r^2 near the axis
    return u_m, float(c[-1]), float(np.sum(rho * A) / np.sum(A)), xc


def measure():
    g = gas()
    xs = np.linspace(0.0, 20 * D, 201)
    ys = np.linspace(0.0, R, 21)
    mesh = graded_rectangle(xs, ys, bottom=(("axis", "axis", None),), kinds={"top": "wall"}, axisymmetric=True)
    mesh.patches  # noqa: B018
    bc = {"left": BoundaryCondition("total_pressure_inlet", {"p0": P0, "T0": T0}),
          "right": BoundaryCondition("pressure_outlet", {"p": P_OUT}),
          "top": BoundaryCondition("no_slip_wall"), "axis": BoundaryCondition("axis")}
    num = Numerics(time_scheme=LUSGS, cfl=5, cfl_max=1e3, max_iterations=150000, residual_drop=9, limiter="None")
    s = EulerSolver(mesh, g, bc, num, viscous=ViscousSettings(LAMINAR))
    t = time.perf_counter()
    r = s.solve(uniform_state(mesh.n_cells, P_OUT / (g.R * T0), (20.0, 0.0), 0.5 * (P0 + P_OUT)))
    TIMING["run"] = (r.iterations, time.perf_counter() - t, r.status, mesh.n_cells,
                     float(r.residuals[-1].max()) if len(r.residuals) else 0.0)
    if r.status == "diverged":
        return {k: float("nan") for k in ("umax_over_umean", "wall_shear", "pressure_drop")}
    W = r.W
    s.residual(primitive_to_conserved(W, g), True, W)
    u_m, u_c, rho, x15 = section(mesh, W, 15 * D)
    u_a, _, _, xa = section(mesh, W, 14 * D)
    u_b, _, _, xb = section(mesh, W, 16 * D)
    data = wall_data(s, W)
    xw = data["x"][:, 0]
    tau = float(np.linalg.norm(data["tau_w"][np.argmin(np.abs(xw - x15))]))
    sel = (xw >= 14 * D) & (xw <= 16 * D)
    dpdx = float(np.polyfit(xw[sel], data["p"][sel], 1)[0])
    ref = -8.0 * MU * u_m / R**2 - 4.0 / 3.0 * rho * u_m * (u_b - u_a) / (xb - xa)
    TIMING["Re_bulk"] = rho * u_m * D / MU
    TIMING["M_centre"] = u_c / float(g.sound_speed(T0))
    return {"umax_over_umean": u_c / u_m, "wall_shear": tau * R / (MU * u_m), "pressure_drop": dpdx / ref}


def study():
    it, w, st, n, res = TIMING["run"]
    return {"title": "Run", "columns": ["Cells", "Iterations", "Time [s]", "Status", "Residual", "Re (bulk, D)",
                                        "Centreline Mach"],
            "rows": [[f"{n:,}", f"{it:,}", f"{w:.0f}", st, f"{res:.1e}", f"{TIMING.get('Re_bulk', 0):.1f}",
                      f"{TIMING.get('M_centre', 0):.3f}"]], "notes": ["LU-SGS, CFL 5 -> 1000 (SER)."]}

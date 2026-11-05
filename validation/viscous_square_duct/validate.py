# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Laminar square-duct flow in 3D (set-up in reference.toml). The exact series of White (2006) eq. 3-48 is evaluated here
and must reproduce the pre-registered reference values (2.0962, 56.91) to 0.01 %, so the references are computed, not
typed in."""

import math
import time

import numpy as np

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import LUSGS, EulerSolver, Numerics
from aeroflowsim.euler.state import primitive_to_conserved, uniform_state
from aeroflowsim.euler.viscous import LAMINAR, ViscousSettings
from aeroflowsim.euler.wall_fields import wall_data
from aeroflowsim.simple_meshes import box_mesh_3d
from validation.viscous_couette.validate import MU, gas

A = 1e-3                                 # side [m]
P0, P_OUT, T0 = 5200.0, 5000.0, 300.0
TIMING = {}


def series(terms=300, n=400):
    """(u_max/u_m, f Re) of fully developed flow in a square duct |y|, |z| < b (White 2006 eq. 3-48 with a = b):
    u = 16 b^2 G / (mu pi^3) sum_{i odd} (-1)^((i-1)/2) [1 - cosh(i pi z/2b)/cosh(i pi/2)] cos(i pi y/2b) / i^3."""
    b = 1.0
    s = (np.arange(n) + 0.5) / n * 2.0 - 1.0
    Y, Z = np.meshgrid(s, s, indexing="ij")
    u = np.zeros_like(Y)
    u0 = 0.0
    for i in range(1, 2 * terms, 2):
        k = i * math.pi / 2.0
        c = (-1) ** ((i - 1) // 2) / i**3
        u += c * (1.0 - np.exp(k * (np.abs(Z) - 1.0)) * (1.0 + np.exp(-2.0 * k * np.abs(Z))) / (1.0 + math.exp(-2.0 * k))) * np.cos(k * Y)
        u0 += c * (1.0 - 2.0 * math.exp(-k) / (1.0 + math.exp(-2.0 * k)))
    scale = 16.0 / math.pi**3                          # b = G = mu = 1
    u, u0 = u * scale, u0 * scale
    um = float(u.mean())
    # mean wall shear = G A / P = (2b)^2 / (8 b) = b / 2; f Re = 8 tau D_h / (mu u_m), D_h = 2 b
    return u0 / um, 8.0 * 0.5 * 2.0 / um


def measure():
    ratio, fre = series()
    if abs(ratio / 2.0962 - 1) > 1e-4 or abs(fre / 56.91 - 1) > 1e-4:
        raise RuntimeError(f"The series gives {ratio:.5f} and {fre:.4f}, not the pre-registered references.")
    g = gas()
    mesh = box_mesh_3d(64, "hexahedra", lo=(0.0, 0.0, 0.0), hi=(8 * A, A / 2, A / 2), ny=12, nz=12)
    bc = {"xmin": BoundaryCondition("total_pressure_inlet", {"p0": P0, "T0": T0}),
          "xmax": BoundaryCondition("pressure_outlet", {"p": P_OUT}),
          "ymin": BoundaryCondition("symmetry"), "zmin": BoundaryCondition("symmetry"),
          "ymax": BoundaryCondition("no_slip_wall"), "zmax": BoundaryCondition("no_slip_wall")}
    num = Numerics(time_scheme=LUSGS, cfl=5, cfl_max=1e3, max_iterations=100000, residual_drop=9, limiter="None")
    s = EulerSolver(mesh, g, bc, num, viscous=ViscousSettings(LAMINAR))
    t = time.perf_counter()
    r = s.solve(uniform_state(mesh.n_cells, P_OUT / (g.R * T0), (10.0, 0.0, 0.0), 0.5 * (P0 + P_OUT)))
    TIMING["run"] = (r.iterations, time.perf_counter() - t, r.status, mesh.n_cells,
                     float(r.residuals[-1].max()) if len(r.residuals) else 0.0)
    if r.status == "diverged":
        return {"umax_over_umean": float("nan"), "fRe": float("nan")}
    W = r.W
    s.residual(primitive_to_conserved(W, g), True, W)
    cc = mesh.cell_centres
    xs = np.unique(np.round(cc[:, 0], 12))
    xc = xs[np.argmin(np.abs(xs - 6 * A))]
    col = np.flatnonzero(np.abs(cc[:, 0] - xc) < 1e-12)
    vol = mesh.cell_volumes[col]
    u = W[1, col]
    u_m = float(np.sum(u * vol) / np.sum(vol))
    # centreline: quadratic fit in y and z of the cells nearest the axis corner (y, z -> 0)
    yz = cc[col, 1:3]
    near = np.argsort(np.hypot(yz[:, 0], yz[:, 1]))[:9]
    M = np.column_stack([np.ones(9), yz[near, 0] ** 2, yz[near, 1] ** 2])
    u_c = float(np.linalg.lstsq(M, u[near], rcond=None)[0][0])
    data = wall_data(s, W)
    on = np.abs(data["x"][:, 0] - xc) < 1e-12
    tau = float(np.sum(np.linalg.norm(data["tau_w"][on], axis=1) * data["area"][on]) / np.sum(data["area"][on]))
    TIMING["Re"] = float(np.mean(W[0, col])) * u_m * A / MU
    return {"umax_over_umean": u_c / u_m, "fRe": 8.0 * tau * A / (MU * u_m)}


def study():
    it, w, st, n, res = TIMING["run"]
    return {"title": "Run", "columns": ["Cells", "Iterations", "Time [s]", "Status", "Residual", "Re (bulk)"],
            "rows": [[f"{n:,}", f"{it:,}", f"{w:.0f}", st, f"{res:.1e}", f"{TIMING.get('Re', 0):.1f}"]],
            "notes": ["Quarter duct, LU-SGS, CFL 5 -> 1000 (SER)."]}

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""TMR turbulent flat plate, SA and SST on a grid series (set-up and references in reference.toml)."""

import time

import numpy as np

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import LUSGS, EulerSolver, Numerics
from aeroflowsim.euler.state import primitive_to_conserved, uniform_state
from aeroflowsim.euler.turbulence import attach_turbulence
from aeroflowsim.euler.viscous import SA, SST, ViscousSettings
from aeroflowsim.euler.wall_fields import wall_data
from aeroflowsim.gases import gas_model
from aeroflowsim.simple_meshes import geometric_points, graded_rectangle
from validation.common import is_quick

X_REF = 0.970084071
RUNS = []


def grids():
    return [(136, 96, 4e-6)] if is_quick() else [(136, 96, 4e-6), (272, 192, 2e-6), (544, 384, 1e-6)]


def run(model, nx, ny, first):
    g = gas_model("air")
    T, M = 300.0, 0.2
    a = float(g.sound_speed(T))
    U, mu = M * a, float(g.mu(T))
    rho = 5e6 * mu / U
    p = rho * g.R * T
    n_front = max(nx // 8, 4)
    n_plate = nx - n_front
    xs = np.concatenate([geometric_points(0.0, -0.33, n_front, 4e-4 * 136 / nx)[::-1][:-1],
                         geometric_points(0.0, 2.0, n_plate, 4e-4 * 136 / nx)])
    ys = geometric_points(0.0, 1.0, ny, first)
    mesh = graded_rectangle(xs, ys, bottom=(("front", "symmetry", 0.0), ("plate", "wall", None)))
    fs = {"mach": M, "p": p, "T": T}
    bc = {"left": BoundaryCondition("far_field", fs), "top": BoundaryCondition("far_field", fs),
          "right": BoundaryCondition("pressure_outlet", {"p": p}), "front": BoundaryCondition("symmetry"),
          "plate": BoundaryCondition("no_slip_wall")}
    num = Numerics(time_scheme=LUSGS, cfl=5, cfl_max=1e3, max_iterations=150000, residual_drop=8, limiter="None")
    s = EulerSolver(mesh, g, bc, num, viscous=ViscousSettings(model))
    attach_turbulence(s)
    t = time.perf_counter()
    r = s.solve(uniform_state(mesh.n_cells, rho, (U, 0.0), p))
    wall = time.perf_counter() - t
    s.residual(primitive_to_conserved(r.W, g), True, r.W)
    d = wall_data(s, r.W)
    x = d["x"][:, 0]
    o = np.argsort(x)
    cf = np.linalg.norm(d["tau_w"], axis=1) / (0.5 * rho * U * U)
    value = float(np.interp(X_REF, x[o], cf[o])) if r.status != "diverged" else float("nan")
    RUNS.append([model, f"{nx} x {ny}", f"{mesh.n_cells:,}", f"{r.iterations:,}", f"{wall:.0f}", r.status,
                 f"{r.residuals[-1].max():.1e}" if len(r.residuals) else "-", f"{d['y_plus'].max():.2f}", f"{value:.6e}"])
    return value


def measure():
    out = {}
    for model, key in ((SA, "cf_sa"), (SST, "cf_sst")):
        for nx, ny, first in grids():
            out[key] = run(model, nx, ny, first)       # the last (finest) grid is the compared value
    return out


def study():
    return {"title": "Grid series", "columns": ["Model", "Grid", "Cells", "Iterations", "Time [s]", "Status",
                                                "Residual", "y+ max", "Cf(0.97)"],
            "rows": RUNS, "notes": ["LU-SGS (CFL 5 -> 1000), turbulence loosely coupled implicit SGS, first-order "
                                    "turbulence convection (as the TMR CFL3D/FUN3D runs)."]}

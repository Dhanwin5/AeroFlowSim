# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Plane Couette flow with viscous heating, 2D quads and 3D hexahedra (reference.toml has the set-up and the exact
solution). Wall shear from the solver's own wall flux (euler/wall_fields.wall_data); peak temperature rise from the
cell temperatures interpolated quadratically to mid-gap."""

import dataclasses
import math
import time

import numpy as np

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import LUSGS, EulerSolver, Numerics
from aeroflowsim.euler.state import uniform_state
from aeroflowsim.euler.viscous import LAMINAR, ViscousSettings
from aeroflowsim.euler.wall_fields import wall_data
from aeroflowsim.gases import gas_model
from aeroflowsim.gases.data import TransportLaw
from aeroflowsim.gases.model import CaloricallyPerfectGas
from aeroflowsim.simple_meshes import box_mesh_3d, rectangle_mesh

MU, K = 1.846e-5, 0.02624        # constant viscosity [Pa s] and conductivity [W/(m K)]
H, P, T_W = 1e-3, 1000.0, 300.0  # gap [m], pressure [Pa], wall temperature [K]
TIMING = {}


def gas():
    base = gas_model("air").data
    return CaloricallyPerfectGas(dataclasses.replace(base, viscosity=TransportLaw("power", MU, 300.0, n=0.0),
                                                     conductivity=TransportLaw("power", K, 300.0, n=0.0)))


def run(dim):
    g = gas()
    U = 0.2 * math.sqrt(1.4 * g.R * T_W)
    wall = {"thermal": "Isothermal", "T_wall": T_W}
    if dim == 2:
        mesh = rectangle_mesh(4, 32, 0.0, H / 4, 0.0, H)
        bc = {"left": BoundaryCondition("supersonic_outlet"), "right": BoundaryCondition("supersonic_outlet"),
              "bottom": BoundaryCondition("no_slip_wall", wall),
              "top": BoundaryCondition("no_slip_wall", {**wall, "u_wall": U})}
        vel = (U / 2, 0.0)
    else:
        mesh = box_mesh_3d(2, "hexahedra", hi=(H / 4, H, H / 4), ny=32, nz=2)
        bc = {"xmin": BoundaryCondition("supersonic_outlet"), "xmax": BoundaryCondition("supersonic_outlet"),
              "zmin": BoundaryCondition("symmetry"), "zmax": BoundaryCondition("symmetry"),
              "ymin": BoundaryCondition("no_slip_wall", wall),
              "ymax": BoundaryCondition("no_slip_wall", {**wall, "u_wall": U})}
        vel = (U / 2, 0.0, 0.0)
    num = Numerics(time_scheme=LUSGS, cfl=5, cfl_max=1e3, max_iterations=60000, residual_drop=10, limiter="None")
    s = EulerSolver(mesh, g, bc, num, viscous=ViscousSettings(LAMINAR))
    t = time.perf_counter()
    r = s.solve(uniform_state(mesh.n_cells, P / (g.R * T_W), vel, P))
    TIMING[dim] = (r.iterations, time.perf_counter() - t, r.status, mesh.n_cells)
    if r.status == "diverged":
        return float("nan"), float("nan")
    from aeroflowsim.euler.state import primitive_to_conserved
    s.residual(primitive_to_conserved(r.W, g), True, r.W)
    data = wall_data(s, r.W)
    bottom = data["x"][:, 1] < 0.5 * H
    tau = float(np.mean(np.linalg.norm(data["tau_w"][bottom], axis=1)))
    y = mesh.cell_centres[:, 1]
    T = r.W[-1] / (r.W[0] * g.R)
    near = np.argsort(np.abs(y - 0.5 * H))[: 3 * mesh.n_cells // 32 + 3]
    c = np.polyfit(y[near] - 0.5 * H, T[near], 2)
    rise = c[-1] - T_W
    return tau / (MU * U / H), rise / (MU * U**2 / (8.0 * K))


def measure():
    s2, t2 = run(2)
    s3, t3 = run(3)
    return {"shear_2d": s2, "temperature_rise_2d": t2, "shear_3d": s3, "temperature_rise_3d": t3}


def study():
    rows = [[f"{d}D", f"{n:,}", f"{it:,}", f"{w:.1f}", st] for d, (it, w, st, n) in TIMING.items()]
    return {"title": "Runs", "columns": ["Case", "Cells", "Iterations", "Time [s]", "Status"], "rows": rows,
            "notes": ["LU-SGS, CFL 5 -> 1000 (SER), residual drop 10 orders."]}

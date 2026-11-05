# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Laminar flat plate (Blasius) in 2D and a one-layer 3D extrusion (set-up in reference.toml). The plate runner `plate()`
is shared with validation/viscous_plate_heat."""

import dataclasses
import math
import time

import numpy as np
from scipy.integrate import solve_ivp

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import LUSGS, EulerSolver, Numerics
from aeroflowsim.euler.state import primitive_to_conserved, uniform_state
from aeroflowsim.euler.viscous import LAMINAR, ViscousSettings
from aeroflowsim.euler.wall_fields import wall_data
from aeroflowsim.gases import gas_model
from aeroflowsim.gases.model import CaloricallyPerfectGas
from aeroflowsim.simple_meshes import extrude_2d, geometric_points, graded_rectangle

L_PLATE, RE_PER_M = 0.1, 2e6
TIMING = {}


def blasius():
    """(f''(0), eta_99) of the Blasius equation f''' + f f''/2 = 0, f(0) = f'(0) = 0, f'(inf) = 1 (shooting)."""
    def end(s):
        sol = solve_ivp(lambda t, y: [y[1], y[2], -0.5 * y[0] * y[2]], (0, 15), [0, 0, s], rtol=1e-11, atol=1e-12)
        return sol.y[1, -1] - 1.0
    lo, hi = 0.2, 0.5
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if end(mid) < 0 else (lo, mid)
    s = 0.5 * (lo + hi)
    sol = solve_ivp(lambda t, y: [y[1], y[2], -0.5 * y[0] * y[2]], (0, 15), [0, 0, s], rtol=1e-11, atol=1e-12,
                    dense_output=True)
    eta = np.linspace(0, 15, 150001)
    fp = sol.sol(eta)[1]
    return s, float(np.interp(0.99, fp, eta))


def plate_gas(constant_pr=False):
    g = gas_model("air")
    if constant_pr:
        g = CaloricallyPerfectGas(dataclasses.replace(g.data, conductivity=None, prandtl=0.72))
    return g


def plate_mesh():
    xs = np.concatenate([geometric_points(0.0, -0.05, 20, 1e-4)[::-1][:-1], geometric_points(0.0, L_PLATE, 120, 1e-4)])
    ys = geometric_points(0.0, 0.05, 64, 1e-5)
    return graded_rectangle(xs, ys, bottom=(("front", "symmetry", 0.0), ("plate", "wall", None)),
                            kinds={"left": "inlet", "right": "outlet", "top": "farfield"})


def plate(mach, T_inf, wall=None, dim=2, constant_pr=False, key=""):
    """Run the plate; returns (solver, W, gas, U_inf, rho_inf) after a final residual evaluation."""
    g = plate_gas(constant_pr)
    c = float(g.sound_speed(T_inf))
    U = mach * c
    mu = float(g.mu(T_inf))
    rho = RE_PER_M * mu / U
    p = rho * g.R * T_inf
    mesh = plate_mesh()
    fs = {"mach": mach, "p": p, "T": T_inf}
    if mach > 1.0:
        bc = {"left": BoundaryCondition("supersonic_inlet", fs), "right": BoundaryCondition("supersonic_outlet"),
              "top": BoundaryCondition("far_field", fs)}
    else:
        bc = {"left": BoundaryCondition("far_field", fs), "right": BoundaryCondition("pressure_outlet", {"p": p}),
              "top": BoundaryCondition("far_field", fs)}
    bc["front"] = BoundaryCondition("symmetry")
    bc["plate"] = BoundaryCondition("no_slip_wall", wall or {})
    vel = (U, 0.0)
    if dim == 3:
        mesh = extrude_2d(mesh, depth=1e-3)
        for name in [q.name for q in mesh.patches if q.name not in bc]:
            bc[name] = BoundaryCondition("symmetry")
        vel = (U, 0.0, 0.0)
    num = Numerics(time_scheme=LUSGS, cfl=5, cfl_max=1e3, max_iterations=60000, residual_drop=8, limiter="None")
    s = EulerSolver(mesh, g, bc, num, viscous=ViscousSettings(LAMINAR))
    t = time.perf_counter()
    r = s.solve(uniform_state(mesh.n_cells, rho, vel, p))
    TIMING[key or f"M{mach:g} {dim}D"] = (r.iterations, time.perf_counter() - t, r.status, mesh.n_cells,
                                          float(r.residuals[-1].max()) if len(r.residuals) else 0.0)
    s.residual(primitive_to_conserved(r.W, g), True, r.W)
    return s, r.W, g, U, rho, mesh, r.status


def at_x(data, x, values):
    xw = data["x"][:, 0]
    order = np.argsort(xw)
    return float(np.interp(x, xw[order], values[order]))


def measure():
    fpp, eta99 = blasius()
    s, W, g, U, rho, mesh, status = plate(0.2, 300.0)
    if status == "diverged":
        return {"cf_worst": float("nan"), "delta99": float("nan"), "extrusion_3d": float("nan")}
    data = wall_data(s, W)
    q = 0.5 * rho * U**2
    cf = np.linalg.norm(data["tau_w"], axis=1) / q
    worst = 1.0
    for rex in (1e4, 3e4, 1e5):
        x = rex / RE_PER_M
        ratio = at_x(data, x, cf) / (2.0 * fpp / math.sqrt(rex))
        if abs(ratio - 1.0) > abs(worst - 1.0):
            worst = ratio
    # delta_99 at Re_x = 1e5: the cell column nearest to x
    x = 1e5 / RE_PER_M
    cc = mesh.cell_centres
    xs = np.unique(np.round(cc[:, 0], 12))
    xc = xs[np.argmin(np.abs(xs - x))]
    col = np.flatnonzero(np.abs(cc[:, 0] - xc) < 1e-12)
    col = col[np.argsort(cc[col, 1])]
    d99 = float(np.interp(0.99 * U, W[1, col], cc[col, 1]))
    # eta = y sqrt(U / (nu x)) in f''' + f f''/2 = 0  ->  y_99 = eta_99 x / sqrt(Re_x)
    d99_ref = eta99 * xc / math.sqrt(RE_PER_M * xc)
    cf2 = at_x(data, x, cf)
    s3, W3, *_rest = plate(0.2, 300.0, dim=3)
    d3 = wall_data(s3, W3)
    cf3 = at_x(d3, x, np.linalg.norm(d3["tau_w"], axis=1) / q)
    TIMING["fpp"] = fpp
    return {"cf_worst": worst, "delta99": d99 / d99_ref, "extrusion_3d": cf3 / cf2}


def study():
    rows = [[k, f"{n:,}", f"{it:,}", f"{w:.0f}", st, f"{res:.1e}"] for k, v in TIMING.items()
            if isinstance(v, tuple) for (it, w, st, n, res) in [v]]
    return {"title": "Runs", "columns": ["Run", "Cells", "Iterations", "Time [s]", "Status", "Residual"], "rows": rows,
            "notes": [f"Blasius f''(0) from the solved ODE: {TIMING.get('fpp', float('nan')):.5f}"]}

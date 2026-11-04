# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Method of Manufactured Solutions (MMS): measures the order of accuracy of the 2D / axisymmetric Euler solver.

The idea (Roache 2002; Roy 2005): choose a smooth "manufactured" flow W_m(x, y) that is NOT a solution of the
Euler equations, put it into the equations and compute what is left over, the source term

    S_m = div F(W_m)                                     (planar)
    S_m = r div F(W_m) + G(W_m) - p e_r                  (axisymmetric, per radian; G = radial flux vector)

Solving  div F(W) = S_m  numerically must then give W -> W_m as the mesh is refined, and the error
|W_h - W_m| must fall like h^p with p the order of the scheme (2 for MUSCL with least-squares gradients).
Because W_m is known everywhere, this checks every term of the discretisation: fluxes, gradients,
reconstruction, limiter, axisymmetric source and the time-step-independent steady state.

The manufactured solution follows Roy, Nelson, Smith & Ober (2004), "Verification of Euler/Navier-Stokes
codes using the method of manufactured solutions", Int. J. Numer. Meth. Fluids 44, 599-620:

    phi(x, y) = phi_0 + phi_x f_x(a_x pi x / L) + phi_y f_y(a_y pi y / L)    (f = sin or cos)

with constants chosen here so the flow is subsonic in some regions and supersonic in others
(Mach 0.5 to 1.6). The derivatives are written out by hand (no symbolic algebra); the source term is
evaluated at each cell centroid and multiplied by the cell area (midpoint rule: second-order accurate).

Boundary condition for verification only: the ghost state is the exact solution at the face centre, and the
boundary value used by the gradients is the exact face value too (MMSSolver below), so the boundaries add
no error of their own.
"""

import math
from dataclasses import dataclass

import numpy as np

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import EulerSolver, Numerics
from aeroflowsim.euler.limiters import NO_LIMITER
from aeroflowsim.gases.library import gas_model
from aeroflowsim.simple_meshes import rectangle_mesh

# (constant, x amplitude, y amplitude, x wave number, y wave number, x function, y function)
# rho [kg/m³], u, v [m/s], p [Pa]; L = 1 m.
TERMS = {
    "rho": (1.0, 0.15, -0.1, 1.0, 0.5, "sin", "cos"),
    "u": (320.0, 50.0, -30.0, 2.0 / 3.0, 1.5, "sin", "cos"),
    "v": (150.0, -60.0, 40.0, 1.5, 1.0, "cos", "sin"),
    "p": (1.0e5, 0.2e5, 0.5e5, 2.0, 1.0, "cos", "sin"),
}
VARIABLES = ("rho", "u", "v", "p")
L = 1.0   # [m]


def _wave(kind, a, s):
    """f(a pi s / L) and its derivative d/ds."""
    k = a * math.pi / L
    if kind == "sin":
        return np.sin(k * s), k * np.cos(k * s)
    return np.cos(k * s), -k * np.sin(k * s)


def manufactured(x, y):
    """Value, d/dx and d/dy of rho, u, v, p at the points (x, y): {name: (value, d_dx, d_dy)}."""
    out = {}
    for name, (c0, cx, cy, ax, ay, fx, fy) in TERMS.items():
        gx, dgx = _wave(fx, ax, x)
        gy, dgy = _wave(fy, ay, y)
        out[name] = (c0 + cx * gx + cy * gy, cx * dgx, cy * dgy)
    return out


def exact_state(x, y):
    """Primitive state W = [rho, u, v, p] (4, n) of the manufactured solution."""
    m = manufactured(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    return np.array([m[k][0] for k in VARIABLES])


def source(x, y, gas, axisymmetric=False):
    """Source term (4, n) per unit planar area, at the points (x, y).

    Planar:        S = dF/dx + dG/dy
    Axisymmetric:  S = r (dF/dx + dG/dr) + G - (0, 0, p, 0)   (r = y; per radian)
    with F = (rho u, rho u² + p, rho u v, u (E + p)), G = (rho v, rho u v, rho v² + p, v (E + p)),
    E = rho e(T) + rho (u² + v²) / 2, T = p / (rho R), and dE = e drho + rho cv dT + rho (u du + v dv).
    Every derivative by the product and chain rules from the derivatives of rho, u, v, p.
    """
    m = manufactured(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    rho, rx, ry = m["rho"]
    u, ux, uy = m["u"]
    v, vx, vy = m["v"]
    p, px, py = m["p"]
    R = gas.R
    T = p / (rho * R)                                                  # [K]
    e, cv = gas.internal_energy(T), gas.cv(T)                         # [J/kg], [J/(kg K)]
    k2 = u * u + v * v
    E = rho * e + 0.5 * rho * k2                                       # [J/m³]

    def dE(dr, du, dv, dp):
        dT = (dp * rho - p * dr) / (rho * rho * R)
        return dr * e + rho * cv * dT + 0.5 * dr * k2 + rho * (u * du + v * dv)

    Ex, Ey = dE(rx, ux, vx, px), dE(ry, uy, vy, py)
    Fx = np.array([rx * u + rho * ux,
                   rx * u * u + 2.0 * rho * u * ux + px,
                   rx * u * v + rho * ux * v + rho * u * vx,
                   ux * (E + p) + u * (Ex + px)])
    Gy = np.array([ry * v + rho * vy,
                   ry * u * v + rho * uy * v + rho * u * vy,
                   ry * v * v + 2.0 * rho * v * vy + py,
                   vy * (E + p) + v * (Ey + py)])
    if not axisymmetric:
        return Fx + Gy
    G = np.array([rho * v, rho * u * v, rho * v * v + p, v * (E + p)])
    S = y * (Fx + Gy) + G
    S[2] -= p
    return S


class MMSSolver(EulerSolver):
    """EulerSolver with the exact solution as boundary condition and the manufactured source (verification only)."""

    def __init__(self, mesh, gas, numerics):
        conditions = {p.name: BoundaryCondition("slip_wall") for p in mesh.patches}   # replaced by ghosts() below
        W_ref = exact_state(0.5, 0.5)
        super().__init__(mesh, gas, conditions, numerics, L_ref=1.0,
                         scales=(W_ref[0], 400.0, 400.0, W_ref[3]))
        g = self.geom
        fc = g.face_centres[g.boundary_faces]
        self.W_boundary = exact_state(fc[:, 0], fc[:, 1])               # exact state at the boundary faces
        cc = g.cell_centres
        # Source integrated over each cell: S(centroid) x planar area (axisymmetric: per radian as the fluxes)
        self.source = source(cc[:, 0], cc[:, 1], gas, mesh.axisymmetric) * g.planar_volumes

    def ghosts(self, Wb):
        return self.W_boundary

    def boundary_face_values(self, Wb_in, ghost_c):
        return self.W_boundary


# ---- the order-of-accuracy study --------------------------------------------------------------------

MESH_KINDS = ("quads", "distorted quads", "triangles", "mixed")


def mms_mesh(kind, n, axisymmetric=False):
    """Mesh of the unit square (planar) or of [0, 1] x [0.5, 1.5] (axisymmetric, off the axis) with n x n cells."""
    y0 = 0.5 if axisymmetric else 0.0
    opts = {"quads": {}, "distorted quads": {"warp": 0.04}, "triangles": {"triangles": True},
            "mixed": {"mixed": True}}[kind]
    return rectangle_mesh(n, n, 0.0, 1.0, y0, y0 + 1.0, axisymmetric=axisymmetric, **opts)


@dataclass
class MMSRun:
    kind: str
    n: int
    cells: int
    h: float                    # sqrt(mean cell area) [m]
    errors: dict                # norm -> (4,) error per variable (L1, L2, Linf)
    iterations: int
    residual: float             # final normalised residual (max over the equations)
    wall_time_s: float


def run_level(kind, n, order=2, limiter=NO_LIMITER, axisymmetric=False, gas="air", residual_drop=9.0,
              max_iterations=60000, cfl=0.8):
    """Solve the MMS problem on one mesh (started from the exact solution) and measure the discretisation error."""
    mesh = mms_mesh(kind, n, axisymmetric)
    model = gas_model(gas)
    num = Numerics(cfl=cfl, order=order, limiter=limiter, max_iterations=max_iterations,
                   residual_drop=residual_drop, carbuncle_fix=False)
    solver = MMSSolver(mesh, model, num)
    cc = solver.geom.cell_centres
    W_exact = exact_state(cc[:, 0], cc[:, 1])
    res = solver.solve(W_exact.copy())
    err = res.W - W_exact
    area = solver.geom.planar_volumes
    w = area / area.sum()
    errors = {"L1": np.sum(np.abs(err) * w, axis=1),
              "L2": np.sqrt(np.sum(err**2 * w, axis=1)),
              "Linf": np.abs(err).max(axis=1)}
    return MMSRun(kind, n, mesh.n_cells, float(math.sqrt(area.mean())), errors, res.iterations,
                  float(res.residuals[-1].max()) if len(res.residuals) else 0.0, res.wall_time_s)


def observed_orders(runs, norm="L2"):
    """Observed order between consecutive levels, per variable: p = ln(e_c / e_f) / ln(h_c / h_f)."""
    out = []
    for coarse, fine in zip(runs[:-1], runs[1:]):
        out.append(np.log(coarse.errors[norm] / fine.errors[norm]) / math.log(coarse.h / fine.h))
    return out


def study(kind, levels=(16, 32, 64, 128), **kwargs):
    """Runs on every level (refinement ratio 2) for one mesh kind; returns the list of MMSRun."""
    return [run_level(kind, n, **kwargs) for n in levels]


def run_job(args):
    """One level as a picklable job for a process pool: args = (kind, n, axisymmetric, order, limiter);
    returns (args, plain-number summary)."""
    kind, n, axi, order, limiter = args
    r = run_level(kind, n, order=order, limiter=limiter, axisymmetric=axi, residual_drop=8.0, max_iterations=200000)
    return args, {"h": r.h, "cells": r.cells, "L1": r.errors["L1"].tolist(), "L2": r.errors["L2"].tolist(),
                  "Linf": r.errors["Linf"].tolist(), "iterations": r.iterations, "residual": r.residual,
                  "time": r.wall_time_s}


# ---- 3D (5 equations): the same idea with a z dependence and a third velocity component ------------------

# (constant, x, y, z amplitudes, x, y, z wave numbers, x, y, z functions): Roy et al. (2004) style, extended to z
# with the third terms chosen so the flow is again subsonic in places and supersonic in others (Mach about 0.6-1.5).
TERMS_3D = {
    "rho": (1.0, 0.15, -0.1, 0.08, 1.0, 0.5, 0.75, "sin", "cos", "sin"),
    "u": (320.0, 50.0, -30.0, 20.0, 2.0 / 3.0, 1.5, 1.0, "sin", "cos", "cos"),
    "v": (150.0, -60.0, 40.0, -25.0, 1.5, 1.0, 0.5, "cos", "sin", "sin"),
    "w": (100.0, 30.0, -20.0, 35.0, 0.5, 1.0, 1.25, "sin", "sin", "cos"),
    "p": (1.0e5, 0.2e5, 0.5e5, 0.15e5, 2.0, 1.0, 1.5, "cos", "sin", "cos"),
}
VARIABLES_3D = ("rho", "u", "v", "w", "p")


def manufactured_3d(x, y, z):
    """{name: (value, (d/dx, d/dy, d/dz))} of rho, u, v, w, p at the points (x, y, z)."""
    out = {}
    for name, (c0, cx, cy, cz, ax, ay, az, fx, fy, fz) in TERMS_3D.items():
        gx, dgx = _wave(fx, ax, x)
        gy, dgy = _wave(fy, ay, y)
        gz, dgz = _wave(fz, az, z)
        out[name] = (c0 + cx * gx + cy * gy + cz * gz, (cx * dgx, cy * dgy, cz * dgz))
    return out


def exact_state_3d(x, y, z):
    """Primitive state W = [rho, u, v, w, p] (5, n) of the 3D manufactured solution."""
    m = manufactured_3d(*(np.asarray(a, dtype=float) for a in (x, y, z)))
    return np.array([m[k][0] for k in VARIABLES_3D])


def source_3d(x, y, z, gas):
    """Source term (5, n) per unit volume: S = sum_k d F_k / d x_k with the Euler flux in direction k
        F_k = (rho u_k, rho u_k u_j + p delta_kj, u_k (E + p)),  E = rho e(T) + rho |u|²/2,  T = p / (rho R).
    Every derivative by the product and chain rules from the derivatives of rho, u, v, w, p (as source())."""
    m = manufactured_3d(*(np.asarray(a, dtype=float) for a in (x, y, z)))
    rho, drho = m["rho"]
    p, dp = m["p"]
    vel = [m[k][0] for k in ("u", "v", "w")]
    dvel = [m[k][1] for k in ("u", "v", "w")]           # dvel[j][k] = d u_j / d x_k
    R = gas.R
    T = p / (rho * R)
    e, cv = gas.internal_energy(T), gas.cv(T)
    k2 = sum(u * u for u in vel)
    E = rho * e + 0.5 * rho * k2
    S = np.zeros((5,) + np.shape(rho))
    for k in range(3):
        uk, duk = vel[k], dvel[k][k]
        dT = (dp[k] * rho - p * drho[k]) / (rho * rho * R)
        dE = drho[k] * e + rho * cv * dT + 0.5 * drho[k] * k2 + rho * sum(vel[j] * dvel[j][k] for j in range(3))
        S[0] += drho[k] * uk + rho * duk
        for j in range(3):
            # d/dx_k (rho u_k u_j) = drho u_k u_j + rho du_k u_j + rho u_k du_j
            S[1 + j] += drho[k] * uk * vel[j] + rho * duk * vel[j] + rho * uk * dvel[j][k]
        S[1 + k] += dp[k]
        S[4] += duk * (E + p) + uk * (dE + dp[k])
    return S


class MMSSolver3D(EulerSolver):
    """3D EulerSolver with the exact solution on the boundary and the manufactured source (verification only)."""

    def __init__(self, mesh, gas, numerics):
        conditions = {p.name: BoundaryCondition("slip_wall") for p in mesh.patches}
        W_ref = exact_state_3d(0.5, 0.5, 0.5)
        super().__init__(mesh, gas, conditions, numerics, L_ref=1.0,
                         scales=(W_ref[0], 400.0, 400.0, 400.0, W_ref[4]))
        g = self.geom
        fc = g.face_centres[g.boundary_faces]
        self.W_boundary = exact_state_3d(fc[:, 0], fc[:, 1], fc[:, 2])
        cc = g.cell_centres
        self.source = source_3d(cc[:, 0], cc[:, 1], cc[:, 2], gas) * g.planar_volumes

    def ghosts(self, Wb):
        return self.W_boundary

    def boundary_face_values(self, Wb_in, ghost_c):
        return self.W_boundary


MESH_KINDS_3D = ("hexahedra", "prisms", "tetrahedra")
WARP_3D = 0.03          # smooth distortion of the 3D MMS boxes (curved grid lines, non-planar quad faces)


def run_level_3d(kind, n, order=2, limiter=NO_LIMITER, gas="air", residual_drop=9.0, max_iterations=20000,
                 cfl=0.8, time_scheme=None, gradient=None):
    """Solve the 3D MMS problem on an n x n x n box of `kind` cells and measure the discretisation error."""
    from aeroflowsim.euler.solver import LUSGS
    from aeroflowsim.simple_meshes import box_mesh_3d
    mesh = box_mesh_3d(n, kind, warp=WARP_3D)
    model = gas_model(gas)
    num = Numerics(cfl=cfl, order=order, limiter=limiter, max_iterations=max_iterations, residual_drop=residual_drop,
                   carbuncle_fix=False, time_scheme=time_scheme or LUSGS, cfl_max=50.0,
                   **({"gradient": gradient} if gradient else {}))
    solver = MMSSolver3D(mesh, model, num)
    cc = solver.geom.cell_centres
    W_exact = exact_state_3d(cc[:, 0], cc[:, 1], cc[:, 2])
    res = solver.solve(W_exact.copy())
    err = res.W - W_exact
    vol = solver.geom.planar_volumes
    w = vol / vol.sum()
    errors = {"L1": np.sum(np.abs(err) * w, axis=1), "L2": np.sqrt(np.sum(err**2 * w, axis=1)),
              "Linf": np.abs(err).max(axis=1)}
    return MMSRun(kind, n, mesh.n_cells, float(vol.mean() ** (1.0 / 3.0)), errors, res.iterations,
                  float(res.residuals[-1].max()) if len(res.residuals) else 0.0, res.wall_time_s)

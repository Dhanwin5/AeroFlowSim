# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Method of Manufactured Solutions for the Navier-Stokes equations (laminar): order of accuracy of the viscous terms.

The same manufactured flows as the Euler study (aeroflowsim/mms.py: Roy, Nelson, Smith & Ober 2004, extended to 3D),
now with the viscous flux. The source term is

    planar / 3D:   S = div F(W_m) - div F_v(W_m)
    axisymmetric:  S = [d(r F)/dx + d(r G)/dr - p e_r] - [d(r F_v)/dx + d(r G_v)/dr] + tau_thth e_r     (per radian)

The inviscid part is the analytic source of mms.py. The viscous flux F_v needs only FIRST derivatives of the
manufactured fields (written out by hand from mms.manufactured); its divergence is taken by a fourth-order central
difference with step h = 1e-3 m (error ~ (k h)^4 / 30 ~ 1e-9 relative for wave numbers k ~ 2 pi / m: far below the
discretisation errors being measured, ~1e-4 on the finest mesh).

The gas is air with an artificially large viscosity (power law mu = 2 Pa s (T / 300 K)^0.7, Pr = 0.72, as Roy et al.
used mu = 10 Pa s) so the viscous terms are as large as the convective ones (Reynolds number ~150 on the unit box):
otherwise they would be invisible in the error. mu depends on T, so the temperature dependence is verified too.
"""

import dataclasses
import math

import numpy as np

from aeroflowsim import mms
from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.limiters import NO_LIMITER
from aeroflowsim.euler.solver import LUSGS, EulerSolver, Numerics
from aeroflowsim.euler.viscous import LAMINAR, ViscousSettings
from aeroflowsim.gases.data import TransportLaw
from aeroflowsim.gases.library import gas_model
from aeroflowsim.gases.model import CaloricallyPerfectGas

H_FD = 1e-3          # step of the fourth-order central differences [m]


def ns_gas(mu_ref=2.0):
    """Air with an artificially large viscosity (module docstring)."""
    data = gas_model("air").data
    data = dataclasses.replace(data, viscosity=TransportLaw("power", mu_ref, 300.0, n=0.7), conductivity=None,
                               prandtl=0.72, id="air-mms", name="Air (MMS, large viscosity)")
    return CaloricallyPerfectGas(data)


def _fields(points, dim):
    """Velocity, its derivatives, T and its derivatives of the manufactured flow at the points (tuple of coords).
    Returns (vel[dim], dvel[i][j] = du_i/dx_j, T, dT[j], rho, p)."""
    if dim == 2:
        m = mms.manufactured(*points)
        rho, rx, ry = m["rho"]
        p, px, py = m["p"]
        drho, dp = (rx, ry), (px, py)
        vel = [m["u"][0], m["v"][0]]
        dvel = [[m["u"][1], m["u"][2]], [m["v"][1], m["v"][2]]]
    else:
        m = mms.manufactured_3d(*points)
        rho, drho = m["rho"]
        p, dp = m["p"]
        vel = [m[k][0] for k in ("u", "v", "w")]
        dvel = [list(m[k][1]) for k in ("u", "v", "w")]
    return vel, dvel, rho, drho, p, dp


def viscous_flux(points, gas, dim, axisymmetric=False):
    """Physical viscous flux in each direction j: list of (dim + 2, n) arrays, and tau_thth (axisymmetric) or None."""
    vel, dvel, rho, drho, p, dp = _fields(points, dim)
    R = gas.R
    T = p / (rho * R)
    dT = [(dp[j] * rho - p * drho[j]) / (rho * rho * R) for j in range(dim)]
    mu, k = gas.mu(T), gas.k(T)
    div = sum(dvel[i][i] for i in range(dim))
    if axisymmetric:
        div = div + vel[1] / points[1]
    out = []
    for j in range(dim):
        F = np.zeros((dim + 2,) + np.shape(rho))
        for i in range(dim):
            tij = mu * (dvel[i][j] + dvel[j][i])
            if i == j:
                tij = tij - 2.0 / 3.0 * mu * div
            F[1 + i] = tij
            F[-1] += tij * vel[i]
        F[-1] += k * dT[j]
        out.append(F)
    tau_tt = None
    if axisymmetric:
        tau_tt = mu * (2.0 * vel[1] / points[1] - 2.0 / 3.0 * div)
    return out, tau_tt


def _divergence(points, gas, dim, axisymmetric):
    """sum_j d/dx_j (r^a F_v,j) by fourth-order central differences (a = 1 axisymmetric, else 0)."""
    h = H_FD
    total = 0.0
    for j in range(dim):
        acc = 0.0
        for shift, w in ((2.0, -1.0), (1.0, 8.0), (-1.0, -8.0), (-2.0, 1.0)):
            pts = [np.asarray(c, dtype=float) + (shift * h if k == j else 0.0) for k, c in enumerate(points)]
            F = viscous_flux(pts, gas, dim, axisymmetric)[0][j]
            if axisymmetric:
                F = F * pts[1]
            acc = acc + w * F
        total = total + acc / (12.0 * h)
    return total


def source_ns(points, gas, dim, axisymmetric=False):
    """Navier-Stokes MMS source (dim + 2, n) per unit planar area / volume (module docstring)."""
    if dim == 2:
        S = mms.source(points[0], points[1], gas, axisymmetric)
    else:
        S = mms.source_3d(*points, gas)
    S = S - _divergence(points, gas, dim, axisymmetric)
    if axisymmetric:
        S[2] += viscous_flux(points, gas, dim, True)[1]
    return S


class MMSSolverNS(EulerSolver):
    """Navier-Stokes solver with the exact solution on the boundary and the manufactured source (verification only)."""

    def __init__(self, mesh, gas, numerics):
        conditions = {p.name: BoundaryCondition("slip_wall") for p in mesh.patches}
        dim = mesh.dim
        exact = mms.exact_state if dim == 2 else mms.exact_state_3d
        W_ref = exact(*([0.5] * dim))
        scales = (W_ref[0],) + (400.0,) * dim + (W_ref[-1],)
        super().__init__(mesh, gas, conditions, numerics, L_ref=1.0, scales=scales,
                         viscous=ViscousSettings(LAMINAR))
        g = self.geom
        fc = g.face_centres[g.boundary_faces]
        self.W_boundary = exact(*(fc[:, k] for k in range(dim)))
        cc = g.cell_centres
        self.source = source_ns(tuple(cc[:, k] for k in range(dim)), gas, dim, mesh.axisymmetric) * g.planar_volumes
        self.exact = exact(*(cc[:, k] for k in range(dim)))

    def ghosts(self, Wb):
        return self.W_boundary

    def boundary_face_values(self, Wb_in, ghost_c):
        return self.W_boundary


MESH_KINDS = mms.MESH_KINDS + mms.MESH_KINDS_3D


def ns_mesh(kind, n, axisymmetric=False):
    if kind in mms.MESH_KINDS_3D:
        from aeroflowsim.simple_meshes import box_mesh_3d
        return box_mesh_3d(n, kind, warp=mms.WARP_3D)
    return mms.mms_mesh(kind, n, axisymmetric)


def run_level(kind, n, axisymmetric=False, order=2, residual_drop=9.0, max_iterations=20000, cfl=0.8, cfl_max=50.0,
              time_scheme=LUSGS, mu_ref=2.0):
    """Solve the Navier-Stokes MMS problem on one mesh (started from the exact solution); errors as mms.run_level."""
    mesh = ns_mesh(kind, n, axisymmetric)
    num = Numerics(cfl=cfl, order=order, limiter=NO_LIMITER, max_iterations=max_iterations,
                   residual_drop=residual_drop, carbuncle_fix=False, time_scheme=time_scheme, cfl_max=cfl_max)
    solver = MMSSolverNS(mesh, ns_gas(mu_ref), num)
    res = solver.solve(solver.exact.copy())
    err = res.W - solver.exact
    vol = solver.geom.planar_volumes
    w = vol / vol.sum()
    errors = {"L1": np.sum(np.abs(err) * w, axis=1), "L2": np.sqrt(np.sum(err**2 * w, axis=1)),
              "Linf": np.abs(err).max(axis=1)}
    h = float(vol.mean() ** (1.0 / mesh.dim))
    return mms.MMSRun(kind, n, mesh.n_cells, h, errors, res.iterations,
                      float(res.residuals[-1].max()) if len(res.residuals) else 0.0, res.wall_time_s)


def run_job(args):
    """One level as a picklable job: args = (kind, n, axisymmetric); returns (args, plain-number summary)."""
    kind, n, axi = args
    r = run_level(kind, n, axi, residual_drop=8.0, max_iterations=100000)
    return args, {"h": r.h, "cells": r.cells, "L1": r.errors["L1"].tolist(), "L2": r.errors["L2"].tolist(),
                  "Linf": r.errors["Linf"].tolist(), "iterations": r.iterations, "residual": r.residual,
                  "time": r.wall_time_s}


observed_orders = mms.observed_orders
del math


# ---- turbulence transport: order of accuracy of the scalar operator (euler/turbulence.py) ------------------------
# A manufactured scalar q_m transported by the (fixed) manufactured mean flow with constant diffusion Gamma:
#     rho u . grad q - (1/r^a) div(r^a Gamma grad q) = S_m          (a = 1 axisymmetric, else 0)
# solved with the turbulence models' discretisation (upwind convection with the mean flow's face mass fluxes,
# corrected-gradient diffusion, implicit SGS). EXPECTED ORDER (stated before measuring): 1, because the convection of
# the turbulence equations is first-order upwind (as in CFL3D / FUN3D runs of the TMR) and the cell Peclet numbers are
# large; diffusion and sources alone are second order.

GAMMA_MMS = 0.5          # [Pa s]


def scalar_exact(points):
    x, y = points[0], points[1]
    q = 1.0 + 0.5 * np.sin(np.pi * x) * np.cos(0.5 * np.pi * y)
    if len(points) == 3:
        q = q + 0.3 * np.sin(0.75 * np.pi * points[2])
    return q


def _scalar_source(points, dim, axisymmetric):
    h = H_FD
    pts = [np.asarray(c, dtype=float) for c in points]
    exact = mms.exact_state if dim == 2 else mms.exact_state_3d
    W = exact(*pts)
    grad = []
    for j in range(dim):
        a = [c + (h if k == j else 0.0) for k, c in enumerate(pts)]
        b = [c - (h if k == j else 0.0) for k, c in enumerate(pts)]
        grad.append((scalar_exact(a) - scalar_exact(b)) / (2 * h))
    conv = W[0] * sum(W[1 + j] * grad[j] for j in range(dim))
    diff = 0.0
    for j in range(dim):
        acc = 0.0
        for shift, w in ((2.0, -1.0), (1.0, 8.0), (-1.0, -8.0), (-2.0, 1.0)):
            p2 = [c + (shift * h if k == j else 0.0) for k, c in enumerate(pts)]
            gp = (scalar_exact([c + (h if k == j else 0.0) for k, c in enumerate(p2)])
                  - scalar_exact([c - (h if k == j else 0.0) for k, c in enumerate(p2)])) / (2 * h)
            flux = GAMMA_MMS * gp * (p2[1] if axisymmetric else 1.0)
            acc = acc + w * flux
        diff = diff + acc / (12.0 * h)
    if axisymmetric:
        diff = diff / pts[1]
    return conv - diff


def run_turbulence_level(kind, n, axisymmetric=False, sweeps=4000, tol=1e-11):
    """Error (L2, Linf) of the turbulence transport operator on one mesh (module comment above)."""
    from aeroflowsim.euler.state import primitive_to_conserved
    from aeroflowsim.euler.turbulence import TurbulenceModel
    mesh = ns_mesh(kind, n, axisymmetric)
    num = Numerics(order=2, limiter=NO_LIMITER, carbuncle_fix=False)
    solver = MMSSolverNS(mesh, ns_gas(1e-6), num)
    W = solver.exact
    solver.residual(primitive_to_conserved(W, solver.gas), True, W)
    solver.stage0_viscous = solver.last_viscous
    cc = solver.geom.cell_centres
    pts = tuple(cc[:, k] for k in range(mesh.dim))
    fc = solver.geom.face_centres[solver.geom.boundary_faces]
    qb = scalar_exact(tuple(fc[:, k] for k in range(mesh.dim)))
    S = _scalar_source(pts, mesh.dim, mesh.axisymmetric)

    class Scalar(TurbulenceModel):
        names = ("q",)

        def freestream_values(self, fs, settings):
            return np.array([1.0])

        def boundary_values(self, Q, W_, mass_b):
            return qb[None, :]

        def eddy_viscosity(self, W_, Q, grads):
            return None

        def sources(self, W_, Q, grads, gradQ):
            return S[None], np.zeros((1, len(S))), np.full((1, len(S)), GAMMA_MMS)

    model = Scalar(solver, {"rho": 1.0, "mu": 1.0, "a": 1.0, "U": 1.0})
    model.Q = scalar_exact(pts)[None, :].copy()
    dt = solver.time_steps(W, 1e6)
    for it in range(sweeps):
        res = model.step(W, dt, solver.face_mass_flux)
        if it > 5 and res < tol:
            break
    err = model.Q[0] - scalar_exact(pts)
    vol = solver.geom.planar_volumes
    w = vol / vol.sum()
    return float(vol.mean() ** (1.0 / mesh.dim)), float(np.sqrt(np.sum(err**2 * w))), float(np.abs(err).max())

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Demo case: steady 1D heat conduction in a rod with uniform heat generation.

Equation:   k d2T/dx2 + q_gen = 0      on 0 <= x <= L
Boundaries: T(0) = T_left,  T(L) = T_right
Solved by pseudo-time marching to steady state (see README.md).
"""

import numpy as np

from aeroflowsim.geometry import WallProfile
from aeroflowsim.mesh import Mesh1D
from aeroflowsim.results import Field, Result


def build_mesh(params):
    """Uniform mesh from x = 0 to x = L."""
    x = np.linspace(0.0, params["L"], params["n_nodes"])  # node positions [m]
    return Mesh1D(x=x)


def _residual(T, dx, k, q_gen):
    """Discrete equation residual at interior nodes: d2T/dx2 + q_gen/k  [K/m²]."""
    return (T[2:] - 2.0 * T[1:-1] + T[:-2]) / dx**2 + q_gen / k


def run(params, mesh, progress):
    """March dT/dtau = d2T/dx2 + q_gen/k in pseudo-time until it stops changing."""
    k = params["k"]            # thermal conductivity [W/(m·K)]
    q_gen = params["q_gen"]    # volumetric heat generation [W/m³]
    x = mesh.x                 # node positions [m]
    dx = mesh.dx[0]            # node spacing [m] (uniform mesh)

    # Initial guess: straight line between the two wall temperatures [K]
    T = np.linspace(params["T_left"], params["T_right"], mesh.n_nodes)

    # Pseudo-time step: beta = dtau/dx² = 0.5 is the explicit stability limit.
    # With beta = 0.5 each update is exactly one Jacobi iteration.
    beta = 0.5  # [-]

    residuals = []        # normalised residual history [-]
    r0 = None             # first residual, used for normalisation [K/m²]
    converged = False
    iteration = 0
    for iteration in range(1, params["max_iter"] + 1):
        R = _residual(T, dx, k, q_gen)               # [K/m²]
        T[1:-1] = T[1:-1] + beta * dx**2 * R          # update interior nodes; ends stay fixed
        r = float(np.sqrt(np.mean(R**2)))             # RMS residual [K/m²]
        if r0 is None:
            r0 = r if r > 0.0 else 1.0                # avoid dividing by zero
        residuals.append(r / r0)
        progress(iteration, residuals[-1])
        if residuals[-1] < params["tol"]:
            converged = True
            break

    # Heat flux leaving the rod at each end [W/m²], from 2nd-order one-sided derivatives
    dTdx_left = (-3.0 * T[0] + 4.0 * T[1] - T[2]) / (2.0 * dx)      # [K/m]
    dTdx_right = (3.0 * T[-1] - 4.0 * T[-2] + T[-3]) / (2.0 * dx)   # [K/m]
    q_left = k * dTdx_left       # leaving through x = 0 (flowing in -x direction) [W/m²]
    q_right = -k * dTdx_right    # leaving through x = L (flowing in +x direction) [W/m²]

    i_max = int(np.argmax(T))
    return Result(
        fields={"T": Field(values=T, unit="K", label="Temperature")},
        residuals=residuals,
        key_numbers={
            "T_max": (float(T[i_max]), "K"),
            "x_Tmax": (float(x[i_max]), "m"),
            "q_left": (float(q_left), "W/m²"),
            "q_right": (float(q_right), "W/m²"),
        },
        iterations=iteration,
        converged=converged,
        # Outline for the shape view. The rod has no diameter input, so this constant
        # radius (5 % of the length) is for display only and does not enter the physics.
        shape=WallProfile(x=[0.0, params["L"]], r=[0.05 * params["L"]] * 2),  # [m]
    )


def reference(params, mesh):
    """Exact solution: T(x) = T_left + (T_right - T_left) x/L + q_gen/(2k) x (L - x)."""
    L, k, q_gen = params["L"], params["k"], params["q_gen"]   # [m], [W/(m·K)], [W/m³]
    x = mesh.x                                                # [m]
    T = params["T_left"] + (params["T_right"] - params["T_left"]) * x / L \
        + q_gen / (2.0 * k) * x * (L - x)                     # [K]
    return {"T": Field(values=T, unit="K", label="Temperature")}

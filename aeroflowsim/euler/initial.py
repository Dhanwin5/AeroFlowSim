# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Initial solutions: where the march to a steady state starts.

    uniform        the free stream (or a state at rest) everywhere: works for every case, but a nozzle
                   then has to "discover" its whole flow, which takes many iterations.
    quasi-1D       nozzles: the isentropic quasi-1D solution of the wall profile, M(x) from the area
                   ratio A(x)/A* (subsonic before the throat, supersonic after it), p and T from p0, T0.
                   The radial velocity follows the wall slope, growing linearly from the axis:
                   v = u (r / r_wall) dr_wall/dx. Close to the final flow, so far fewer iterations.
    restart        the primitive fields of a previous run on the same mesh (continue a run).
"""

import numpy as np

from aeroflowsim import gasdynamics as gd

UNIFORM, QUASI_1D, RESTART = "Uniform (free stream)", "Quasi-1D solution", "Previous result (restart)"


def quasi1d_state(mesh, profile, gas, p0, T0):
    """Primitive state (4, C) of the isentropic quasi-1D nozzle flow on an axisymmetric (or planar) mesh."""
    x = mesh.cell_centres[:, 0]
    r = mesh.cell_centres[:, 1]
    xc = np.clip(x, profile.x[0], profile.x[-1])
    g = float(gas.gamma(T0))
    r_wall = profile.radius_at(xc)                                          # [m]
    A_ratio = (r_wall / profile.r_throat) ** 2 if mesh.axisymmetric else r_wall / profile.r_throat
    A_ratio = np.maximum(A_ratio, 1.0 + 1e-9)
    supersonic = xc > profile.x_throat
    M = np.empty_like(x)
    for flag in (False, True):
        sel = supersonic == flag
        unique, inverse = np.unique(np.round(A_ratio[sel], 10), return_inverse=True)
        M[sel] = np.array([gd.mach_from_area_ratio(a, g, flag) for a in unique])[inverse]
    T = T0 / gd.t0_over_t(M, g)                                             # [K]
    p = p0 / gd.p0_over_p(M, g)                                             # [Pa]
    u = M * np.asarray(gas.sound_speed(T))                                  # [m/s]
    h = 1e-6 * (profile.x[-1] - profile.x[0])
    slope = (profile.radius_at(np.clip(xc + h, profile.x[0], profile.x[-1]))
             - profile.radius_at(np.clip(xc - h, profile.x[0], profile.x[-1]))) / (2.0 * h)
    v = u * np.clip(r / r_wall, 0.0, 1.0) * slope
    speed = np.hypot(u, v)
    scale = np.where(speed > 0.0, u / speed, 1.0)        # keep |velocity| = M c
    W = np.empty((4, mesh.n_cells))
    W[0] = p / (gas.R * T)
    W[1], W[2] = u * scale, v * scale
    W[3] = p
    return W


def restart_state(fields, mesh):
    """Primitive state from the fields of a previous result (keys rho, u, v, p), on the same mesh."""
    try:
        W = np.array([fields[k] for k in ("rho", "u", "v", "p")], dtype=float)
    except KeyError as error:
        raise ValueError(f"The previous result has no field {error}; it cannot be used to restart.") from None
    if W.shape[1] != mesh.n_cells:
        raise ValueError(f"The previous result has {W.shape[1]:,} cells but the mesh has {mesh.n_cells:,}: "
                         "restart needs the same mesh. Run from a uniform or quasi-1D start instead.")
    return W

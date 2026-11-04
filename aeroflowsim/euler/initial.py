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
    continue       the flow of the previous result on the same mesh: what Run does by default when the project
                   has one (the run carries on, iteration 159 after 158); the two starts above are used only
                   for a fresh start ("Start from scratch", a new mesh, or no result yet).
"""

import numpy as np

from aeroflowsim import gasdynamics as gd

UNIFORM, QUASI_1D = "Uniform (free stream)", "Quasi-1D solution"
PRIMITIVE_KEYS = {2: ("rho", "u", "v", "p"), 3: ("rho", "u", "v", "w", "p")}   # result fields of W, by mesh dimension
RESTART = "Previous result (restart)"   # an old option of the Initial solution input (projects are converted)


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


def quasi1d_state_3d(mesh, profile, gas, p0, T0):
    """Primitive state (5, C) of the isentropic quasi-1D nozzle flow on a 3D mesh of a nozzle with its axis along x:
    the axisymmetric start above with r = sqrt(y^2 + z^2), the radial velocity split into its y and z parts."""
    from types import SimpleNamespace
    c = mesh.cell_centres
    r = np.hypot(c[:, 1], c[:, 2])
    plane = SimpleNamespace(cell_centres=np.column_stack([c[:, 0], r, np.zeros(len(r))]), axisymmetric=True,
                            n_cells=mesh.n_cells)
    W2 = quasi1d_state(plane, profile, gas, p0, T0)
    W = np.empty((5, mesh.n_cells))
    safe = np.where(r > 0.0, r, 1.0)
    W[0], W[1], W[4] = W2[0], W2[1], W2[3]
    W[2] = np.where(r > 0.0, W2[2] * c[:, 1] / safe, 0.0)
    W[3] = np.where(r > 0.0, W2[2] * c[:, 2] / safe, 0.0)
    return W


def restart_state(fields, mesh):
    """Primitive state from the fields of a previous result (keys rho, u, v, p; 3D also w), on the same mesh.

    fields: {key: array}, or the continuation dict of aeroflowsim.result_io.continuation_data ({"fields": ...}).
    """
    if "fields" in fields:
        fields = fields["fields"]
    try:
        W = np.array([fields[k] for k in PRIMITIVE_KEYS[3 if mesh.dim == 3 else 2]], dtype=float)
    except KeyError as error:
        raise ValueError(f"The previous result has no field {error}; it cannot be used to restart.") from None
    if W.shape[1] != mesh.n_cells:
        raise ValueError(f"The previous result has {W.shape[1]:,} cells but the mesh has {mesh.n_cells:,}: "
                         "restart needs the same mesh. Run from a uniform or quasi-1D start instead.")
    return W

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Wall quantities of a viscous run (2D, axisymmetric, 3D): wall shear stress, skin friction, heat flux, Stanton
number, y+, and the split of the body force into pressure and friction parts.

Everything comes from the solver's own wall fluxes of the last residual evaluation (the same numbers that moved
momentum and energy), so the forces of the friction and of the pressure add up exactly to the body force:

    traction of the gas on the wall   f = p n - (tau . n)          (n out of the gas, into the wall)  [Pa]
    wall shear stress                 tau_w = -(tau . n) minus its normal part (the tangential traction) [Pa]
    skin-friction coefficient         Cf = tau_w . t / q_inf  (t: the free-stream direction projected on the wall,
                                      so Cf < 0 shows reversed flow / separation)
    wall heat flux INTO the wall      q_w = -(k grad T) . n = -(F_v,energy - (tau . n) . u_wall)       [W/m²]
    Stanton number                    St = q_w / (rho_inf |u_inf| cp (T0_inf - T_w))   (T0 = total temperature)
    friction velocity, y+             u_tau = sqrt(|tau_w| / rho_w),  y+ = rho_w u_tau y1 / mu_w
with y1 the distance from the wall face to the centre of its cell (|d . n|), rho_w and mu_w at the wall (T_w and
the inside pressure). Under the Euler flow model there is no viscous flux: friction, q_w and y+ are not defined.
"""

import numpy as np


def _wall_local(solver, names=None):
    """Boundary-local indices of the no-slip wall faces (all, or of the named patches)."""
    out = [local for name, bc, local, _info in solver.patches
           if bc.type == "no_slip_wall" and (names is None or name in names)]
    return np.concatenate(out) if out else np.zeros(0, dtype=np.int64)


def wall_data(solver, W, names=None) -> dict:
    """Per wall face of the no-slip walls (all, or the named patches): x (n, dim) [m], area (n) [m² or m³ per radian],
    normal (n, dim), p [Pa], traction (n, dim) viscous traction -(tau.n) [Pa], tau_w (n, dim) wall shear stress [Pa],
    q_w [W/m²], T_w [K], rho_w, mu_w, y1 [m], u_tau [m/s], y_plus [-]. Needs a residual evaluated with the state W
    (solver.boundary_flux and solver.boundary_viscous_flux)."""
    g = solver.geom
    local = _wall_local(solver, names)
    faces = g.n_interior + local
    A = g.flux_areas[faces]
    ok = A > 0.0                                       # faces on the axis have no area
    local, faces, A = local[ok], faces[ok], A[ok]
    n = solver.boundary_normals[local]
    dim = g.dim
    FV = solver.boundary_viscous_flux[:, local] if solver.boundary_viscous_flux is not None else np.zeros(
        (dim + 2, len(local)))
    FA = solver.boundary_flux[:, local]
    traction = -(FV[1:-1] / A).T                       # -(tau . n) [Pa]
    p = np.einsum("kf,fk->f", FA[1:-1] + FV[1:-1], n) / A   # inviscid momentum flux = p n A
    tn = np.einsum("fk,fk->f", traction, n)
    tau_w = traction - tn[:, None] * n
    cells = g.boundary_owner[local]
    p_in = W[-1, cells]
    Tw = solver.wall_T_of(local, W)
    rho_w = p_in / (solver.gas.R * Tw)
    mu_w = np.asarray(solver.gas.mu(Tw), dtype=float)
    u_wall = np.zeros((len(local), dim))
    u_wall[:, 0] = solver.wall_u_face[local]           # sliding walls: the energy flux includes (tau . n) . u_wall
    work = np.einsum("fk,fk->f", -traction, u_wall)    # (tau . n) . u_wall
    q_w = -(FV[-1] / A - work)
    y1 = solver.vop.dn[faces] if hasattr(solver, "vop") else np.full(len(local), np.nan)
    tw = np.linalg.norm(tau_w, axis=1)
    u_tau = np.sqrt(tw / rho_w)
    return {"faces": local, "x": g.face_centres[faces], "area": A, "normal": n, "p": p, "traction": traction,
            "tau_w": tau_w, "q_w": q_w, "T_w": Tw, "rho_w": rho_w, "mu_w": mu_w, "y1": y1, "u_tau": u_tau,
            "y_plus": rho_w * u_tau * y1 / mu_w}


def skin_friction(data, direction, q_inf):
    """Signed Cf = tau_w . t / q_inf with t the unit projection of `direction` (free stream / nozzle axis) on the
    wall; faces where the direction is normal to the wall use the magnitude."""
    d = np.asarray(direction, dtype=float)[:data["normal"].shape[1]]
    t = d[None, :] - np.einsum("fk,k->f", data["normal"], d)[:, None] * data["normal"]
    norm = np.linalg.norm(t, axis=1)
    tw = np.linalg.norm(data["tau_w"], axis=1)
    along = np.where(norm > 1e-12, np.einsum("fk,fk->f", data["tau_w"], t) / np.maximum(norm, 1e-300), tw)
    return along / q_inf


def stanton(data, rho_inf, speed, cp, T0_inf):
    """St = q_w / (rho_inf |u_inf| cp (T0_inf - T_w)) (NaN where T_w = T0_inf)."""
    dT = T0_inf - data["T_w"]
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.abs(dT) > 1e-9, data["q_w"] / (rho_inf * speed * cp * dT), np.nan)


def force_split(solver, W, names, p_inf=0.0):
    """(pressure force, friction force) of the named walls, each a (dim,) vector [N; per metre in planar 2D, full
    circle in axisymmetric flow (radial components then cancel: set to 0)]. The pressure force uses p - p_inf."""
    g = solver.geom
    dim = g.dim
    Fp, Ff = np.zeros(dim), np.zeros(dim)
    for name, bc, local, _info in solver.patches:
        if name not in names:
            continue
        faces = g.n_interior + local
        A = g.flux_areas[faces] * solver.full_circle
        n = solver.boundary_normals[local]
        FV = solver.boundary_viscous_flux[:, local] if solver.boundary_viscous_flux is not None else 0.0 * \
            solver.boundary_flux[:, local]
        FA = solver.boundary_flux[:, local]
        mom = (FA[1:-1] + FV[1:-1]).T * solver.full_circle          # p n A (inviscid part only)
        Fp += (mom - p_inf * n * A[:, None]).sum(axis=0)
        Ff += (-FV[1:-1].T * solver.full_circle).sum(axis=0)
    if solver.mesh.axisymmetric:
        Fp[1] = Ff[1] = 0.0
    return Fp, Ff


__all__ = ["wall_data", "skin_friction", "stanton", "force_split"]

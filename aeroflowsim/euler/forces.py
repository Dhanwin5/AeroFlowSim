# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integrated quantities from the boundary fluxes: mass flow, thrust, Isp, Cf, Cd; Cl, Cd, Cm and Cp.

All of them are sums of the boundary-face fluxes F A that the solver has just computed
(EulerSolver.stage0_boundary_flux): the same numbers that moved mass and momentum in the last
iteration, so mass and momentum balances close exactly at a steady state. Axisymmetric fluxes are per
radian and are multiplied by 2 pi (full circle); planar 2D values are per metre of depth.

Nozzle thrust, two ways (they must agree when the run has converged, a check of conservation):
    exit plane   F_exit = sum_outlet (rho u_x u_n + p n_x) A                 = mdot u_e + p_e A_e
    wall + inlet F_wall = - sum_inlet (rho u_x u_n + p n_x) A - sum_wall p n_x A
(the steady x-momentum balance of the gas in the nozzle: inlet + wall + exit momentum fluxes = 0; the
axisymmetric source acts in r only). Both are VACUUM thrusts; the thrust at a back pressure p_a is
F - p_a A_e,x. Isp = F / (mdot g0), thrust coefficient Cf = F / (p0 A_t), discharge coefficient
Cd = mdot / mdot_1D (the ideal choked mass flow of isentropic quasi-1D theory).

Body forces: the force of the gas on a wall is sum_wall (p - p_inf) n A (n points out of the gas, into
the body). Subtracting p_inf changes nothing for a closed body and makes half bodies (on a symmetry
plane or the axis) correct. Wind axes: drag along the free-stream direction, lift normal to it.
Cl = L / (q A_ref), Cd = D / (q A_ref), Cm = M / (q A_ref L_ref) (nose-up positive, about x_ref).

3D (body_forces_3d): x is the flow axis at zero incidence, y up, z sideways. Wind axes from the angle of attack alpha
and the sideslip beta: drag direction d = (cos a cos b, sin a cos b, sin b), lift direction l = (-sin a, cos a, 0), side
direction s = d x l. D = F.d, L = F.l, Y = F.s; Cd, Cl, Cy = D, L, Y / (q A_ref). Moment vector about x_ref
M = sum r x (p - p_inf) n A [N m] (body axes), its coefficients CMx,y,z = M / (q A_ref L_ref), and the pitching moment
Cm = -CMz (nose-up positive, as in 2D). Symmetry planes (half / quarter domains): each plane through x_ref with normal
along axis k mirrors the body, so the whole body has F_k = 0 and the other force components doubled, and (M is an axial
vector) M_k doubled and the other moment components zero. Applied once per plane (a quarter domain: x 4 in drag).
"""

import math

import numpy as np

G0 = 9.80665    # standard gravity, defines Isp [m/s²]


def _patch(solver, name):
    for patch_name, bc, local, info in solver.patches:
        if patch_name == name:
            return local
    raise KeyError(f"No patch '{name}'.")


def patch_flux(solver, name):
    """Sum over a patch of F A, full circle / per metre: (dim + 2,) [kg/s, N, N, W]."""
    return solver.stage0_boundary_flux[:, _patch(solver, name)].sum(axis=1) * solver.full_circle


def patch_area_vector(solver, name):
    """Sum over a patch of n A, full circle / per metre: (dim,) [m²]."""
    local = _patch(solver, name)
    g = solver.geom
    return (solver.boundary_normals[local] * g.flux_areas[g.n_interior + local][:, None]).sum(axis=0) * solver.full_circle


def patch_names_of(conditions, *types):
    """Names of the patches whose boundary condition ({name: BoundaryCondition}) is one of the given types."""
    return [name for name, bc in conditions.items() if bc.type in types]


def mass_flow(solver, names):
    """Mass flow out through the named patches [kg/s] (negative = in)."""
    return float(sum(patch_flux(solver, n)[0] for n in names))


def nozzle_numbers(solver, inlets, outlets, walls):
    """{mdot_in, mdot_out, thrust_exit, thrust_wall, exit_area_x}: vacuum thrusts [N], mass flows [kg/s]."""
    m_in = -mass_flow(solver, inlets)
    m_out = mass_flow(solver, outlets)
    exit_x = sum(patch_flux(solver, n)[1] for n in outlets)
    inlet_x = sum(patch_flux(solver, n)[1] for n in inlets)
    wall_x = sum(patch_flux(solver, n)[1] for n in walls)
    area_x = sum(patch_area_vector(solver, n)[0] for n in outlets)
    return {"mdot_in": m_in, "mdot_out": m_out, "thrust_exit": float(exit_x), "thrust_wall": float(-inlet_x - wall_x),
            "exit_area_x": float(area_x)}


def wind_axes(angle_deg):
    """Unit vectors (drag direction, lift direction) for a free stream at angle_deg to the x axis."""
    a = math.radians(angle_deg)
    return np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])


def body_forces(solver, walls, p_inf, q_inf, angle_deg, A_ref, L_ref, x_ref=(0.0, 0.0), mirror=1.0):
    """Force and moment coefficients of the walls.

    mirror = 2 for a planar half body on a symmetry plane (drag doubled, lift and moment zero by symmetry).
    Returns {Fx, Fy (body axes) [N or N/m], D, L, Cd, Cl, Cm}.
    """
    g = solver.geom
    Fxy = np.zeros(2)
    moment = 0.0
    for name in walls:
        local = _patch(solver, name)
        n = solver.boundary_normals[local][:, :2]
        A = g.flux_areas[g.n_interior + local] * solver.full_circle
        mom = solver.stage0_boundary_flux[1:3, local] * solver.full_circle      # p n A on a wall
        f = mom.T - p_inf * n * A[:, None]                                        # (p - p_inf) n A
        Fxy += f.sum(axis=0)
        if not solver.mesh.axisymmetric:
            r = g.face_centres[g.n_interior + local][:, :2] - np.asarray(x_ref)
            moment -= float(np.sum(r[:, 0] * f[:, 1] - r[:, 1] * f[:, 0]))       # nose-up positive
    if solver.mesh.axisymmetric:
        Fxy[1] = 0.0                                   # the radial forces cancel round the circle
    drag_dir, lift_dir = wind_axes(angle_deg)
    Fxy_full = Fxy.copy()
    if mirror != 1.0:
        Fxy_full = np.array([Fxy[0] * mirror, 0.0])
        moment = 0.0
    D, L = float(Fxy_full @ drag_dir), float(Fxy_full @ lift_dir)
    return {"Fx": float(Fxy_full[0]), "Fy": float(Fxy_full[1]), "D": D, "L": L,
            "Cd": D / (q_inf * A_ref), "Cl": L / (q_inf * A_ref), "Cm": moment / (q_inf * A_ref * L_ref)}


def wall_pressure(solver, names):
    """(face centres (n, dim) [m], wall pressure (n,) [Pa]) of the named wall patches, from the wall fluxes."""
    g = solver.geom
    xs, ps = [], []
    for name in names:
        local = _patch(solver, name)
        A = g.flux_areas[g.n_interior + local]
        ok = A > 0.0
        n = solver.boundary_normals[local]
        flux = solver.stage0_boundary_flux[1:-1, local]
        visc = getattr(solver, "stage0_viscous_flux", None)
        if visc is not None:
            flux = flux + visc[1:-1, local]                 # viscous runs: the inviscid part (p n A) only
        p = np.einsum("kf,fk->f", flux, n)
        xs.append(g.face_centres[g.n_interior + local][ok])
        ps.append(p[ok] / A[ok])
    if not xs:
        return np.zeros((0, g.dim)), np.zeros(0)
    return np.concatenate(xs), np.concatenate(ps)


def symmetry_planes(mesh, names) -> tuple:
    """Axes (0 = x, 1 = y, 2 = z) of the flat symmetry planes in the named patches of a 3D mesh.

    A face belongs to the plane of its normal's largest component; a plane counts only if its faces lie in one plane
    normal to that axis (within 1e-9 of the domain size). Tilted or curved symmetry faces are ignored here, so forces
    are then reported for the meshed part only (and the result says so through its symmetry factor)."""
    axes = []
    size = max(float(np.ptp(mesh.nodes, axis=0).max()), 1e-300)
    for p in mesh.patches:
        if p.name not in names:
            continue
        n = mesh.face_normals[p.faces]
        c = mesh.face_centres[p.faces]
        axis = np.argmax(np.abs(n), axis=1)
        for k in range(3):
            on = axis == k
            if on.any() and np.all(np.abs(n[on, k]) > 1.0 - 1e-9) and float(np.ptp(c[on, k])) < 1e-9 * size:
                if k not in axes:
                    axes.append(k)
    return tuple(sorted(axes))


def wind_axes_3d(alpha_deg, beta_deg):
    """Unit vectors (drag, lift, side) for angle of attack alpha and sideslip beta (see the module docstring)."""
    a, b = math.radians(alpha_deg), math.radians(beta_deg)
    d = np.array([math.cos(a) * math.cos(b), math.sin(a) * math.cos(b), math.sin(b)])
    l = np.array([-math.sin(a), math.cos(a), 0.0])
    return d, l, np.cross(d, l)


def body_forces_3d(solver, walls, p_inf, q_inf, alpha_deg, beta_deg, A_ref, L_ref, x_ref=(0.0, 0.0, 0.0), planes=()):
    """Forces and moments of the walls of a 3D mesh, completed by the symmetry planes (axes in `planes`).

    Returns {Fx, Fy, Fz [N], Mx, My, Mz [N m], D, L, Y [N], Cd, Cl, Cy, CMx, CMy, CMz, Cm, factor} for the WHOLE body
    (factor = 2 ** number of symmetry planes: the meshed part is 1/factor of it)."""
    g = solver.geom
    F, M = np.zeros(3), np.zeros(3)
    for name in walls:
        local = _patch(solver, name)
        n = solver.boundary_normals[local]
        A = g.flux_areas[g.n_interior + local]
        f = solver.stage0_boundary_flux[1:4, local].T - p_inf * n * A[:, None]      # (p - p_inf) n A [N]
        r = g.face_centres[g.n_interior + local] - np.asarray(x_ref, dtype=float)
        F += f.sum(axis=0)
        M += np.cross(r, f).sum(axis=0)
    for k in planes:                     # mirror images: F_k and the moment components other than k cancel
        F = 2.0 * F
        F[k] = 0.0
        M_k = 2.0 * M[k]
        M = np.zeros(3)
        M[k] = M_k
    d, l, s = wind_axes_3d(alpha_deg, beta_deg)
    D, L, Y = float(F @ d), float(F @ l), float(F @ s)
    qA, qAL = q_inf * A_ref, q_inf * A_ref * L_ref
    return {"Fx": float(F[0]), "Fy": float(F[1]), "Fz": float(F[2]), "Mx": float(M[0]), "My": float(M[1]),
            "Mz": float(M[2]), "D": D, "L": L, "Y": Y, "Cd": D / qA, "Cl": L / qA, "Cy": Y / qA,
            "CMx": float(M[0]) / qAL, "CMy": float(M[1]) / qAL, "CMz": float(M[2]) / qAL, "Cm": -float(M[2]) / qAL,
            "factor": float(2 ** len(planes))}

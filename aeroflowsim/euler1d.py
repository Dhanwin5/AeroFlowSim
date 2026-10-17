# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reusable numerics for the 1D Euler equations (ideal gas), finite-volume form.

Equations (conservative form):
    dU/dt + dF(U)/dx = 0,
    U = [rho, rho*u, E]          conserved variables  [kg/m³, kg/(m²·s), J/m³]
    F = [rho*u, rho*u² + p, u*(E + p)]
    E = p/(gamma - 1) + rho*u²/2  (total energy per unit volume, ideal gas)

Method (see cases/sod_shock_tube/README.md for the plain-words explanation):
    - HLLC approximate Riemann solver for the face fluxes (Toro section 10.4)
    - MUSCL reconstruction of the primitive variables with the minmod limiter
    - SSP-RK2 (Heun) time stepping, time step from the CFL condition
    - transmissive (zero-gradient) boundaries via ghost cells

Array layout: every state is a numpy array of shape (3, n), one column per cell:
    U = conserved  (rows: rho, rho*u, E)
    W = primitive  (rows: rho [kg/m³], u [m/s], p [Pa])

The functions are deliberately small and independent, so the quasi-1D nozzle case can
reuse them and add its own boundary conditions and area source terms.
Nothing here imports the GUI.
"""

import numpy as np

N_GHOST = 2  # ghost cells on each side; MUSCL needs two to reconstruct the boundary faces


# ---- conversions -----------------------------------------------------------------------

def primitive_to_conserved(W, gamma):
    """[rho, u, p] -> [rho, rho*u, E]."""
    rho, u, p = W
    return np.array([rho, rho * u, p / (gamma - 1.0) + 0.5 * rho * u**2])


def conserved_to_primitive(U, gamma):
    """[rho, rho*u, E] -> [rho, u, p]."""
    rho = U[0]                                   # [kg/m³]
    u = U[1] / rho                               # [m/s]
    p = (gamma - 1.0) * (U[2] - 0.5 * U[1] * u)  # [Pa]
    return np.array([rho, u, p])


def sound_speed(W, gamma):
    """Speed of sound c = sqrt(gamma p / rho)  [m/s] for primitive states W."""
    return np.sqrt(gamma * W[2] / W[0])


def euler_flux(W, gamma):
    """Physical flux F(U) computed from primitive states W."""
    rho, u, p = W
    E = p / (gamma - 1.0) + 0.5 * rho * u**2     # [J/m³]
    return np.array([rho * u, rho * u**2 + p, u * (E + p)])


# ---- face flux: HLLC -------------------------------------------------------------------

def hllc_flux(WL, WR, gamma):
    """HLLC flux at every face from the left states WL and right states WR (shape (3, n_faces)).

    The Riemann fan at a face is modelled by the fastest left wave S_L, the fastest right
    wave S_R and a contact wave S* between them, with two constant "star" states around
    the contact (Toro eq. 10.37-10.39). Wave speeds: S_L = min(u_L - c_L, u_R - c_R),
    S_R = max(u_L + c_L, u_R + c_R) (Davis estimate, Toro eq. 10.48).
    """
    rho_l, u_l, p_l = WL
    rho_r, u_r, p_r = WR
    c_l, c_r = sound_speed(WL, gamma), sound_speed(WR, gamma)

    s_l = np.minimum(u_l - c_l, u_r - c_r)   # [m/s]
    s_r = np.maximum(u_l + c_l, u_r + c_r)   # [m/s]
    # Contact speed from equal star pressures on both sides (Toro eq. 10.37) [m/s]
    s_star = ((p_r - p_l + rho_l * u_l * (s_l - u_l) - rho_r * u_r * (s_r - u_r))
              / (rho_l * (s_l - u_l) - rho_r * (s_r - u_r)))

    UL, UR = primitive_to_conserved(WL, gamma), primitive_to_conserved(WR, gamma)
    FL, FR = euler_flux(WL, gamma), euler_flux(WR, gamma)

    def star_flux(rho, u, p, U, F, s):
        """F*_K = F_K + S_K (U*_K - U_K), with the star state from Toro eq. (10.39)."""
        factor = rho * (s - u) / (s - s_star)                       # [kg/m³]
        U_star = factor * np.array([
            np.ones_like(rho),
            s_star,
            U[2] / rho + (s_star - u) * (s_star + p / (rho * (s - u))),
        ])
        return F + s * (U_star - U)

    F_star_l = star_flux(rho_l, u_l, p_l, UL, FL, s_l)
    F_star_r = star_flux(rho_r, u_r, p_r, UR, FR, s_r)

    # Pick the flux by where the face (x/t = 0) sits in the wave fan.
    return np.where(0.0 <= s_l, FL,
           np.where(0.0 <= s_star, F_star_l,
           np.where(0.0 <= s_r, F_star_r, FR)))


# ---- reconstruction: MUSCL with minmod limiter -----------------------------------------

def minmod(a, b):
    """The smaller of the two slopes if they have the same sign, otherwise zero."""
    return np.where(a * b > 0.0, np.sign(a) * np.minimum(np.abs(a), np.abs(b)), 0.0)


def muscl_reconstruct(Wg):
    """Left and right states at the faces from cell values with ghost cells.

    Wg: primitive states including N_GHOST = 2 ghost cells on each side, shape (3, n + 4).
    Returns (WL, WR), each shape (3, n + 1): the states just left and right of each
    of the n + 1 faces of the n real cells. Inside each cell the profile is linear,
    with the minmod-limited slope (a slope per cell, not divided by dx).
    """
    slope = minmod(Wg[:, 1:-1] - Wg[:, :-2], Wg[:, 2:] - Wg[:, 1:-1])  # cells 1 .. n+2
    W_east = Wg[:, 1:-1] + 0.5 * slope   # value at each cell's right face
    W_west = Wg[:, 1:-1] - 0.5 * slope   # value at each cell's left face
    WL = W_east[:, :-1]   # cells 1 .. n+1  (left neighbour of faces 0 .. n)
    WR = W_west[:, 1:]    # cells 2 .. n+2  (right neighbour of faces 0 .. n)
    return WL, WR


# ---- boundaries ------------------------------------------------------------------------

def transmissive_ghosts(W):
    """Add N_GHOST ghost cells at each end that copy the end cell (zero gradient)."""
    return np.concatenate([np.repeat(W[:, :1], N_GHOST, axis=1),
                           W,
                           np.repeat(W[:, -1:], N_GHOST, axis=1)], axis=1)


# ---- spatial operator, time step, time integration --------------------------------------

def face_fluxes(U, gamma, boundary=transmissive_ghosts):
    """HLLC fluxes at all n + 1 faces, shape (3, n + 1).

    boundary: function that adds N_GHOST ghost cells to the primitive states
    (transmissive by default; other cases can pass inflow/outflow conditions).
    """
    Wg = boundary(conserved_to_primitive(U, gamma))
    WL, WR = muscl_reconstruct(Wg)
    return hllc_flux(WL, WR, gamma)


def flux_divergence(U, dx, gamma, boundary=transmissive_ghosts):
    """Right-hand side L(U) = -(F_{i+1/2} - F_{i-1/2}) / dx of the semi-discrete equations."""
    F = face_fluxes(U, gamma, boundary)
    return -(F[:, 1:] - F[:, :-1]) / dx


def cfl_time_step(U, dx, gamma, cfl):
    """Largest stable time step [s]: dt = CFL * dx / max(|u| + c)."""
    W = conserved_to_primitive(U, gamma)
    max_speed = np.abs(W[1]) + sound_speed(W, gamma)   # [m/s]
    return cfl * float(np.min(dx / max_speed))


def ssp_rk2_step(U, dt, rhs):
    """One SSP-RK2 (Heun) step: U1 = U + dt L(U);  U_new = (U + U1 + dt L(U1)) / 2.

    rhs: function U -> L(U). Passing it in lets other cases add source terms.
    """
    U1 = U + dt * rhs(U)
    return 0.5 * U + 0.5 * (U1 + dt * rhs(U1))

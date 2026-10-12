"""Quasi-1D Euler equations (flow in a duct of slowly varying area A(x)), finite-volume form.

Equations, written for a slice of the duct (not per unit area):
    d(U A)/dt + d(F A)/dx = S,      S = [0, p dA/dx, 0]
U and F are the 1D Euler conserved variables and flux (see core/euler1d.py). The source is the
axial push of the slanted wall on the gas. Discretely, for cell i between faces i-1/2 and i+1/2:

    V_i dU_i/dt = -(F A)_{i+1/2} + (F A)_{i-1/2} + [0, p_i (A_{i+1/2} - A_{i-1/2}), 0]

With this form of the source, gas at rest stays exactly at rest ("well-balanced"): every face
flux is then (0, p, 0) and the momentum terms cancel to the last bit.

The face fluxes (HLLC + MUSCL/minmod) and SSP-RK2 come unchanged from core/euler1d.py; this
module only adds the areas, local time steps and nozzle inlet/outlet boundary conditions.
Nothing here imports the GUI. See cases/quasi1d_nozzle/README.md for the explanation.
"""

import numpy as np

from core.euler1d import N_GHOST, conserved_to_primitive, face_fluxes, sound_speed


def quasi1d_rhs(U, A_faces, volumes, gamma, boundary):
    """Right-hand side dU/dt of the semi-discrete quasi-1D equations, shape (3, n).

    U        conserved states per unit volume, shape (3, n)
    A_faces  area of each of the n + 1 faces [m²]
    volumes  volume of each cell [m³]
    boundary function adding the ghost cells to the primitive states (see nozzle_boundary)
    """
    F = face_fluxes(U, gamma, boundary)                      # flux per unit area at each face
    p = (gamma - 1.0) * (U[2] - 0.5 * U[1] ** 2 / U[0])      # cell pressure [Pa]
    A_left, A_right = A_faces[:-1], A_faces[1:]              # [m²]
    rhs = -(F[:, 1:] * A_right - F[:, :-1] * A_left)
    # Momentum: -(F_R A_R - F_L A_L) + p_i (A_R - A_L), written in the identical form
    # -((F_R - p_i) A_R - (F_L - p_i) A_L). For gas at rest F = p on both faces, so each bracket
    # is exactly 0 - the plain form would leave a round-off "force" of ~1e-16 p A.
    rhs[1] = -((F[1, 1:] - p) * A_right - (F[1, :-1] - p) * A_left)
    return rhs / volumes


def local_time_steps(U, dx, gamma, cfl):
    """One stable time step per cell [s]: dt_i = CFL dx_i / (|u_i| + c_i) (steady problems only)."""
    W = conserved_to_primitive(U, gamma)
    return cfl * dx / (np.abs(W[1]) + sound_speed(W, gamma))


def inlet_state(u, p0, T0, gamma, R):
    """Primitive state [rho, u, p] at a reservoir-fed inlet with velocity u [m/s].

    Total pressure p0 [Pa] and total temperature T0 [K] are fixed (they come from the reservoir);
    the velocity is taken from inside the domain. Then (isentropic, energy conservation):
        T = T0 - u²/(2 cp),   p = p0 (T/T0)^(gamma/(gamma-1)),   rho = p / (R T)
    """
    cp = gamma * R / (gamma - 1.0)                 # [J/(kg·K)]
    T = T0 - u**2 / (2.0 * cp)                     # [K]
    if np.any(T <= 0.0):
        raise RuntimeError("Inlet velocity too high: the static temperature became negative.")
    p = p0 * (T / T0) ** (gamma / (gamma - 1.0))   # [Pa]
    return np.array([p / (R * T), u, p])


def nozzle_boundary(p0, T0, p_back, gamma, R):
    """Ghost-cell function for a nozzle fed by a reservoir (p0, T0) and exhausting at p_back.

    Inlet (subsonic): p0 and T0 imposed, velocity extrapolated from the first cell.
    Outlet: supersonic last cell -> everything extrapolated (copied);
            subsonic last cell   -> pressure = p_back, density and velocity extrapolated.
    Returns a function W -> W with N_GHOST ghost cells on each side.
    """
    def add_ghosts(W):
        inlet = inlet_state(W[1, 0], p0, T0, gamma, R)
        outlet = W[:, -1].copy()
        if abs(outlet[1]) < sound_speed(outlet, gamma):    # subsonic exit: back pressure acts
            outlet[2] = p_back
        return np.concatenate([np.repeat(inlet[:, None], N_GHOST, axis=1),
                               W,
                               np.repeat(outlet[:, None], N_GHOST, axis=1)], axis=1)
    return add_ghosts

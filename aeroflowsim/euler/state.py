# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Flow states: conserved <-> primitive variables, temperature and speed of sound, through the GasModel.

    W = [rho, u_1 .. u_dim, p]          primitive  [kg/m³, m/s, Pa]
    U = [rho, rho u_1 .. rho u_dim, E]  conserved  [kg/m³, kg/(m² s), J/m³]

with E = rho (e(T) + |u|²/2) the total energy per unit volume. Every gas property comes from the
GasModel (aeroflowsim/gases/model.py): T from the internal energy e with gas.temperature(e),
p = rho R T, c = gas.sound_speed(T). So a thermally perfect gas or a mixture later needs no change here.
Both arrays have shape (dim + 2, n): one column per cell or per face.
"""

import numpy as np


def n_velocity(W) -> int:
    """Number of velocity components (the space dimension) of a state array."""
    return W.shape[0] - 2


def temperature(W, gas):
    """Static temperature T = p / (rho R) [K] of primitive states."""
    return W[-1] / (W[0] * gas.R)


def sound_speed(W, gas):
    """Speed of sound [m/s] of primitive states."""
    return gas.sound_speed(temperature(W, gas))


def primitive_to_conserved(W, gas):
    """[rho, u, p] -> [rho, rho u, E]."""
    rho, vel, p = W[0], W[1:-1], W[-1]
    e = gas.internal_energy(p / (rho * gas.R))                  # [J/kg]
    U = np.empty_like(W)
    U[0] = rho
    U[1:-1] = rho * vel
    U[-1] = rho * (e + 0.5 * np.sum(vel * vel, axis=0))         # [J/m³]
    return U


def conserved_to_primitive(U, gas):
    """[rho, rho u, E] -> [rho, u, p]; the temperature comes from e = E/rho - |u|²/2 via the gas model."""
    rho = U[0]
    vel = U[1:-1] / rho                                          # [m/s]
    e = U[-1] / rho - 0.5 * np.sum(vel * vel, axis=0)            # [J/kg]
    W = np.empty_like(U)
    W[0] = rho
    W[1:-1] = vel
    W[-1] = rho * gas.R * gas.temperature(e)                     # p = rho R T [Pa]
    return W


def mach_number(W, gas):
    """Mach number |u| / c [-]."""
    vel = W[1:-1]
    return np.sqrt(np.sum(vel * vel, axis=0)) / sound_speed(W, gas)


def total_pressure(W, gas):
    """Total (stagnation) pressure p0 = p (1 + (gamma-1)/2 M²)^(gamma/(gamma-1)) [Pa].

    Isentropic relation with the gas's gamma at the static temperature (exact for a calorically
    perfect gas, the only model so far).
    """
    T = temperature(W, gas)
    g = gas.gamma(T)
    M2 = mach_number(W, gas) ** 2
    return W[-1] * (1.0 + 0.5 * (g - 1.0) * M2) ** (g / (g - 1.0))


def total_temperature(W, gas):
    """Total temperature T0 = T + |u|²/(2 cp) [K]."""
    T = temperature(W, gas)
    vel = W[1:-1]
    return T + 0.5 * np.sum(vel * vel, axis=0) / gas.cp(T)


def entropy(W, gas, p_ref=101325.0, T_ref=298.15):
    """Specific entropy relative to (p_ref, T_ref): s = cp ln(T/T_ref) - R ln(p/p_ref) [J/(kg K)].

    Constant along streamlines in smooth inviscid flow; a rise shows shocks or numerical losses.
    """
    T = temperature(W, gas)
    return gas.cp(T) * np.log(T / T_ref) - gas.R * np.log(W[-1] / p_ref)


def uniform_state(n, rho, velocity, p):
    """Primitive array (dim + 2, n) of one state repeated n times; velocity is a sequence of dim numbers."""
    velocity = np.asarray(velocity, dtype=float)
    W = np.empty((len(velocity) + 2, n))
    W[0] = rho
    W[1:-1] = velocity[:, None]
    W[-1] = p
    return W


def state_from_mach(gas, mach, p, T, direction):
    """(rho, velocity vector) for Mach number, static p [Pa], T [K] and a unit direction vector."""
    direction = np.asarray(direction, dtype=float)
    speed = mach * float(gas.sound_speed(T))       # [m/s]
    return p / (gas.R * T), speed * direction / np.linalg.norm(direction)


def is_physical(W) -> np.ndarray:
    """True where density and pressure are positive and finite (per column)."""
    return np.isfinite(W).all(axis=0) & (W[0] > 0.0) & (W[-1] > 0.0)

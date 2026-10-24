# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Face fluxes: HLLC and HLLE in the face-normal frame, and the shock-aware hybrid (carbuncle fix).

Every face has a unit normal n (from owner to neighbour, or out of the domain). Only the velocity
component along n, u_n = u . n, moves gas through the face; the tangential part is carried along.
So the 1D Riemann problem is solved along n:
    rotate   u_n = u . n  (the tangential velocity u - u_n n stays as it is)
    solve    wave speeds S_L, S*, S_R and the star states of the 1D HLLC solver (Toro sec. 10.4)
    rotate back: the momentum flux is rho u u_n + p n, the star velocity u + (S* - u_n) n.
Written with vectors like this, the same code works for any number of velocity components (2D, 3D):
it is the "rotated" HLLC, without building rotation matrices.

Wave speeds: Einfeldt's estimate (Einfeldt 1988, eq. 5.7-5.9) from the sqrt(rho)-weighted averages. It
needs only the speeds of sound of the two states (no gamma), so it works with every GasModel.

Carbuncle fix (shock_sensor + hybrid_flux): HLLC resolves contacts exactly, and at strong shocks that
exactness lets disturbances run along the shock front without damping ("carbuncle", odd-even
decoupling; Quirk 1994). HLLE adds dissipation exactly there. So near STRONG shocks (pressure ratio
across a face above about 1.5) the flux is blended smoothly from HLLC to HLLE; everywhere else HLLC is
used unchanged. The smooth blend (not an on/off switch) keeps steady residuals converging. This is
Quirk's (1994) "hybrid" cure with a pressure sensor; Nishikawa & Kitamura (2008) apply the same idea with
rotated normals.
"""

import numpy as np

from aeroflowsim.euler.state import primitive_to_conserved, sound_speed

# Shock sensor: blend weight w = 0 below SENSOR_START, 1 above SENSOR_FULL (relative pressure jump
# |p_R - p_L| / min(p_L, p_R) across the faces of the two cells next to a face) [-].
SENSOR_START = 0.5     # pressure ratio 1.5 across one face: begin blending towards HLLE
SENSOR_FULL = 1.0      # pressure ratio 2 across one face: pure HLLE


def normal_velocity(W, normals):
    """u . n for every column; normals has shape (n, dim)."""
    return np.sum(W[1:-1] * normals.T, axis=0)


def physical_flux(W, U, un, normals):
    """Euler flux through a face of unit normal n: [rho u_n, rho u u_n + p n, (E + p) u_n]."""
    p = W[-1]
    F = np.empty_like(W)
    F[0] = U[0] * un
    F[1:-1] = U[1:-1] * un + p * normals.T
    F[-1] = (U[-1] + p) * un
    return F


def _einfeldt_speeds(WL, WR, unL, unR, cL, cR):
    """Smallest and largest signal speeds S_L, S_R [m/s] (Einfeldt 1988)."""
    sqL, sqR = np.sqrt(WL[0]), np.sqrt(WR[0])
    un_avg = (sqL * unL + sqR * unR) / (sqL + sqR)                          # [m/s]
    eta2 = 0.5 * sqL * sqR / (sqL + sqR) ** 2
    d = np.sqrt((sqL * cL**2 + sqR * cR**2) / (sqL + sqR) + eta2 * (unR - unL) ** 2)   # [m/s]
    return np.minimum(unL - cL, un_avg - d), np.maximum(unR + cR, un_avg + d)


def _face_states(WL, WR, normals, gas):
    """Everything both fluxes need: conserved states, normal velocities, sound speeds, wave speeds."""
    UL, UR = primitive_to_conserved(WL, gas), primitive_to_conserved(WR, gas)
    unL, unR = normal_velocity(WL, normals), normal_velocity(WR, normals)
    cL, cR = sound_speed(WL, gas), sound_speed(WR, gas)
    sL, sR = _einfeldt_speeds(WL, WR, unL, unR, cL, cR)
    return UL, UR, unL, unR, sL, sR


def hllc_flux(WL, WR, normals, gas):
    """HLLC flux per unit face area, shape (dim + 2, n_faces), in the global x, y (, z) frame."""
    UL, UR, unL, unR, sL, sR = _face_states(WL, WR, normals, gas)
    return _hllc(WL, WR, UL, UR, unL, unR, sL, sR, normals)


def _hllc(WL, WR, UL, UR, unL, unR, sL, sR, normals):
    rhoL, pL = WL[0], WL[-1]
    rhoR, pR = WR[0], WR[-1]
    # Contact speed from equal star pressures on both sides (Toro eq. 10.37) [m/s]
    s_star = ((pR - pL + rhoL * unL * (sL - unL) - rhoR * unR * (sR - unR))
              / (rhoL * (sL - unL) - rhoR * (sR - unR)))
    FL = physical_flux(WL, UL, unL, normals)
    FR = physical_flux(WR, UR, unR, normals)

    def star_flux(W, U, un, F, s):
        """F*_K = F_K + S_K (U*_K - U_K) with the star state of Toro eq. (10.39), in vector form."""
        rho, p = W[0], W[-1]
        factor = rho * (s - un) / (s - s_star)                              # star density [kg/m³]
        U_star = np.empty_like(U)
        U_star[0] = factor
        U_star[1:-1] = factor * (W[1:-1] + (s_star - un) * normals.T)       # only u_n changes: to S*
        U_star[-1] = factor * (U[-1] / rho + (s_star - un) * (s_star + p / (rho * (s - un))))
        return F + s * (U_star - U)

    # Pick the flux by where the face (x/t = 0) sits in the wave fan.
    return np.where(sL >= 0.0, FL,
           np.where(s_star >= 0.0, star_flux(WL, UL, unL, FL, sL),
           np.where(sR > 0.0, star_flux(WR, UR, unR, FR, sR), FR)))


def hlle_flux(WL, WR, normals, gas):
    """HLLE flux per unit face area (Harten, Lax, van Leer 1983 with Einfeldt's wave speeds)."""
    UL, UR, unL, unR, sL, sR = _face_states(WL, WR, normals, gas)
    return _hlle(WL, WR, UL, UR, unL, unR, sL, sR, normals)


def _hlle(WL, WR, UL, UR, unL, unR, sL, sR, normals):
    bL, bR = np.minimum(sL, 0.0), np.maximum(sR, 0.0)
    FL = physical_flux(WL, UL, unL, normals)
    FR = physical_flux(WR, UR, unR, normals)
    return (bR * FL - bL * FR + bL * bR * (UR - UL)) / (bR - bL)


def blend_weight(sensor):
    """HLLE weight w in [0, 1] from the face shock sensor (smooth ramp between the two thresholds)."""
    return np.clip((sensor - SENSOR_START) / (SENSOR_FULL - SENSOR_START), 0.0, 1.0)


def hybrid_flux(WL, WR, normals, gas, weight=None):
    """(1 - w) HLLC + w HLLE per face; w = None or 0 everywhere gives pure HLLC.

    HLLE is evaluated only on the faces with w > 0 (normally a thin band around strong shocks).
    """
    UL, UR, unL, unR, sL, sR = _face_states(WL, WR, normals, gas)
    F = _hllc(WL, WR, UL, UR, unL, unR, sL, sR, normals)
    if weight is None:
        return F
    near = np.flatnonzero(weight > 0.0)
    if len(near):
        sel = (slice(None), near)
        F_hlle = _hlle(WL[sel], WR[sel], UL[sel], UR[sel], unL[near], unR[near], sL[near], sR[near], normals[near])
        w = weight[near]
        F[sel] = (1.0 - w) * F[sel] + w * F_hlle
    return F

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Real-gas estimate: the compressibility factor Z = p / (rho R T) from the Peng-Robinson equation.

An ideal gas has Z = 1. Real molecules attract each other (Z < 1) and take up room (Z > 1); both
matter when the gas is dense: high pressure, or a temperature not far above the critical point.
The ideal-gas validity check (aeroflowsim/checks.py) uses Z to warn when the ideal-gas solver is
used outside its range, e.g. a 300 bar N2 tank (Z = 1.14) or R-236fa near saturation.

Peng-Robinson (Peng & Robinson, Ind. Eng. Chem. Fundam. 15 (1976) 59-64), in molar form:

    p = R_u T / (v - b) - a alpha(T) / (v^2 + 2 b v - b^2)
    a = 0.45724 R_u^2 Tc^2 / pc,   b = 0.07780 R_u Tc / pc
    alpha = (1 + kappa (1 - sqrt(T / Tc)))^2,   kappa = 0.37464 + 1.54226 omega - 0.26992 omega^2

With A = a alpha p / (R_u T)^2 and B = b p / (R_u T) this is a cubic in Z:

    Z^3 - (1 - B) Z^2 + (A - 3 B^2 - 2 B) Z - (A B - B^2 - B^3) = 0

The gas (vapour) root is the largest real root. Typical accuracy in Z: about 1-2 % for simple gases
away from the critical point, a few % for polar molecules (enough for a 2 % warning threshold). This
module is also the start of the Phase 5 real-gas model.
"""

import numpy as np

from aeroflowsim.gases.model import R_UNIVERSAL


def peng_robinson_z(p, T, T_critical, p_critical, acentric_factor):
    """Compressibility factor Z (gas root) at pressures p [Pa] and temperatures T [K] (numbers or arrays)."""
    p, T = np.broadcast_arrays(np.asarray(p, dtype=float), np.asarray(T, dtype=float))
    w = acentric_factor
    kappa = 0.37464 + 1.54226 * w - 0.26992 * w * w
    alpha = (1.0 + kappa * (1.0 - np.sqrt(T / T_critical))) ** 2
    a = 0.45724 * R_UNIVERSAL**2 * T_critical**2 / p_critical     # [Pa m^6/mol^2]
    b = 0.07780 * R_UNIVERSAL * T_critical / p_critical            # [m^3/mol]
    A = a * alpha * p / (R_UNIVERSAL * T) ** 2
    B = b * p / (R_UNIVERSAL * T)
    Z = np.empty(p.shape)
    for i in np.ndindex(p.shape):                                  # one small cubic per state
        roots = np.roots([1.0, -(1.0 - B[i]), A[i] - 3.0 * B[i] ** 2 - 2.0 * B[i],
                          -(A[i] * B[i] - B[i] ** 2 - B[i] ** 3)])
        real = roots.real[np.abs(roots.imag) < 1e-9 * max(1.0, np.abs(roots).max())]
        Z[i] = real[real > B[i]].max()                             # physical roots have v > b, i.e. Z > B
    return Z if Z.ndim else float(Z)

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Viscous (Navier-Stokes) fluxes for the finite-volume solver: 2D planar, axisymmetric and 3D.

The viscous flux through a face with unit normal n (per unit area) is (Blazek 2015 sec. 2.2; Hirsch 2007 ch. 2)

    F_v = [ 0,  tau . n,  (tau . u + k grad T) . n ]
    tau = mu_eff (grad u + grad u^T - 2/3 (div u) I)          (Stokes hypothesis)

with mu_eff = mu(T) + mu_t and k_eff = k(T) + cp mu_t / Pr_t (Pr_t = 0.9). mu and k come from the GasModel at the
face temperature; mu_t (turbulent viscosity) from the turbulence model, zero for laminar flow.
The residual of a cell is  sum_f (F_inv - F_v) A_f  (solver.py).

Face gradient ("corrected" or edge-normal form, used by OpenFOAM, Fluent, SU2 and Blazek eq. 5.67): the mean of the
two cell gradients, with its component along the cell-to-cell vector d replaced by the direct difference

    grad_f = g_mean - (g_mean . t - (phi_N - phi_P) / |d|) t,        t = d / |d|

so the derivative along d is the compact two-point difference (no odd-even decoupling, exact for linear fields) and
the other components come from the cell gradients. At a boundary face phi_N is the boundary value at the face
centre (no-slip wall: u = 0 and T = T_wall) and d runs from the cell centre to the face centre.

Axisymmetric (x, r; per radian, as the inviscid part): div u = du/dx + dv/dr + v/r in tau, and the hoop stress
tau_thth = mu_eff (2 v/r - 2/3 div u) enters the r-momentum equation as the source -tau_thth A (A = planar cell
area, the same G_r of the well-balanced pressure term, theory manual section 12). 3D: the same flux, no extra term.

Time step and implicit diagonal (Blazek eq. 6.22 and sec. 6.2.4): the viscous spectral radius of a face is
    lambda_v,f = max(4/3, gamma / Pr_eff) (mu_eff / rho)_f / |d_f . n_f|      [m/s]
added to the convective one: dt_i = CFL V_i / (Lambda_c,i + sum_f lambda_v,f A_f), and in LU-SGS on the diagonal and
as a Laplacian-like off-diagonal coupling. These terms are kept SEPARATE from the convective dissipation so a later
low-Mach preconditioner can scale them on their own.
"""

from dataclasses import dataclass, field

import numpy as np

EULER, LAMINAR, SA, SST = "Euler", "Laminar", "Spalart-Allmaras", "k-omega SST"
FLOW_MODELS = (EULER, LAMINAR, SA, SST)
TURBULENT_MODELS = (SA, SST)
PR_T = 0.9                       # turbulent Prandtl number [-]
ADIABATIC, ISOTHERMAL = "Adiabatic", "Isothermal"
WALL_THERMAL = (ADIABATIC, ISOTHERMAL)
WALL_NOTE = "Fully turbulent, low-Re wall treatment only (no wall functions, no transition): mesh for y+ about 1."


def is_viscous(model) -> bool:
    return model not in (None, "", EULER)


@dataclass
class ViscousSettings:
    """What the solver needs to add the viscous terms.

    model: Laminar, Spalart-Allmaras or k-omega SST (Euler = no viscous terms; the solver is then given None).
    walls: {patch name: (thermal condition, T_wall [K])} of the no-slip walls.
    turbulence: free-stream turbulence {"intensity": [-], "viscosity_ratio": mu_t/mu [-]} (turbulent models).
    """

    model: str = LAMINAR
    walls: dict = field(default_factory=dict)
    turbulence: dict = field(default_factory=dict)
    prandtl_t: float = PR_T

    @property
    def turbulent(self) -> bool:
        return self.model in TURBULENT_MODELS


class ViscousOperator:
    """Face geometry of the viscous fluxes, computed once per mesh (NumPy reference + Numba kernel)."""

    def __init__(self, geom):
        g = geom
        self.geom = g
        nI = g.n_interior
        d = np.empty((g.n_faces, g.dim))
        d[:nI] = g.cell_centres[g.neighbour] - g.cell_centres[g.owner[:nI]]
        d[nI:] = g.face_centres[nI:] - g.cell_centres[g.boundary_owner]
        self.d = np.ascontiguousarray(d)                               # [m]
        self.d_len2 = np.einsum("fk,fk->f", d, d)                      # |d|² [m²]
        self.dn = np.maximum(np.abs(np.einsum("fk,fk->f", d, g.normals)), 1e-300)   # |d . n| [m]
        self.face_r = (np.ascontiguousarray(g.face_centres[:, 1]) if g.axisymmetric else np.zeros(g.n_faces))
        self.cell_r = g.cell_centres[:, 1] if g.axisymmetric else None
        self.axisymmetric = bool(g.axisymmetric)

    # ---- face values -----------------------------------------------------------------------------

    def face_mean(self, Xc, Xb):
        """Mean of the two cells (interior) or the boundary value (boundary faces): (n, F)."""
        g = self.geom
        nI = g.n_interior
        out = np.empty((Xc.shape[0], g.n_faces))
        out[:, :nI] = 0.5 * (Xc[:, g.owner[:nI]] + Xc[:, g.neighbour])
        out[:, nI:] = Xb
        return out

    def face_gradients(self, Xc, Xb, grad):
        """Corrected face gradients (n, dim, F) of the cell values Xc (n, C), boundary values Xb (n, B) and the cell
        gradients grad (n, dim, C) (module docstring)."""
        g = self.geom
        nI = g.n_interior
        gm = np.empty((Xc.shape[0], g.dim, g.n_faces))
        gm[:, :, :nI] = 0.5 * (grad[:, :, g.owner[:nI]] + grad[:, :, g.neighbour])
        gm[:, :, nI:] = grad[:, :, g.boundary_owner]
        dphi = np.empty((Xc.shape[0], g.n_faces))
        dphi[:, :nI] = Xc[:, g.neighbour] - Xc[:, g.owner[:nI]]
        dphi[:, nI:] = Xb - Xc[:, g.boundary_owner]
        along = np.einsum("vkf,fk->vf", gm, self.d)                    # g_mean . d
        corr = (dphi - along) / self.d_len2                            # [unit / m²]
        corr[:, nI:] *= 2.0                                            # boundary: second-order one-sided
        return gm + corr[:, None, :] * self.d.T[None, :, :]

    # ---- the flux (NumPy reference) --------------------------------------------------------------

    def fluxes(self, Xc, Xb, grad, mu_f, k_f, heat_mask):
        """Viscous flux times flux area, (dim + 2, F). X = [u_1 .. u_dim, T]; mu_f, k_f effective face values;
        heat_mask (F) multiplies the heat flux (0 on adiabatic walls)."""
        g = self.geom
        dim = g.dim
        gf = self.face_gradients(Xc, Xb, grad)                         # (dim + 1, dim, F)
        uf = self.face_mean(Xc, Xb)[:dim]                              # (dim, F)
        G = gf[:dim]                                                   # G[i, j] = d u_i / d x_j
        div = np.zeros(g.n_faces)
        for k in range(dim):
            div += G[k, k]
        if self.axisymmetric:
            r = self.face_r
            div += np.where(r > 0.0, uf[1] / np.where(r > 0.0, r, 1.0), 0.0)
        n = g.normals.T                                                # (dim, F)
        FV = np.zeros((dim + 2, g.n_faces))
        for i in range(dim):
            t = np.zeros(g.n_faces)
            for j in range(dim):
                tij = mu_f * (G[i, j] + G[j, i])
                if i == j:
                    tij = tij - (2.0 / 3.0) * mu_f * div
                t += tij * n[j]
            FV[1 + i] = t                                              # (tau . n)_i
            FV[-1] += t * uf[i]                                        # (tau . n) . u = (tau . u) . n (tau symmetric)
        q = np.zeros(g.n_faces)
        for j in range(dim):
            q += gf[dim, j] * n[j]
        FV[-1] += heat_mask * k_f * q
        return FV * g.flux_areas

    def hoop_source(self, Xc, grad, mu_c):
        """Axisymmetric hoop stress tau_thth = mu (2 v/r - 2/3 div u) per cell [Pa] (zero array for planar meshes)."""
        if not self.axisymmetric:
            return None
        r = self.cell_r
        v_r = Xc[1] / r
        div = grad[0, 0] + grad[1, 1] + v_r
        return mu_c * (2.0 * v_r - (2.0 / 3.0) * div)

    def spectral_radius(self, rho_f, mu_f, gamma, prandtl_eff):
        """Viscous spectral radius per face [m/s]: max(4/3, gamma/Pr) (mu/rho)_f / |d . n|."""
        fac = np.maximum(4.0 / 3.0, gamma / prandtl_eff)
        return fac * mu_f / rho_f / self.dn


__all__ = ["EULER", "LAMINAR", "SA", "SST", "FLOW_MODELS", "TURBULENT_MODELS", "PR_T", "ADIABATIC", "ISOTHERMAL",
           "WALL_THERMAL", "WALL_NOTE", "ViscousSettings", "ViscousOperator", "is_viscous"]

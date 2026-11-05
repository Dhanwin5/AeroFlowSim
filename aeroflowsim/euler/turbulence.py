# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""RANS turbulence models: Spalart-Allmaras (SA-noft2) and Menter's k-omega SST (2003, vorticity production = TMR
"SST-V"), for 2D, axisymmetric and 3D. Fully turbulent, low-Re wall treatment only (no wall functions, no transition).

Every model equation has the form (per unit volume; written for the turbulence variable q = nu_tilde, k or omega)

    rho Dq/Dt = div(Gamma grad q) + S(q)                        (non-conservative = conservative minus q x continuity)

discretised by finite volumes with the MEAN-FLOW's own face mass fluxes m_f (outward, from the HLLC flux of the last
residual: the same numbers that move mass):

    rho_i V_i dq_i/dt = - sum_f min(m_f, 0) (q_j - q_i)            first-order upwind convection (inflow faces only)
                        + sum_f Gamma_f A_f (grad q)_f . n_f        corrected face gradient (viscous.py, first-order
                                                                    one-sided at boundaries)
                        + V_i S_i                                   sources at the cell centre

Implicit, LOOSELY COUPLED (decision, as SU2 and CFL3D do it): after every mean-flow iteration the turbulence equations
take one implicit step with the same local time step, a symmetric Gauss-Seidel sweep (forward + backward, fixed cell
order: deterministic) of
    [rho V/dt + sum_f (max(-m_f, 0) + Gamma_f A_f / |d.n|) + V J] dq_i - sum_j c_ij dq_j = residual_i
with J >= 0 the derivative of the destruction terms (implicit on the diagonal), production explicit. Every coefficient
is positive, so the matrix is an M-matrix: dq cannot make q negative from a positive residual, and the update is further
limited so q stays positive (q_new >= 0.1 q_old; nu_tilde >= 0). Why loosely coupled rather than a block system with the
mean flow: the mean-flow LU-SGS operator is a scalar (Rusanov) approximation already, so a block coupling would gain
little, and the separate scalar sweep keeps positivity (Spalart & Allmaras 1992 sec. 3; Blazek 2015 sec. 7.2.1).

SA-noft2 (NASA Turbulence Modeling Resource, TMR, "SA-noft2"; Spalart & Allmaras 1992; Allmaras, Johnson, Spalart
2012 for the S_tilde limiter), compressible form of the TMR:
    rho D nut/Dt = rho cb1 S_t nut - rho cw1 fw (nut/d)^2 + (1/sigma)[div((mu + rho nut) grad nut) + rho cb2 |grad nut|^2]
                   - (1/sigma)(nu + nut) grad rho . grad nut
    chi = nut/nu, fv1 = chi^3/(chi^3 + cv1^3), mu_t = rho nut fv1, fv2 = 1 - chi/(1 + chi fv1),
    S_bar = nut fv2/(kappa^2 d^2), S_t = Omega + S_bar if S_bar >= -cv2 Omega
            else Omega + Omega (cv2^2 Omega + cv3 S_bar)/((cv3 - 2 cv2) Omega - S_bar),
    r = min(nut/(S_t kappa^2 d^2), 10), g = r + cw2 (r^6 - r), fw = g [(1 + cw3^6)/(g^6 + cw3^6)]^(1/6)
    cb1 0.1355, sigma 2/3, cb2 0.622, kappa 0.41, cw1 = cb1/kappa^2 + (1 + cb2)/sigma, cw2 0.3, cw3 2, cv1 7.1,
    cv2 0.7, cv3 0.9.  Wall nut = 0; free stream nut = 3 nu (TMR) or from the eddy-viscosity ratio.
SST (Menter, Kuntz & Langtry 2003; TMR "SST-V": production from the vorticity magnitude Omega):
    rho Dk/Dt = P - beta* rho omega k + div((mu + sigma_k mu_t) grad k),  P = min(mu_t Omega^2, 10 beta* rho omega k)
    rho Dw/Dt = gamma rho Omega^2 - beta rho omega^2 + div((mu + sigma_w mu_t) grad w)
                + 2 (1 - F1) rho sigma_w2 / omega grad k . grad omega
    mu_t = rho a1 k / max(a1 omega, S F2), S = sqrt(2 S_ij S_ij), constants blended phi = F1 phi1 + (1 - F1) phi2:
    sigma_k 0.85 / 1.0, sigma_w 0.5 / 0.856, beta 0.075 / 0.0828, gamma 5/9 / 0.44, beta* 0.09, a1 0.31, kappa 0.41,
    F1 = tanh(arg1^4), arg1 = min(max(sqrt(k)/(beta* omega d), 500 nu/(d^2 omega)), 4 rho sigma_w2 k/(CD d^2)),
    CD = max(2 rho sigma_w2 grad k . grad omega / omega, 1e-10), F2 = tanh(arg2^2),
    arg2 = max(2 sqrt(k)/(beta* omega d), 500 nu/(d^2 omega)).
    Wall k = 0, omega = 60 nu / (beta1 y1^2) (Menter 1994's 10 x 6 nu/(beta1 y1^2); y1 = first cell-centre distance);
    free stream k = 9e-9 a^2, omega = 1e-6 rho a^2 / mu (TMR) or from intensity and viscosity ratio.
Axisymmetric: the volumes and face areas are already r-weighted (per radian), which gives the radius-weighted diffusion
(1/r) d/dr (r Gamma dq/dr) exactly; the scalar equations have no hoop terms; the strain magnitude includes the hoop
strain v/r: S^2 = 2 (S_xx^2 + S_rr^2 + (v/r)^2 + 2 S_xr^2) - (2/3)... (deviatoric part not used; Omega has no v/r term).
"""

import numpy as np

from aeroflowsim.euler.viscous import SA, SST

# SA constants
CB1, SIGMA, CB2, KAPPA = 0.1355, 2.0 / 3.0, 0.622, 0.41
CW1 = CB1 / KAPPA**2 + (1.0 + CB2) / SIGMA
CW2, CW3, CV1, CV2, CV3 = 0.3, 2.0, 7.1, 0.7, 0.9
# SST constants (set 1 / set 2)
SK1, SW1, B1, G1 = 0.85, 0.5, 0.075, 5.0 / 9.0
SK2, SW2, B2, G2 = 1.0, 0.856, 0.0828, 0.44
BSTAR, A1 = 0.09, 0.31
MIN_FRACTION = 0.1          # q_new >= this x q_old (positivity of k, omega; SA: also nut >= 0)


def sa_fv1(chi):
    c3 = chi**3
    return c3 / (c3 + CV1**3)


def sa_chi_from_ratio(ratio):
    """chi with chi fv1(chi) = mu_t/mu (Newton)."""
    chi = max(ratio, 1.0) ** 0.25 * 3.0
    for _ in range(100):
        f = chi * sa_fv1(chi) - ratio
        h = 1e-7 * max(chi, 1e-3)
        df = ((chi + h) * sa_fv1(chi + h) - (chi - h) * sa_fv1(chi - h)) / (2 * h)
        chi = max(chi - f / df, 1e-8)
    return chi


class TurbulenceModel:
    """Base class: storage, boundary values, the implicit step. Subclasses: SAModel, SSTModel."""

    names = ()
    labels = {}

    def __init__(self, solver, freestream, settings=None):
        from aeroflowsim.euler.viscous import ViscousOperator
        from aeroflowsim.wall_distance import wall_distance
        self.solver = solver
        g = self.geom = solver.geom
        self.vop = getattr(solver, "vop", None) or ViscousOperator(g)
        walls = [name for name, bc, _l, _i in solver.patches if bc.type == "no_slip_wall"]
        d = wall_distance(solver.mesh, walls)
        size = float(np.ptp(g.cell_centres, axis=0).max())
        self.d = np.where(np.isfinite(d), d, 1e3 * size)           # no wall: "far" [m]
        self.freestream = freestream                               # dict rho, mu, a, U
        self.Q_inf = self.freestream_values(freestream, settings or {})
        self.Q = np.repeat(self.Q_inf[:, None], g.n_cells, axis=1)
        nB = g.n_boundary
        self.wall_b = np.zeros(nB, dtype=bool)
        self.free_b = np.zeros(nB, dtype=bool)                     # boundaries that bring free-stream turbulence in
        for _name, bc, local, _info in solver.patches:
            if bc.type == "no_slip_wall":
                self.wall_b[local] = True
            elif bc.type in ("far_field", "supersonic_inlet", "total_pressure_inlet", "mass_flow_inlet",
                             "pressure_outlet", "supersonic_outlet"):
                self.free_b[local] = True                          # inflow faces take the free stream (backflow too)
        self.y1 = self.vop.dn[g.n_interior:]                       # wall face to cell centre [m]
        self.norm = None
        self.history = []
        self.last_residual = 0.0

    # ---- to be provided by the models ----
    def freestream_values(self, fs, settings):
        raise NotImplementedError

    def wall_values(self, W_in, mu_in):
        raise NotImplementedError

    def eddy_viscosity(self, W, Q, grads):
        raise NotImplementedError

    def sources(self, W, Q, grads, gradQ):
        """(S (n, C) explicit source per volume, J (n, C) >= 0 implicit diagonal per volume, Gamma (n, C) diffusion
        coefficient per cell)."""
        raise NotImplementedError

    # ---- shared ----
    def boundary_values(self, Q, W, mass_b):
        """(n, B): walls -> wall values; inflow faces of in/outlets and far field -> free stream; others -> inside."""
        g = self.geom
        Qb = Q[:, g.boundary_owner].copy()
        inflow = self.free_b & (mass_b < 0.0)
        Qb[:, inflow] = self.Q_inf[:, None]
        if self.wall_b.any():
            cells = g.boundary_owner[self.wall_b]
            T = W[-1, cells] / (W[0, cells] * self.solver.gas.R)
            mu = np.asarray(self.solver.gas.mu(T), dtype=float)
            Qb[:, self.wall_b] = self.wall_values(W[:, cells], mu, self.y1[self.wall_b])
        return Qb

    def velocity_gradients(self):
        lv = getattr(self.solver, "stage0_viscous", None) or self.solver.last_viscous
        dim = self.geom.dim
        return lv["grad"][:dim], lv["Xc"][:dim]

    def invariants(self, W):
        """(Omega vorticity magnitude, S strain-rate magnitude sqrt(2 S_ij S_ij)) per cell [1/s] (axisymmetric: hoop
        strain v/r included in S)."""
        G, vel = self.velocity_gradients()
        dim = self.geom.dim
        if dim == 2:
            om = np.abs(G[1, 0] - G[0, 1])
        else:
            om = np.sqrt((G[2, 1] - G[1, 2]) ** 2 + (G[0, 2] - G[2, 0]) ** 2 + (G[1, 0] - G[0, 1]) ** 2)
        s2 = np.zeros(self.geom.n_cells)
        for i in range(dim):
            for j in range(dim):
                sij = 0.5 * (G[i, j] + G[j, i])
                s2 += 2.0 * sij * sij
        if self.geom.axisymmetric:
            s2 += 2.0 * (vel[1] / self.geom.cell_centres[:, 1]) ** 2
        return om, np.sqrt(s2)

    def step(self, W, dt, mass_flux):
        """One implicit step of the turbulence equations from the mean-flow state W (the state of this iteration's
        residual), local time steps dt and face mass fluxes (F,). Updates self.Q and solver.mu_t; returns the
        normalised residual (max over the equations)."""
        from aeroflowsim.euler import kernels as kn
        g, s = self.geom, self.solver
        nI = g.n_interior
        Q = self.Q
        n = Q.shape[0]
        Qb = self.boundary_values(Q, W, mass_flux[nI:])
        gradQ = s._gradient_of(Q, Qb)
        S, J, Gam = self.sources(W, Q, None, gradQ)
        # face diffusion coefficients (mean of the cells; boundary: the inside cell) and corrected face gradients
        Gf = self.vop.face_mean(Gam, Gam[:, g.boundary_owner])
        gm = np.empty((n, g.dim, g.n_faces))
        gm[:, :, :nI] = 0.5 * (gradQ[:, :, g.owner[:nI]] + gradQ[:, :, g.neighbour])
        gm[:, :, nI:] = gradQ[:, :, g.boundary_owner]
        dq = np.empty((n, g.n_faces))
        dq[:, :nI] = Q[:, g.neighbour] - Q[:, g.owner[:nI]]
        dq[:, nI:] = Qb - Q[:, g.boundary_owner]
        d = self.vop.d
        along = np.einsum("vkf,fk->vf", gm, d)
        corr = (dq - along) / self.vop.d_len2
        gn = np.einsum("vkf,fk->vf", gm, g.normals) + corr * np.einsum("fk,fk->f", d, g.normals)
        diff = Gf * gn * g.flux_areas                              # diffusion flux INTO the owner (n, F)
        inflow_own = np.minimum(mass_flux, 0.0)                    # owner's inflow (m out of owner < 0)
        conv_own = -inflow_own * dq                                # into owner: |m| (q_N - q_P)
        outflow_own = np.maximum(mass_flux[:nI], 0.0)              # = inflow into the neighbour
        conv_nb = outflow_own * (-dq[:, :nI])                      # into neighbour: m (q_P - q_N)
        R = np.zeros((n, g.n_cells))
        for v in range(n):
            R[v] += np.bincount(g.owner, conv_own[v] + diff[v], minlength=g.n_cells)
            R[v] += np.bincount(g.neighbour, conv_nb[v] - diff[v, :nI], minlength=g.n_cells)
        V = g.volumes
        R += S * V                                                 # sources per volume x (r-weighted) volume
        # implicit operator (slot form)
        sf = np.where(g.slot_used, g.slot_face, 0)
        m_out = g.slot_sign * mass_flux[sf]                        # outward of the cell
        conv_c = np.maximum(-m_out, 0.0)
        diff_c = (Gf[:, sf] * g.flux_areas[sf] / self.vop.dn[sf])  # (n, C, k)
        coef = np.where(g.slot_used, conv_c[None] + diff_c, 0.0)
        rho = W[0]
        D = rho * V / dt + coef.sum(axis=2) + J * V
        X = np.empty_like(R)
        kn.scalar_sgs(np.ascontiguousarray(R), np.ascontiguousarray(D), np.ascontiguousarray(coef),
                      np.ascontiguousarray(g.slot_other), X)
        Q_new = np.maximum(Q + X, MIN_FRACTION * Q)
        self.Q = self.clip(Q_new)
        self.solver.mu_t = self.eddy_viscosity(W, self.Q, None)
        rms = np.sqrt(np.mean((R / V) ** 2, axis=1))
        if self.norm is None or len(self.history) < 5:
            self.norm = rms if self.norm is None else np.maximum(self.norm, rms)
        res = rms / np.where(self.norm > 0, self.norm, 1.0)
        self.history.append(res)
        self.last_residual = float(res.max())
        return self.last_residual

    def clip(self, Q):
        return Q


class SAModel(TurbulenceModel):
    names = ("nu_tilde",)
    labels = {"nu_tilde": ("SA working variable nu_tilde", "m²/s")}

    def freestream_values(self, fs, settings):
        nu = fs["mu"] / fs["rho"]
        if settings.get("viscosity_ratio"):
            return np.array([sa_chi_from_ratio(settings["viscosity_ratio"]) * nu])
        return np.array([3.0 * nu])

    def wall_values(self, W_in, mu_in, y1):
        return np.zeros((1, W_in.shape[1]))

    def eddy_viscosity(self, W, Q, grads):
        rho = W[0]
        mu = np.asarray(self.solver.gas.mu(W[-1] / (rho * self.solver.gas.R)), dtype=float)
        chi = rho * Q[0] / mu
        return rho * Q[0] * sa_fv1(chi)

    def clip(self, Q):
        return np.maximum(Q, 0.0)

    def sources(self, W, Q, _grads, gradQ):
        rho = W[0]
        T = W[-1] / (rho * self.solver.gas.R)
        mu = np.asarray(self.solver.gas.mu(T), dtype=float)
        nu = mu / rho
        nt = Q[0]
        d = self.d
        om, _S = self.invariants(W)
        chi = nt / nu
        fv1 = sa_fv1(chi)
        fv2 = 1.0 - chi / (1.0 + chi * fv1)
        Sbar = nt * fv2 / (KAPPA**2 * d**2)
        with np.errstate(divide="ignore", invalid="ignore"):
            St = np.where(Sbar >= -CV2 * om, om + Sbar,
                          om + om * (CV2**2 * om + CV3 * Sbar) / ((CV3 - 2.0 * CV2) * om - Sbar))
            r = np.where(St > 0.0, np.minimum(nt / (St * KAPPA**2 * d**2), 10.0), 10.0)
        g6 = r + CW2 * (r**6 - r)
        fw = g6 * ((1.0 + CW3**6) / (g6**6 + CW3**6)) ** (1.0 / 6.0)
        prod = rho * CB1 * St * nt
        dest = rho * CW1 * fw * (nt / d) ** 2
        gq = gradQ[0]
        grad_rho = self.solver._gradient_of(W[:1], self.solver.boundary_face_values(
            W[:, self.geom.boundary_owner], self.solver.ghosts(W[:, self.geom.boundary_owner]))[:1])[0]
        cross = (rho * CB2 * np.sum(gq * gq, axis=0) - (nu + nt) * np.sum(grad_rho * gq, axis=0)) / SIGMA
        S = prod - dest + cross
        J = 2.0 * rho * CW1 * fw * nt / d**2
        Gam = (mu + rho * nt) / SIGMA
        return S[None], J[None], Gam[None]


class SSTModel(TurbulenceModel):
    names = ("k", "omega")
    labels = {"k": ("Turbulent kinetic energy k", "m²/s²"), "omega": ("Specific dissipation rate omega", "1/s")}

    def freestream_values(self, fs, settings):
        a, rho, mu, U = fs["a"], fs["rho"], fs["mu"], fs["U"]
        if settings.get("viscosity_ratio") is not None and settings.get("intensity") is not None:
            k = 1.5 * (settings["intensity"] * max(U, 1e-6)) ** 2
            return np.array([k, rho * k / (mu * max(settings["viscosity_ratio"], 1e-12))])
        return np.array([9e-9 * a * a, 1e-6 * rho * a * a / mu])

    def wall_values(self, W_in, mu_in, y1):
        nu = mu_in / W_in[0]
        return np.vstack([np.zeros(W_in.shape[1]), 60.0 * nu / (B1 * y1**2)])

    def _blend(self, W, Q, gradQ):
        rho = W[0]
        mu = np.asarray(self.solver.gas.mu(W[-1] / (rho * self.solver.gas.R)), dtype=float)
        nu = mu / rho
        k, w = Q
        d = self.d
        cdkw = 2.0 * rho * SW2 * np.sum(gradQ[0] * gradQ[1], axis=0) / w
        CD = np.maximum(cdkw, 1e-10)
        sk = np.sqrt(np.maximum(k, 0.0))
        a1 = np.minimum(np.maximum(sk / (BSTAR * w * d), 500.0 * nu / (d * d * w)), 4.0 * rho * SW2 * k / (CD * d * d))
        F1 = np.tanh(a1**4)
        a2 = np.maximum(2.0 * sk / (BSTAR * w * d), 500.0 * nu / (d * d * w))
        F2 = np.tanh(a2**2)
        return mu, F1, F2, cdkw

    def eddy_viscosity(self, W, Q, grads):
        rho = W[0]
        _om, S = self.invariants(W)
        if getattr(self, "_F2", None) is None or len(self._F2) != len(rho):
            F2 = np.ones_like(rho)
        else:
            F2 = self._F2
        return rho * A1 * Q[0] / np.maximum(A1 * Q[1], S * F2)

    def sources(self, W, Q, _grads, gradQ):
        rho = W[0]
        k, w = Q
        mu, F1, F2, cdkw = self._blend(W, Q, gradQ)
        self._F2 = F2
        om, S = self.invariants(W)
        mu_t = rho * A1 * k / np.maximum(A1 * w, S * F2)
        sk = F1 * SK1 + (1 - F1) * SK2
        sw = F1 * SW1 + (1 - F1) * SW2
        beta = F1 * B1 + (1 - F1) * B2
        gam = F1 * G1 + (1 - F1) * G2
        P = np.minimum(mu_t * om * om, 10.0 * BSTAR * rho * w * k)
        Sk = P - BSTAR * rho * w * k
        Sw = gam * rho * om * om - beta * rho * w * w + (1.0 - F1) * cdkw
        J = np.vstack([BSTAR * rho * w, 2.0 * beta * rho * w])
        Gam = np.vstack([mu + sk * mu_t, mu + sw * mu_t])
        return np.vstack([Sk, Sw]), J, Gam


def make_model(solver, freestream, settings):
    model = solver.viscous.model
    if model == SA:
        return SAModel(solver, freestream, settings)
    if model == SST:
        return SSTModel(solver, freestream, settings)
    raise ValueError(f"No turbulence model '{model}'.")


def freestream_of(solver, problem=None, params=None):
    """Reference state of the free-stream turbulence: the first far-field / supersonic-inlet condition, else the first
    total-pressure inlet (its stagnation state, speed 0.1 a0), else the template inputs."""
    gas = solver.gas
    for _name, bc, _l, _i in solver.patches:
        if bc.type in ("far_field", "supersonic_inlet"):
            v = bc.values
            T, p = v["T"], v["p"]
            a = float(gas.sound_speed(T))
            return {"rho": p / (gas.R * T), "mu": float(gas.mu(T)), "a": a, "U": v["mach"] * a}
    for _name, bc, _l, _i in solver.patches:
        if bc.type in ("total_pressure_inlet",):
            T, p = bc.values["T0"], bc.values["p0"]
            a = float(gas.sound_speed(T))
            return {"rho": p / (gas.R * T), "mu": float(gas.mu(T)), "a": a, "U": 0.1 * a}
    for _name, bc, _l, _i in solver.patches:
        if bc.type == "mass_flow_inlet":
            T = bc.values["T0"]
            a = float(gas.sound_speed(T))
            p = 101325.0
            return {"rho": p / (gas.R * T), "mu": float(gas.mu(T)), "a": a, "U": 0.1 * a}
    T = 300.0
    a = float(gas.sound_speed(T))
    return {"rho": 1.2, "mu": float(gas.mu(T)), "a": a, "U": 0.1 * a}


def attach_turbulence(solver, params=None, problem=None, restart_fields=None):
    """Create the turbulence model of a turbulent solver (solver.turbulence) and its initial mu_t."""
    settings = solver.viscous.turbulence or {}
    model = make_model(solver, freestream_of(solver, problem, params), settings)
    if restart_fields:
        vals = [restart_fields.get(n) for n in model.names]
        if all(v is not None and len(v) == model.geom.n_cells for v in vals):
            model.Q = np.array([np.asarray(v, dtype=float) for v in vals])
    solver.turbulence = model
    return model


__all__ = ["SAModel", "SSTModel", "attach_turbulence", "make_model", "sa_fv1", "sa_chi_from_ratio"]

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Euler solver: residual (gradients -> reconstruction -> flux -> sum), time stepping, convergence.

Semi-discrete finite-volume form for cell i with volume V_i (axisymmetric: per radian):

    V_i dU_i/dt = - sum_f F(W_L, W_R; n_f) A_f  +  S_i

F is the numerical flux per unit area (flux.py), A_f the flux area of face f (geometry.py). The only
source is the axisymmetric pressure source S_i = (0, 0, p_i A_i, 0) in the r-momentum equation (A_i the
planar cell area). It is written in the WELL-BALANCED form

    momentum:  - sum_f (F_mom,f - p_i n_f) A_f       (= - sum_f F_mom,f A_f + p_i G_i)

with the geometric vector G_i = sum_f n_f A_f (geometry.py). For a planar cell G_i = 0 (a closed
surface); for an axisymmetric cell its radial part is exactly A_i, so p_i G_i IS the pressure source.
Gas at rest has F_mom,f = p n_f on every face, so each bracket is zero: it stays at rest to round-off.
Same idea as the quasi-1D solver (aeroflowsim/quasi1d.py).

Time stepping (explicit, multistage): SSP-RK3 of Shu & Osher (1988) (default), or Jameson's four-stage
scheme (Jameson, Schmidt, Turkel 1981) with alpha = 1/4, 1/3, 1/2, 1. Steady cases use LOCAL time
steps (each cell its own stable dt, which does not change the steady solution); time-accurate cases use
one global dt.   dt_i = CFL V_i / Lambda_i,  Lambda_i = 1/2 sum_f (|u_i . n_f| + c_i) A_f   (Blazek eq. 6.22).

Robustness: optional first-order start; positivity fallback (reconstruct.py logic inside residual());
if a step gives negative density or pressure, or NaN, the last good state is restored and the CFL number
halved (at most MAX_CFL_REDUCTIONS times, then the run stops cleanly as "diverged").

Convergence (steady): the residual has dropped `residual_drop` orders AND every convergence monitor
(e.g. thrust, Cd) changed less than `monitor_tolerance` (relative) over the last `monitor_window` iterations.
"""

import time
from dataclasses import dataclass, field

import numpy as np

from aeroflowsim.euler.boundary import PatchInfo, ghost_state
from aeroflowsim.euler.flux import blend_weight, hybrid_flux, normal_velocity
from aeroflowsim.euler.geometry import FVGeometry
from aeroflowsim.euler.gradients import LEAST_SQUARES, Gradients
from aeroflowsim.euler.limiters import VENKATAKRISHNAN, limiter_factors
from aeroflowsim.euler.state import conserved_to_primitive, is_physical, primitive_to_conserved, sound_speed

SSP_RK3, JAMESON_RK4 = "SSP-RK3", "Jameson 4-stage"
TIME_SCHEMES = (SSP_RK3, JAMESON_RK4)
MAX_CFL_REDUCTIONS = 4        # halve the CFL number at most this often before giving up
CHECKPOINT_EVERY = 20         # iterations between saved "last good" states
NORM_ITERATIONS = 5           # residuals are normalised by their largest value in the first 5 iterations

CONVERGED, MAX_ITERATIONS, DIVERGED, END_TIME, STOPPED = (
    "converged", "max_iterations", "diverged", "end_time", "stopped")


@dataclass
class Numerics:
    """Numerical settings (the Setup step's Numerics group)."""

    cfl: float = 0.8                        # Courant number [-]
    order: int = 2                          # 1 or 2 (MUSCL)
    gradient: str = LEAST_SQUARES
    limiter: str = VENKATAKRISHNAN
    venkat_k: float = 5.0                   # Venkatakrishnan's K [-]
    freeze_limiter_orders: float = 0.0      # freeze the limiter after this residual drop [orders]; 0 = never
    first_order_iterations: int = 0         # first-order iterations before second order
    time_scheme: str = SSP_RK3
    local_time_stepping: bool = True        # steady: True; time-accurate: False
    max_iterations: int = 20000
    residual_drop: float = 6.0              # steady convergence: residual drop [orders]
    monitor_tolerance: float = 1e-4         # relative change of the convergence monitors [-]
    monitor_window: int = 200               # ... over this many iterations
    end_time: float | None = None           # time-accurate runs: stop at this time [s]
    carbuncle_fix: bool = True              # HLLE blend near strong shocks

    def __post_init__(self):
        if self.time_scheme not in TIME_SCHEMES:
            raise ValueError(f"Unknown time scheme '{self.time_scheme}'; use one of {', '.join(TIME_SCHEMES)}.")
        if self.order not in (1, 2):
            raise ValueError("The order of accuracy must be 1 or 2.")


@dataclass
class SolveResult:
    """What EulerSolver.solve() returns."""

    W: np.ndarray                     # final primitive state (dim + 2, C)
    status: str                       # converged, max_iterations, diverged, end_time or stopped
    iterations: int
    residuals: np.ndarray             # (iterations, dim + 2) normalised L2 residual per equation [-]
    monitors: dict = field(default_factory=dict)       # name -> array of values per iteration
    positivity_events: int = 0        # faces that fell back to first order (summed over iterations)
    positivity_last: int = 0          # ... in the last iteration
    cfl_reductions: int = 0
    cfl_final: float = 0.0
    wall_time_s: float = 0.0
    time: float = 0.0                 # physical time reached (time-accurate runs) [s]
    limiter_frozen_at: int | None = None
    message: str = ""


class EulerSolver:
    """Finite-volume Euler solver on a face-based Mesh (2D planar / axisymmetric; 3D-ready).

    conditions: {patch name: BoundaryCondition}, one for every patch of the mesh.
    L_ref:  reference length for the limiter's eps [m]; scales: reference size of each primitive
            variable (dim + 2 numbers), e.g. (rho_inf, |u_inf|, |u_inf|, p_inf).
    """

    def __init__(self, mesh, gas, conditions, numerics=None, L_ref=1.0, scales=None):
        self.mesh, self.gas = mesh, gas
        self.numerics = numerics or Numerics()
        self.geom = FVGeometry(mesh)
        self.grad = Gradients(self.geom, self.numerics.gradient)
        self.L_ref, self.scales = L_ref, None if scales is None else np.asarray(scales, dtype=float)
        missing = [p.name for p in mesh.patches if p.name not in conditions]
        if missing:
            raise ValueError(f"No boundary condition for: {', '.join(missing)}.")
        g, nI = self.geom, self.geom.n_interior
        full_circle = 2.0 * np.pi if mesh.axisymmetric else 1.0
        self.patches = []     # (name, condition, boundary-local indices, PatchInfo)
        for p in mesh.patches:
            local = np.arange(p.start, p.start + p.count) - nI
            area = float(g.flux_areas[p.start:p.start + p.count].sum()) * full_circle
            self.patches.append((p.name, conditions[p.name], local, PatchInfo(p.name, area)))
        self.boundary_normals = g.normals[nI:]
        self.full_circle = full_circle
        self.psi_frozen = None
        self.last_positivity = 0
        self.boundary_flux = None       # (n_vars, B) flux x flux area of the last residual evaluation

    # ---- boundary ghost states ---------------------------------------------------------------------

    def ghosts(self, Wb):
        """Ghost states (n_vars, B) of every boundary face from the inside states Wb (n_vars, B)."""
        out = np.empty_like(Wb)
        for _name, bc, local, info in self.patches:
            out[:, local] = ghost_state(bc, Wb[:, local], self.boundary_normals[local], self.gas, info)
        return out

    # ---- the residual ------------------------------------------------------------------------------

    def residual(self, U, second_order=True, W=None):
        """dU/dt (n_vars, C) and the primitive state W used."""
        g, nI = self.geom, self.geom.n_interior
        if W is None:
            W = conserved_to_primitive(U, self.gas)
        own, nb = g.owner, g.neighbour
        Wb_in = W[:, g.boundary_owner]
        ghost_c = self.ghosts(Wb_in)                         # first-order ghosts
        Wb_face = 0.5 * (Wb_in + ghost_c)                    # boundary value at the face centre

        if second_order:
            grad = self.grad.gradient(W, Wb_face)            # (n_vars, dim, C)
            if self.psi_frozen is not None:
                psi = self.psi_frozen
            else:
                psi = limiter_factors(g, grad, W, Wb_face, self.numerics.limiter, self.numerics.venkat_k,
                                      self.L_ref, self.scales)
            self.last_psi = psi
            dW = np.einsum("vkc,cfk->vcf", grad, g.slot_offset) * psi[:, :, None]   # (n_vars, C, k)
            WL = W[:, own] + dW[:, own, g.owner_slot]
            WR_int = W[:, nb] + dW[:, nb, g.neighbour_slot]
            WR_b = self.ghosts(WL[:, nI:])
            WR = np.concatenate([WR_int, WR_b], axis=1)
            # Positivity: a face whose reconstructed states are not physical falls back to first order.
            bad = ~(is_physical(WL) & is_physical(WR))
            self.last_positivity = int(np.count_nonzero(bad))
            if self.last_positivity:
                first_R = np.concatenate([W[:, nb], ghost_c], axis=1)
                WL[:, bad] = W[:, own[bad]]
                WR[:, bad] = first_R[:, bad]
        else:
            self.last_positivity = 0
            WL = W[:, own]
            WR = np.concatenate([W[:, nb], ghost_c], axis=1)

        weight = self._shock_weight(W, ghost_c) if self.numerics.carbuncle_fix else None
        F = hybrid_flux(WL, WR, g.normals, self.gas, weight)
        FA = F * g.flux_areas
        self.boundary_flux = FA[:, nI:]
        R = g.sum_over_faces(FA)
        R[1:-1] -= W[-1] * g.geometric_source               # well-balanced pressure term (see docstring)
        return -R / g.volumes, W

    def _shock_weight(self, W, ghost_c):
        """HLLE blend weight per face from a pressure-jump sensor (flux.py, carbuncle fix).

        Face jump s_f = |p_R - p_L| / min(p_L, p_R) with cell (first-order) pressures; cell sensor = largest
        s_f over its faces; face weight from the larger cell sensor of its two cells: a band about two cells
        wide on each side of a strong shock.
        """
        g = self.geom
        p = W[-1]
        p_other = np.concatenate([p[g.neighbour], ghost_c[-1]])
        p_own = p[g.owner]
        s_face = np.abs(p_other - p_own) / np.minimum(p_own, p_other)
        s_cell = np.where(g.slot_used, s_face[np.maximum(g.slot_face, 0)], 0.0).max(axis=1)
        s = s_cell[g.owner].copy()
        s[:g.n_interior] = np.maximum(s[:g.n_interior], s_cell[g.neighbour])
        w = blend_weight(s)
        return w if np.any(w > 0.0) else None

    # ---- time steps --------------------------------------------------------------------------------

    def time_steps(self, W, cfl):
        """Stable time step of every cell [s] (local time stepping; take the minimum for a global step)."""
        g = self.geom
        c = sound_speed(W, self.gas)                                     # [m/s]
        un = np.abs(np.einsum("kc,cfk->cf", W[1:-1], g.slot_normal))     # |u_i . n_f| [m/s]
        lam = 0.5 * np.sum((un + c[:, None]) * g.slot_planar_area, axis=1)   # [m³/s]
        return cfl * g.planar_volumes / lam

    # ---- the loop ----------------------------------------------------------------------------------

    def solve(self, W0, progress=None, monitor=None, monitor_scales=None, converge_on=()):
        """March from the primitive state W0 (n_vars, C) and return a SolveResult.

        progress(iteration, residual, info): called every iteration (may raise to stop the run).
        monitor(solver, W) -> {name: value}: monitors recorded every iteration (mass flows, forces, ...),
            from the state W at the start of the iteration and its boundary fluxes (solver.stage0_boundary_flux).
        converge_on: names of the monitors that must settle for steady convergence;
        monitor_scales: {name: scale} so a monitor near zero (e.g. Cl at zero incidence) is judged against
        a sensible size instead of its own tiny value.
        """
        num = self.numerics
        t_start = time.perf_counter()
        n_vars = W0.shape[0]
        U = primitive_to_conserved(W0, self.gas)
        cfl = num.cfl
        good_U, good_it, good_t = U.copy(), 0, 0.0
        res_hist, norm = [], None
        mon_hist = {}
        positivity_total = cfl_reductions = 0
        status, message = MAX_ITERATIONS, ""
        t_phys = 0.0
        it = 0
        frozen_at = None
        self.psi_frozen = None
        steady = num.end_time is None
        if not steady:
            num.local_time_stepping = False
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            while it < num.max_iterations:
                second = num.order == 2 and it >= num.first_order_iterations
                W = conserved_to_primitive(U, self.gas)
                dt = self.time_steps(W, cfl)
                if not num.local_time_stepping:
                    dt_glob = float(np.min(dt))
                    if not steady:
                        dt_glob = min(dt_glob, num.end_time - t_phys)
                    dt = np.full_like(dt, dt_glob)
                U_new, R0 = self._step(U, W, dt, second)
                W_new = conserved_to_primitive(U_new, self.gas)
                if not (np.all(np.isfinite(R0)) and np.all(is_physical(W_new))):
                    if cfl_reductions >= MAX_CFL_REDUCTIONS:
                        status = DIVERGED
                        message = (f"The solution became unphysical (negative density or pressure, or NaN) at "
                                   f"iteration {it + 1}, even after {cfl_reductions} CFL reductions.")
                        U = good_U
                        break
                    cfl_reductions += 1
                    cfl *= 0.5
                    U = good_U.copy()
                    del res_hist[good_it:]
                    for v in mon_hist.values():
                        del v[good_it:]
                    it, t_phys = good_it, good_t
                    self.psi_frozen = None
                    continue
                U = U_new
                it += 1
                positivity_total += self.last_positivity
                if not steady:
                    t_phys += float(dt[0])
                rms = np.sqrt(np.mean(R0**2, axis=1))                   # per equation
                if it <= NORM_ITERATIONS:
                    norm = rms if norm is None else np.maximum(norm, rms)
                res = rms / np.where(norm > 0.0, norm, 1.0)
                res_hist.append(res)
                values = monitor(self, W) if monitor is not None else {}
                for k, v in values.items():
                    mon_hist.setdefault(k, []).append(float(v))
                level = float(res.max())
                if (num.freeze_limiter_orders > 0.0 and self.psi_frozen is None and second
                        and level <= 10.0 ** (-num.freeze_limiter_orders)):
                    self.psi_frozen = self.last_psi.copy()
                    frozen_at = it
                if progress is not None:
                    progress(it, level, {"residuals": res, "monitors": values, "positivity": self.last_positivity,
                                         "cfl": cfl})
                if it % CHECKPOINT_EVERY == 0:
                    good_U, good_it, good_t = U.copy(), it, t_phys
                if not steady:
                    if t_phys >= num.end_time * (1.0 - 1e-12):
                        status = END_TIME
                        break
                elif (it > NORM_ITERATIONS and level <= 10.0 ** (-num.residual_drop)
                      and _settled(mon_hist, converge_on, monitor_scales or {}, num)):
                    status = CONVERGED
                    break
        W = conserved_to_primitive(U, self.gas)
        residuals = np.array(res_hist) if res_hist else np.zeros((0, n_vars))
        return SolveResult(W=W, status=status, iterations=it, residuals=residuals,
                           monitors={k: np.array(v) for k, v in mon_hist.items()},
                           positivity_events=positivity_total, positivity_last=self.last_positivity,
                           cfl_reductions=cfl_reductions, cfl_final=cfl,
                           wall_time_s=time.perf_counter() - t_start, time=t_phys, limiter_frozen_at=frozen_at,
                           message=message)

    def _step(self, U, W, dt, second):
        """One multistage step; returns (new U, residual dU/dt of the first stage)."""
        R0, _ = self.residual(U, second, W)
        self.stage0_boundary_flux = self.boundary_flux     # fluxes of the state W, for the monitors
        if self.numerics.time_scheme == SSP_RK3:
            U1 = U + dt * R0
            U2 = 0.75 * U + 0.25 * (U1 + dt * self.residual(U1, second)[0])
            return U / 3.0 + 2.0 / 3.0 * (U2 + dt * self.residual(U2, second)[0]), R0
        Uk = U + 0.25 * dt * R0
        for alpha in (1.0 / 3.0, 0.5, 1.0):
            Uk = U + alpha * dt * self.residual(Uk, second)[0]
        return Uk, R0


def _settled(history, names, scales, num) -> bool:
    """True if every named monitor changed less than the tolerance over the last window."""
    for name in names:
        values = history.get(name)
        if values is None:
            continue
        if len(values) < num.monitor_window:
            return False
        window = np.asarray(values[-num.monitor_window:])
        size = max(abs(float(window.mean())), scales.get(name, 0.0), 1e-300)
        if (window.max() - window.min()) > num.monitor_tolerance * size:
            return False
    return True


def boundary_mass_flow(solver, patch_name):
    """Mass flow OUT through a patch [kg/s] (axisymmetric: full circle; planar: per metre of depth)."""
    for name, _bc, local, _info in solver.patches:
        if name == patch_name:
            return float(solver.stage0_boundary_flux[0, local].sum()) * solver.full_circle
    raise KeyError(patch_name)


__all__ = ["Numerics", "EulerSolver", "SolveResult", "boundary_mass_flow", "normal_velocity",
           "SSP_RK3", "JAMESON_RK4", "TIME_SCHEMES"]

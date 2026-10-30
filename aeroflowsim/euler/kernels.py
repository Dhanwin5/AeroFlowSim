# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Numba kernels of the residual: the same equations as the NumPy code, written as loops over cells and faces.

Why loops: NumPy evaluates one formula over a whole array at a time, so a residual with ~40 formulas walks
through memory ~40 times and allocates ~40 temporary arrays. A compiled loop does all the formulas for one
face (or cell) while its numbers are in the CPU cache: same arithmetic, 10-30 x less memory traffic.

The NumPy code (flux.py, gradients.py, limiters.py, geometry.py, state.py) stays the REFERENCE: every kernel
here must agree with it to 1e-12 (relative, per residual evaluation; tests/test_kernels.py). The order of a few
sums differs, so the last digits may differ; nothing else does.

Rules for every kernel (so the same kernels can later be ported to a GPU with CuPy / CUDA unchanged):
  * a pure function of flat NumPy arrays and plain numbers: no Python objects, no global state;
  * outputs are passed in (preallocated once per solver): no allocation inside the loops;
  * each loop iteration writes only its own cell or face: no two iterations write the same number, so the
    loops run in parallel (prange) with no locks and the result does NOT depend on the number of threads.
    Face sums are done by GATHER: each cell adds up the fluxes of its own faces in its own fixed slot order
    (instead of each face scattering into two cells, which would need atomic adds and make the summation
    order depend on the thread timing). So two runs give identical histories, for any thread count.

Gas: the kernels take R, cv and gamma as numbers, i.e. a calorically perfect gas (the only GasModel so far).
Another gas model runs the NumPy path (prepare() returns None) until its kernels are written.

Compilation: on the first use of each kernel (about 10-30 s for all of them, once), cached on disk
(cache=True) so later runs start at once. If no cache folder is writable, the kernels compile in memory
on every start (slower start, same results).
"""

import math
import warnings

import numpy as np

try:
    import numba
    from numba import prange
    NUMBA_ERROR = ""
except Exception as exc:         # missing or broken Numba: the NumPy path runs (aeroflowsim/compute.py)
    numba = None
    prange = range
    NUMBA_ERROR = f"{type(exc).__name__}: {exc}"

# Limiter codes (the kernels take numbers, not strings)
NONE_CODE, BARTH_CODE, VENKAT_CODE = 0, 1, 2
SENSOR_START, SENSOR_FULL = 0.5, 1.0      # same as flux.py
TINY = 1e-300


def _cache_works() -> bool:
    """True if Numba can cache compiled code on this machine (a writable cache folder exists)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            numba.njit(cache=True)(lambda x: x + 1)
        return True
    except Exception:
        return False


CACHE = numba is not None and _cache_works()


def _jit(parallel=True):
    if numba is None:
        return lambda f: f
    return numba.njit(parallel=parallel, cache=CACHE, fastmath=False, error_model="numpy", nogil=True)


# ---- state conversion -------------------------------------------------------------------------------

@_jit()
def primitive(U, R, cv, W):
    """[rho, rho u, E] -> [rho, u, p] for every column (state.conserved_to_primitive, e = cv T)."""
    nv, n = U.shape
    for i in prange(n):
        rho = U[0, i]
        ke = 0.0
        for k in range(1, nv - 1):
            u = U[k, i] / rho
            W[k, i] = u
            ke += u * u
        e = U[nv - 1, i] / rho - 0.5 * ke
        W[0, i] = rho
        W[nv - 1, i] = rho * R * (e / cv)


# ---- gradients ----------------------------------------------------------------------------------------

@_jit()
def gradients(X, slot_other, coef_other, coef_self, grad):
    """grad[v, k, i] = sum over the slots s of cell i of a_sk X[v, other_s]  +  b_ik X[v, i]
    (least squares: a = c_s, b = -sum_s c_s; Green-Gauss: the face-average weights; gradients.py).

    X = [cell values, boundary face values] (n_vars, C + B), so no branch is needed in the loop."""
    nv = X.shape[0]
    C, k_max = slot_other.shape
    dim = coef_other.shape[2]
    for i in prange(C):
        for v in range(nv):
            wi = X[v, i]
            for k in range(dim):
                acc = coef_self[i, k] * wi      # sum in a register; write the result once
                for s in range(k_max):
                    acc += coef_other[i, s, k] * X[v, slot_other[i, s]]
                grad[v, k, i] = acc


# ---- limiter -------------------------------------------------------------------------------------------

@_jit()
def limiter(kind, W, X, grad, slot_other, slot_used, slot_offset, cell_size, K, L_ref, size, psi):
    """psi[v, i] in [0, 1] (limiters.py): Barth-Jespersen or Venkatakrishnan, min over the cell's faces.

    size[v, i]: the scale of variable v in cell i (eps² = (K h / L_ref)³ size²)."""
    nv, C = W.shape
    k_max = slot_other.shape[1]
    dim = slot_offset.shape[2]
    for i in prange(C):
        h3 = (K * cell_size[i] / L_ref) ** 3
        for v in range(nv):
            if kind == NONE_CODE:
                psi[v, i] = 1.0
                continue
            wi = W[v, i]
            vmax = wi
            vmin = wi
            for s in range(k_max):
                x = X[v, slot_other[i, s]]
                vmax = max(vmax, x)
                vmin = min(vmin, x)
            d_max = max(vmax - wi, 0.0)
            d_min = min(vmin - wi, 0.0)
            eps2 = h3 * size[v, i] ** 2
            p = 1.0
            for s in range(k_max):
                if not slot_used[i, s]:
                    continue
                delta = grad[v, 0, i] * slot_offset[i, s, 0]
                for k in range(1, dim):
                    delta += grad[v, k, i] * slot_offset[i, s, k]
                if abs(delta) < TINY:
                    continue
                bound = d_max if delta > 0.0 else d_min
                if kind == BARTH_CODE:
                    f = min(1.0, bound / delta)
                else:
                    num = (bound * bound + eps2) * delta + 2.0 * delta * delta * bound
                    den = bound * bound + 2.0 * delta * delta + bound * delta + eps2
                    f = num / (den * delta)
                p = min(p, f)
            psi[v, i] = min(max(p, 0.0), 1.0)


# ---- reconstruction to the faces ----------------------------------------------------------------------

@_jit()
def reconstruct(W, grad, psi, owner, neighbour, owner_slot, neighbour_slot, slot_offset, second, WL, WR):
    """Face states: WL[:, f] for every face, WR[:, f] for the interior faces (MUSCL: W + psi grad . r_f)."""
    nv, C = W.shape
    F = owner.shape[0]
    nI = neighbour.shape[0]
    dim = slot_offset.shape[2]
    for f in prange(F):
        o = owner[f]
        so = owner_slot[f]
        for v in range(nv):
            d = 0.0
            if second:
                d = grad[v, 0, o] * slot_offset[o, so, 0]
                for k in range(1, dim):
                    d += grad[v, k, o] * slot_offset[o, so, k]
                d *= psi[v, o]
            WL[v, f] = W[v, o] + d
        if f < nI:
            n = neighbour[f]
            sn = neighbour_slot[f]
            for v in range(nv):
                d = 0.0
                if second:
                    d = grad[v, 0, n] * slot_offset[n, sn, 0]
                    for k in range(1, dim):
                        d += grad[v, k, n] * slot_offset[n, sn, k]
                    d *= psi[v, n]
                WR[v, f] = W[v, n] + d


# ---- shock sensor (carbuncle fix) ---------------------------------------------------------------------

@_jit()
def shock_weight(W, ghost_c, owner, neighbour, normals, slot_face, s_face, s_cell, weight):
    """HLLE blend weight per face (EulerSolver._shock_weight); returns nothing, fills weight (F,).

    s_face (F,), s_cell (C,) are work arrays."""
    nv, C = W.shape
    F = owner.shape[0]
    nI = neighbour.shape[0]
    dim = normals.shape[1]
    for f in prange(F):
        o = owner[f]
        p_own = W[nv - 1, o]
        un = 0.0
        if f < nI:
            n = neighbour[f]
            p_other = W[nv - 1, n]
            for k in range(dim):
                un += (W[1 + k, o] + W[1 + k, n]) * normals[f, k]
        else:
            b = f - nI
            p_other = ghost_c[nv - 1, b]
            for k in range(dim):
                un += (W[1 + k, o] + ghost_c[1 + k, b]) * normals[f, k]
        un *= 0.5
        if (p_other - p_own) * un > 0.0:
            s_face[f] = abs(p_other - p_own) / min(p_own, p_other)
        else:
            s_face[f] = 0.0
    k_max = slot_face.shape[1]
    for i in prange(C):
        m = 0.0
        for s in range(k_max):
            f = slot_face[i, s]
            if f >= 0:
                m = max(m, s_face[f])
        s_cell[i] = m
    for f in prange(F):
        s = s_cell[owner[f]]
        if f < nI:
            s = max(s, s_cell[neighbour[f]])
        weight[f] = min(max((s - SENSOR_START) / (SENSOR_FULL - SENSOR_START), 0.0), 1.0)


# ---- face fluxes ---------------------------------------------------------------------------------------

@_jit(parallel=False)
def _physical(W, f):
    nv = W.shape[0]
    if not (W[0, f] > 0.0 and W[nv - 1, f] > 0.0):
        return False
    for v in range(nv):
        if not math.isfinite(W[v, f]):
            return False
    return True


@_jit()
def fluxes(WL, WR, W, ghost_c, owner, neighbour, normals, flux_areas, weight, use_weight, second,
           R, cv, gamma, FA, bad):
    """Flux x flux area of every face: (1 - w) HLLC + w HLLE (flux.py), with the positivity fallback.

    A face whose reconstructed states are not physical takes first-order states (bad[f] = 1)."""
    nv = WL.shape[0]
    F = owner.shape[0]
    nI = neighbour.shape[0]
    dim = nv - 2
    for f in prange(F):
        bad[f] = 0
        if second and not (_physical(WL, f) and _physical(WR, f)):
            bad[f] = 1
            o = owner[f]
            for v in range(nv):
                WL[v, f] = W[v, o]
                WR[v, f] = W[v, neighbour[f]] if f < nI else ghost_c[v, f - nI]
        rL = WL[0, f]
        rR = WR[0, f]
        pL = WL[nv - 1, f]
        pR = WR[nv - 1, f]
        unL = 0.0
        unR = 0.0
        kL = 0.0
        kR = 0.0
        for k in range(dim):
            unL += WL[1 + k, f] * normals[f, k]
            unR += WR[1 + k, f] * normals[f, k]
            kL += WL[1 + k, f] * WL[1 + k, f]
            kR += WR[1 + k, f] * WR[1 + k, f]
        EL = rL * (cv * (pL / (rL * R)) + 0.5 * kL)
        ER = rR * (cv * (pR / (rR * R)) + 0.5 * kR)
        cL = math.sqrt(gamma * R * (pL / (rL * R)))
        cR = math.sqrt(gamma * R * (pR / (rR * R)))
        # Einfeldt wave speeds
        sqL = math.sqrt(rL)
        sqR = math.sqrt(rR)
        un_avg = (sqL * unL + sqR * unR) / (sqL + sqR)
        eta2 = 0.5 * sqL * sqR / (sqL + sqR) ** 2
        d = math.sqrt((sqL * cL**2 + sqR * cR**2) / (sqL + sqR) + eta2 * (unR - unL) ** 2)
        sL = min(unL - cL, un_avg - d)
        sR = max(unR + cR, un_avg + d)
        s_star = ((pR - pL + rL * unL * (sL - unL) - rR * unR * (sR - unR))
                  / (rL * (sL - unL) - rR * (sR - unR)))
        w = weight[f] if use_weight else 0.0
        A = flux_areas[f]
        bL = min(sL, 0.0)
        bR = max(sR, 0.0)
        for v in range(nv):
            # physical fluxes and conserved states of both sides, component v
            if v == 0:
                UL = rL
                UR = rR
                FL = rL * unL
                FR = rR * unR
            elif v == nv - 1:
                UL = EL
                UR = ER
                FL = (EL + pL) * unL
                FR = (ER + pR) * unR
            else:
                UL = rL * WL[v, f]
                UR = rR * WR[v, f]
                FL = UL * unL + pL * normals[f, v - 1]
                FR = UR * unR + pR * normals[f, v - 1]
            # HLLC: pick the flux by where x/t = 0 sits in the wave fan
            if sL >= 0.0:
                Fh = FL
            elif s_star >= 0.0:
                fac = rL * (sL - unL) / (sL - s_star)
                if v == 0:
                    Us = fac
                elif v == nv - 1:
                    Us = fac * (EL / rL + (s_star - unL) * (s_star + pL / (rL * (sL - unL))))
                else:
                    Us = fac * (WL[v, f] + (s_star - unL) * normals[f, v - 1])
                Fh = FL + sL * (Us - UL)
            elif sR > 0.0:
                fac = rR * (sR - unR) / (sR - s_star)
                if v == 0:
                    Us = fac
                elif v == nv - 1:
                    Us = fac * (ER / rR + (s_star - unR) * (s_star + pR / (rR * (sR - unR))))
                else:
                    Us = fac * (WR[v, f] + (s_star - unR) * normals[f, v - 1])
                Fh = FR + sR * (Us - UR)
            else:
                Fh = FR
            if w > 0.0:
                Fe = (bR * FL - bL * FR + bL * bR * (UR - UL)) / (bR - bL)
                Fh = (1.0 - w) * Fh + w * Fe
            FA[v, f] = Fh * A


# ---- face sums and the residual ------------------------------------------------------------------------

@_jit()
def face_sums(FA, W, slot_face, slot_sign, geometric_source, source, use_source, volumes, dUdt):
    """dU/dt of every cell (solver.residual): - [sum_f sign F A - p G (+ source)] / V, summed by GATHER
    (each cell over its own faces in slot order: deterministic, thread-count independent)."""
    nv, C = W.shape
    k_max = slot_face.shape[1]
    for i in prange(C):
        for v in range(nv):
            r = 0.0
            for s in range(k_max):
                f = slot_face[i, s]
                if f >= 0:
                    r += slot_sign[i, s] * FA[v, f]
            if 0 < v < nv - 1:
                r -= W[nv - 1, i] * geometric_source[v - 1, i]
            if use_source:
                r -= source[v, i]
            dUdt[v, i] = -r / volumes[i]


# ---- time steps ----------------------------------------------------------------------------------------

@_jit()
def time_steps(W, slot_normal_by_axis, slot_planar_area, planar_volumes, cfl, R, gamma, dt):
    """dt_i = CFL V_i / Lambda_i, Lambda_i = 1/2 sum_f (|u_i . n_f| + c_i) A_f (solver.time_steps)."""
    nv, C = W.shape
    dim = nv - 2
    k_max = slot_planar_area.shape[1]
    for i in prange(C):
        c = math.sqrt(gamma * R * (W[nv - 1, i] / (W[0, i] * R)))
        lam = 0.0
        for s in range(k_max):
            un = W[1, i] * slot_normal_by_axis[0, i, s]
            for k in range(1, dim):
                un += W[1 + k, i] * slot_normal_by_axis[k, i, s]
            lam += (abs(un) + c) * slot_planar_area[i, s]
        dt[i] = cfl * planar_volumes[i] / (0.5 * lam)


# ---- set-up per solver (NumPy, once) ------------------------------------------------------------------

class KernelData:
    """The flat arrays and work buffers the kernels need for one solver (built once, reused every call)."""

    def __init__(self, solver, R, cv, gamma):
        g = solver.geom
        nv = g.dim + 2
        self.R, self.cv, self.gamma = float(R), float(cv), float(gamma)
        self.coef_other, coef_self = slot_gradient_coefficients(g, solver.numerics.gradient)
        self.coef_self = np.ascontiguousarray(coef_self.sum(axis=1))      # (C, dim): the cell's own weight
        C, F, nI, B = g.n_cells, g.n_faces, g.n_interior, g.n_boundary
        self.X = np.empty((nv, C + B))                                     # [cell values, boundary values]
        self.grad = np.zeros((nv, g.dim, C))
        self.psi = np.ones((nv, C))
        self.size = np.empty((nv, C))
        self.WL = np.empty((nv, F))
        self.WR = np.empty((nv, F))
        self.FA = np.empty((nv, F))
        self.bad = np.zeros(F, dtype=np.int8)
        self.weight = np.zeros(F)
        self.s_face = np.zeros(F)
        self.s_cell = np.zeros(C)
        self.no_source = np.zeros((nv, 1))
        self.slot_used = np.ascontiguousarray(g.slot_used)
        self.slot_other = np.ascontiguousarray(g.slot_other)
        self.slot_offset = np.ascontiguousarray(g.slot_offset)
        self.slot_face = np.ascontiguousarray(g.slot_face)
        self.slot_sign = np.ascontiguousarray(g.slot_sign)
        self.normals = np.ascontiguousarray(g.normals)
        self.geometric_source = np.ascontiguousarray(g.geometric_source)
        del nI, B


def slot_gradient_coefficients(g, method):
    """Per cell and slot the gradient weights (C, k_max, dim): a on the other value, b on the cell's own value.

    The same numbers as the sparse matrices of gradients.py, arranged by slot instead of matrix row."""
    from aeroflowsim.euler.gradients import LEAST_SQUARES
    C, nI, dim = g.n_cells, g.n_interior, g.dim
    used = g.slot_used
    f = np.where(used, g.slot_face, 0)
    cells = np.broadcast_to(np.arange(C)[:, None], f.shape)
    interior = f < nI
    a = np.zeros(f.shape + (dim,))
    b = np.zeros(f.shape + (dim,))
    if method == LEAST_SQUARES:
        # offset to the other value: the other cell centre, or the boundary face centre
        other_x = np.where(interior[..., None], g.cell_centres[np.where(g.slot_other < C, g.slot_other, 0)],
                           g.face_centres[f])
        d = np.where(used[..., None], other_x - g.cell_centres[:, None, :], 0.0)        # (C, k, dim) [m]
        dd = np.einsum("csk,csk->cs", d, d)
        w2 = np.where(used, 1.0 / np.where(used, dd, 1.0), 0.0)
        A = np.einsum("cs,csa,csb->cab", w2, d, d)
        coeff = np.einsum("cab,csb->csa", np.linalg.inv(A), w2[..., None] * d)          # (C, k, dim) [1/m]
        a[:] = coeff
        b[:] = -coeff
    else:
        S = g.normals[f] * g.planar_areas[f][..., None] * g.slot_sign[..., None]       # outward area vectors
        V = g.planar_volumes[cells][..., None]
        a[:] = np.where(interior[..., None], 0.5 * S / V, S / V)
        b[:] = np.where(interior[..., None], 0.5 * S / V, 0.0)
        a[~used] = 0.0
        b[~used] = 0.0
    return np.ascontiguousarray(a), np.ascontiguousarray(b)


def prepare(solver):
    """KernelData for this solver, or None if the NumPy path must run (no Numba, or not a calorically perfect gas)."""
    if numba is None:
        return None
    from aeroflowsim.gases.model import CaloricallyPerfectGas
    gas = solver.gas
    if not isinstance(gas, CaloricallyPerfectGas):
        return None
    return KernelData(solver, gas.R, float(gas.cv(300.0)), float(gas.gamma(300.0)))


def set_threads(n: int):
    if numba is not None:
        numba.set_num_threads(max(1, min(int(n), numba.config.NUMBA_NUM_THREADS)))


def get_threads() -> int:
    return numba.get_num_threads() if numba is not None else 1

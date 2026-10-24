# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Slope limiters for unstructured meshes: one factor psi in [0, 1] per cell and variable.

The reconstructed face value is  phi_f = phi_i + psi_i g_i . r_f  (r_f: cell centre -> face centre).
A limiter makes sure no face value overshoots the largest or undershoots the smallest value among the
cell and its face neighbours, so the scheme creates no new extrema (no wiggles at shocks).
Per face of cell i, with Delta = g_i . r_f (the unlimited change) and Delta_max = phi_max - phi_i,
Delta_min = phi_min - phi_i (Delta_max for Delta > 0, Delta_min for Delta < 0, called D below):

    Barth-Jespersen (1989):   psi_f = min(1, D / Delta)
    Venkatakrishnan (1995):   psi_f = [(D² + eps²) Delta + 2 Delta² D] / [D² + 2 Delta² + D Delta + eps²] / Delta

and psi_i = the smallest psi_f over the cell's faces. Barth-Jespersen is strict but non-smooth (min,
max), which can stall a steady residual. Venkatakrishnan's version is smooth; eps² lets small
differences through unlimited, so smooth regions keep second order and the residual converges. The
classic choice eps² = (K h)³ is not dimensionally consistent; here, as in many codes, it is written for
non-dimensional values:  eps² = (K h / L_ref)³ * scale²  with h the cell size, L_ref a reference length
and `scale` a reference size of the variable (e.g. the free-stream pressure). K = 5 is the usual default
(larger K = less limiting).

Freezing (option, solver.py): after the residual has dropped by a set number of orders, psi is kept
fixed. This stops limiter "chatter" from stalling the residual (the quasi-1D minmod limiter does exactly
that on fine meshes, see the gap register).
"""

import numpy as np

VENKATAKRISHNAN, BARTH_JESPERSEN = "Venkatakrishnan", "Barth-Jespersen"
LIMITERS = (VENKATAKRISHNAN, BARTH_JESPERSEN)


def neighbour_bounds(geom, Wc, Wb):
    """phi_max - phi_i (>= 0) and phi_min - phi_i (<= 0) over each cell and its face neighbours, (n_vars, C)."""
    X = np.concatenate([Wc, Wb], axis=1)
    values = X[:, geom.slot_other]                       # (n_vars, C, k_max); padding = the cell itself
    return np.maximum(values.max(axis=2) - Wc, 0.0), np.minimum(values.min(axis=2) - Wc, 0.0)


def limiter_factors(geom, grad, Wc, Wb, kind=VENKATAKRISHNAN, K=5.0, L_ref=1.0, scale=None, delta=None):
    """psi (n_vars, C) for the gradients grad (n_vars, dim, C).

    delta: the unlimited changes grad . r_f (n_vars, C, k_max) if the caller has them already.
    """
    if kind not in LIMITERS:
        raise ValueError(f"Unknown limiter '{kind}'; use one of {', '.join(LIMITERS)}.")
    d_max, d_min = neighbour_bounds(geom, Wc, Wb)
    if delta is None:
        delta = geom.change_to_faces(grad)                     # unlimited change to each face (n_vars, C, k)
    bound = np.where(delta > 0.0, d_max[:, :, None], d_min[:, :, None])
    small = np.abs(delta) < 1e-300
    safe = np.where(small, 1.0, delta)
    if kind == BARTH_JESPERSEN:
        psi = np.minimum(1.0, bound / safe)
    else:
        if scale is None:
            scale = np.maximum(np.abs(Wc).max(axis=1), 1e-30)
        eps2 = ((K * geom.cell_size / L_ref) ** 3)[None, :] * (np.asarray(scale, dtype=float) ** 2)[:, None]
        eps2 = eps2[:, :, None]
        num = (bound**2 + eps2) * delta + 2.0 * delta**2 * bound
        den = bound**2 + 2.0 * delta**2 + bound * delta + eps2
        psi = num / (den * safe)
    psi = np.where(small | ~geom.slot_used[None], 1.0, psi)
    return np.clip(psi.min(axis=2), 0.0, 1.0)

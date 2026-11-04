# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""MMS order of accuracy of the 3D Euler solver (aeroflowsim/mms.py, run_level_3d): warped boxes of hexahedra, prisms
and tetrahedra, second order without limiter, LU-SGS to a residual drop of 8 orders. Full set: 12^3 and 24^3 cubes
(order between them); quick set: 6^3 and 12^3. The compared value is the smallest L2 order over rho, u, v, w, p."""

from aeroflowsim import mms
from validation.common import is_quick

RUNS = {}


def measure():
    levels = (6, 12) if is_quick() else (12, 24)
    out = {}
    for kind in mms.MESH_KINDS_3D:
        runs = [mms.run_level_3d(kind, n, residual_drop=8.0) for n in levels]
        RUNS[kind] = runs
        out[kind] = float(min(mms.observed_orders(runs)[0]))
    return out


def study():
    rows = []
    for kind, runs in RUNS.items():
        orders = mms.observed_orders(runs)[0]
        for r in runs:
            rows.append([kind, f"{r.n}^3", f"{r.cells:,}", f"{r.iterations:,}", f"{r.wall_time_s:.1f}",
                         " ".join(f"{e:.3e}" for e in r.errors["L2"])])
        rows.append([kind, "order", "", "", "", " ".join(f"{o:.3f}" for o in orders)])
    return {"title": "Levels (L2 errors of rho, u, v, w, p)",
            "columns": ["Cells", "Box", "Count", "Iterations", "Time [s]", "L2 error / order"],
            "rows": rows, "notes": ["Hexahedra, Kuhn tetrahedra (6 per cube) and prisms (2 per cube), warp 0.03."]}

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""MMS order of accuracy of the laminar Navier-Stokes terms (aeroflowsim/mms_ns.py) in 2D, axisymmetric and 3D.
Full set: 2D 32, 64, 128 cells per side, 3D 12^3 and 24^3; quick set: 2D 16, 32, 64 and 3D 6^3, 12^3. The compared
value is the smallest L2 order over the variables between the two finest meshes. Runs are spread over the cores."""

import os
from concurrent.futures import ProcessPoolExecutor

from aeroflowsim import mms, mms_ns
from validation.common import is_quick

RUNS = {}
KINDS = {"quads": ("quads", False), "distorted_quads": ("distorted quads", False), "triangles": ("triangles", False),
         "axi_quads": ("quads", True), "axi_triangles": ("triangles", True), "hexahedra": ("hexahedra", False),
         "prisms": ("prisms", False), "tetrahedra": ("tetrahedra", False)}


def _levels(kind):
    if kind in mms.MESH_KINDS_3D:
        return (6, 12) if is_quick() else (12, 24)
    return (16, 32, 64) if is_quick() else (32, 64, 128)


def measure():
    jobs = [(kind, n, axi) for key, (kind, axi) in KINDS.items() for n in _levels(kind)]
    workers = max(1, min(len(jobs), (os.cpu_count() or 2) // 2))
    with ProcessPoolExecutor(workers) as pool:
        done = dict(pool.map(mms_ns.run_job, jobs))
    out = {}
    for key, (kind, axi) in KINDS.items():
        runs = []
        for n in _levels(kind):
            d = done[(kind, n, axi)]
            runs.append(mms.MMSRun(kind, n, d["cells"], d["h"], {k: __import__("numpy").array(d[k])
                                                                 for k in ("L1", "L2", "Linf")},
                                   d["iterations"], d["residual"], d["time"]))
        RUNS[key] = runs
        out[key] = float(min(mms.observed_orders(runs)[-1]))
    return out


def study():
    rows = []
    for key, runs in RUNS.items():
        orders = mms.observed_orders(runs)
        for r in runs:
            rows.append([key, str(r.n), f"{r.cells:,}", f"{r.iterations:,}", f"{r.wall_time_s:.1f}",
                         " ".join(f"{e:.3e}" for e in r.errors["L2"])])
        rows.append([key, "order", "", "", "", " ".join(f"{o:.3f}" for o in orders[-1])])
    return {"title": "Levels (L2 errors of rho, velocity components, p)",
            "columns": ["Mesh", "n", "Cells", "Iterations", "Time [s]", "L2 error / order (finest pair)"],
            "rows": rows,
            "notes": ["Air with mu = 2 Pa s (T/300 K)^0.7, Pr 0.72 (viscous terms as large as the convective ones).",
                      "Boundary faces: second-order one-sided face gradient (aeroflowsim/euler/viscous.py)."]}

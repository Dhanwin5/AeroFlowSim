# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""MMS order-of-accuracy study of the 2D / axisymmetric Euler solver (aeroflowsim/mms.py).

Four mesh kinds (quads, smoothly distorted quads, triangles, mixed), planar and axisymmetric, second order
without limiter (the pass/fail numbers), plus first order and second order with the Venkatakrishnan limiter
(reported, not pass/fail). Full set: 16, 32, 64, 128 cells per side; quick set: 8, 16, 32. Every mesh is solved
from the exact solution to a residual drop of 8 orders; the runs are spread over the processor cores.
The GCI tool (aeroflowsim/gci.py) is applied to the L2 error of p on the three finest meshes as a check that the
error sequence is in the asymptotic range.
"""

import json
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from aeroflowsim import gci, mms
from validation.common import is_quick

HERE = Path(__file__).resolve().parent
RESULTS = {}
VARIANTS = [  # (key prefix, axisymmetric, order, limiter)
    ("", False, 2, "None"), ("axi_", True, 2, "None"),
    ("first_", False, 1, "None"), ("venkat_", False, 2, "Venkatakrishnan"),
]


def _levels():
    return (8, 16, 32) if is_quick() else (16, 32, 64, 128)


def measure():
    levels = _levels()
    jobs = [(kind, n, axi, order, lim) for _, axi, order, lim in VARIANTS for kind in mms.MESH_KINDS
            for n in levels]
    jobs.sort(key=lambda j: -j[1])                       # big meshes first (best use of the cores)
    workers = max(1, min(len(jobs), (os.cpu_count() or 2) - 2))
    with ProcessPoolExecutor(workers) as pool:
        for args, out in pool.map(mms.run_job, jobs):
            RESULTS[args] = out
    measured = {}
    for prefix, axi, order, lim in VARIANTS:
        for kind in mms.MESH_KINDS:
            runs = [RESULTS[(kind, n, axi, order, lim)] for n in levels]
            fine_pair = [math.log(np.array(runs[-2]["L2"])[k] / np.array(runs[-1]["L2"])[k])
                         / math.log(runs[-2]["h"] / runs[-1]["h"]) for k in range(4)]
            measured[prefix + kind.replace(" ", "_")] = min(fine_pair)
    (HERE / "last_study.json").write_text(json.dumps(
        {"levels": levels, "runs": {"|".join(map(str, k)): v for k, v in RESULTS.items()}}, indent=1))
    return measured


def study():
    levels = _levels()
    rows = []
    for prefix, axi, order, lim in VARIANTS:
        for kind in mms.MESH_KINDS:
            runs = [RESULTS[(kind, n, axi, order, lim)] for n in levels]
            h = [r["h"] for r in runs]
            orders = {norm: [gci.observed_order(h, [r[norm][k] for r in runs])[-1] for k in range(4)]
                      for norm in ("L1", "L2", "Linf")}
            g = gci.three_mesh(h[-1:-4:-1], [r["L2"][3] for r in runs[-1:-4:-1]])
            label = ("axisymmetric" if axi else "planar") + f", order {order}" + (", " + lim if lim != "None" else "")
            rows.append([label, kind, " / ".join(f"{e:.2e}" for e in runs[-1]["L2"]),
                         " / ".join(f"{p:.2f}" for p in orders["L1"]),
                         " / ".join(f"{p:.2f}" for p in orders["L2"]),
                         " / ".join(f"{p:.2f}" for p in orders["Linf"]),
                         f"{g.p:.2f}", f"{g.asymptotic_ratio:.2f}",
                         f"{sum(r['iterations'] for r in runs):,}", f"{sum(r['time'] for r in runs):.0f}"])
    return {"title": f"Observed orders between the two finest meshes ({' / '.join(map(str, levels))} cells per side)",
            "columns": ["Scheme", "Mesh", "L2 error finest (rho / u / v / p)", "Order L1", "Order L2",
                        "Order Linf", "GCI p (L2 of p)", "GCI asympt. ratio", "Iterations", "Time [s]"],
            "rows": rows,
            "notes": ["Orders listed per variable rho / u / v / p. Errors in SI units (kg/m³, m/s, m/s, Pa).",
                      "The GCI columns apply the three-mesh GCI procedure (aeroflowsim/gci.py) to the L2 error of p: "
                      "its observed order should match and the asymptotic ratio be near 1.",
                      "First order and the Venkatakrishnan limiter are reported for information (not pass/fail): "
                      "the limiter clips smooth extrema on coarse meshes, so its order is lower there."]}

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


def _levels(order=2, limiter="None"):
    """Mesh levels: the pass/fail runs (second order, no limiter) on 16-128 cells per side; first order and the
    limiter (reported only) on 8-64, which shows their behaviour at a quarter of the cost. Quick set: 8-32."""
    if is_quick():
        return (8, 16, 32)
    return (16, 32, 64, 128) if (order == 2 and limiter == "None") else (8, 16, 32, 64)


def measure():
    jobs = [(kind, n, axi, order, lim) for _, axi, order, lim in VARIANTS for kind in mms.MESH_KINDS
            for n in _levels(order, lim)]
    jobs.sort(key=lambda j: -j[1])                       # big meshes first (best use of the cores)
    workers = max(1, min(len(jobs), (os.cpu_count() or 2) - 2))
    with ProcessPoolExecutor(workers) as pool:
        for args, out in pool.map(mms.run_job, jobs):
            RESULTS[args] = out
    measured = {}
    for prefix, axi, order, lim in VARIANTS:
        levels = _levels(order, lim)
        for kind in mms.MESH_KINDS:
            runs = [RESULTS[(kind, n, axi, order, lim)] for n in levels]
            fine_pair = [math.log(np.array(runs[-2]["L2"])[k] / np.array(runs[-1]["L2"])[k])
                         / math.log(runs[-2]["h"] / runs[-1]["h"]) for k in range(4)]
            measured[prefix + kind.replace(" ", "_")] = min(fine_pair)
    (HERE / ("last_study_quick.json" if is_quick() else "last_study.json")).write_text(json.dumps(
        {"levels": list(_levels()), "runs": {"|".join(map(str, k)): v for k, v in RESULTS.items()}}, indent=1))
    return measured


def study():
    rows = []
    for prefix, axi, order, lim in VARIANTS:
        levels = _levels(order, lim)
        for kind in mms.MESH_KINDS:
            runs = [RESULTS[(kind, n, axi, order, lim)] for n in levels]
            h = [r["h"] for r in runs]
            orders = {norm: [gci.observed_order(h, [r[norm][k] for r in runs])[-1] for k in range(4)]
                      for norm in ("L1", "L2", "Linf")}
            g = gci.three_mesh(h[-1:-4:-1], [r["L2"][3] for r in runs[-1:-4:-1]])
            label = (("axisymmetric" if axi else "planar") + f", order {order}" + (", " + lim if lim != "None" else "")
                     + f" ({levels[0]}-{levels[-1]})")
            rows.append([label, kind, " / ".join(f"{e:.2e}" for e in runs[-1]["L2"]),
                         " / ".join(f"{p:.2f}" for p in orders["L1"]),
                         " / ".join(f"{p:.2f}" for p in orders["L2"]),
                         " / ".join(f"{p:.2f}" for p in orders["Linf"]),
                         f"{g.p:.2f}", f"{g.asymptotic_ratio:.2f}",
                         f"{sum(r['iterations'] for r in runs):,}", f"{sum(r['time'] for r in runs):.0f}"])
    return {"title": "Observed orders between the two finest meshes (cells per side in brackets)",
            "columns": ["Scheme", "Mesh", "L2 error finest (rho / u / v / p)", "Order L1", "Order L2",
                        "Order Linf", "GCI p (L2 of p)", "GCI asympt. ratio", "Iterations", "Time [s]"],
            "rows": rows,
            "notes": ["Orders listed per variable rho / u / v / p. Errors in SI units (kg/m³, m/s, m/s, Pa).",
                      "The GCI columns apply the three-mesh GCI procedure (aeroflowsim/gci.py) to the L2 error of p: "
                      "its observed order should match and the asymptotic ratio be near 1.",
                      "First order and the Venkatakrishnan limiter are reported for information (not pass/fail): "
                      "Finding (Prompt 7b): with Venkatakrishnan's limiter the order does NOT approach 2 on finer meshes; "
                      "on triangles and mixed meshes it falls towards 1. Its threshold eps² = (K h / L)³ scale² shrinks "
                      "faster than the cell-to-cell differences of a smooth field (h^1.5 against h), so the limiter "
                      "clips the smooth extrema more and more as the mesh is refined. Smooth flows on fine meshes "
                      "therefore keep full second order only with 'None' or a larger K; an order-preserving limiter "
                      "(e.g. Michalak and Ollivier-Gooch 2008) is in the gap register."]}

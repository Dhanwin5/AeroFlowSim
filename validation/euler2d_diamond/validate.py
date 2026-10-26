# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Diamond airfoil (t/c = 0.1) at Mach 2, alpha 0 and 2 deg, with the external_2d template, against
shock-expansion theory (aeroflowsim.gasdynamics.diamond_airfoil).

Rectangle domain 0.5 c upstream, 1 c downstream, 1.5 c above and below (full domain: the lifting case is not
symmetric), Gmsh triangles with wall cells of 0.01 c (quick set: 0.02 c). Template defaults otherwise; a short
first-order start as for the wedge. Face pressures are the mean wall pressure of each face's middle 60 %
(20 % to 80 % of the face length, away from the corners where the discrete waves are smeared over a few
cells). Cl and Cd are the template's own force coefficients (wall pressure fluxes).
"""

import math

import numpy as np

import aeroflowsim
from aeroflowsim.gasdynamics import diamond_airfoil
from validation.common import is_quick

CASE = "cases/external_2d"
BASE = {"shape": "Diamond airfoil", "diamond.thickness_ratio": 0.1, "domain_shape": "Rectangle", "upstream": 0.5,
        "downstream": 1.0, "height": 1.5, "half_domain": False, "mach": 2.0, "first_order_iterations": 200,
        "max_iter": 12000}
QUICK_RUN = {"max_iter": 5000}
# The residual stalls near 4e-3 in a few cells at the foot of the attached leading-edge shock (a limiter limit cycle,
# found with the residual field of aeroflowsim/post); Cl and Cd are steady to 1e-6 long before the iteration limit.
# The stall is a Prompt 8 item (implicit time stepping), see the gap register.
RUNS = {}


def _sizes():
    return {"surface_size": 0.02, "farfield_size": 0.08} if is_quick() else {"surface_size": 0.01, "farfield_size": 0.05}


def _faces(out):
    """Mean p/p_inf on the middle 60 % of each of the four faces."""
    mesh = out.mesh
    p = out.result.series["wall_p"]
    x, y = out.result.series["wall_x"], out.result.series["wall_y"]
    p_inf = out.params["p_inf"]
    alpha = math.radians(out.params["alpha"])
    # wall coordinates are in the body frame (the body is not rotated; the free stream is)
    res = {}
    for name, upper, front in (("upper_front", True, True), ("upper_rear", True, False),
                               ("lower_front", False, True), ("lower_rear", False, False)):
        side = (y > 0) if upper else (y < 0)
        part = (x < 0.5) if front else (x > 0.5)
        s = (x - (0.0 if front else 0.5)) / 0.5
        keep = side & part & (s > 0.2) & (s < 0.8)
        res[name] = float(np.mean(p[keep]) / p_inf)
    return res


def _run(alpha):
    if alpha not in RUNS:
        out = aeroflowsim.run_case(CASE, {**BASE, **_sizes(), "alpha": alpha, **(QUICK_RUN if is_quick() else {})})
        r = out.result
        RUNS[alpha] = {"faces": _faces(out), "Cl": r.key_numbers["Cl"][0], "Cd": r.key_numbers["Cd"][0],
                       "Cm": r.key_numbers["Cm"][0], "cells": out.mesh.n_cells, "iterations": r.iterations,
                       "converged": r.converged, "time": r.key_numbers["wall_time"][0]}
    return RUNS[alpha]


def measure():
    a0, a2 = _run(0.0), _run(2.0)
    out = {"Cd_alpha0": a0["Cd"], "Cl_alpha2": a2["Cl"], "Cd_alpha2": a2["Cd"]}
    out.update({f"p_{k}": v for k, v in a2["faces"].items()})
    return out


def study():
    rows = []
    for alpha, m in RUNS.items():
        theory = diamond_airfoil(2.0, 0.1, alpha, 1.4)
        rows.append([f"{alpha:g}", f"{m['cells']:,}", f"{m['iterations']:,}", "yes" if m["converged"] else "NO",
                     f"{m['time']:.0f}", f"{m['Cl']:.5f} ({theory['Cl']:.5f})", f"{m['Cd']:.5f} ({theory['Cd']:.5f})"]
                    + [f"{m['faces'][k]:.4f} ({theory['p'][k]:.4f})" for k in
                       ("upper_front", "upper_rear", "lower_front", "lower_rear")])
    return {"title": "Runs (theory in brackets)", "columns": ["alpha [deg]", "Cells", "Iterations", "Converged",
                                                              "Time [s]", "Cl", "Cd", "p/p_inf upper front",
                                                              "upper rear", "lower front", "lower rear"],
            "rows": rows,
            "notes": ["Shock-expansion theory is exact for the inviscid flow on the faces (attached shocks, simple "
                      "waves); Cl = 0 at alpha = 0 is not compared as a percentage (|Cl| is listed).",
                      "Wall size 0.02 c in the quick set, 0.01 c in the full set."]}

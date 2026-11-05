# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""N2 cube-sat nozzle, laminar, Cd and Isp loss versus throat Reynolds number (reference.toml)."""

import math

import aeroflowsim
from aeroflowsim.discovery import load_case
from aeroflowsim.parameters import defaults
from aeroflowsim.smart_rules import flow_scales

CASE = "cases/nozzle_axi"
ROWS = []


def run(p0, model):
    p = {"p0": p0, "p_back": 1000.0 * p0 / 5e5, "flow_model": model, "max_iter": 30000}
    out = aeroflowsim.run_case(CASE, p)
    k = out.result.key_numbers
    return k["discharge_coefficient"][0], k["Isp_vacuum"][0], out.result


def measure():
    case = load_case(CASE)
    base = defaults(case.parameters())
    cds, res = {}, {}
    for p0 in (1e5, 3.16e5, 1e6):
        q = dict(base, p0=p0)
        Re = flow_scales(case, q)["Re"]
        cd, isp, r = run(p0, "Laminar")
        _cd0, isp0, r0 = run(p0, "Euler")
        cds[p0], res[p0] = cd, Re
        ROWS.append([f"{p0 / 1e5:.3g}", f"{Re:.3g}", f"{cd:.4f}", f"{isp:.2f}", f"{isp0:.2f}",
                     f"{100 * (1 - isp / isp0):.2f}", f"{r.iterations:,} ({r.info.get('status')})",
                     f"{r.key_numbers.get('y_plus_max', (0,))[0]:.2f}"])
    s1 = (1 - cds[1e5]) * math.sqrt(res[1e5])
    s10 = (1 - cds[1e6]) * math.sqrt(res[1e6])
    rises = cds[1e5] < cds[3.16e5] < cds[1e6]
    return {"bl_scaling": s10 / s1, "cd_rises": 1.0 if rises else 0.0}


def study():
    return {"title": "Reynolds-number sweep (laminar; Isp loss against the Euler run on the same mesh)",
            "columns": ["p0 [bar]", "Re_t", "Cd", "Isp vac [s]", "Isp Euler [s]", "Isp loss [%]", "Iterations",
                        "y+ max"], "rows": ROWS, "notes": ["Throat Reynolds number from the sonic throat state, L = D_t."]}

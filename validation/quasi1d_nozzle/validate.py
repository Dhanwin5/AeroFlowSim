# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Quasi-1D nozzle validation: two runs of the default nozzle, in the units of reference.toml.

1. p_back = 1 kPa (default): fully supersonic divergent part -> exit state, mass flow, thrust.
2. p_back = 2.5 bar: a normal shock stands in the divergent part -> its position. The residual
   stalls near 1e-3 once the shock has settled (the limiter keeps switching at the shock, see the
   case README), so 30 000 iterations are enough, as in cases/quasi1d_nozzle/test_case.py.
"""

import aeroflowsim


def measure():
    supersonic = aeroflowsim.run_case("cases/quasi1d_nozzle").result.key_numbers
    shock = aeroflowsim.run_case("cases/quasi1d_nozzle", {"p_back": 2.5e5, "max_iter": 30000}).result.key_numbers
    return {
        "M_exit": supersonic["M_exit"][0],                                   # [-]
        "p_exit": supersonic["p_exit"][0] / 1e3,                             # [Pa] -> [kPa]
        "mdot": supersonic["mdot"][0] * 1e6,                                 # [kg/s] -> [mg/s]
        "F_vacuum": supersonic["F_vacuum"][0] * 1e3,                         # [N] -> [mN]
        "x_shock": (shock["x_shock"][0] - shock["x_throat"][0]) * 1e3,      # [m] -> [mm]
    }


# Mesh-refinement study (a first step towards a GCI tool): each mesh twice as fine as the one before.
STUDY_CELLS = (150, 300, 600, 1200)
STUDY_TOL = 1e-6        # 6 orders: on fine meshes the minmod limiter stalls the residual near 1e-7 at the
                        # throat (see the case README); the exit values are steady long before that


def study():
    """Exit Mach number and shock position on four meshes, with the change between meshes and the
    observed order of convergence p = ln(d1 / d2) / ln 2 of the last three exit Mach numbers."""
    import math
    from aeroflowsim.case import get_derived
    from aeroflowsim.discovery import load_case
    from aeroflowsim.parameters import defaults
    case = load_case("cases/quasi1d_nozzle")
    M_exact = get_derived(case, defaults(case.parameters()))["Design exit Mach number"][0]
    x_exact = 0.3208                                                    # [mm], reference.toml
    M, x, n_iter = [], [], []
    for n in STUDY_CELLS:
        run = aeroflowsim.run_case("cases/quasi1d_nozzle", {"n_cells": n, "tol": STUDY_TOL}).result
        M.append(run.key_numbers["M_exit"][0])
        n_iter.append(run.iterations)
        shock = aeroflowsim.run_case("cases/quasi1d_nozzle", {"n_cells": n, "p_back": 2.5e5,
                                                              "max_iter": 30000 * n // 300}).result.key_numbers
        x.append((shock["x_shock"][0] - shock["x_throat"][0]) * 1e3)    # [m] -> [mm]
    d1, d2 = M[-2] - M[-3], M[-1] - M[-2]
    order = math.log(abs(d1 / d2)) / math.log(2.0)
    M_richardson = M[-1] + d2 / (2.0**order - 1.0)
    rows = []
    for i, n in enumerate(STUDY_CELLS):
        change = "" if i == 0 else f"{M[i] - M[i - 1]:+.5f}"
        rows.append([f"{n}", f"{n_iter[i]}", f"{M[i]:.5f}", change, f"{100 * abs(M[i] / M_exact - 1):.3f}",
                     f"{x[i]:.4f}", f"{100 * abs(x[i] / x_exact - 1):.2f}"])
    return {"title": "Mesh-refinement study (cells doubled each time)",
            "columns": ["Cells", "Iterations", "Exit Mach", "Change", "Error vs theory %",
                        "Shock past throat [mm]", "Shock error %"],
            "rows": rows,
            "M_exit": M, "x_shock": x,
            "notes": [f"Exit Mach number: observed order of convergence p = {order:.2f} from the last three meshes; "
                      f"Richardson extrapolation {M_richardson:.5f}; isentropic theory {M_exact:.5f}.",
                      "Shock position: the captured shock is one or two cells wide, so its interpolated position "
                      "can move by up to a cell width between meshes; its error falls from "
                      f"{100 * abs(x[0] / x_exact - 1):.2f} % ({STUDY_CELLS[0]} cells) to "
                      f"{100 * abs(x[-1] / x_exact - 1):.2f} % ({STUDY_CELLS[-1]} cells).",
                      f"Supersonic runs converged to a residual drop of {STUDY_TOL:g}; shock runs use "
                      "30 000 iterations per 300 cells (their residual stalls near 1e-3, see the case README)."]}

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Laminar flat plate at Mach 2: adiabatic-wall (recovery) temperature and isothermal-wall heat flux (reference.toml)."""

import math

import numpy as np

from aeroflowsim.euler.wall_fields import wall_data
from validation.viscous_blasius.validate import RE_PER_M, TIMING, at_x, plate

M, T_INF, T_W, PR = 2.0, 200.0, 300.0, 0.72


def measure():
    x = 1e5 / RE_PER_M
    s, W, g, U, rho, mesh, st = plate(M, T_INF, None, constant_pr=True, key="M2 adiabatic")
    gam, cp = float(g.gamma(T_INF)), float(g.cp(T_INF))
    T_aw = T_INF * (1.0 + math.sqrt(PR) * 0.5 * (gam - 1.0) * M * M)
    Tw = at_x(wall_data(s, W), x, wall_data(s, W)["T_w"])
    s2, W2, *_ = plate(M, T_INF, {"thermal": "Isothermal", "T_wall": T_W}, constant_pr=True, key="M2 isothermal")
    q = at_x(wall_data(s2, W2), x, wall_data(s2, W2)["q_w"])
    T_star = T_INF * (0.5 + 0.039 * M * M + 0.5 * T_W / T_INF)
    C_star = (T_INF / T_star) * float(g.mu(T_star)) / float(g.mu(T_INF))   # rho* mu* / (rho mu), p constant
    cf = 0.664 * math.sqrt(C_star) / math.sqrt(1e5)
    q_ref = cf / (2.0 * PR ** (2.0 / 3.0)) * rho * U * cp * (T_aw - T_W)
    return {"recovery_temperature": Tw / T_aw, "heat_flux": q / q_ref}


def study():
    rows = [[k, f"{n:,}", f"{it:,}", f"{w:.0f}", st, f"{res:.1e}"] for k, v in TIMING.items()
            if isinstance(v, tuple) for (it, w, st, n, res) in [v]]
    return {"title": "Runs", "columns": ["Run", "Cells", "Iterations", "Time [s]", "Status", "Residual"], "rows": rows,
            "notes": []}

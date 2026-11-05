# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Laminar cylinder at Re = 40 through the external_2d template (reference.toml)."""

import numpy as np

import aeroflowsim
from aeroflowsim.gases import gas_model
from validation.common import is_quick

CASE = "cases/external_2d"
RUNS = []


def params(n_body, n_normal, first):
    g = gas_model("air")
    T, M, D = 300.0, 0.2, 1.0
    U = M * float(g.sound_speed(T))
    rho = 40.0 * float(g.mu(T)) / (U * D)
    return {"shape": "Circular cylinder", "mesh_type": "Structured C/O-grid", "grid_preset": "Custom",
            "grid_n_body": n_body, "grid_n_normal": n_normal, "grid_first_height": first, "grid_far_distance": 40.0,
            "grid_growth": 1.1, "flow_model": "Laminar", "mach": M, "p_inf": rho * g.R * T, "T_inf": T, "alpha": 0.0,
            "max_iter": 40000, "tol": 1e-6, "cfl": 5.0, "limiter": "None", "venkat_k": 5.0}


def run(name, n_body, n_normal, first):
    out = aeroflowsim.run_case(CASE, params(n_body, n_normal, first))
    res = out.result
    mesh = out.mesh
    cc = mesh.cell_centres
    u = res.fields["u"].values
    # wake centre line: the cells nearest y = 0 behind the cylinder (x > D), u averaged over the two sides
    behind = np.flatnonzero((cc[:, 0] > 1.0) & (np.abs(cc[:, 1]) < 0.05))
    xs = np.unique(np.round(cc[behind, 0], 9))
    L = float("nan")
    prev = None
    for x0 in np.sort(xs):
        near = behind[np.abs(cc[behind, 0] - x0) < 1e-9]
        if len(near):
            uc = float(np.mean(u[near[np.argsort(np.abs(cc[near, 1]))[:2]]]))
            if uc > 0.0 and prev is not None:
                L = prev[0] + (x0 - prev[0]) * (-prev[1]) / (uc - prev[1]) - 1.0     # linear: u = 0
                break
            prev = (x0, uc)
    cd = float(res.key_numbers["Cd"][0])
    RUNS.append([name, f"{mesh.n_cells:,}", f"{res.iterations:,}", res.info.get("status", ""),
                 f"{res.residuals[-1]:.1e}" if res.residuals else "-", f"{cd:.4f}", f"{L:.3f}",
                 f"{res.key_numbers['Cd_friction'][0]:.4f}", f"{res.info.get('wall_time_s', 0):.0f}"])
    return res, cd, L


def measure():
    med, cd_m, _ = run("Medium", 80 if is_quick() else 160, 40 if is_quick() else 80, 0.004 if is_quick() else 0.002)
    if is_quick():
        return {"L_over_D": float("nan"), "Cd": cd_m, "converged": float(med.converged), "cd_grid": 1.0}
    fine, cd_f, L_f = run("Fine", 320, 160, 0.001)
    return {"L_over_D": L_f, "Cd": cd_f, "converged": float(med.converged), "cd_grid": cd_m / cd_f}


def study():
    return {"title": "Runs", "columns": ["Grid", "Cells", "Iterations", "Status", "Residual", "Cd", "L/D (approx.)",
                                         "Cd friction", "Time [s]"], "rows": RUNS,
            "notes": ["L/D: u = 0 on the wake centre line, linear between cell centres."]}

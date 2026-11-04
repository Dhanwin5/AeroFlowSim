# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The default N2 nozzle in 2D axisymmetric (nozzle_axi) and in 3D (the same structured 2D mesh revolved by 90 deg into
a quarter with two symmetry planes, solved by external_3d's internal-flow path with the SAME numerics as the 2D run).
Full set: Medium 2D mesh (200 x 40), 16 segments per quarter (128,000 cells); quick set: Coarse (100 x 20), 8 segments.
The ratios 3D / 2D of the mass flow and the vacuum thrust are compared with 1; the polygon factor of the revolved
cross-sections is reported (it is part of the difference)."""

import math

from aeroflowsim.discovery import load_case
from aeroflowsim.parameters import defaults, validate
from aeroflowsim.simple_meshes import revolve_axisymmetric
from aeroflowsim.workspace_mesh import mesh_for
from validation.common import is_quick

RUNS = {}
SAME = ("cfl", "order", "limiter", "venkat_k", "freeze_limiter", "gradient", "time_scheme", "max_iter", "tol",
        "monitor_tol", "monitor_window", "carbuncle_fix", "first_order_iterations")


def measure():
    preset, n_theta = ("Coarse", 8) if is_quick() else ("Medium", 16)
    axi, ext = load_case("cases/nozzle_axi"), load_case("cases/external_3d")
    p2 = validate(axi.parameters(), {**defaults(axi.parameters()), "mesh_preset": preset, "max_iter": 30000})
    m2 = mesh_for(axi, p2)
    r2 = axi.run(p2, m2, lambda *a: False)
    m3 = revolve_axisymmetric(m2, 90.0, n_theta)
    bnd = {"inlet": {"type": "total_pressure_inlet", "p0": p2["p0"], "T0": p2["T0"]},
           "outlet": {"type": "pressure_outlet", "p": p2["p_back"]}}
    p3 = validate(ext.parameters(), {**defaults(ext.parameters()), "gas": p2["gas"], "boundaries": bnd,
                                     **{k: p2[k] for k in SAME}})
    r3 = ext.run(p3, m3, lambda *a: False)
    n = 4 * n_theta
    RUNS.update({"2D": (m2, r2), "3D": (m3, r3), "polygon": n / (2 * math.pi) * math.sin(2 * math.pi / n)})
    k2, k3 = r2.key_numbers, r3.key_numbers
    return {"mdot_ratio": k3["mdot"][0] / k2["mdot"][0], "thrust_ratio": k3["F_vacuum"][0] / k2["F_vacuum"][0]}


def study():
    rows = []
    for name in ("2D", "3D"):
        m, r = RUNS[name]
        k = r.key_numbers
        rows.append([name, f"{m.n_cells:,}", f"{r.iterations:,}", "yes" if r.converged else "NO",
                     f"{k['wall_time'][0]:.0f}", f"{1e6 * k['mdot'][0]:.4f}", f"{1e3 * k['F_vacuum'][0]:.4f}",
                     f"{1e3 * k['F_vacuum_wall'][0]:.4f}", f"{k['Isp_vacuum'][0]:.3f}"])
    return {"title": "Runs (same profile, same numerics)",
            "columns": ["Run", "Cells", "Iterations", "Converged", "Time [s]", "mdot [mg/s]", "F exit [mN]",
                        "F wall+inlet [mN]", "Isp [s]"],
            "rows": rows, "notes": [f"Polygon factor of the revolved cross-sections: {RUNS['polygon']:.5f} (the 3D "
                                    "throat area is this times the circle's)."]}

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The default N2 nozzle with the 2D axisymmetric Euler solver, on six meshes (structured and Gmsh triangles,
three sizes each), through the one engine (aeroflowsim.run_case) with the template's default numerics.

Nothing is tuned: every run uses the defaults of nozzle_axi (quasi-1D start, CFL 0.8, SSP-RK3, limiter frozen
after four orders, converged at a residual drop of six orders with thrust and exit mass flow settled), only
the mesh changes. The study table reports the numbers, the iterations and the wall-clock time of every run, the
quasi-1D template's own result for comparison, and the observed order of the Isp on the structured meshes.
"""

import math

import aeroflowsim

CASE = "cases/nozzle_axi"
MESHES = [  # (label, inputs)
    ("structured 50 x 10", {"mesh_preset": "Custom", "nx": 50, "nr": 10}),
    ("structured 100 x 20", {"mesh_preset": "Coarse"}),
    ("structured 200 x 40", {"mesh_preset": "Medium"}),
    ("triangles, wall 0.16 D_t", {"mesh_type": "Triangles (Gmsh)", "surface_size": 0.16, "max_size": 0.8}),
    ("triangles, wall 0.08 D_t", {"mesh_type": "Triangles (Gmsh)", "surface_size": 0.08, "max_size": 0.4}),
    ("triangles, wall 0.04 D_t", {"mesh_type": "Triangles (Gmsh)", "surface_size": 0.04, "max_size": 0.2}),
]
RUN = {"max_iter": 80000}       # an upper limit only: every run stops when it has converged
RUNS = {}


def _run(label, inputs):
    if label not in RUNS:
        out = aeroflowsim.run_case(CASE, {**inputs, **RUN})
        RUNS[label] = (out.mesh.n_cells, out.result)
    return RUNS[label]


def measure():
    for label, inputs in MESHES:
        _run(label, inputs)
    finest = RUNS["structured 200 x 40"][1].key_numbers
    triangles = RUNS["triangles, wall 0.04 D_t"][1].key_numbers
    return {
        "mass_balance": finest["mdot_exit"][0] / finest["mdot_inlet"][0],
        "thrust_two_ways": finest["F_vacuum_wall"][0] / finest["F_vacuum"][0],
        "Isp_vacuum": finest["Isp_vacuum"][0],
        "Isp_vacuum_triangles": triangles["Isp_vacuum"][0],
    }


def study():
    rows = []
    for label, _inputs in MESHES:
        cells, r = RUNS[label]
        k = r.key_numbers
        rows.append([label, f"{cells:,}", f"{r.iterations:,}", "yes" if r.converged else "NO",
                     f"{k['wall_time'][0]:.0f}", f"{1e6 * k['mdot'][0]:.4f}", f"{k['discharge_coefficient'][0]:.4f}",
                     f"{1e3 * k['F_vacuum'][0]:.4f}", f"{1e3 * k['F_vacuum_wall'][0]:.4f}",
                     f"{k['Isp_vacuum'][0]:.3f}", f"{k['Isp_2D_over_quasi1D'][0]:.4f}",
                     f"{100 * (1 - k['p0_exit'][0] / 5e5):.3f}"])
    quasi = aeroflowsim.run_case("cases/quasi1d_nozzle").result.key_numbers
    isp = [RUNS[label][1].key_numbers["Isp_vacuum"][0] for label, _ in MESHES[:3]]
    notes = [f"Quasi-1D template (cases/quasi1d_nozzle, defaults): vacuum Isp {quasi['Isp_vacuum'][0]:.3f} s, mass flow "
             f"{1e6 * quasi['mdot'][0]:.4f} mg/s; ideal quasi-1D theory of the same wall {RUNS['structured 200 x 40'][1].key_numbers['Isp_quasi1D'][0]:.3f} s.",
             "Conical divergence estimate: 72.53 s x (1 + cos 15 deg)/2 = 71.29 s (point-source flow).",
             "Cd = mass flow / ideal quasi-1D choked mass flow of the same throat; the throat is sharp (Rcu = Rcd = 0), "
             "so the sonic line is curved and the 2D nozzle passes less than 1D theory.",
             "p0 loss: drop of the mass-flux-weighted exit total pressure below the inlet p0 = 5 bar (numerical "
             "entropy; an isentropic nozzle loses nothing). It falls as the mesh is refined.",
             "Wall-clock times: plain NumPy on one core (Numba and implicit time stepping follow in Prompt 8)."]
    if isp[2] != isp[1] and (isp[1] - isp[0]) / (isp[2] - isp[1]) > 0:
        p = math.log(abs((isp[1] - isp[0]) / (isp[2] - isp[1]))) / math.log(2.0)
        richardson = isp[2] + (isp[2] - isp[1]) / (2.0**p - 1.0)
        notes.append(f"Structured meshes (refinement ratio 2): observed order of the Isp {p:.2f}, Richardson "
                     f"extrapolation {richardson:.3f} s.")
    return {"title": "Mesh study", "columns": ["Mesh", "Cells", "Iterations", "Converged", "Time [s]",
                                               "Mass flow [mg/s]", "Cd", "F exit [mN]", "F wall [mN]", "Isp [s]",
                                               "Isp / Isp 1D", "p0 loss [%]"],
            "rows": rows, "notes": notes, "Isp": isp}

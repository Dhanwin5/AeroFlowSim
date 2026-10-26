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

import aeroflowsim
from aeroflowsim import gci
from validation.common import is_quick

CASE = "cases/nozzle_axi"
MESHES = [  # (label, inputs)
    ("structured 50 x 10", {"mesh_preset": "Custom", "nx": 50, "nr": 10}),
    ("structured 100 x 20", {"mesh_preset": "Coarse"}),
    ("structured 200 x 40", {"mesh_preset": "Medium"}),
    ("triangles, wall 0.16 D_t", {"mesh_type": "Triangles (Gmsh)", "surface_size": 0.16, "max_size": 0.8}),
    ("triangles, wall 0.08 D_t", {"mesh_type": "Triangles (Gmsh)", "surface_size": 0.08, "max_size": 0.4}),
    ("triangles, wall 0.04 D_t", {"mesh_type": "Triangles (Gmsh)", "surface_size": 0.04, "max_size": 0.2}),
]
ROUNDED = {"Rcu_ratio": 1.5, "Rcd_ratio": 0.4}     # rounded throat: upstream / downstream radius of curvature / r_t
ROUNDED_MESHES = [
    ("rounded throat, structured 100 x 20", {"mesh_preset": "Coarse", **ROUNDED}),
    ("rounded throat, structured 200 x 40", {"mesh_preset": "Medium", **ROUNDED}),
]
QUICK_MESHES = [MESHES[0], MESHES[3], ("rounded throat, structured 50 x 10",
                                       {"mesh_preset": "Custom", "nx": 50, "nr": 10, **ROUNDED})]
RUN = {"max_iter": 80000}       # an upper limit only: every run stops when it has converged
TRIANGLE_RUN = {"max_iter": 30000}   # triangle meshes stall near a residual of 1e-4 (sharp throat corner, see the
                                     # notes): a shorter budget; their monitors have settled long before
RUNS = {}


def _run(label, inputs):
    if label not in RUNS:
        budget = TRIANGLE_RUN if inputs.get("mesh_type", "").startswith("Triangles") else RUN
        out = aeroflowsim.run_case(CASE, {**inputs, **budget})
        RUNS[label] = (out.mesh.n_cells, out.result)
    return RUNS[label]


def _meshes():
    return QUICK_MESHES if is_quick() else MESHES + ROUNDED_MESHES


def measure():
    for label, inputs in _meshes():
        _run(label, inputs)
    if is_quick():
        finest = RUNS["structured 50 x 10"][1].key_numbers
        triangles = RUNS["triangles, wall 0.16 D_t"][1].key_numbers
    else:
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
    for label, _inputs in _meshes():
        cells, r = RUNS[label]
        k = r.key_numbers
        rows.append([label, f"{cells:,}", f"{r.iterations:,}", "yes" if r.converged else "NO",
                     f"{k['wall_time'][0]:.0f}", f"{1e6 * k['mdot'][0]:.4f}", f"{k['discharge_coefficient'][0]:.4f}",
                     f"{1e3 * k['F_vacuum'][0]:.4f}", f"{1e3 * k['F_vacuum_wall'][0]:.4f}",
                     f"{k['Isp_vacuum'][0]:.3f}", f"{k['Isp_2D_over_quasi1D'][0]:.4f}",
                     f"{100 * (1 - k['p0_exit'][0] / 5e5):.3f}"])
    quasi = aeroflowsim.run_case("cases/quasi1d_nozzle").result.key_numbers
    if is_quick():
        return {"title": "Mesh study (quick set: coarse meshes only)", "columns": COLUMNS, "rows": rows,
                "notes": ["Quick set: the coarsest structured and triangle meshes and the coarse rounded-throat mesh."],
                "Isp": []}
    isp = [RUNS[label][1].key_numbers["Isp_vacuum"][0] for label, _ in MESHES[:3]]
    notes = [f"Quasi-1D template (cases/quasi1d_nozzle, defaults): vacuum Isp {quasi['Isp_vacuum'][0]:.3f} s, mass flow "
             f"{1e6 * quasi['mdot'][0]:.4f} mg/s; ideal quasi-1D theory of the same wall {RUNS['structured 200 x 40'][1].key_numbers['Isp_quasi1D'][0]:.3f} s.",
             "Conical divergence estimate: 72.53 s x (1 + cos 15 deg)/2 = 71.29 s (point-source flow).",
             "Cd = mass flow / ideal quasi-1D choked mass flow of the same throat; the throat is sharp (Rcu = Rcd = 0), "
             "so the sonic line is curved and the 2D nozzle passes less than 1D theory.",
             "p0 loss: drop of the mass-flux-weighted exit total pressure below the inlet p0 = 5 bar (numerical "
             "entropy; an isentropic nozzle loses nothing). Most of it is made at the SHARP throat corner, a singular "
             "expansion point of the inviscid flow; it does not fall clearly on these meshes. With a rounded throat "
             "(Rcu/Rt = 1.5, Rcd/Rt = 0.4) the coarsest triangle mesh already gives about 1 %.",
             "Triangle meshes: the residual stalls near 1e-4 in a few cells at the sharp throat corner (also slow, "
             "but still falling, with a rounded throat), so they do not meet the convergence criterion; the thrust "
             "from both methods and the Isp have settled to about 0.1 %. Implicit time stepping (Prompt 8) is the "
             "planned cure (gap register).",
             "Wall-clock times: plain NumPy on one core (Numba and implicit time stepping follow in Prompt 8)."]
    try:
        g = gci.three_mesh((1.0, 2.0, 4.0), isp[::-1])          # cell size relative to the finest (ratio 2)
        notes.append(f"Structured meshes, Isp (GCI tool, aeroflowsim/gci.py): {g.summary('s')}.")
    except ValueError as exc:
        notes.append(f"Structured meshes, Isp: no GCI ({exc}).")
    sharp = [RUNS[label][1].key_numbers for label in ("structured 100 x 20", "structured 200 x 40")]
    round_ = [RUNS[label][1].key_numbers for label, _ in ROUNDED_MESHES]
    loss = lambda k: 100 * (1 - k["p0_exit"][0] / 5e5)
    notes.append("Sharp vs rounded throat (Rcu/Rt = 1.5, Rcd/Rt = 0.4), structured 100 x 20 and 200 x 40: p0 loss "
                 f"{loss(sharp[0]):.3f} / {loss(sharp[1]):.3f} % (sharp) and {loss(round_[0]):.3f} / {loss(round_[1]):.3f} % "
                 f"(rounded); Cd {sharp[0]['discharge_coefficient'][0]:.4f} / {sharp[1]['discharge_coefficient'][0]:.4f} "
                 f"(sharp) and {round_[0]['discharge_coefficient'][0]:.4f} / {round_[1]['discharge_coefficient'][0]:.4f} "
                 "(rounded).")
    smaller = loss(round_[1]) < loss(sharp[1])
    falls = loss(round_[1]) < loss(round_[0])
    if smaller and falls:
        notes.append("Finding: the rounded throat's loss is smaller and falls with refinement, so the loss of the sharp "
                     "throat is made at its corner (a singular point of the inviscid flow), not by the scheme in smooth flow.")
    else:
        notes.append(f"Finding: rounded-throat loss {'smaller' if smaller else 'NOT smaller'} than the sharp one and "
                     f"{'falling' if falls else 'NOT falling'} with refinement (see the gap register).")
    return {"title": "Mesh study", "columns": COLUMNS, "rows": rows, "notes": notes, "Isp": isp}


COLUMNS = ["Mesh", "Cells", "Iterations", "Converged", "Time [s]", "Mass flow [mg/s]", "Cd", "F exit [mN]",
           "F wall [mN]", "Isp [s]", "Isp / Isp 1D", "p0 loss [%]"]

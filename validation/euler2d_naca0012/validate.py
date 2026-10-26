# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""NACA 0012 in inviscid flow: transonic (Mach 0.8, alpha 1.25 deg) and subcritical (Mach 0.5, alpha 1.25 deg), with
the external_2d template in a C-domain made in the geometry workspace, on three meshes, with the GCI tool.

Geometry: the NACA 0012 equation with its ORIGINAL last coefficient (-0.1015), extended in chord until the thickness
closes and scaled to unit chord, as in the reference (Vassberg & Jameson 2010) - the file
naca0012_vassberg_jameson.dat, read by the shape library's coordinates-file shape.
Domain: C-domain (workspace Enclosure) of radius 30 c, 30 c downstream; characteristic far field without a point
vortex correction (as OVERFLOW and CFL3D without vortex in the reference). Gmsh triangles, wall cells of 0.01, 0.005
and 0.0025 c (refinement ratio 2); the quick set runs only the coarsest mesh.
The three-mesh GCI (aeroflowsim/gci.py) gives the extrapolated Cl and Cd, compared with the grid-converged values
of the reference. Prompt 8 speed is needed for the finer meshes of a proper study (see the gap register).
"""

from pathlib import Path

import aeroflowsim
from aeroflowsim import gci
from aeroflowsim.discovery import load_case
from aeroflowsim.geometry_model import template_document
from aeroflowsim.geometry_model.operations import Enclosure
from aeroflowsim.parameters import defaults, validate
from aeroflowsim.workspace_mesh import mesh_for
from validation.common import is_quick

HERE = Path(__file__).resolve().parent
CASE = "cases/external_2d"
LEVELS = {"wall 0.01 c": 0.01, "wall 0.005 c": 0.005, "wall 0.0025 c": 0.0025}
CONDITIONS = {"transonic": 0.8, "subcritical": 0.5}
RUNS = {}


def _levels():
    return dict(list(LEVELS.items())[:1]) if is_quick() else LEVELS


def _run(condition, label, size):
    key = (condition, label)
    if key not in RUNS:
        case = load_case(CASE)
        params = validate(case.parameters(), {
            **defaults(case.parameters()), "shape": "Custom coordinates file",
            "coordinates_file.file": str(HERE / "naca0012_vassberg_jameson.dat"), "mach": CONDITIONS[condition],
            "alpha": 1.25, "surface_size": size, "farfield_size": 2.0, "size_growth": 1.15, "max_iter": 60000})
        doc = template_document(case)
        doc.operations[1].suppressed = True                     # the template's own far field is replaced by
        doc.add(Enclosure(kind="c_domain", radius=30.0, downstream=30.0))   # a C-domain from the workspace
        mesh = mesh_for(case, params, doc)
        out = aeroflowsim.run_case(case, params, mesh=mesh)
        r = out.result
        RUNS[key] = {"cells": mesh.n_cells, "h": size, "Cl": r.key_numbers["Cl"][0], "Cd": r.key_numbers["Cd"][0],
                     "Cm": r.key_numbers["Cm"][0], "iterations": r.iterations, "converged": r.converged,
                     "time": r.key_numbers["wall_time"][0]}
    return RUNS[key]


def _extrapolated(condition, name):
    runs = [_run(condition, label, size) for label, size in _levels().items()]
    if len(runs) < 3:
        return runs[-1][name], None
    fine_to_coarse = runs[::-1]
    try:
        g = gci.three_mesh([r["cells"] ** -0.5 for r in fine_to_coarse], [r[name] for r in fine_to_coarse])
    except ValueError:
        return runs[-1][name], None
    if g.oscillatory or not (0.5 < g.p < 4.0):
        return runs[-1][name], g          # no trustworthy extrapolation: compare the finest mesh
    return g.extrapolated, g


def measure():
    return {"Cl_transonic": _extrapolated("transonic", "Cl")[0], "Cd_transonic": _extrapolated("transonic", "Cd")[0],
            "Cl_subcritical": _extrapolated("subcritical", "Cl")[0]}


def study():
    rows = []
    for (condition, label), m in RUNS.items():
        rows.append([f"Mach {CONDITIONS[condition]}", label, f"{m['cells']:,}", f"{m['iterations']:,}",
                     "yes" if m["converged"] else "NO", f"{m['time']:.0f}", f"{m['Cl']:.5f}", f"{m['Cd']:.6f}",
                     f"{m['Cm']:.5f}"])
    notes = ["Reference (Vassberg & Jameson 2010, Table 11, p. 1165): Mach 0.8, alpha 1.25 deg: continuum Cl 0.3482 "
             "(CFL3D) to 0.3562 (FLO82), Cd 0.02245 to 0.02268; Table 10: Mach 0.5, alpha 1.25 deg: Cl 0.17978 to "
             "0.18035, Cd -> 0 (FLO82 4.5e-8).",
             "Cm here is about the quarter chord (template convention); the reference's Cm is about the quarter chord as well."]
    for condition in CONDITIONS:
        for name in ("Cl", "Cd"):
            if len(_levels()) == 3:
                value, g = _extrapolated(condition, name)
                if g is not None:
                    notes.append(f"Mach {CONDITIONS[condition]}, {name}: GCI {g.summary()}.")
    subsonic_cd = [RUNS[("subcritical", label)]["Cd"] for label in _levels()]
    notes.append("Mach 0.5 drag on the three meshes: " + ", ".join(f"{cd:.6f}" for cd in subsonic_cd) +
                 " (inviscid subcritical flow has zero drag; it must fall with refinement).")
    return {"title": "Runs", "columns": ["Condition", "Mesh", "Cells", "Iterations", "Converged", "Time [s]", "Cl",
                                         "Cd", "Cm"], "rows": rows, "notes": notes, "subsonic_cd": subsonic_cd}

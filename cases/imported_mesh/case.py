# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Start from an existing mesh: a 2D / axisymmetric Euler run on a mesh file made elsewhere.

The mesh is read by aeroflowsim/mesh_io.py (Gmsh, SU2, CGNS, Fluent), its boundary names become patches whose types
come from the 'Boundary types' input (or from the names), and the flow is solved with the same Euler solver and boundary-
condition table as every template (aeroflowsim/euler/setup.py). There is no geometry to edit: the Geometry step only shows
the file inputs. Same engine, same results from the GUI, the command line and scripts. See README.md.
"""

from pathlib import Path

from aeroflowsim import mesh_io
from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.setup import external_problem, solve
from aeroflowsim.gases import gas_model

PROJECT_DIR = Path(__file__).resolve().parents[2]    # relative file names start here


def _path(params) -> Path:
    path = Path(params["mesh_file"])
    return path if path.is_absolute() else PROJECT_DIR / path


def _raw(params):
    return mesh_io.read_mesh_file(_path(params))


def build_mesh(params):
    """The mesh of the file: units to metres, boundary names to patches (patch names = the names in the file)."""
    return mesh_io.mesh_from_raw(_raw(params), params["length_unit"], params["body_type"] == "Axisymmetric",
                                 mesh_io.parse_tag_map(params["boundary_map"]))


def estimated_cells(params):
    """Number of cells of the file (read without building the mesh)."""
    return _raw(params).n_cells


def derived(params):
    """Read-only numbers under the inputs: what the file holds, its size, and the type each boundary name gets."""
    raw = _raw(params)
    mapping = mesh_io.parse_tag_map(params["boundary_map"])
    rows = {}
    for row in mesh_io.tag_table(raw):
        kind = mapping.get(row["name"]) or row["guess"] or "NOT SET: choose a type"
        rows[f"Boundary '{row['name']}'"] = (f"{kind} ({row['edges']} edges)", "")
    return {"File format": (raw.format, ""), "Cells": (f"{raw.n_cells:,}", ""),
            "Size in the file's unit": (mesh_io.size_text(raw), ""), **rows}


# ---- flow -------------------------------------------------------------------------------------------------------

def gas(params):
    return gas_model(params["gas"], base=PROJECT_DIR)


def reference_length(params):
    return params["reference_length"]


def boundary_defaults(params):
    """The condition each kind of boundary starts with: free stream at far fields and inlets, slip walls."""
    free_stream = {"mach": params["mach"], "p": params["p_inf"], "T": params["T_inf"], "flow_angle": params["alpha"]}
    return {"farfield": BoundaryCondition("far_field", free_stream), "wall": BoundaryCondition("slip_wall"),
            "symmetry": BoundaryCondition("symmetry"), "axis": BoundaryCondition("axis"),
            "inlet": BoundaryCondition("supersonic_inlet", free_stream),
            "outlet": BoundaryCondition("supersonic_outlet")}


def run(params, mesh, progress, restart=None):
    """Solve the steady Euler equations; Cl, Cd, Cm about (0, 0) with the reference length and area of the inputs."""
    problem = external_problem(params, mesh, gas(params), boundary_defaults(params), params["reference_area"],
                               params["reference_length"], (0.0, 0.0), restart)
    return solve(problem, params, mesh, progress)

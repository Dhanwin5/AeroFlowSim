# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Axisymmetric nozzle: 2D face-based mesh of the upper half of a converging-diverging nozzle.

Mesh only for now (schema.toml: solver = false); the 2D axisymmetric Euler solver follows in
Prompt 7 and will use the same mesh. Geometry from aeroflowsim/geometry.py (conical with a sharp or
rounded throat, or CSV); structured mesh from aeroflowsim/nozzle_mesh.py or triangle mesh from
aeroflowsim/gmsh_mesh.py (optional Gmsh); quality checks from aeroflowsim/checks.py. See README.md.
"""

import math
from pathlib import Path

from aeroflowsim.geometry import conical_nozzle, read_profile_csv
from aeroflowsim.nozzle_mesh import CLUSTER_STRENGTHS, PRESETS, Inflation, structured_nozzle_mesh

CASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CASE_DIR.parent.parent    # relative CSV paths start here
STRUCTURED = "Structured"               # options of the mesh_type input (schema.toml)
TRIANGLES = "Triangles (Gmsh)"
PARAMETRIC = "Parametric (conical)"     # options of the geometry_source input (schema.toml)
CUSTOM_CSV = "Custom profile (CSV)"
DEG = math.pi / 180.0   # one degree [rad]


def geometry(params):
    """The nozzle wall as a WallProfile [m]; ValueError with a 'what to fix' message if invalid."""
    if params["geometry_source"] == CUSTOM_CSV:
        path = Path(params["profile_csv"])
        if not path.is_absolute():
            path = PROJECT_DIR / path
        return read_profile_csv(path)
    return conical_nozzle(params["d_inlet"], params["L_inlet"], params["half_angle_conv"] * DEG,
                          params["d_throat"], params["half_angle_div"] * DEG, params["d_exit"],
                          params["Rcu_ratio"], params["Rcd_ratio"])


def mesh_size(params):
    """(cells along x, cells across) from the preset, or the typed numbers for "Custom"."""
    if params["mesh_preset"] == "Custom":
        return params["nx"], params["nr"]
    return PRESETS[params["mesh_preset"]]


def inflation(params):
    """The Inflation settings, or None when inflation is off."""
    if not params["inflation"]:
        return None
    return Inflation(params["first_layer_height"], params["n_layers"], params["growth_rate"])


def gmsh_settings(params, profile):
    """Gmsh settings: the relative sizes times the throat diameter."""
    from aeroflowsim.gmsh_mesh import GmshSettings     # (works without Gmsh installed)
    d_throat = 2.0 * profile.r_throat                   # [m]
    return GmshSettings(
        surface_size=params["surface_size"] * d_throat, max_size=params["max_size"] * d_throat,
        growth=params["size_growth"], edge_refinement=params["edge_refinement"],
        quads=params["cell_type"] != "Triangles", inflation=inflation(params),
        msh_path=CASE_DIR / "mesh" / "mesh.msh" if params["save_msh"] else None)


def workspace_settings(params):
    """Gmsh settings for a geometry edited in the geometry workspace (sizes x the throat diameter input)."""
    return gmsh_settings(params, geometry(params))


def build_mesh(params):
    """Mesh from the axis (r = 0) to the wall, inlet to exit (a face-based Mesh): structured or Gmsh."""
    profile = geometry(params)
    if params["mesh_type"] == TRIANGLES:
        from aeroflowsim.gmsh_mesh import nozzle_mesh
        return nozzle_mesh(profile, gmsh_settings(params, profile))
    nx, nr = mesh_size(params)
    delta = CLUSTER_STRENGTHS[params["clustering_strength"]] if params["throat_clustering"] else 0.0
    return structured_nozzle_mesh(profile, nx, nr, delta, inflation(params))


def estimated_cells(params):
    """Number of cells (exact for the structured mesh, a quick estimate for Gmsh)."""
    if params["mesh_type"] == TRIANGLES:
        from aeroflowsim.gmsh_mesh import estimate_nozzle_cells
        profile = geometry(params)
        return estimate_nozzle_cells(profile, gmsh_settings(params, profile))
    nx, nr = mesh_size(params)
    return nx * nr


def derived(params):
    """Read-only numbers shown under the inputs: mesh size, cell sizes and total inflation thickness."""
    if params["mesh_type"] == TRIANGLES:
        profile = geometry(params)
        settings = gmsh_settings(params, profile)
        numbers = {"Estimated cells": (f"about {estimated_cells(params):,}", ""),
                   "Wall cell size": (settings.surface_size, "m"),
                   "Largest cell size": (settings.max_size, "m")}
    else:
        nx, nr = mesh_size(params)
        numbers = {"Cells (along x × across)": (f"{nx} × {nr} = {nx * nr:,}", "")}
    layers = inflation(params)
    if layers is not None:
        numbers["Total inflation thickness"] = (layers.thickness, "m")
    return numbers

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Axisymmetric nozzle: 2D face-based mesh of the upper half of a converging-diverging nozzle.

Mesh only for now (schema.toml: solver = false); the 2D axisymmetric Euler solver follows in
Prompt 7 and will use the same mesh. Geometry from aeroflowsim/geometry.py (conical or CSV), mesh
from aeroflowsim/nozzle_mesh.py, quality checks from aeroflowsim/checks.py. See README.md.
"""

import math
from pathlib import Path

from aeroflowsim.geometry import conical_nozzle, read_profile_csv
from aeroflowsim.nozzle_mesh import CLUSTER_STRENGTHS, PRESETS, Inflation, structured_nozzle_mesh

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent   # relative CSV paths start here
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
                          params["d_throat"], params["half_angle_div"] * DEG, params["d_exit"])


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


def build_mesh(params):
    """Structured quad mesh from the axis (r = 0) to the wall, inlet to exit (a face-based Mesh)."""
    nx, nr = mesh_size(params)
    delta = CLUSTER_STRENGTHS[params["clustering_strength"]] if params["throat_clustering"] else 0.0
    return structured_nozzle_mesh(geometry(params), nx, nr, delta, inflation(params))


def derived(params):
    """Read-only numbers shown under the inputs: the mesh size and the total inflation thickness."""
    nx, nr = mesh_size(params)
    numbers = {"Cells (along x × across)": (f"{nx} × {nr} = {nx * nr:,}", "")}
    layers = inflation(params)
    if layers is not None:
        numbers["Total inflation thickness"] = (layers.thickness, "m")
    return numbers

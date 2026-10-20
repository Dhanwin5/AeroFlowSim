# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Custom 2D geometry: any planar or axisymmetric geometry made in the geometry workspace, meshed.

Mesh only for now (schema.toml: solver = false). The geometry has no inputs here: it is the
project's workspace history (Geometry step: import DXF / STEP / IGES / CSV / .dat, draw, enclosure,
named boundaries, refinement regions), meshed by aeroflowsim/workspace_mesh.py with the settings
below. Cell sizes are multiples of the geometry's reference length (BuiltGeometry.reference_length).
See README.md.
"""

from aeroflowsim.gmsh_mesh import GmshSettings
from aeroflowsim.nozzle_mesh import Inflation


def workspace_settings(params, built):
    """Gmsh settings in metres: the relative sizes times the geometry's reference length L."""
    L = built.reference_length()                       # [m]
    layers = None
    if params["inflation"]:
        layers = Inflation(params["first_layer_height"] * L, params["n_layers"], params["growth_rate"])
    return GmshSettings(surface_size=params["surface_size"] * L, max_size=params["max_size"] * L,
                        growth=params["size_growth"], edge_refinement=params["edge_refinement"],
                        quads=params["cell_type"] != "Triangles", inflation=layers)


def build_mesh(params):
    """Called only when the workspace is still empty (an edited geometry is meshed by workspace_mesh)."""
    raise ValueError("There is no geometry yet: import a file or draw one in the Geometry step, then name its "
                     "boundaries.")

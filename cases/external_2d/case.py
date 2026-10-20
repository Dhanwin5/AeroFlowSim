# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Body in a free stream: mesh of the flow around a shape from the shape library.

Mesh only for now (schema.toml: solver = false); the 2D / axisymmetric Euler solver follows in
Prompt 7 and will use the same mesh. The shape comes from aeroflowsim/shapes/ (the Shape dropdown
is added automatically), the mesh from aeroflowsim/gmsh_mesh.py (needs the optional Gmsh).
All lengths in the inputs are multiples of the shape's reference length. See README.md.
"""

from pathlib import Path

from aeroflowsim.gmsh_mesh import Domain, GmshSettings, estimate_external_cells, external_mesh
from aeroflowsim.nozzle_mesh import Inflation
from aeroflowsim.shapes import make_profile

CASE_DIR = Path(__file__).resolve().parent


def geometry(params):
    """The body outline (a ShapeProfile) for the chosen shape and its inputs."""
    return make_profile(params)


def domain(params, profile):
    """The far-field boundary, in metres."""
    L = profile.reference_length    # [m]
    return Domain(shape=params["domain_shape"], radius=params["domain_radius"] * L,
                  upstream=params["upstream"] * L, downstream=params["downstream"] * L,
                  height=params["height"] * L, half=params["half_domain"])


def settings(params, profile):
    """Gmsh settings, in metres."""
    L = profile.reference_length    # [m]
    layers = None
    if params["inflation"]:
        layers = Inflation(params["first_layer_height"] * L, params["n_layers"], params["growth_rate"])
    return GmshSettings(surface_size=params["surface_size"] * L, max_size=params["farfield_size"] * L,
                        growth=params["size_growth"], edge_refinement=params["edge_refinement"],
                        quads=params["cell_type"] != "Triangles", inflation=layers,
                        msh_path=CASE_DIR / "mesh" / "mesh.msh" if params["save_msh"] else None)


def workspace_settings(params):
    """Gmsh settings for a geometry edited in the geometry workspace (sizes x the shape's reference length)."""
    return settings(params, geometry(params))


def build_mesh(params):
    """Gmsh mesh of the fluid around the body (patches wall, farfield, and symmetry or axis)."""
    profile = geometry(params)
    return external_mesh(profile, domain(params, profile), settings(params, profile))


def estimated_cells(params):
    """Quick estimate of the number of cells (no Gmsh run)."""
    profile = geometry(params)
    return estimate_external_cells(profile, domain(params, profile), settings(params, profile))


def derived(params):
    """Read-only numbers shown under the inputs."""
    profile = geometry(params)
    s = settings(params, profile)
    numbers = {
        "Estimated cells": (f"about {estimated_cells(params):,}", ""),
        "Reference length": (profile.reference_length, "m"),
        "Reference area": (profile.reference_area, "m²"),
        "Surface cell size": (s.surface_size, "m"),
    }
    if s.inflation is not None:
        numbers["Total inflation thickness"] = (s.inflation.thickness, "m")
    return numbers

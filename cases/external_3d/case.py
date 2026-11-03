# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Body in free stream, 3D (mesh only): a body with its axis along x inside a far field, tetrahedra + prism layers.

The geometry is a 3D workspace document (aeroflowsim/geometry_model/operations3d.py): the template's own geometry is
"Template body" (body_3d below) + "Template far field" (domain_3d); edited in the Geometry step it can be any STEP/IGES
solid or combination of bodies. Every mesh is made by aeroflowsim/workspace_mesh3d.py (also the template's own: the
same mesher, edited or not), with the sizes of workspace_settings_3d. There is no run() yet (schema.toml solver = false).
"""

from pathlib import Path
from types import SimpleNamespace

from aeroflowsim.gases import gas_model
from aeroflowsim.geometry_model import ReplayContext, replay, template_document
from aeroflowsim.geometry_model.operations3d import Box, Cone, Cylinder, Enclosure3D, Sphere
from aeroflowsim.nozzle_mesh import Inflation
from aeroflowsim.workspace_mesh3d import MeshSettings3D, estimate_cells_3d, mesh_3d

CASE_DIR = Path(__file__).parent
PROJECT_DIR = CASE_DIR.parent.parent    # relative custom-gas paths start here


def _this():
    """This template as the replay sees it (the functions the template operations call)."""
    return SimpleNamespace(body_3d=body_3d, domain_3d=domain_3d, workspace_settings_3d=workspace_settings_3d)


# ---- geometry -----------------------------------------------------------------------------------

def body_3d(params):
    """The template's body as one 3D operation (its faces get the id of the Template body step)."""
    d, length = params["diameter"], params.get("length", params["diameter"])      # [m]
    shape = params["body_shape"]
    if shape == "Sphere":
        return Sphere("", radius=0.5 * d)
    if shape == "Cylinder":
        return Cylinder("", ax=length, radius=0.5 * d)
    if shape == "Nose cone":                                  # tip upstream at x = 0, base at x = length
        return Cone("", x=length, ax=-length, r1=0.5 * d, r2=0.0)
    if shape == "Box":
        return Box("", x0=0.0, y0=-0.5 * d, z0=-0.5 * d, dx=length, dy=d, dz=d)
    raise ValueError(f"unknown body '{shape}'")


def domain_3d(params):
    """The far field as an Enclosure3D (sizes in reference lengths)."""
    return Enclosure3D("", kind=params["domain_shape"].lower(), upstream=params["upstream"],
                       downstream=params["downstream"], lateral=params["lateral"], radius=params["domain_radius"],
                       half=params["half_domain"])


def reference_length(params):
    """The largest extent of the template's body [m] (the enclosure and the mesh sizes are multiples of it)."""
    if params["body_shape"] == "Sphere":
        return params["diameter"]
    return max(params["diameter"], params["length"])


# ---- mesh ---------------------------------------------------------------------------------------

def workspace_settings_3d(params, built=None):
    """Mesh settings in metres: sizes x the reference length L of the geometry (its walls; the template's body when
    there is no geometry yet)."""
    L = built.reference_length() if built is not None and not built.empty else reference_length(params)   # [m]
    layers = None
    if params["inflation"]:
        layers = Inflation(params["first_layer_height"] * L, params["n_layers"], params["growth_rate"])
    return MeshSettings3D(surface_size=params["surface_size"] * L, max_size=params["farfield_size"] * L,
                          growth=params["size_growth"], curvature=params["curvature_cells"], inflation=layers)


def size_inputs(params, built=None):
    """Where the cell sizes are (for the suggestions): an input value = metres / scale."""
    L = built.reference_length() if built is not None and not built.empty else reference_length(params)
    return {"surface": ("surface_size", L), "max": ("farfield_size", L), "first_layer": ("first_layer_height", L)}


def build_mesh(params):
    """The template's own geometry (no workspace edits), meshed like any 3D workspace geometry."""
    return mesh_3d(template_document(_this()), ReplayContext(_this(), params),
                   lambda built: workspace_settings_3d(params, built))


def estimated_cells(params):
    """Quick estimate of the number of cells (the geometry is replayed, not meshed)."""
    built = replay(template_document(_this()), ReplayContext(_this(), params), triangulate=False)
    return estimate_cells_3d(built, workspace_settings_3d(params, built))


def derived(params):
    """Read-only numbers shown under the inputs."""
    s = workspace_settings_3d(params)
    numbers = {"Estimated cells": (f"about {estimated_cells(params):,}", ""),
               "Reference length": (reference_length(params), "m"), "Cell size on the body": (s.surface_size, "m"),
               "Largest cell size": (s.max_size, "m")}
    if s.inflation is not None:
        numbers["Total prism layer thickness"] = (s.inflation.thickness, "m")
    return numbers


# ---- flow (for the first-layer suggestion now; the 3D solver later) ---------------------------------

def gas(params):
    """The GasModel of the "gas" input."""
    return gas_model(params["gas"], base=PROJECT_DIR)

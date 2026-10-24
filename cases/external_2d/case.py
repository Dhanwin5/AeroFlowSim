# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Body in a free stream: steady 2D or axisymmetric Euler flow around a shape from the shape library.

The shape comes from aeroflowsim/shapes/ (the Shape dropdown is added automatically), the mesh from
aeroflowsim/gmsh_mesh.py, the flow from the Euler solver of aeroflowsim/euler/ (its inputs are added by
euler_solver = true in schema.toml). This file only says what is special about a body: the free stream
at the far field and the force coefficients with the shape's reference length and area
(aeroflowsim/euler/setup.py, external_problem). All lengths in the inputs are multiples of the shape's
reference length. See README.md.
"""

from pathlib import Path

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.setup import external_problem, solve
from aeroflowsim.gases import gas_model
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


def workspace_settings(params, built=None):
    """Gmsh settings for a geometry edited in the geometry workspace (sizes x the shape's reference length)."""
    return settings(params, geometry(params))


def size_inputs(params, built=None):
    """Where the cell sizes are (for the suggested-sizes smart rule): an input value = metres / scale."""
    L = geometry(params).reference_length                 # the shape's reference length [m]
    return {"surface": ("surface_size", L), "max": ("farfield_size", L), "edge_refinement": "edge_refinement",
            "first_layer": ("first_layer_height", L)}


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


# ---- flow -------------------------------------------------------------------------------------------

PROJECT_DIR = CASE_DIR.parent.parent    # relative custom-gas paths start here


def gas(params):
    """The GasModel of the "gas" input."""
    return gas_model(params["gas"], base=PROJECT_DIR)


def reference_length(params):
    """The shape's reference length [m] (chord, length or diameter): Reynolds number, Cm."""
    return geometry(params).reference_length


def boundary_defaults(params):
    """The condition each kind of boundary starts with: the free stream at the far field, slip walls."""
    free_stream = {"mach": params["mach"], "p": params["p_inf"], "T": params["T_inf"], "flow_angle": params["alpha"]}
    return {"farfield": BoundaryCondition("far_field", free_stream), "wall": BoundaryCondition("slip_wall"),
            "symmetry": BoundaryCondition("symmetry"), "axis": BoundaryCondition("axis")}


def run(params, mesh, progress, restart=None):
    """Solve the steady Euler equations around the body; Cl, Cd, Cm with the shape's reference values.

    Moments are taken about the quarter-length point on the axis (x_front + L/4, 0), nose-up positive.
    """
    profile = geometry(params)
    L = profile.reference_length
    x_ref = (float(profile.points[:, 0].min()) + 0.25 * L, 0.0)
    problem = external_problem(params, mesh, gas(params), boundary_defaults(params), profile.reference_area, L,
                               x_ref, restart)
    return solve(problem, params, mesh, progress)

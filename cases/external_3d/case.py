# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Body in free stream, 3D Euler: a body with its axis along x inside a far field, tetrahedra (+ optional prism layers).

The geometry is a 3D workspace document (aeroflowsim/geometry_model/operations3d.py): the template's own geometry is
"Template body" (body_3d below) + "Template far field" (domain_3d); edited in the Geometry step it can be any STEP/IGES
solid or combination of bodies. Every mesh is made by aeroflowsim/workspace_mesh3d.py (also the template's own: the
same mesher, edited or not), with the sizes of workspace_settings_3d. run() solves the steady 3D Euler equations
(aeroflowsim/euler/setup.py): far field + slip walls + symmetry planes, forces and coefficients of the whole body. A mesh
with an inlet boundary (a fluid nozzle from STEP or a revolve, faces named inlet / outlet) is an internal flow instead:
total-pressure inlet, pressure outlet, mass flow, thrust two ways and Isp (nozzle_problem).
"""

from pathlib import Path
from types import SimpleNamespace

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler import forces
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
    """The far field as an Enclosure3D (sizes in reference lengths). "quarter" is passed only when it is on, so the
    documents of projects made before it existed replay exactly as before."""
    extra = {"quarter": True} if params["half_domain"] and params.get("quarter_domain") else {}
    return Enclosure3D("", kind=params["domain_shape"].lower(), upstream=params["upstream"],
                       downstream=params["downstream"], lateral=params["lateral"], radius=params["domain_radius"],
                       half=params["half_domain"], **extra)


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
    if not params["reference_area"]:
        numbers["Reference area (frontal area of the template body)"] = (_template_frontal_area(params), "m²")
    return numbers


def _template_frontal_area(params):
    """Frontal area of the template's own body (the shadow on the y-z plane) [m²]; a STEP body's comes from its mesh."""
    import math
    d = params["diameter"]
    return d * d if params["body_shape"] == "Box" else math.pi * d * d / 4.0


# ---- flow ---------------------------------------------------------------------------------------

def gas(params):
    """The GasModel of the "gas" input."""
    return gas_model(params["gas"], base=PROJECT_DIR)


def boundary_defaults(params):
    """The condition each kind of boundary starts with: the free stream at the far field (and at a supersonic inlet),
    slip walls, symmetry planes; a nozzle's inlet and outlet: total-pressure inlet and pressure outlet (Setup table)."""
    free_stream = {"mach": params["mach"], "p": params["p_inf"], "T": params["T_inf"], "flow_angle": params["alpha"]}
    return {"farfield": BoundaryCondition("far_field", free_stream), "wall": BoundaryCondition("slip_wall"),
            "symmetry": BoundaryCondition("symmetry"),
            "inlet": BoundaryCondition("total_pressure_inlet"), "outlet": BoundaryCondition("pressure_outlet",
                                                                                            {"p": params["p_inf"]})}


FREE_STREAM_INPUTS = ("mach", "p_inf", "T_inf", "alpha", "beta")


def hidden_inputs(params, mesh):
    """An internal flow (the mesh has an inlet) does not use the free stream: hide its inputs (the inlet and outlet
    conditions are set in the boundary-condition table)."""
    return set(FREE_STREAM_INPUTS) if getattr(mesh, "patches", None) and is_internal(mesh) else set()


def is_internal(mesh) -> bool:
    """True for an internal flow (a nozzle or duct): the mesh has an inlet boundary."""
    return any(p.type == "inlet" for p in mesh.patches)


def reference_values(params, mesh):
    """(A_ref [m²], L_ref [m], moment point (x, y, z) [m], reason): the inputs, or 0 = from the walls (smart rule)."""
    from aeroflowsim.smart_rules import reference_values_3d
    walls = [p.name for p in mesh.patches if p.type == "wall"]
    planes = forces.symmetry_planes(mesh, [p.name for p in mesh.patches if p.type == "symmetry"])
    auto = reference_values_3d(mesh, walls, planes)
    area = params["reference_area"] or auto.area
    length = params["reference_length"] or auto.length
    point = (float(auto.moment_point[0]) - 0.25 * auto.length + 0.25 * length, 0.0, 0.0)
    return area, length, point, auto.reason


def run(params, mesh, progress, restart=None):
    """Solve the steady 3D Euler equations: a body in the free stream (forces of the whole body, symmetry planes
    completed), or, when the mesh has an inlet, the internal flow of a nozzle."""
    from aeroflowsim.euler.setup import external_problem, nozzle_problem_3d, solve
    if params.get("mesh_only"):
        raise ValueError("'Mesh only (do not solve)' is on (Setup step, Solver group): this project only makes the mesh. "
                         "Turn it off to run the 3D Euler solver, or export the mesh from the Mesh step.")
    if mesh.dim != 3:
        raise ValueError("This template solves 3D meshes only.")
    model = gas(params)
    if is_internal(mesh):
        problem = nozzle_problem_3d(params, mesh, model, boundary_defaults(params), restart)
    else:
        area, length, point, _reason = reference_values(params, mesh)
        problem = external_problem(params, mesh, model, boundary_defaults(params), area, length, point, restart)
    return solve(problem, params, mesh, progress)

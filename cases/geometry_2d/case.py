# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Custom 2D geometry: any planar or axisymmetric geometry made in the geometry workspace, meshed and solved.

The geometry has no inputs here: it is the project's workspace history (Geometry step: import DXF / STEP /
IGES / CSV / .dat, draw, enclosure, named boundaries, refinement regions), meshed by
aeroflowsim/workspace_mesh.py with the settings below. Cell sizes are multiples of the geometry's reference
length (BuiltGeometry.reference_length, stored in the mesh info). The flow is internal (a nozzle or duct:
aeroflowsim/euler/setup.py, nozzle_problem) or external (a body in a free stream: external_problem); the
boundary names of the Geometry step are the rows of the boundary-condition table. See README.md.
"""

import math
from pathlib import Path

import numpy as np

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.setup import external_problem, nozzle_problem, solve
from aeroflowsim.gases import gas_model
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


def size_inputs(params, built):
    """Where the cell sizes are (for the suggested-sizes smart rule): an input value = metres / scale."""
    L = built.reference_length()
    return {"surface": ("surface_size", L), "max": ("max_size", L), "edge_refinement": "edge_refinement",
            "first_layer": ("first_layer_height", L)}


def build_mesh(params):
    """Called only when the workspace is still empty (an edited geometry is meshed by workspace_mesh)."""
    raise ValueError("There is no geometry yet: import a file or draw one in the Geometry step, then name its "
                     "boundaries.")


# ---- flow -------------------------------------------------------------------------------------------

INTERNAL = "Internal (nozzle, duct)"
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent     # relative custom-gas paths start here


def gas(params):
    """The GasModel of the "gas" input."""
    return gas_model(params["gas"], base=PROJECT_DIR)


def reservoir_state(params):
    """Reservoir state for the gas checks (internal flow): (p0 [Pa], T0 [K])."""
    return params["p0"], params["T0"]


def boundary_defaults(params):
    """The condition each kind of boundary starts with (the Setup table can change any of them).

    Internal: inlets from the reservoir, outlets and far fields at the back (ambient) pressure.
    External: far fields at the free stream; an inlet or outlet named in a free-stream geometry gets the
    free stream as a supersonic inlet / the far-field condition.
    """
    common = {"wall": BoundaryCondition("slip_wall"), "symmetry": BoundaryCondition("symmetry"),
              "axis": BoundaryCondition("axis")}
    if params["flow_type"] == INTERNAL:
        back = BoundaryCondition("pressure_outlet", {"p": params["p_back"]})
        return {**common, "inlet": BoundaryCondition("total_pressure_inlet", {"p0": params["p0"], "T0": params["T0"]}),
                "outlet": back, "farfield": back}
    free = {"mach": params["mach"], "p": params["p_inf"], "T": params["T_inf"], "flow_angle": params["alpha"]}
    return {**common, "farfield": BoundaryCondition("far_field", free), "inlet": BoundaryCondition("far_field", free),
            "outlet": BoundaryCondition("far_field", free)}


def run(params, mesh, progress, restart=None):
    """Solve the steady Euler equations on the workspace mesh (internal or external flow)."""
    if params["flow_type"] == INTERNAL:
        problem = nozzle_problem(params, mesh, gas(params), boundary_defaults(params), restart)
        return solve(problem, params, mesh, progress)
    L = float(mesh.info.get("reference_length", 1.0))         # [m]
    walls = [p for p in mesh.patches if p.type == "wall"]
    nodes = np.unique(np.concatenate([mesh.face_nodes[p.start:p.start + p.count].ravel() for p in walls])) if walls \
        else np.zeros(0, dtype=int)
    nodes = nodes[nodes >= 0]
    xy = mesh.nodes[nodes, :2] if len(nodes) else np.zeros((1, 2))
    area = params["ref_area"]
    if area <= 0.0:
        area = math.pi * float(np.abs(xy[:, 1]).max()) ** 2 if mesh.axisymmetric else L * 1.0
    x_ref = (float(xy[:, 0].min()) + 0.25 * L, 0.0)
    problem = external_problem(params, mesh, gas(params), boundary_defaults(params), area, L, x_ref, restart)
    return solve(problem, params, mesh, progress)

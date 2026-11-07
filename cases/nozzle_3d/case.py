# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""3D nozzle, 3D Euler (full 3D release stage): the conical contour of the axisymmetric nozzle template revolved about
the x axis, a quarter (two symmetry planes, the default) or the full nozzle, with an optional plume region behind the
exit as a second cell zone.

Geometry: a 3D workspace document (aeroflowsim/geometry_model/operations3d.py). The template's own geometry is
"Template body" = Revolve(profile "nozzle") of the wall points from aeroflowsim/geometry.py (conical_nozzle, the same
function and inputs as cases/nozzle_axi), with faces inlet / wall / outlet and the symmetry planes of a 90-degree
revolve; with the plume on, "Template far field" = a revolved rectangle behind the exit (its boundaries "plume_outlet":
pressure outlets) joined to the nozzle by Fluid zones (Fragment; zones "nozzle" and "plume"). Edited in the Geometry
step it can be any STEP nozzle with faces named inlet / outlet. Every mesh is made by aeroflowsim/workspace_mesh3d.py.

Flow: aeroflowsim/euler/setup.py nozzle_problem_3d with the nozzle wall only ("wall") as the thrust wall: mass flow,
thrust two ways (exit momentum + pressure; and wall pressure + inlet momentum), Isp, Cf, discharge coefficient, all
for the WHOLE nozzle (x 4 for the quarter). With a plume region the exit-plane thrust is measured on the plume's outer
boundary, so the vacuum thrust to quote is the wall thrust F_vacuum_wall (see README.md).
"""

import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.setup import nozzle_problem_3d, solve
from aeroflowsim.gases import gas_model
from aeroflowsim.geometry import conical_nozzle
from aeroflowsim.geometry_model import ReplayContext, replay, template_document
from aeroflowsim.geometry_model.operations3d import FluidZones3D, Revolve
from aeroflowsim.nozzle_mesh import Inflation
from aeroflowsim.workspace_mesh3d import MeshSettings3D, estimate_cells_3d, mesh_3d

CASE_DIR = Path(__file__).parent
PROJECT_DIR = CASE_DIR.parent.parent    # relative custom-gas paths start here
DEG = math.pi / 180.0                   # one degree [rad]
PLUME = "plume_outlet"                  # boundary name of the plume region's outer faces


# ---- geometry -----------------------------------------------------------------------------------

def geometry(params):
    """The nozzle wall as a WallProfile [m] (the conical nozzle of cases/nozzle_axi)."""
    return conical_nozzle(params["d_inlet"], params["L_inlet"], params["half_angle_conv"] * DEG, params["d_throat"],
                          params["half_angle_div"] * DEG, params["d_exit"], params["Rcu_ratio"], params["Rcd_ratio"])


def _angle(params) -> float:
    return 90.0 if params["quarter_domain"] else 360.0


def body_3d(params):
    """The nozzle (the gas inside it) as one Revolve operation."""
    wall = geometry(params)
    points = np.column_stack([wall.x, wall.r]).tolist()
    return Revolve("", profile="nozzle", points=points, angle=_angle(params), role="fluid")


class PlumeRegion:
    """The plume region behind the exit as one template step: a revolved rectangle (outer faces plume_outlet,
    pressure outlets; the base annulus plume_base, a slip wall) joined to the nozzle by Fluid zones (Fragment), zones
    "nozzle" (the body of the Template body step, op1) and "plume" (this step). One step, so the geometry the user sees
    and edits in the Geometry step is the one that is meshed."""

    def __init__(self, revolve, nozzle_id="op1"):
        self.revolve, self.nozzle_id, self.id = revolve, nozzle_id, ""

    def apply(self, kernel, context):
        self.revolve.id = self.id
        self.revolve.apply(kernel, context)
        FluidZones3D(f"{self.id}:zones", bodies=[self.nozzle_id, self.id],
                     names={self.nozzle_id: "nozzle", self.id: "plume"}).apply(kernel, context)


def domain_3d(params):
    """The plume region (PlumeRegion), or None without a plume."""
    if not params["plume"]:
        return None
    wall = geometry(params)
    x_e, d_e = float(wall.x[-1]), 2.0 * float(wall.r[-1])
    length, radius = params["plume_length"] * d_e, params["plume_radius"] * d_e
    rect = [[x_e, 0.0], [x_e + length, 0.0], [x_e + length, radius], [x_e, radius]]
    names = [["", ""], [PLUME, "outlet"], [PLUME, "outlet"], ["plume_base", "wall"]]
    return PlumeRegion(Revolve("", profile="points", points=rect, angle=_angle(params), role="fluid", names=names))


def _template_document(params):
    """The template's history (Template body + Template far field = the plume region, when it is on)."""
    return template_document(_this())


def _this():
    """This template as the replay sees it (the functions the template operations call)."""
    return SimpleNamespace(body_3d=body_3d, domain_3d=domain_3d, workspace_settings_3d=workspace_settings_3d)


def reference_length(params):
    """The throat diameter [m]: the mesh sizes are multiples of it."""
    return 2.0 * geometry(params).r_throat


# ---- mesh ---------------------------------------------------------------------------------------

def workspace_settings_3d(params, built=None):
    """Mesh settings in metres: sizes x the throat diameter."""
    L = reference_length(params)
    layers = None
    if params["inflation"]:
        layers = Inflation(params["first_layer_height"] * L, params["n_layers"], params["growth_rate"])
    return MeshSettings3D(surface_size=params["surface_size"] * L, max_size=params["farfield_size"] * L,
                          growth=params["size_growth"], curvature=params["curvature_cells"], inflation=layers)


def size_inputs(params, built=None):
    """Where the cell sizes are (for the suggestions): an input value = metres / scale."""
    L = reference_length(params)
    return {"surface": ("surface_size", L), "max": ("farfield_size", L), "first_layer": ("first_layer_height", L)}


def build_mesh(params):
    """The template's own geometry (no workspace edits), meshed by the 3D workspace mesher."""
    return mesh_3d(_template_document(params), ReplayContext(_this(), params),
                   lambda built: workspace_settings_3d(params, built))


def estimated_cells(params):
    """Quick estimate of the number of cells (the geometry is replayed, not meshed)."""
    built = replay(_template_document(params), ReplayContext(_this(), params), triangulate=False)
    return estimate_cells_3d(built, workspace_settings_3d(params, built))


def derived(params):
    """Read-only numbers shown under the inputs."""
    wall = geometry(params)
    s = workspace_settings_3d(params)
    numbers = {"Estimated cells": (f"about {estimated_cells(params):,}", ""),
               "Area ratio A_exit / A_throat": ((wall.r[-1] / wall.r_throat) ** 2, "-"),
               "Nozzle length": (float(wall.x[-1] - wall.x[0]), "m"),
               "Cell size on the wall": (s.surface_size, "m"), "Largest cell size": (s.max_size, "m")}
    if s.inflation is not None:
        numbers["Total prism layer thickness"] = (s.inflation.thickness, "m")
    return numbers


# ---- flow ---------------------------------------------------------------------------------------

def gas(params):
    """The GasModel of the "gas" input."""
    return gas_model(params["gas"], base=PROJECT_DIR)


def reservoir_state(params):
    """Chamber (total) state checked by the gas validity checks: (p0 [Pa], T0 [K])."""
    return params["p0"], params["T0"]


def boundary_defaults(params):
    """Total-pressure inlet (chamber), pressure outlet at the back pressure (also the plume region's outer faces), slip
    walls, symmetry planes."""
    return {"inlet": BoundaryCondition("total_pressure_inlet", {"p0": params["p0"], "T0": params["T0"]}),
            "outlet": BoundaryCondition("pressure_outlet", {"p": params["p_back"]}),
            "wall": BoundaryCondition("slip_wall"), "symmetry": BoundaryCondition("symmetry")}


def run(params, mesh, progress, restart=None):
    """Solve the steady 3D nozzle flow; the thrust wall is the nozzle wall (patch "wall"). With a plume region the
    exit numbers (mass flow, exit thrust, Isp, Cf, discharge coefficient) are measured on the nozzle -> plume interface
    (exit_plane_numbers), not on the plume's outer boundary."""
    problem = nozzle_problem_3d(params, mesh, gas(params), boundary_defaults(params), restart, wall_names=["wall"])
    result = solve(problem, params, mesh, progress)
    if "nozzle" in mesh.cell_zones and "plume" in mesh.cell_zones:
        result.key_numbers.update(exit_plane_numbers(mesh, result, params["p_back"]))
    return result


def exit_plane_numbers(mesh, result, p_back) -> dict:
    """Mass flow and vacuum thrust through the exit plane = the interface between the zones "nozzle" and "plume", from
    the solver's own face fluxes there (series interface_flux: flux x area, owner -> neighbour), for the whole nozzle
    (x the symmetry factor). Vacuum exit thrust = the x-momentum flux int (rho u^2 + p) dA of the exit plane; the
    thrust at the back pressure subtracts p_back x exit area. Cf = F / (p0 A_throat), as nozzle_problem_3d."""
    from aeroflowsim.euler.setup import G0
    faces = np.asarray(result.series["interface_faces"], dtype=np.int64)
    flux = np.asarray(result.series["interface_flux"])
    index = mesh.cell_zone_index()
    sign = np.where(index[mesh.owner[faces]] == mesh.zone_names.index("nozzle"), 1.0, -1.0)   # nozzle -> plume
    k = result.key_numbers
    factor = k["symmetry_factor"][0]
    mdot = factor * float(np.sum(sign * flux[0]))                                          # [kg/s]
    thrust = factor * float(np.sum(sign * flux[1]))                                        # [N]
    area_x = factor * float(np.sum(sign * mesh.face_normals[faces, 0] * mesh.face_areas[faces]))   # [m²]
    wall = k["F_vacuum_wall"][0]
    out = {"mdot": (mdot, "kg/s"), "mdot_exit": (mdot, "kg/s"), "F_vacuum": (thrust, "N"),
           "F_at_p_back": (thrust - p_back * area_x, "N"),
           "discharge_coefficient": (mdot / k["mdot_1D"][0], "-"),
           "Isp_vacuum": (thrust / (mdot * G0) if mdot > 0 else 0.0, "s"),
           "Isp_vacuum_wall": (wall / (mdot * G0) if mdot > 0 else 0.0, "s"),
           "thrust_difference": (100.0 * abs(thrust - wall) / abs(thrust) if thrust else 0.0, "%")}
    if k.get("F_vacuum", (0.0,))[0] and "Cf_vacuum" in k:
        out["Cf_vacuum"] = (k["Cf_vacuum"][0] * thrust / k["F_vacuum"][0], "-")
    return out

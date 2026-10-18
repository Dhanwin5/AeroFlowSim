# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Gmsh mesh geometry validation: domain areas and volumes, wall length and the rounded-throat nozzle.

External bodies (cases/external_2d, default 1 m bodies in a far-field circle of radius 20 m), each on
the default mesh and with all cell sizes divided by 2 ("fine") and 4 ("finer"):
    cylinder wall length       sum of the wall patch face areas / 1 m depth               [m]
    domain area                sum of the planar cell volumes / 1 m depth                 [m²]
    cone volume                2 pi x sum of the axisymmetric cell volumes (half domain)  [m³]
Rounded-throat nozzle (cases/nozzle_axi, Rcu/Rt = 1.5, Rcd/Rt = 0.4): volume of revolution [mm³] of the
structured mesh (Coarse, Medium, Fine) and of the triangle mesh (default, fine, finer).
No solver is run. Needs Gmsh (pip install -e ".[mesh]").
"""

import math

from aeroflowsim.discovery import load_case
from aeroflowsim.mesh import DEPTH_2D
from aeroflowsim.parameters import defaults

LEVELS = {"default": 1.0, "fine": 2.0, "finer": 4.0}   # cell sizes divided by this


def measure():
    values = {}
    external = load_case("cases/external_2d")
    base = defaults(external.parameters())
    for level, k in LEVELS.items():
        p = {**base, "surface_size": base["surface_size"] / k, "farfield_size": base["farfield_size"] / k}
        mesh = external.build_mesh({**p, "shape": "Circular cylinder"})
        values[f"cylinder_wall_{level}"] = mesh.face_areas[mesh.patch("wall").faces].sum() / DEPTH_2D   # [m]
        values[f"cylinder_area_{level}"] = mesh.cell_volumes.sum() / DEPTH_2D                           # [m²]
        for shape, name in (("Diamond airfoil", "diamond"), ("Wedge", "wedge")):
            values[f"{name}_area_{level}"] = external.build_mesh({**p, "shape": shape}).cell_volumes.sum() / DEPTH_2D
        cone = external.build_mesh({**p, "shape": "Conical nose cone"})
        values[f"cone_volume_{level}"] = 2.0 * math.pi * cone.axi_cell_volumes.sum()                    # [m³]

    nozzle = load_case("cases/nozzle_axi")
    p = {**defaults(nozzle.parameters()), "Rcu_ratio": 1.5, "Rcd_ratio": 0.4}
    for preset in ("Coarse", "Medium", "Fine"):
        mesh = nozzle.build_mesh({**p, "mesh_preset": preset})
        values[f"nozzle_structured_{preset.lower()}"] = 2.0 * math.pi * mesh.axi_cell_volumes.sum() * 1e9   # [mm³]
    for level, k in LEVELS.items():
        mesh = nozzle.build_mesh({**p, "mesh_type": "Triangles (Gmsh)", "surface_size": p["surface_size"] / k,
                                  "max_size": p["max_size"] / k})
        values[f"nozzle_triangles_{level}"] = 2.0 * math.pi * mesh.axi_cell_volumes.sum() * 1e9           # [mm³]
    return values

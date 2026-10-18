# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Axisymmetric nozzle mesh validation: mesh geometry vs exact geometry, on three mesh sizes.

For the default conical nozzle of cases/nozzle_axi, built with the Coarse, Medium and Fine presets:
    planar area     sum of the planar cell volumes / 1 m depth                          [mm²]
    volume          2 pi x sum of the axisymmetric cell volumes (volume x r, per radian) [mm³]
    wall length     sum of the wall patch face areas / 1 m depth                         [mm]
No solver is run: this checks the mesh format's geometry (face areas, cell volumes, Pappus
axisymmetric metrics) and the generator's wall representation.
"""

import math

from aeroflowsim.discovery import load_case
from aeroflowsim.mesh import DEPTH_2D
from aeroflowsim.parameters import defaults


def measure():
    case = load_case("cases/nozzle_axi")
    values = {}
    for preset in ("Coarse", "Medium", "Fine"):
        mesh = case.build_mesh({**defaults(case.parameters()), "mesh_preset": preset})
        name = preset.lower()
        values[f"area_{name}"] = mesh.cell_volumes.sum() / DEPTH_2D * 1e6                    # [m²] -> [mm²]
        values[f"volume_{name}"] = 2.0 * math.pi * mesh.axi_cell_volumes.sum() * 1e9         # [m³] -> [mm³]
        values[f"wall_{name}"] = mesh.face_areas[mesh.patch("wall").faces].sum() / DEPTH_2D * 1e3   # [mm]
    return values

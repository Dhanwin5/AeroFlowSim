# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Geometry workspace validation: geometries made in the workspace, meshed, against exact values.

Three geometries built from workspace histories (aeroflowsim/geometry_model/) and meshed by
aeroflowsim/workspace_mesh.py, each on a default mesh and with the cell sizes divided by 2 and 4:
    circle minus cylinder    sketched far-field circle R = 20 m minus a sketched cylinder D = 1 m
                             (template geometry_2d): domain area [m²] and wall length [m]
    C-domain minus NACA 0012 NACA 0012 (chord 1 m, closed trailing edge) in a C-domain of radius 10 c,
                             15 c downstream (template external_2d, its own far field switched off):
                             domain area [m²]
    nozzle + plume region    the default conical N2 nozzle with a plume region 10 x 5 exit diameters
                             (template nozzle_axi, triangles): volume of revolution [mm³]
No solver is run.
"""

import math

from aeroflowsim.discovery import load_case
from aeroflowsim.geometry_model import GeometryDocument, ReplayContext, replay, template_document
from aeroflowsim.geometry_model.operations import BooleanOp, Enclosure, Sketch
from aeroflowsim.gui.geometry_logic import accept_suggestions
from aeroflowsim.mesh import DEPTH_2D
from aeroflowsim.parameters import defaults, validate
from aeroflowsim.workspace_mesh import mesh_for

LEVELS = {"default": 1.0, "fine": 2.0, "finer": 4.0}   # cell sizes divided by this


def _wall_length(mesh, patch):
    edges = mesh.face_nodes[mesh.patch(patch).faces, :2]
    return float(sum(math.dist(mesh.nodes[a, :2], mesh.nodes[b, :2]) for a, b in edges))


def measure():
    values = {}
    # 1. Circle minus cylinder, sketched in the Custom 2D geometry template.
    geo = load_case("cases/geometry_2d")
    doc = GeometryDocument([Sketch("op1", kind="circle", points=[[0.0, 0.0], [20.0, 0.0]], role="fluid"),
                            Sketch("op2", kind="circle", points=[[0.0, 0.0], [0.5, 0.0]], role="solid"),
                            BooleanOp("op3", kind="subtract", objects=["op1:face"], tools=["op2:face"])])
    base = validate(geo.parameters(), {**defaults(geo.parameters()), "surface_size": 0.005, "max_size": 2.0})
    doc = accept_suggestions(doc, replay(doc, ReplayContext(geo, base)))          # wall and farfield
    for level, k in LEVELS.items():
        p = {**base, "surface_size": base["surface_size"] / k, "max_size": base["max_size"] / k}
        mesh = mesh_for(geo, p, doc)
        values[f"cylinder_area_{level}"] = mesh.cell_volumes.sum() / DEPTH_2D                  # [m²]
        values[f"cylinder_wall_{level}"] = _wall_length(mesh, "wall")                          # [m]

    # 2. NACA 0012 in a C-domain (external_2d with its own far field switched off).
    ext = load_case("cases/external_2d")
    base = validate(ext.parameters(), {**defaults(ext.parameters()), "shape": "NACA 4-digit airfoil"})
    doc = template_document(ext)
    doc.operations[1].suppressed = True
    doc.add(Enclosure(kind="c_domain", radius=10.0, downstream=15.0))
    for level, k in LEVELS.items():
        p = {**base, "surface_size": base["surface_size"] / k, "farfield_size": base["farfield_size"] / k}
        values[f"naca_area_{level}"] = mesh_for(ext, p, doc).cell_volumes.sum() / DEPTH_2D     # [m²]

    # 3. Nozzle with a plume region (nozzle_axi, triangles).
    noz = load_case("cases/nozzle_axi")
    base = validate(noz.parameters(), {**defaults(noz.parameters()), "mesh_type": "Triangles (Gmsh)"})
    doc = template_document(noz)
    doc.add(Enclosure(kind="plume", plume_length=10.0, plume_height=5.0))
    for level, k in LEVELS.items():
        p = {**base, "surface_size": base["surface_size"] / k, "max_size": base["max_size"] / k}
        mesh = mesh_for(noz, p, doc)
        values[f"plume_volume_{level}"] = 2.0 * math.pi * mesh.axi_cell_volumes.sum() * 1e9    # [mm³]
    return values

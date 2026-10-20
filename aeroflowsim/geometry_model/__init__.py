# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The 2D geometry workspace model: a history of operations replayed in a CAD kernel (no GUI code).

    document.py    GeometryDocument (the history), replay(), template_document()
    operations.py  one class per operation (template shape, transform, enclosure, names, ...)
    kernel.py      the only code calling Gmsh's OpenCASCADE kernel; stable edge ids ("lineage")
    built.py       the replayed geometry as plain data: vertices, edges, faces, names, regions
    boundaries.py  boundary types, suggestions and checks
    picking.py     which vertex / edge / face is under a clicked point
"""

from aeroflowsim.geometry_model.built import FLUID, SOLID, Boundary, BuiltGeometry, Edge, Face, Region, Vertex
from aeroflowsim.geometry_model.document import (
    HISTORY_FILE, GeometryDocument, ReplayContext, has_workspace, replay, template_document)
from aeroflowsim.geometry_model.operations import OPERATIONS, Operation, operation_from_dict

__all__ = ["FLUID", "SOLID", "Boundary", "BuiltGeometry", "Edge", "Face", "Region", "Vertex", "HISTORY_FILE",
           "GeometryDocument", "ReplayContext", "has_workspace", "replay", "template_document", "OPERATIONS",
           "Operation", "operation_from_dict"]

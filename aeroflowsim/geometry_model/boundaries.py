# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Boundary names and types: the table of types, name rules, automatic suggestions and checks.

A boundary type says what kind of boundary condition the solver will use there (Prompt 7). The
table below is the ONE place that lists them: Prompt 7 adds rows such as "total-pressure inlet",
"mass-flow inlet", "pressure outlet", "supersonic inlet" and "supersonic outlet", and the GUI
dropdown, the colours and the checks pick them up automatically.
"""

import re

import numpy as np

from aeroflowsim.geometry_model.built import FLUID, SOLID, Boundary

# type: (label in the GUI, short description)
BOUNDARY_TYPES = {
    "inlet": ("Inlet", "flow enters here"),
    "outlet": ("Outlet", "flow leaves here"),
    "wall": ("Wall", "solid surface (slip wall for inviscid flow)"),
    "farfield": ("Far field", "free stream, far from the body"),
    "symmetry": ("Symmetry", "mirror plane (planar half domain)"),
    "axis": ("Axis", "axis of an axisymmetric geometry (y = 0)"),
}
NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,47}$")
AXIS_TOLERANCE = 1e-9       # an edge lies on y = 0 if |y| < this x geometry size [-]


def check_type(kind):
    if kind not in BOUNDARY_TYPES:
        raise ValueError(f"'{kind}' is not a boundary type; choose one of {', '.join(BOUNDARY_TYPES)}")


def check_name(name):
    """A patch name: starts with a letter; letters, digits, _ and - only (it is used in file names)."""
    if not NAME_PATTERN.match(str(name)):
        raise ValueError(f"'{name}' is not a valid boundary name: start with a letter and use only letters, "
                         "digits, _ and - (at most 48 characters)")


def on_axis(edge, size) -> bool:
    """True if the whole edge lies on y = 0."""
    return bool(np.all(np.abs(edge.points[:, 1]) <= AXIS_TOLERANCE * size))


def suggestions(built) -> dict:
    """{edge id: Boundary} suggested for the boundary edges that have no name yet.

    Rules (the user confirms or changes them):
      - an edge on y = 0 of an axisymmetric geometry -> axis;
      - an edge that came from a solid body (it is a piece of a solid face's edge) -> wall;
      - an edge on the outer loop of the fluid -> farfield when the fluid has holes (bodies),
        otherwise left unnamed (inlet / outlet / wall need the user's judgement);
      - an edge of a hole in the fluid (a body cut out) -> wall.
    """
    out = {}
    size = built.size
    outer, holes = set(), set()
    for face in built.faces_with_role(FLUID):
        if face.loops:
            outer.update(face.loops[0])
            for loop in face.loops[1:]:
                holes.update(loop)
    has_holes = bool(holes)
    for edge_id in built.boundary_edges():
        if edge_id in built.names:
            continue
        edge = built.edges[edge_id]
        if built.axisymmetric and on_axis(edge, size):
            out[edge_id] = Boundary("axis", "axis", origin="suggested")
        elif edge_id in holes:
            out[edge_id] = Boundary("wall", "wall", origin="suggested")
        elif edge_id in outer and has_holes:
            out[edge_id] = Boundary("farfield", "farfield", origin="suggested")
    return out


def boundary_problems(built) -> list:
    """[(level, text)] about boundary names: every boundary edge named, types consistent."""
    problems = []
    unnamed = [e for e in built.boundary_edges() if e not in built.names]
    if unnamed:
        problems.append(("error", f"{len(unnamed)} boundary edge(s) have no name; every boundary edge needs a name "
                                  "and a type before meshing (Name boundary)."))
    types = {}
    for edge_id in built.boundary_edges():
        b = built.names.get(edge_id)
        if b is not None:
            types.setdefault(b.name, set()).add(b.type)
    for name, kinds in types.items():
        if len(kinds) > 1:
            problems.append(("error", f"The boundary name '{name}' is used with different types "
                                      f"({', '.join(sorted(kinds))}); names must be unique."))
    if built.axisymmetric:
        size = built.size
        for edge_id in built.boundary_edges():
            b = built.names.get(edge_id)
            if b is not None and b.type == "axis" and not on_axis(built.edges[edge_id], size):
                problems.append(("error", f"'{b.name}' has type axis but does not lie on y = 0."))
    if not built.faces_with_role(FLUID) and built.faces_with_role(SOLID):
        problems.append(("error", "There is no fluid region yet: add an enclosure around the body, or mark a face as "
                                  "fluid."))
    return problems

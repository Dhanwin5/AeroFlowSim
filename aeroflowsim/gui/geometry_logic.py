# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The logic of the geometry workspace page, without any Qt (so it is tested without a window).

The page (gui/steps/geometry.py) only draws and forwards clicks; everything that decides
something lives here:
    FIELDS                 which settings of each operation the user can edit, and how they are shown
                           (lengths in mm in the GUI, metres inside)
    operation_for()        a new operation, pre-filled from what is selected (e.g. Fillet from a vertex)
    boundary_rows()        the Boundaries table
    rename_boundary(), set_boundary_type(), accept_suggestions()   edit the names (as history operations)
    points_of(), with_points()   the point table / dragged points of an operation
    selection_rows(), history_rows()   texts for the Properties panel and the History list
Every edit returns a NEW document; the window turns "old document -> new document" into an
undoable command.
"""

import math
from dataclasses import dataclass

import numpy as np

from aeroflowsim.geometry_model import FLUID, SOLID
from aeroflowsim.geometry_model.boundaries import BOUNDARY_TYPES, suggestions
from aeroflowsim.geometry_model.importers import UNITS
from aeroflowsim.geometry_model.operations import (
    TEMPLATE_TYPES, BooleanOp, Delete, Enclosure, Fillet, NameBoundary, Refinement, SetRole, Transform)

MM = 1e-3                   # one millimetre [m]: lengths are shown and typed in mm


@dataclass(frozen=True)
class Field:
    """One editable setting of an operation."""

    key: str
    label: str
    kind: str                       # "length" (m inside, mm shown), "number", "angle" (deg), "ratio" (x L),
                                    # "choice", "bool", "text"
    options: tuple = ()             # choices: (value, label) pairs
    show_if: tuple = None           # (other key, (values...)): shown only then
    help: str = ""

    @property
    def unit(self) -> str:
        return {"length": "mm", "angle": "°", "ratio": "L"}.get(self.kind, "")


def _choices(values):
    return tuple((v, v.replace("_", "-").capitalize()) for v in values)


ROLE_CHOICES = ((FLUID, "Fluid (meshed)"), (SOLID, "Solid (cut out)"))
FIELDS = {
    "transform": (
        Field("kind", "Transform", "choice", _choices(Transform.KINDS)),
        Field("dx", "Move x", "length", show_if=("kind", ("move",))),
        Field("dy", "Move y", "length", show_if=("kind", ("move",))),
        Field("cx", "Centre / point x", "length", show_if=("kind", ("rotate", "scale", "mirror"))),
        Field("cy", "Centre / point y", "length", show_if=("kind", ("rotate", "scale", "mirror"))),
        Field("angle", "Angle", "angle", show_if=("kind", ("rotate", "mirror")),
              help="Rotate: counter-clockwise (a negative angle lifts the nose: angle of attack). Mirror: "
                   "the mirror line's angle from the x axis."),
        Field("factor", "Factor", "number", show_if=("kind", ("scale",))),
        Field("copy", "Keep the original (copy)", "bool"),
    ),
    "fillet": (Field("radius", "Radius", "length"),),
    "boolean": (Field("kind", "Boolean", "choice", _choices(BooleanOp.KINDS)),
                Field("keep_tools", "Keep the tool faces", "bool")),
    "set_role": (Field("role", "Role", "choice", ROLE_CHOICES),),
    "enclosure": (
        Field("kind", "Shape", "choice", (("circle", "Circle"), ("rectangle", "Rectangle"),
                                          ("c_domain", "C-domain (airfoils)"))),
        Field("radius", "Radius", "ratio", show_if=("kind", ("circle", "c_domain")),
              help="In reference lengths L (the length of the body along x)."),
        Field("upstream", "Upstream", "ratio", show_if=("kind", ("rectangle",))),
        Field("downstream", "Downstream", "ratio", show_if=("kind", ("rectangle", "c_domain"))),
        Field("height", "Height", "ratio", show_if=("kind", ("rectangle",))),
        Field("half", "Half domain (symmetry / axis on y = 0)", "bool"),
    ),
    "name_boundary": (
        Field("name", "Name", "text", help="Becomes the mesh patch name: letters, digits, _ and -."),
        Field("kind", "Type", "choice", tuple((k, label) for k, (label, _) in BOUNDARY_TYPES.items())),
        Field("inflation", "Inflation layers on these edges", "bool"),
    ),
    "refinement": (
        Field("shape", "Shape", "choice", _choices(Refinement.SHAPES)),
        Field("x0", "x min / start x", "length", show_if=("shape", ("box", "wake"))),
        Field("y0", "y min / start y", "length", show_if=("shape", ("box", "wake"))),
        Field("x1", "x max / end x", "length", show_if=("shape", ("box", "wake"))),
        Field("y1", "y max / end y", "length", show_if=("shape", ("box", "wake"))),
        Field("xc", "Centre x", "length", show_if=("shape", ("circle",))),
        Field("yc", "Centre y", "length", show_if=("shape", ("circle",))),
        Field("radius", "Radius", "length", show_if=("shape", ("circle",))),
        Field("width", "Width", "length", show_if=("shape", ("wake",))),
        Field("size", "Cell size", "length"),
    ),
    "import": (
        Field("unit", "Unit of the numbers", "choice", (("file", "As the file says"),) + _choices(UNITS)),
        Field("role", "The faces are", "choice", (("auto", "Decide (edge on y = 0: fluid)"),) + ROLE_CHOICES),
        Field("tolerance", "Healing tolerance (x size)", "number"),
        Field("section", "Cutting plane for solids", "choice", (("xy", "x-y"), ("xz", "x-z"), ("yz", "y-z"))),
    ),
}


def fields_for(op) -> tuple:
    return FIELDS.get(op.type, ())


def shown(field, params) -> bool:
    return field.show_if is None or params.get(field.show_if[0]) in field.show_if[1]


def to_text(field, value) -> str:
    """The value as shown in a field (lengths in mm)."""
    if field.kind == "length":
        return f"{float(value) / MM:.8g}"
    if field.kind in ("number", "angle", "ratio"):
        return f"{float(value):.8g}"
    return str(value)


def from_text(field, text):
    """The typed text as a value (lengths back to metres); ValueError with a message if it is not a number."""
    if field.kind in ("length", "number", "angle", "ratio"):
        try:
            value = float(str(text).replace(",", "."))
        except ValueError:
            raise ValueError(f"{field.label}: '{text}' is not a number") from None
        if not math.isfinite(value):
            raise ValueError(f"{field.label}: the number must be finite")
        return value * MM if field.kind == "length" else value
    return text


# ---- new operations from the selection --------------------------------------------------------

def _faces_of(selection, built):
    """Face ids of the selection (an edge or vertex counts as its faces)."""
    faces = []
    for kind, entity in selection:
        ids = [entity] if kind == "face" else \
            built.edges[entity].faces if kind == "edge" else \
            sorted({f for e in built.vertices[entity].edges for f in built.edges[e].faces})
        faces += [f for f in ids if f not in faces]
    return faces


def _centre(selection, built):
    pts = []
    for kind, entity in selection:
        if kind == "face":
            pts.append(built.faces[entity].centroid)
        elif kind == "edge":
            pts.append(built.edges[entity].midpoint)
        else:
            pts.append(built.vertices[entity].xy)
    if not pts:
        box = built.bbox() or (0.0, 0.0, 0.0, 0.0)
        return np.array([0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3])])
    return np.mean(pts, axis=0)


def operation_for(kind, selection, built):
    """A new operation of this kind, pre-filled from the selection; ValueError says what to select."""
    if kind == "transform":
        c = _centre(selection, built)
        return Transform(targets=_faces_of(selection, built), cx=float(c[0]), cy=float(c[1]))
    if kind == "delete":
        targets = _faces_of([s for s in selection if s[0] == "face"], built) + \
            [e for k, e in selection if k == "edge" and not built.edges[e].faces]
        if not targets:
            raise ValueError("Select the faces (or free curves) to delete.")
        return Delete(targets=targets)
    if kind == "fillet":
        edges = []
        for k, entity in selection:
            if k == "vertex":
                edges = list(built.vertices[entity].edges)
            elif k == "edge":
                edges.append(entity)
        if len(edges) != 2:
            raise ValueError("Select the corner (a point where exactly two edges meet), or the two edges.")
        shortest = min(built.edges[e].length for e in edges)
        return Fillet(edges=edges, radius=float(f"{0.2 * shortest:.2g}"))
    if kind == "set_role":
        faces = _faces_of(selection, built)
        if not faces:
            raise ValueError("Select the faces to mark as fluid or solid.")
        role = SOLID if built.faces[faces[0]].role == FLUID else FLUID
        return SetRole(faces=faces, role=role)
    if kind == "boolean":
        faces = _faces_of(selection, built)
        if len(faces) < 2:
            raise ValueError("Select two or more faces: the first is the object, the others the tools.")
        return BooleanOp(kind="subtract", objects=faces[:1], tools=faces[1:])
    if kind == "name_boundary":
        edges = [e for k, e in selection if k == "edge"]
        if not edges:
            raise ValueError("Select the edges to name (Shift- or Ctrl-click for several).")
        current = {(built.names[e].name, built.names[e].type) for e in edges if e in built.names}
        if len(current) == 1:
            name, kind_ = current.pop()
        else:
            sugg = suggestions(built)
            kinds = {sugg[e].type for e in edges if e in sugg}
            kind_ = kinds.pop() if len(kinds) == 1 else "wall"
            name = kind_
        inflation = any(built.names[e].inflation for e in edges if e in built.names)
        return NameBoundary(edges=edges, name=name, kind=kind_, inflation=inflation)
    if kind == "enclosure":
        return Enclosure()
    if kind == "refinement":
        box = built.bbox() or (0.0, 0.0, 1.0, 1.0)
        size = max(box[2] - box[0], box[3] - box[1])
        if selection:
            pts = np.vstack([built.edges[e].points for e in _edges_of(selection, built)])
            (x0, y0), (x1, y1) = pts.min(axis=0), pts.max(axis=0)
            pad = 0.1 * max(x1 - x0, y1 - y0, 1e-12)
            x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
        else:
            c = _centre([], built)
            x0, y0, x1, y1 = c[0] - 0.1 * size, c[1] - 0.1 * size, c[0] + 0.1 * size, c[1] + 0.1 * size
        nice = float(f"{size / 200:.1g}")
        return Refinement(shape="box", x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1),
                          xc=float(0.5 * (x0 + x1)), yc=float(0.5 * (y0 + y1)),
                          radius=float(0.5 * max(x1 - x0, y1 - y0)), width=float(0.1 * (y1 - y0)), size=nice)
    raise ValueError(f"unknown operation '{kind}'")


def _edges_of(selection, built):
    out = []
    for kind, entity in selection:
        if kind == "edge":
            ids = [entity]
        elif kind == "vertex":
            ids = built.vertices[entity].edges
        else:
            ids = [e for loop in built.faces[entity].loops for e in loop]
        out += [e for e in ids if e not in out]
    return out


# ---- boundaries table ----------------------------------------------------------------------------------

def boundary_rows(built) -> list:
    """[(name, type, number of edges, inflation, how named)] of the fluid boundary; unnamed edges last."""
    rows = []
    for name, (kind, edges) in built.patches().items():
        origins = {built.names[e].origin for e in edges}
        rows.append((name, kind, len(edges), "yes" if any(built.names[e].inflation for e in edges) else "",
                     "you" if "user" in origins else "automatic"))
    unnamed = [e for e in built.boundary_edges() if e not in built.names]
    if unnamed:
        rows.append(("(no name)", "", len(unnamed), "", "name them"))
    return rows


def edges_named(built, name) -> list:
    return [e for e in built.boundary_edges() if e in built.names and built.names[e].name == name]


def rename_boundary(document, built, old, new):
    """A new document in which the boundary `old` is called `new` everywhere (same type and inflation)."""
    edges = edges_named(built, old)
    if not edges:
        raise ValueError(f"There is no boundary called '{old}'.")
    doc = document.copy()
    first = built.names[edges[0]]
    doc.add(NameBoundary(edges=edges, name=new, kind=first.type, inflation=first.inflation))
    return doc


def set_boundary_type(document, built, name, kind, inflation=None):
    """A new document in which the boundary `name` has the type `kind` (and inflation, if given)."""
    edges = edges_named(built, name)
    if not edges:
        raise ValueError(f"There is no boundary called '{name}'.")
    doc = document.copy()
    keep = any(built.names[e].inflation for e in edges) if inflation is None else bool(inflation)
    doc.add(NameBoundary(edges=edges, name=name, kind=kind, inflation=keep))
    return doc


def accept_suggestions(document, built):
    """A new document with one Name boundary operation per suggested name; None if there is nothing to accept."""
    groups = {}
    for edge_id, b in suggestions(built).items():
        groups.setdefault((b.name, b.type), []).append(edge_id)
    if not groups:
        return None
    doc = document.copy()
    for (name, kind), edges in sorted(groups.items()):
        doc.add(NameBoundary(edges=sorted(edges), name=name, kind=kind))
    return doc


# ---- points of an operation (point table, dragging) ------------------------------------------------

def has_points(op) -> bool:
    return "points" in op.params and op.params.get("format", "points") in ("coordinates", "wall_profile", "points")


def _point_scale(op) -> float:
    if op.type == "import":
        if op.params["format"] == "wall_profile":
            return MM
        unit = op.params["unit"]
        return UNITS["m" if unit == "file" else unit]
    return 1.0


def points_of(op) -> np.ndarray:
    """The points of an operation in metres (n, 2)."""
    return np.asarray(op.params["points"], dtype=float).reshape(-1, 2) * _point_scale(op)


def with_points(op, points_m):
    """A copy of the operation with new points (given in metres)."""
    from aeroflowsim.geometry_model import operation_from_dict
    new = operation_from_dict(op.to_dict())
    new.params["points"] = (np.asarray(points_m, dtype=float) / _point_scale(op)).tolist()
    return new


def replace_operation(document, op):
    doc = document.copy()
    doc.replace(op)
    return doc


# ---- texts ----------------------------------------------------------------------------------------------

def mm(value) -> str:
    return f"{value / MM:.6g}"


def selection_rows(built, selection) -> list:
    """(property, value, unit) rows describing the selection."""
    if not selection:
        return []
    if len(selection) > 1:
        counts = {}
        for kind, _ in selection:
            counts[kind] = counts.get(kind, 0) + 1
        rows = [(f"Selected {k}s", str(n), "") for k, n in counts.items()]
        length = sum(built.edges[e].length for k, e in selection if k == "edge")
        if length:
            rows.append(("Total edge length", mm(length), "mm"))
        return rows
    kind, entity = selection[0]
    if kind == "edge":
        e = built.edges[entity]
        b = built.names.get(entity)
        return [("Edge", e.id, ""), ("Kind", e.kind, ""), ("Length", mm(e.length), "mm"),
                ("Start x, y", f"{mm(e.points[0, 0])}, {mm(e.points[0, 1])}", "mm"),
                ("End x, y", f"{mm(e.points[-1, 0])}, {mm(e.points[-1, 1])}", "mm"),
                ("Boundary", f"{b.name} ({b.type})" if b else ("inside the fluid" if len(e.faces) > 1 else
                                                                "no name yet" if e.faces else "free curve"), ""),
                ("Inflation", "yes" if b and b.inflation else "no", "")]
    if kind == "vertex":
        v = built.vertices[entity]
        rows = [("Point x", mm(v.xy[0]), "mm"), ("Point y", mm(v.xy[1]), "mm"), ("Edges here", str(len(v.edges)), "")]
        if len(v.edges) == 2:
            rows.append(("Corner angle", f"{corner_angle(built, v):.4g}", "°"))
        return rows
    f = built.faces[entity]
    rows = [("Face", f.id, ""), ("Role", f.role, ""), ("Area", f"{f.area / MM**2:.6g}", "mm²"),
            ("Centroid x, y", f"{mm(f.centroid[0])}, {mm(f.centroid[1])}", "mm"), ("Holes", str(len(f.loops) - 1), "")]
    if built.axisymmetric:
        rows.append(("Volume of revolution", f"{2 * math.pi * f.area * f.centroid[1] / MM**3:.6g}", "mm³"))
    return rows


def corner_angle(built, vertex) -> float:
    """Angle [deg] between the two edges at a vertex (180 = straight on)."""
    dirs = []
    for e in vertex.edges[:2]:
        p = built.edges[e].points
        a, b = (p[0], p[1]) if np.linalg.norm(p[0] - vertex.xy) < np.linalg.norm(p[-1] - vertex.xy) else (p[-1], p[-2])
        dirs.append((b - a) / max(np.linalg.norm(b - a), 1e-300))
    return float(np.degrees(np.arccos(np.clip(np.dot(dirs[0], dirs[1]), -1.0, 1.0))))


def history_rows(document, built) -> list:
    """(operation id, text, state) per operation; state "ok", "failed", "suppressed", "not run" or "template"."""
    rows, after_failure = [], False
    for op in document.operations:
        if op.suppressed:
            state = "suppressed"
        elif after_failure:
            state = "not run"
        elif op.id == built.failed_operation:
            state, after_failure = "failed", True
        else:
            state = "template" if op.type in TEMPLATE_TYPES else "ok"
        rows.append((op.id, op.summary(), state))
    return rows

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The operations of a geometry history: one small class per kind of step.

Every operation has
    id          "op1", "op2" ... (given by the document, never reused)
    suppressed  True: skipped when the history is replayed (like "suppress feature" in CAD)
    params      a dict of plain numbers / text / lists (saved as JSON in geometry/history.json)
and apply(kernel, context), which builds its part of the geometry with the Kernel (kernel.py).
All lengths are metres and all angles degrees.

Adding a new kind of operation = one new class with type, title, DEFAULTS and apply(), listed in
OPERATIONS at the bottom. The GUI edits params generically (one field per entry).
"""

import copy
import math

import numpy as np

from aeroflowsim.geometry_model.built import FLUID, SOLID, Boundary, Region

TEMPLATE_TYPES = ("template_shape", "template_enclosure")   # operations that follow the template inputs


class Operation:
    type = ""            # key in history.json
    title = ""           # shown in the History list
    DEFAULTS = {}        # every parameter with its default value

    def __init__(self, id="", suppressed=False, **params):
        unknown = sorted(set(params) - set(self.DEFAULTS))
        if unknown:
            raise ValueError(f"{self.title}: unknown setting(s) {', '.join(unknown)}")
        self.id = id
        self.suppressed = bool(suppressed)
        self.params = copy.deepcopy(self.DEFAULTS)
        self.params.update(copy.deepcopy(params))

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "suppressed": self.suppressed, **copy.deepcopy(self.params)}

    def summary(self) -> str:
        """One line for the History list."""
        return self.title

    def apply(self, kernel, context):
        raise NotImplementedError

    def __eq__(self, other):
        return isinstance(other, Operation) and self.to_dict() == other.to_dict()

    def __repr__(self):
        return f"{type(self).__name__}({self.to_dict()})"


# =============================================================================================
# Template geometry (follows the template's geometry inputs)
# =============================================================================================

class TemplateShape(Operation):
    """The template's own geometry: the parametric / CSV nozzle, or the shape-library body.

    Its parameters ARE the template's geometry inputs (edited in the Inputs panel as before), so
    old projects and templates keep working unchanged.
    """

    type, title = "template_shape", "Template shape"

    def apply(self, kernel, context):
        from aeroflowsim.geometry import WallProfile
        profile = context.template_geometry()
        if profile is None:
            raise ValueError("this template has no geometry")
        if isinstance(profile, WallProfile):
            build_nozzle(kernel, self.id, profile)
        else:
            build_body(kernel, self.id, profile)

    def summary(self) -> str:
        return "Template shape (from the geometry inputs)"


class TemplateEnclosure(Operation):
    """The template's far-field domain around the body (external flow templates), from its inputs."""

    type, title = "template_enclosure", "Template far field"

    def apply(self, kernel, context):
        profile = context.template_geometry()
        domain = context.case.domain(context.params, profile)
        x0, _, x1, _ = profile.bbox
        xc = 0.5 * (x0 + x1)                                 # as in aeroflowsim/gmsh_mesh.py [m]
        half = bool(domain.half or profile.axisymmetric)
        if domain.shape == "Circle":
            dims = {"xc": xc, "radius": domain.radius}
            kind = "circle"
        else:
            dims = {"x0": x0 - domain.upstream, "x1": x1 + domain.downstream, "height": domain.height}
            kind = "rectangle"
        build_enclosure(kernel, self.id, kind, dims, half)

    def summary(self) -> str:
        return "Template far field (from the geometry inputs)"


# =============================================================================================
# Editing
# =============================================================================================

class Transform(Operation):
    """Move, rotate, scale or mirror faces / free curves (all of them when `targets` is empty)."""

    type, title = "transform", "Transform"
    DEFAULTS = {"targets": [], "kind": "move", "dx": 0.0, "dy": 0.0, "cx": 0.0, "cy": 0.0,
                "angle": 0.0, "factor": 1.0, "copy": False}
    KINDS = ("move", "rotate", "scale", "mirror")
    # rotate: angle [deg] counter-clockwise about (cx, cy); scale: factor about (cx, cy);
    # mirror: about the line through (cx, cy) at `angle` [deg] from the x axis.

    def summary(self) -> str:
        p = self.params
        what = "everything" if not p["targets"] else f"{len(p['targets'])} item(s)"
        text = {"move": f"Move {what} by ({p['dx']:.4g}, {p['dy']:.4g}) m",
                "rotate": f"Rotate {what} by {p['angle']:.4g}° about ({p['cx']:.4g}, {p['cy']:.4g}) m",
                "scale": f"Scale {what} by {p['factor']:.4g} about ({p['cx']:.4g}, {p['cy']:.4g}) m",
                "mirror": f"Mirror {what} about the line through ({p['cx']:.4g}, {p['cy']:.4g}) m at "
                          f"{p['angle']:.4g}°"}[p["kind"]]
        return ("Copy and " + text[0].lower() + text[1:]) if p["copy"] else text

    def apply(self, kernel, context):
        p = self.params
        if p["kind"] not in self.KINDS:
            raise ValueError(f"unknown transform '{p['kind']}'")
        if p["kind"] == "scale" and not p["factor"] > 0.0:
            raise ValueError("the scale factor must be positive")
        targets = kernel.dim_tags(p["targets"])
        if not targets:
            raise ValueError("there is nothing to transform")
        if p["copy"]:
            targets = _copy_entities(kernel, targets, self.id)
        occ = kernel.occ
        if p["kind"] == "move":
            occ.translate(targets, p["dx"], p["dy"], 0.0)
        elif p["kind"] == "rotate":
            occ.rotate(targets, p["cx"], p["cy"], 0.0, 0.0, 0.0, 1.0, math.radians(p["angle"]))
        elif p["kind"] == "scale":
            occ.dilate(targets, p["cx"], p["cy"], 0.0, p["factor"], p["factor"], 1.0)
        else:
            t = math.radians(p["angle"])
            a, b = -math.sin(t), math.cos(t)                  # normal of the mirror line
            occ.mirror(targets, a, b, 0.0, -(a * p["cx"] + b * p["cy"]))
        kernel.sync()


class Delete(Operation):
    """Remove faces (with their edges) or free curves."""

    type, title = "delete", "Delete"
    DEFAULTS = {"targets": []}

    def summary(self) -> str:
        return f"Delete {len(self.params['targets'])} item(s)"

    def apply(self, kernel, context):
        if not self.params["targets"]:
            raise ValueError("nothing chosen to delete")
        targets = kernel.dim_tags(self.params["targets"])
        for dim, tag in targets:
            if dim == 1 and len(kernel.gmsh.model.getAdjacencies(1, tag)[0]):
                raise ValueError("an edge of a face cannot be deleted on its own; delete the face, or use "
                                 "booleans to change it")
        kernel.occ.remove(targets, recursive=True)
        kernel.sync()
        for dim, tag in targets:
            if dim == 2:
                kernel.face_meta.pop(tag, None)
        live = set(kernel.curve_tags())
        kernel.edge_meta = {t: m for t, m in kernel.edge_meta.items() if t in live}


class BooleanOp(Operation):
    """Union, subtract or intersect faces: objects (op) tools."""

    type, title = "boolean", "Boolean"
    DEFAULTS = {"kind": "subtract", "objects": [], "tools": [], "keep_tools": False}
    KINDS = ("union", "subtract", "intersect")

    def summary(self) -> str:
        p = self.params
        return f"{p['kind'].capitalize()}: {len(p['objects'])} face(s) with {len(p['tools'])} face(s)"

    def apply(self, kernel, context):
        p = self.params
        if p["kind"] not in self.KINDS:
            raise ValueError(f"unknown boolean '{p['kind']}'")
        kernel.boolean(p["kind"], p["objects"], p["tools"], self.id, remove_tools=not p["keep_tools"])


class SetRole(Operation):
    """Mark faces as fluid (meshed) or solid (a body to cut out of the fluid)."""

    type, title = "set_role", "Fluid / solid"
    DEFAULTS = {"faces": [], "role": FLUID}

    def summary(self) -> str:
        return f"Mark {len(self.params['faces'])} face(s) as {self.params['role']}"

    def apply(self, kernel, context):
        if self.params["role"] not in (FLUID, SOLID):
            raise ValueError("a face is either fluid or solid")
        for face_id in self.params["faces"]:
            kernel.face_meta[kernel.face_by_id(face_id)].role = self.params["role"]


# =============================================================================================
# Domain, names and mesh controls
# =============================================================================================

class Enclosure(Operation):
    """The fluid domain around the solid bodies: circle, rectangle or C-domain, sized in reference
    lengths L (the x-extent of all solid faces), centred on the bodies; the bodies are subtracted."""

    type, title = "enclosure", "Enclosure"
    DEFAULTS = {"kind": "circle", "radius": 20.0, "upstream": 10.0, "downstream": 20.0, "height": 10.0,
                "half": False}
    KINDS = ("circle", "rectangle", "c_domain")
    # circle: radius; rectangle: upstream, downstream, height; c_domain: radius (upstream half circle
    # and half height), downstream. All in reference lengths L [-].

    def summary(self) -> str:
        p = self.params
        size = {"circle": f"radius {p['radius']:g} L", "rectangle":
                f"{p['upstream']:g} L up, {p['downstream']:g} L down, {p['height']:g} L high",
                "c_domain": f"radius {p['radius']:g} L, {p['downstream']:g} L downstream"}.get(p["kind"], "")
        return f"Enclosure: {p['kind'].replace('_', '-')} ({size}){', half' if p['half'] else ''}"

    def apply(self, kernel, context):
        p = self.params
        bodies = kernel.faces_with_role(SOLID)
        if not bodies:
            raise ValueError("an enclosure goes around a solid body, and there is none (mark a face as solid)")
        x0, y0, x1, y1 = _bbox(kernel, [(2, t) for t in bodies])
        L = x1 - x0                                          # reference length [m]
        xc = 0.5 * (x0 + x1)
        if p["kind"] == "circle":
            dims = {"xc": xc, "radius": p["radius"] * L}
        elif p["kind"] == "rectangle":
            dims = {"x0": x0 - p["upstream"] * L, "x1": x1 + p["downstream"] * L, "height": p["height"] * L}
        elif p["kind"] == "c_domain":
            dims = {"xc": xc, "radius": p["radius"] * L, "x1": x1 + p["downstream"] * L}
        else:
            raise ValueError(f"unknown enclosure '{p['kind']}'")
        build_enclosure(kernel, self.id, p["kind"], dims, bool(p["half"] or kernel.axisymmetric))


class NameBoundary(Operation):
    """Give edges a boundary name and type (they become a mesh patch of that name)."""

    type, title = "name_boundary", "Name boundary"
    DEFAULTS = {"edges": [], "name": "", "kind": "wall", "inflation": False}

    def summary(self) -> str:
        p = self.params
        return f"Name {len(p['edges'])} edge(s) '{p['name']}' ({p['kind']}{', inflation' if p['inflation'] else ''})"

    def apply(self, kernel, context):
        from aeroflowsim.geometry_model.boundaries import check_name, check_type
        p = self.params
        check_name(p["name"])
        check_type(p["kind"])
        if not p["edges"]:
            raise ValueError("no edges chosen")
        kernel.names.append((list(p["edges"]), Boundary(p["name"], p["kind"], bool(p["inflation"]), "user"),
                             self.id))


class Refinement(Operation):
    """A refinement region: box (x0 y0 x1 y1), circle (xc yc radius) or wake line (x0 y0 -> x1 y1,
    with a width), where cells are at most `size` [m]."""

    type, title = "refinement", "Refinement region"
    DEFAULTS = {"shape": "box", "x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0, "xc": 0.0, "yc": 0.0,
                "radius": 1.0, "width": 0.1, "size": 0.01}
    SHAPES = ("box", "circle", "wake")

    def summary(self) -> str:
        return f"Refinement {self.params['shape']}: cells ≤ {self.params['size']:.4g} m"

    def apply(self, kernel, context):
        p = self.params
        if p["shape"] not in self.SHAPES:
            raise ValueError(f"unknown refinement region '{p['shape']}'")
        if not p["size"] > 0.0:
            raise ValueError("the cell size must be positive")
        keys = {"box": ("x0", "y0", "x1", "y1"), "circle": ("xc", "yc", "radius"),
                "wake": ("x0", "y0", "x1", "y1", "width")}[p["shape"]]
        values = {k: float(p[k]) for k in keys}
        if p["shape"] == "box" and not (values["x1"] > values["x0"] and values["y1"] > values["y0"]):
            raise ValueError("a refinement box needs x1 > x0 and y1 > y0")
        if p["shape"] == "circle" and not values["radius"] > 0.0:
            raise ValueError("a refinement circle needs a positive radius")
        kernel.regions.append(Region(self.id, p["shape"], values, float(p["size"])))


# =============================================================================================
# Builders shared by the operations
# =============================================================================================

def build_nozzle(kernel, op_id, wall):
    """The fluid inside a nozzle (a WallProfile): wall, inlet, outlet and axis, as the mesher does."""
    from aeroflowsim.gmsh_mesh import nozzle_wall_points
    points, corners, refine = nozzle_wall_points(wall)
    chain = kernel.add_chain(points, corners | refine, False, op_id, "wall", "wall", "wall")
    x_in, x_out = points[0, 0], points[-1, 0]
    axis_in, axis_out = kernel.point(x_in, 0.0), kernel.point(x_out, 0.0)
    axis = kernel.line(axis_in, axis_out)
    outlet = kernel.line(axis_out, chain.point_tags[-1])
    inlet = kernel.line(chain.point_tags[0], axis_in)
    for tag, name in ((axis, "axis"), (outlet, "outlet"), (inlet, "inlet")):
        kernel.name_edge(tag, f"{op_id}:{name}", name, name)
    kernel.add_face([axis, outlet] + list(reversed(chain.curves)) + [inlet], f"{op_id}:nozzle", FLUID)
    kernel.axisymmetric = True


def build_body(kernel, op_id, profile):
    """A closed body outline (a ShapeProfile) as a solid face, split at its corners."""
    chain = kernel.add_chain(profile.points, profile.corners | profile.refine, True, op_id, "body", "wall", "wall")
    kernel.add_face(chain.curves, f"{op_id}:body", SOLID)
    kernel.axisymmetric = bool(profile.axisymmetric)


def build_enclosure(kernel, op_id, kind, dims, half):
    """The outer boundary of the fluid domain (absolute sizes [m], centred on y = 0), minus every solid.

    circle: xc, radius; rectangle: x0, x1, height (from y = 0); c_domain: xc, radius, x1.
    half: only y >= 0, with a symmetry line (planar) or the axis (axisymmetric) on y = 0.
    Outer edges are named "farfield" by default.
    """
    sym = "axis" if kernel.axisymmetric else "symmetry"
    P = kernel.point
    edges = []                                            # (tag, label, name)

    def line(a, b, label, name="farfield"):
        edges.append((kernel.line(a, b), label, name))

    def arc(a, centre, b, label):
        edges.append((kernel.occ.addCircleArc(a, centre, b), label, "farfield"))

    if kind == "circle":
        xc, R = dims["xc"], dims["radius"]
        if not R > 0.0:
            raise ValueError("the enclosure radius must be positive")
        c = P(xc, 0.0)
        right, top, left, bottom = P(xc + R, 0.0), P(xc, R), P(xc - R, 0.0), P(xc, -R)
        arc(right, c, top, "farfield.1")
        arc(top, c, left, "farfield.2")
        if half:
            line(left, right, "symmetry", sym)
        else:
            arc(left, c, bottom, "farfield.3")
            arc(bottom, c, right, "farfield.4")
    elif kind == "rectangle":
        x0, x1, H = dims["x0"], dims["x1"], dims["height"]
        if not (x1 > x0 and H > 0.0):
            raise ValueError("the enclosure rectangle needs a positive length and height")
        lo = 0.0 if half else -H
        a, b, c, d = P(x1, lo), P(x1, H), P(x0, H), P(x0, lo)
        line(a, b, "farfield.right")
        line(b, c, "farfield.top")
        line(c, d, "farfield.left")
        line(d, a, "symmetry" if half else "farfield.bottom", sym if half else "farfield")
    elif kind == "c_domain":
        xc, R, x1 = dims["xc"], dims["radius"], dims["x1"]
        if not (R > 0.0 and x1 > xc):
            raise ValueError("the C-domain needs a positive radius and must end downstream of the body")
        c = P(xc, 0.0)
        top, left, bottom = P(xc, R), P(xc - R, 0.0), P(xc, -R)
        out_top, out_bottom = P(x1, R), P(x1, 0.0 if half else -R)
        arc(top, c, left, "farfield.arc1")
        if half:
            line(left, out_bottom, "symmetry", sym)
        else:
            arc(left, c, bottom, "farfield.arc2")
            line(bottom, out_bottom, "farfield.bottom")
        line(out_bottom, out_top, "farfield.downstream")
        line(out_top, top, "farfield.top")
    else:
        raise ValueError(f"unknown enclosure '{kind}'")
    for tag, label, name in edges:
        kernel.name_edge(tag, f"{op_id}:{label}", name, name if name in (sym, "farfield") else name)
    domain = kernel.add_face([t for t, _, _ in edges], f"{op_id}:domain", FLUID)
    kernel.sync()
    solids = kernel.faces_with_role(SOLID)
    if solids:
        kernel.boolean("subtract", [domain], solids, op_id, role=FLUID)
        if not kernel.faces_with_role(FLUID):
            raise ValueError("the body fills the whole enclosure; make the enclosure larger")


def _bbox(kernel, dim_tags):
    """(x0, y0, x1, y1) of some faces / curves [m], from points on their curves.

    (Gmsh's own bounding boxes are padded by its tolerance, 1e-7, which would make the
    reference length - and so every enclosure size - slightly wrong.)
    """
    curves = set()
    for dim, tag in dim_tags:
        if dim == 2:
            curves.update(abs(t) for _, t in kernel.gmsh.model.getBoundary([(2, tag)], oriented=False))
        else:
            curves.add(tag)
    pts = np.vstack([kernel.sample(c, 401) for c in sorted(curves)])
    (x0, y0), (x1, y1) = pts.min(axis=0), pts.max(axis=0)
    return float(x0), float(y0), float(x1), float(y1)


def _copy_entities(kernel, targets, op_id):
    """Copy faces / free curves; the copies' edges get ids "<original id>@<op id>"."""
    model = kernel.gmsh.model
    copies = kernel.occ.copy(targets)
    kernel.sync()
    for (dim, old), (_, new) in zip(targets, copies):
        if dim == 2:
            meta = kernel.face_meta.get(old)
            if meta is not None:
                kernel.name_face(new, f"{meta.id}@{op_id}", meta.role)
            old_curves = [abs(t) for _, t in model.getBoundary([(2, old)], oriented=False)]
            new_curves = [abs(t) for _, t in model.getBoundary([(2, new)], oriented=False)]
        else:
            old_curves, new_curves = [old], [new]
        for a, b in zip(old_curves, new_curves):
            m = kernel.edge_meta.get(a)
            if m is not None:
                kernel.edge_meta[b] = type(m)(f"{m.id}@{op_id}", tuple(f"{s}@{op_id}" for s in m.sources),
                                              m.default_name, m.default_type)
    return copies


OPERATIONS = {cls.type: cls for cls in (TemplateShape, TemplateEnclosure, Transform, Delete, BooleanOp, SetRole,
                                        Enclosure, NameBoundary, Refinement)}


def operation_from_dict(data) -> Operation:
    """An operation from its saved dict (history.json); ValueError naming the problem."""
    data = dict(data)
    kind = data.pop("type", None)
    if kind not in OPERATIONS:
        raise ValueError(f"unknown geometry operation '{kind}'")
    return OPERATIONS[kind](**data)

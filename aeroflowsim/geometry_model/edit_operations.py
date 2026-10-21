# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Editing operations of the geometry workspace (history steps, like those in operations.py):

    SplitFace   cut faces along curves drawn or selected across them (OCC "fragment"); the pieces
                keep the role; the parts of the cutting curves outside the faces are removed
    SplitEdge   cut an edge at a point (its boundary name goes to both pieces)
    Trim        remove the piece of a curve between its neighbouring crossings, nearest to a point,
                and rebuild the faces from the curves that remain (like trimming in a sketch)
    Extend      lengthen a straight free line until it meets the next curve
    Offset      parallel copies of a chain of edges at a distance: lines stay lines, arcs stay
                concentric arcs, other curves become smooth splines; corners get exact joins
                (lines meet at their intersection, other corners get a round arc)
    Chamfer     cut the corner between two edges with a straight line (fillet rounds it)
    Pattern     copies of faces / free curves in a row (linear) or round a centre (circular)
    Fill        a face from a closed loop of selected curves
    MergeFaces  join faces into one (union)
All lengths in metres, angles in degrees; edge ids follow the lineage rules of kernel.py.
"""

import math

import numpy as np

from aeroflowsim.geometry_model.built import FLUID, SOLID
from aeroflowsim.geometry_model.operations import Operation, _copy_entities


def _free_dangling(kernel, curves):
    """Remove those of `curves` that bound no face any more (leftovers of a cut)."""
    model = kernel.gmsh.model
    live = set(kernel.curve_tags())
    dangling = [(1, c) for c in curves if c in live and len(model.getAdjacencies(1, c)[0]) == 0]
    if dangling:
        kernel.occ.remove(dangling, recursive=True)
        kernel.sync()


class SplitFace(Operation):
    """Cut faces along curves (free curves: drawn lines, arcs, splines across the faces)."""

    type, title = "split_face", "Split face"
    DEFAULTS = {"faces": [], "curves": []}         # faces: [] = every face the curves cross

    def summary(self) -> str:
        p = self.params
        what = f"{len(p['faces'])} face(s)" if p["faces"] else "the faces they cross"
        return f"Split {what} along {len(p['curves'])} curve(s)"

    def apply(self, kernel, context):
        p = self.params
        if not p["curves"]:
            raise ValueError("choose the curve(s) to split along (draw a line across the face)")
        curves = [kernel.edge_by_id(e) for e in p["curves"]]
        faces = [kernel.face_by_id(f) for f in p["faces"]] if p["faces"] else kernel.face_tags()
        if not faces:
            raise ValueError("there is no face to split")
        snap = kernel.snapshot()
        metas = [kernel.face_meta.get(f) for f in faces]
        out, out_map = kernel.occ.fragment([(2, f) for f in faces], [(1, c) for c in curves])
        kernel.sync()
        new_meta = {t: m for t, m in kernel.face_meta.items() if t not in faces}
        split = 0
        for meta, produced in zip(metas, out_map[:len(faces)]):
            pieces = sorted(t for d, t in produced if d == 2)
            split += len(pieces) > 1
            for n, t in enumerate(pieces, start=1):
                if meta is not None:
                    new_meta[t] = type(meta)(meta.id if len(pieces) == 1 else f"{meta.id}#{n}", meta.role)
        kernel.face_meta = {t: m for t, m in new_meta.items() if t in kernel.face_tags()}
        kernel.relabel(snap, self.id, "cut")
        tool_pieces = [t for t, m in kernel.edge_meta.items() if any(s in p["curves"] or
                       any(s.startswith(c + "#") for c in p["curves"]) for s in m.sources)]
        _free_dangling(kernel, tool_pieces)
        if not split:
            raise ValueError("the curves do not cut across any face (they must go from edge to edge)")


class SplitEdge(Operation):
    """Cut an edge at the point nearest to (x, y) [m]."""

    type, title = "split_edge", "Split edge"
    DEFAULTS = {"edge": "", "x": 0.0, "y": 0.0}

    def summary(self) -> str:
        return f"Split edge {self.params['edge']}"

    def apply(self, kernel, context):
        p = self.params
        tag = kernel.edge_by_id(p["edge"])
        model = kernel.gmsh.model
        q, _ = model.getClosestPoint(1, tag, [p["x"], p["y"], 0.0])[:2]
        q = np.asarray(q, dtype=float)[:2]
        ends = [np.asarray(model.getValue(0, t, []))[:2]
                for _, t in model.getBoundary([(1, tag)], combined=False, oriented=False)]
        if any(np.linalg.norm(q - e) <= 1e-9 * kernel.model_size() for e in ends):
            raise ValueError("the split point is at an end of the edge; pick a point inside it")
        faces = list(model.getAdjacencies(1, tag)[0])
        snap = kernel.snapshot()
        point = kernel.point(*q)
        objects = [(2, f) for f in faces] if faces else [(1, tag)]
        metas = {f: kernel.face_meta.get(f) for f in faces}
        out, out_map = kernel.occ.fragment(objects, [(0, point)])
        kernel.sync()
        if faces:
            new_meta = {t: m for t, m in kernel.face_meta.items() if t not in faces}
            for f, produced in zip(faces, out_map):
                for d, t in produced:
                    if d == 2 and metas[f] is not None:
                        new_meta[t] = metas[f]
            kernel.face_meta = new_meta
        kernel.relabel(snap, self.id)


class Trim(Operation):
    """Remove the piece of a curve nearest to (x, y), between the points where it crosses other curves.

    Only the picked curve is cut (at its crossings); the other curves stay as they are. A face that
    used the curve is taken apart: its curves become free (use Split face or Fill to make faces again).
    """

    type, title = "trim", "Trim"
    DEFAULTS = {"x": 0.0, "y": 0.0}

    def summary(self) -> str:
        return f"Trim at ({self.params['x'] * 1e3:.4g}, {self.params['y'] * 1e3:.4g}) mm"

    def apply(self, kernel, context):
        p = self.params
        model, occ = kernel.gmsh.model, kernel.occ
        target = _nearest_curve(kernel, (p["x"], p["y"]))
        if target is None:
            raise ValueError("there is no curve to trim")
        faces = list(model.getAdjacencies(1, target)[0])
        if faces:                                    # the face(s) using the curve are taken apart
            occ.remove([(2, int(f)) for f in faces])
            kernel.sync()
            for f in faces:
                kernel.face_meta.pop(int(f), None)
        target_id = kernel.edge_meta[target].id if target in kernel.edge_meta else f"curve{target}"
        points = _crossings(kernel, target)
        snap = kernel.snapshot()
        if points:                                   # cut the picked curve (only it) where it crosses others
            occ.fragment([(1, target)], [(0, kernel.point(*q)) for q in points])
            kernel.sync()
        kernel.relabel(snap, self.id)
        live = set(kernel.curve_tags())
        pieces = [t for t, m in kernel.edge_meta.items() if t in live and
                  (m.id == target_id or m.id.startswith(target_id + "#"))]
        piece = _nearest_curve(kernel, (p["x"], p["y"]), pieces or None)
        occ.remove([(1, piece)], recursive=True)
        kernel.sync()
        kernel.edge_meta.pop(piece, None)
        kernel.remove_free_points()


class Extend(Operation):
    """Lengthen a straight free line from its end nearest (x, y) until it meets the next curve."""

    type, title = "extend", "Extend"
    DEFAULTS = {"edge": "", "x": 0.0, "y": 0.0}

    def summary(self) -> str:
        return f"Extend {self.params['edge']}"

    def apply(self, kernel, context):
        p = self.params
        model, occ = kernel.gmsh.model, kernel.occ
        tag = kernel.edge_by_id(p["edge"])
        if model.getType(1, tag) != "Line" or len(model.getAdjacencies(1, tag)[0]):
            raise ValueError("only a straight free line (not part of a face) can be extended")
        a, b = kernel.sample(tag, 2)
        near_end = np.linalg.norm(b - [p["x"], p["y"]]) < np.linalg.norm(a - [p["x"], p["y"]])
        fixed, moving = (a, b) if near_end else (b, a)
        direction = (moving - fixed) / np.linalg.norm(moving - fixed)
        best = None
        for other in kernel.curve_tags():
            if other == tag:
                continue
            pts = kernel.sample(other, 401)
            for q0, q1 in zip(pts[:-1], pts[1:]):
                d2 = q1 - q0
                cross = direction[0] * d2[1] - direction[1] * d2[0]
                if abs(cross) < 1e-300:
                    continue
                w = q0 - moving
                t = (w[0] * d2[1] - w[1] * d2[0]) / cross           # along the line beyond its end
                s = (w[0] * direction[1] - w[1] * direction[0]) / cross   # along the other curve's piece
                if t > 1e-12 * kernel.model_size() and -1e-12 <= s <= 1 + 1e-12 and (best is None or t < best):
                    best = t
        if best is None:
            raise ValueError("the line meets no other curve when extended")
        meta = kernel.edge_meta[tag]
        start_tag = [t for _, t in model.getBoundary([(1, tag)], combined=False, oriented=False)][0 if near_end else 1]
        occ.remove([(1, tag)])
        kernel.sync()
        new = occ.addLine(start_tag, kernel.point(*(moving + best * direction)))
        kernel.sync()
        kernel.edge_meta.pop(tag, None)
        kernel.edge_meta[new] = meta
        kernel.remove_free_points()


class Offset(Operation):
    """Parallel copies of a chain (or closed loop) of edges at `distance` [m]: positive = outward for a
    closed loop, to the left of the chain's direction otherwise."""

    type, title = "offset", "Offset"
    DEFAULTS = {"edges": [], "distance": 0.001, "role": SOLID}

    def summary(self) -> str:
        return f"Offset {len(self.params['edges'])} edge(s) by {self.params['distance'] * 1e3:.4g} mm"

    def apply(self, kernel, context):
        from aeroflowsim.geometry_model import healing
        p = self.params
        if not p["edges"]:
            raise ValueError("choose the edges to offset")
        if p["distance"] == 0.0:
            raise ValueError("the offset distance must not be zero")
        chain, closed = _chain(kernel, [kernel.edge_by_id(e) for e in p["edges"]])
        pieces = []                                     # (kind, points (start, [mid], end) or samples, vertex)
        polygon = np.vstack([pts for _, pts in chain])
        area = 0.5 * np.sum(polygon[:, 0] * np.roll(polygon[:, 1], -1) - np.roll(polygon[:, 0], -1) * polygon[:, 1])
        d = p["distance"] * (-1.0 if closed and area > 0 else 1.0) if closed else p["distance"]
        for kind, pts in chain:                         # every edge offset exactly to its left by d
            pieces.append((kind, pts + d * _left_normals(kind, pts)))
        occ, P = kernel.occ, kernel.point
        ends = []                                       # (start point, end point) of every piece after joins
        for kind, moved in pieces:
            ends.append([moved[0].copy(), moved[-1].copy()])
        joins = []
        n_join = len(pieces) if closed else len(pieces) - 1
        for k in range(n_join):
            i, j = k, (k + 1) % len(pieces)
            e, s = ends[i][1], ends[j][0]
            if np.linalg.norm(e - s) <= 1e-12 * kernel.model_size():
                ends[j][0] = ends[i][1]
                continue
            if pieces[i][0] == "line" and pieces[j][0] == "line":       # mitre: the lines meet
                q = _line_intersection(pieces[i][1][0], pieces[i][1][-1], pieces[j][1][0], pieces[j][1][-1])
                if q is not None:
                    ends[i][1] = ends[j][0] = q
                    continue
            joins.append((i, chain[i][1][-1]))                          # round join about the corner
        tags = {}

        def tag_of(point):
            key = (round(float(point[0]), 15), round(float(point[1]), 15))
            if key not in tags:
                tags[key] = P(*point)
            return tags[key]

        curves = []
        for k, ((kind, moved), (a, b)) in enumerate(zip(pieces, ends), start=1):
            if kind == "line":
                c = occ.addLine(tag_of(a), tag_of(b))
            elif kind == "arc":
                c = occ.addCircleArc(tag_of(a), P(*moved[len(moved) // 2]), tag_of(b), center=False)
            else:
                inner = [P(*q) for q in moved[1:-1:4]]
                c = occ.addSpline([tag_of(a)] + inner + [tag_of(b)])
            kernel.name_edge(c, f"{self.id}:e{k}")
            curves.append(c)
        for n, (i, corner) in enumerate(joins, start=1):
            a, b = ends[i][1], ends[(i + 1) % len(pieces)][0]
            c = occ.addCircleArc(tag_of(a), P(*corner), tag_of(b))
            kernel.name_edge(c, f"{self.id}:join{n}")
            curves.append(c)
        kernel.sync()
        if closed:
            healing.build_faces(kernel, curves, self.id, p["role"], report_open=False)


class Chamfer(Operation):
    """Cut the corner between two edges with a straight line: distance d1 along the first, d2 along the second."""

    type, title = "chamfer", "Chamfer"
    DEFAULTS = {"edges": [], "d1": 0.001, "d2": 0.001}

    def summary(self) -> str:
        return f"Chamfer {self.params['d1'] * 1e3:.4g} x {self.params['d2'] * 1e3:.4g} mm"

    def apply(self, kernel, context):
        from aeroflowsim.geometry_model.operations import corner_cut
        p = self.params
        if not (p["d1"] > 0.0 and p["d2"] > 0.0):
            raise ValueError("the chamfer distances must be positive")
        corner_cut(kernel, self.id, p["edges"], lambda a, b: kernel.occ.chamfer2D(a, b, p["d1"], p["d2"]),
                   "chamfer", f"no chamfer of {p['d1'] * 1e3:.4g} x {p['d2'] * 1e3:.4g} mm fits between these edges")


class Pattern(Operation):
    """Copies in a row (linear: steps dx, dy) or round a centre (circular: `angle` [deg] between copies)."""

    type, title = "pattern", "Pattern"
    DEFAULTS = {"targets": [], "kind": "linear", "count": 3, "dx": 0.01, "dy": 0.0, "cx": 0.0, "cy": 0.0,
                "angle": 120.0}
    KINDS = ("linear", "circular")

    def summary(self) -> str:
        p = self.params
        return f"{p['kind'].capitalize()} pattern, {p['count']} in all"

    def apply(self, kernel, context):
        p = self.params
        if p["kind"] not in self.KINDS:
            raise ValueError(f"unknown pattern '{p['kind']}'")
        if int(p["count"]) < 2:
            raise ValueError("a pattern needs at least 2 items in all")
        targets = kernel.dim_tags(p["targets"])
        for k in range(1, int(p["count"])):
            copies = _copy_entities(kernel, targets, f"{self.id}.{k}")
            if p["kind"] == "linear":
                kernel.occ.translate(copies, k * p["dx"], k * p["dy"], 0.0)
            else:
                kernel.occ.rotate(copies, p["cx"], p["cy"], 0.0, 0.0, 0.0, 1.0, math.radians(k * p["angle"]))
        kernel.sync()


class Fill(Operation):
    """A face from a closed loop of selected free curves."""

    type, title = "fill", "Fill"
    DEFAULTS = {"edges": [], "role": SOLID}

    def summary(self) -> str:
        return f"Fill a face from {len(self.params['edges'])} curve(s)"

    def apply(self, kernel, context):
        from aeroflowsim.geometry_model import healing
        tags = [kernel.edge_by_id(e) for e in self.params["edges"]]
        busy = [e for e, t in zip(self.params["edges"], tags) if len(kernel.gmsh.model.getAdjacencies(1, t)[0])]
        if busy:
            raise ValueError(f"{busy[0]} already belongs to a face")
        # Curves drawn separately meet at the same places but not at shared points: glue them first.
        snap = kernel.snapshot()
        glued = healing.glue(kernel, tags, 1e-9 * kernel.model_size())
        kernel.relabel(snap, self.id)
        if not healing.build_faces(kernel, glued, self.id, self.params["role"], report_open=False):
            raise ValueError("the selected curves do not form a closed loop")


class MergeFaces(Operation):
    """Join faces into one (a union; the edges between them disappear)."""

    type, title = "merge_faces", "Merge faces"
    DEFAULTS = {"faces": []}

    def summary(self) -> str:
        return f"Merge {len(self.params['faces'])} faces"

    def apply(self, kernel, context):
        faces = self.params["faces"]
        if len(faces) < 2:
            raise ValueError("choose at least two faces to merge")
        kernel.boolean("union", faces[:1], faces[1:], self.id)


# ---- helpers ------------------------------------------------------------------------------------

def _nearest_curve(kernel, xy, curves=None):
    best, best_d = None, None
    for c in (kernel.curve_tags() if curves is None else curves):
        pts = kernel.sample(c, 201)
        a, b = pts[:-1], pts[1:]
        ab = b - a
        t = np.clip(((np.asarray(xy) - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-300), 0.0, 1.0)
        d = float(np.linalg.norm(a + t[:, None] * ab - np.asarray(xy), axis=1).min())
        if best_d is None or d < best_d:
            best, best_d = c, d
    return best


def _left_normals(kind, pts):
    """Unit normals to the left of the walking direction at every point (exact for lines and arcs)."""
    if kind == "line":
        t = pts[-1] - pts[0]
        n = np.array([-t[1], t[0]]) / np.linalg.norm(t)
        return np.tile(n, (len(pts), 1))
    if kind == "arc":
        from aeroflowsim.geometry_model.inference import circle_of
        centre, _ = circle_of(pts)
        radial = (pts - centre) / np.linalg.norm(pts - centre, axis=1)[:, None]
        k = len(pts) // 2
        t = pts[k + 1] - pts[k - 1]
        side = np.sign(np.dot([-t[1], t[0]], radial[k]))      # left = outward (+1) or inward (-1)
        return side * radial
    t = np.gradient(pts, axis=0)
    return np.column_stack([-t[:, 1], t[:, 0]]) / np.maximum(np.linalg.norm(t, axis=1), 1e-300)[:, None]


def _crossings(kernel, target):
    """Points [m] where the curve `target` crosses or touches other curves (not at its own ends)."""
    model = kernel.gmsh.model
    n = 2 if model.getType(1, target) == "Line" else 1001
    own = kernel.sample(target, n)
    size = kernel.model_size()
    found = [own[0], own[-1]]                        # (its own ends do not count)
    for other in kernel.curve_tags():
        if other == target:
            continue
        pts = kernel.sample(other, 2 if model.getType(1, other) == "Line" else 1001)
        for q in _segment_crossings(own, pts):
            if all(np.linalg.norm(q - f) > 1e-9 * size for f in found):
                exact = np.asarray(model.getClosestPoint(1, target, [q[0], q[1], 0.0])[0], dtype=float)[:2]
                found.append(exact)
    return found[2:]


def _segment_crossings(p, q):
    """Points where the polyline p crosses or touches the polyline q (all segment pairs at once)."""
    a1, d1 = p[:-1, None, :], (p[1:] - p[:-1])[:, None, :]
    a2, d2 = q[None, :-1, :], (q[1:] - q[:-1])[None, :, :]
    cross = d1[..., 0] * d2[..., 1] - d1[..., 1] * d2[..., 0]
    w = a2 - a1
    with np.errstate(divide="ignore", invalid="ignore"):
        s = (w[..., 0] * d2[..., 1] - w[..., 1] * d2[..., 0]) / cross
        t = (w[..., 0] * d1[..., 1] - w[..., 1] * d1[..., 0]) / cross
    eps = 1e-9
    hit = (np.abs(cross) > 1e-300) & (s >= -eps) & (s <= 1 + eps) & (t >= -eps) & (t <= 1 + eps)
    i, j = np.nonzero(hit)
    return list(p[:-1][i] + s[i, j][:, None] * (p[1:] - p[:-1])[i])


def _distance_to(points, q):
    a, b = points[:-1], points[1:]
    ab = b - a
    t = np.clip(((q - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-300), 0.0, 1.0)
    return float(np.linalg.norm(a + t[:, None] * ab - q, axis=1).min())


def _line_intersection(a1, b1, a2, b2):
    d1, d2 = b1 - a1, b2 - a2
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(cross) < 1e-300:
        return None
    w = a2 - a1
    s = (w[0] * d2[1] - w[1] * d2[0]) / cross
    return a1 + s * d1


def _chain(kernel, tags):
    """The curves in chain order, each oriented along the chain: ([(kind, points)], closed?)."""
    model = kernel.gmsh.model
    ends = {t: [x for _, x in model.getBoundary([(1, t)], combined=False, oriented=False)] for t in tags}
    kinds = {t: {"Line": "line", "Circle": "arc"}.get(model.getType(1, t), "spline") for t in tags}
    counts = {}
    for pts in ends.values():
        for x in set(pts):
            counts[x] = counts.get(x, 0) + 1
    start = next((t for t in tags if any(counts[x] == 1 for x in ends[t])), tags[0])
    order, used = [], set()
    current = start
    point = next((x for x in ends[start] if counts[x] == 1), ends[start][0])   # start at a free end
    while current is not None:
        used.add(current)
        pts = kernel.sample(current, 2 if kinds[current] == "line" else 129)
        first = np.asarray(model.getValue(0, point, []))[:2]
        if np.linalg.norm(pts[0] - first) > np.linalg.norm(pts[-1] - first):
            pts = pts[::-1]
        order.append((kinds[current], pts))
        other = [x for x in ends[current] if x != point] or [point]
        point = other[0]
        current = next((t for t in tags if t not in used and point in ends[t]), None)
    if len(used) != len(tags):
        raise ValueError("the chosen edges do not form one connected chain")
    closed = all(counts[x] == 2 for x in counts)
    return order, closed


OPERATIONS = {cls.type: cls for cls in (SplitFace, SplitEdge, Trim, Extend, Offset, Chamfer, Pattern, Fill,
                                        MergeFaces)}

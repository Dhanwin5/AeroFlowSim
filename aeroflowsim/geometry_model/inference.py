# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Inference snapping while drawing: where the cursor point should go, and why (no window needed).

When you draw, the cursor is pulled to "special" points within the pick tolerance (a few pixels
in metres), in this order:
    endpoint      a corner of the geometry or a point of the sketch being drawn
    intersection  where two edges cross
    centre        the centre of a circle arc
    midpoint      the middle of an edge
    tangent       from the last point, the point where a line touches a circle arc
    perpendicular from the last point, the foot of the perpendicular on an edge
    on curve      the nearest point on an edge
then the direction from the last point is pulled to multiples of ANGLE_STEP (0 = horizontal,
90 = vertical ...) and the cursor lines up horizontally / vertically with existing points; at
last the grid (if on). Each answer carries dashed guide lines and a short label for the screen.

The maths: the foot of the perpendicular from p on the line a + t (b - a) is at
t = (p - a).(b - a) / |b - a|²; two segments a1->b1 and a2->b2 cross where
a1 + s d1 = a2 + t d2 (solved with the 2D cross product); a line from p touches a circle
(centre c, radius r) at the points c + r (cos(phi +- beta)) with phi the direction from c to p
and cos(beta) = r / |p - c|.
"""

import math
from dataclasses import dataclass, field

import numpy as np

ANGLE_STEP = 15.0              # direction snapping step from the last point [deg]
ANGLE_TOLERANCE = 1.5          # within this of a multiple of the step, the direction snaps [deg]


@dataclass
class Inference:
    point: np.ndarray                         # (2,) the snapped point [m]
    kind: str = ""                            # "endpoint", "intersection", ..., "grid", or "" (no snap)
    guides: list = field(default_factory=list)   # [(a, b)] dashed helper lines [m]
    label: str = ""                           # short text for the screen, e.g. "endpoint", "90°"


def _segments(built):
    """(a, b, edge index) of every short straight piece of every edge, and the edge list."""
    if built is None or not built.edges:
        return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0, dtype=int), []
    edges = list(built.edges.values())
    a = np.vstack([e.points[:-1] for e in edges])
    b = np.vstack([e.points[1:] for e in edges])
    owner = np.concatenate([np.full(len(e.points) - 1, k) for k, e in enumerate(edges)])
    return a, b, owner, edges


def _foot(p, a, b):
    """Feet of the perpendiculars from p on the segments a->b (clipped to them), and the distances."""
    ab = b - a
    t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-300), 0.0, 1.0)
    foot = a + t[:, None] * ab
    return foot, np.linalg.norm(foot - p, axis=1)


def circle_of(points):
    """(centre, radius) of the circle through the start, middle and end of a point list, or None."""
    a, b, c = points[0], points[len(points) // 2], points[-1]
    if np.allclose(a, c):
        a, b, c = points[0], points[len(points) // 3], points[2 * len(points) // 3]
    d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-300:
        return None
    sq = [q @ q for q in (a, b, c)]
    centre = np.array([(sq[0] * (b[1] - c[1]) + sq[1] * (c[1] - a[1]) + sq[2] * (a[1] - b[1])) / d,
                       (sq[0] * (c[0] - b[0]) + sq[1] * (a[0] - c[0]) + sq[2] * (b[0] - a[0])) / d])
    return centre, float(np.linalg.norm(a - centre))


def segment_intersections(a, b, near, tolerance):
    """Crossing points of segment pairs (a[k] -> b[k]) within `tolerance` of the point `near`."""
    keep = np.flatnonzero(np.minimum(np.linalg.norm(a - near, axis=1), np.linalg.norm(b - near, axis=1))
                          <= tolerance + np.linalg.norm(b - a, axis=1))
    out = []
    for n, i in enumerate(keep):
        for j in keep[n + 1:]:
            d1, d2 = b[i] - a[i], b[j] - a[j]
            cross = d1[0] * d2[1] - d1[1] * d2[0]
            if abs(cross) < 1e-300:
                continue                                 # parallel
            w = a[j] - a[i]
            s = (w[0] * d2[1] - w[1] * d2[0]) / cross
            t = (w[0] * d1[1] - w[1] * d1[0]) / cross
            at_end = lambda u: u < 1e-9 or u > 1.0 - 1e-9
            # (two pieces that only touch at their ends - e.g. neighbouring pieces of one curve - do not count)
            if -1e-9 <= s <= 1 + 1e-9 and -1e-9 <= t <= 1 + 1e-9 and not (at_end(s) and at_end(t)):
                q = a[i] + s * d1
                if np.linalg.norm(q - near) <= tolerance:
                    out.append(q)
    return out


def infer(built, xy, tolerance, last=None, sketch_points=(), grid=None, sketch_segments=()) -> Inference:
    """Where the cursor at xy snaps to (see the module docstring).

    last: the previous point of the entity being drawn (for tangent / perpendicular / angles);
    sketch_points: points already placed in the sketch being drawn; sketch_segments: [(a, b)] its
    straight pieces (so it snaps to itself too); grid: the grid spacing [m] or None.
    """
    p = np.asarray(xy, dtype=float)
    last = None if last is None else np.asarray(last, dtype=float)
    # 1. endpoints: corners of the geometry and the sketch's own points
    candidates = [np.asarray(q, dtype=float) for q in sketch_points]
    if built is not None:
        candidates += [v.xy for v in built.vertices.values() if v.corner]
    if candidates:
        pts = np.array(candidates)
        d = np.linalg.norm(pts - p, axis=1)
        k = int(d.argmin())
        if d[k] <= tolerance:
            return Inference(pts[k].copy(), "endpoint", label="endpoint")
    a, b, owner, edges = _segments(built)
    if len(sketch_segments):
        sa = np.array([s[0] for s in sketch_segments], dtype=float)
        sb = np.array([s[1] for s in sketch_segments], dtype=float)
        a, b = np.vstack([a, sa]), np.vstack([b, sb])
        owner = np.concatenate([owner, np.full(len(sa), -1)])
    # 2. intersections of edges near the cursor
    if len(a):
        crossings = segment_intersections(a, b, p, tolerance)
        if crossings:
            q = min(crossings, key=lambda c: np.linalg.norm(c - p))
            return Inference(q, "intersection", label="intersection")
    # 3. centres of arcs, 4. midpoints of edges
    for edge in edges:
        if edge.kind == "arc":
            circle = circle_of(edge.points)
            if circle is not None and np.linalg.norm(circle[0] - p) <= tolerance:
                return Inference(circle[0], "centre", label="centre")
    for edge in edges:
        if np.linalg.norm(edge.midpoint - p) <= tolerance:
            return Inference(edge.midpoint, "midpoint", label="midpoint")
    for (sa, sb) in sketch_segments:
        mid = 0.5 * (np.asarray(sa) + np.asarray(sb))
        if np.linalg.norm(mid - p) <= tolerance:
            return Inference(mid, "midpoint", label="midpoint")
    if last is not None and len(a):
        # 5. tangent from the last point to an arc
        for edge in edges:
            if edge.kind != "arc":
                continue
            circle = circle_of(edge.points)
            if circle is None:
                continue
            c, r = circle
            dist = np.linalg.norm(last - c)
            if dist <= r:
                continue
            phi = math.atan2(last[1] - c[1], last[0] - c[0])
            beta = math.acos(r / dist)
            for angle in (phi + beta, phi - beta):
                q = c + r * np.array([math.cos(angle), math.sin(angle)])
                # on the arc (not just on its circle)? The edge's points are on the circle, the straight
                # pieces between them a little inside, so allow 1 % of the radius.
                on_arc = _foot(q, edge.points[:-1], edge.points[1:])[1].min() <= 0.01 * r
                if on_arc and np.linalg.norm(q - p) <= tolerance:
                    return Inference(q, "tangent", [(last, q)], "tangent")
        # 6. perpendicular foot from the last point on the edge nearest to the cursor
        foot_c, dist_c = _foot(p, a, b)
        k = int(dist_c.argmin())
        if dist_c[k] <= tolerance:
            ab = b[k] - a[k]
            t = ((last - a[k]) @ ab) / max(ab @ ab, 1e-300)
            if 0.0 <= t <= 1.0:
                q = a[k] + t * ab
                if np.linalg.norm(q - p) <= tolerance and np.linalg.norm(q - last) > tolerance:
                    return Inference(q, "perpendicular", [(last, q)], "perpendicular")
    # 7. on a curve
    if len(a):
        foot_c, dist_c = _foot(p, a, b)
        k = int(dist_c.argmin())
        if dist_c[k] <= tolerance:
            return Inference(foot_c[k], "on curve", label="on curve")
    # 8. direction from the last point in steps of ANGLE_STEP (horizontal / vertical are steps too)
    guides, label, q = [], "", p.copy()
    if last is not None and np.linalg.norm(p - last) > tolerance:
        d = p - last
        angle = math.degrees(math.atan2(d[1], d[0]))
        nearest = ANGLE_STEP * round(angle / ANGLE_STEP)
        if abs(angle - nearest) <= ANGLE_TOLERANCE:
            u = np.array([math.cos(math.radians(nearest)), math.sin(math.radians(nearest))])
            q = last + (d @ u) * u
            guides.append((last, last + 3.0 * (q - last)))
            label = {0: "horizontal", 180: "horizontal", -180: "horizontal", 90: "vertical",
                     -90: "vertical"}.get(int(round(nearest)), f"{nearest % 360:g}°")
            return Inference(q, "angle", guides, label)
    # 9. lined up horizontally / vertically with an existing point
    if candidates:
        pts = np.array(candidates)
        ix = int(np.abs(pts[:, 0] - p[0]).argmin())
        iy = int(np.abs(pts[:, 1] - p[1]).argmin())
        snap_x = abs(pts[ix, 0] - p[0]) <= tolerance
        snap_y = abs(pts[iy, 1] - p[1]) <= tolerance
        if snap_x or snap_y:
            q = np.array([pts[ix, 0] if snap_x else p[0], pts[iy, 1] if snap_y else p[1]])
            if snap_x:
                guides.append((pts[ix], q))
            if snap_y:
                guides.append((pts[iy], q))
            return Inference(q, "aligned", guides, "aligned")
    # 10. the grid
    if grid:
        return Inference(np.round(p / grid) * grid, "grid", label="")
    return Inference(p, "", label="")

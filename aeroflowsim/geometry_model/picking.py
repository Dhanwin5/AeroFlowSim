# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""What did the user click? Pure maths on a BuiltGeometry (no window needed, so it is tested directly).

The view turns the mouse position (pixels) into a world point (x, y) [m] and a tolerance
(a few pixels converted to metres). Then:
  - a VERTEX is picked if one lies within the tolerance (the nearest one);
  - else an EDGE: the distance from the point to every straight segment of every edge's points
    is computed exactly, and the nearest edge within the tolerance wins;
  - else a FACE: the smallest face whose loops contain the point (even-odd ray-casting test).

Distance from point p to the segment a -> b: the nearest point on the segment is a + t (b - a),
with t = clip( (p - a).(b - a) / |b - a|², 0, 1 ), so  d = | a + t (b - a) - p |.
"""

import numpy as np


def _edge_segments(built, edge_ids=None):
    """(a, b, owner): all segments of the edges' point lists, and which edge each belongs to."""
    ids = list(built.edges) if edge_ids is None else list(edge_ids)
    if not ids:
        return np.zeros((0, 2)), np.zeros((0, 2)), []
    a = np.vstack([built.edges[i].points[:-1] for i in ids])
    b = np.vstack([built.edges[i].points[1:] for i in ids])
    owner = np.concatenate([np.full(len(built.edges[i].points) - 1, k) for k, i in enumerate(ids)])
    return a, b, [ids[k] for k in owner]


def distance_to_segments(p, a, b) -> np.ndarray:
    """Distance from point p (2,) to every segment a[k] -> b[k] [m]."""
    ab = b - a
    t = np.clip(((p - a) * ab).sum(axis=1) / np.maximum((ab * ab).sum(axis=1), 1e-300), 0.0, 1.0)
    return np.linalg.norm(a + t[:, None] * ab - p, axis=1)


def nearest_edge(built, xy, tolerance, edge_ids=None):
    """(edge id, distance [m]) of the edge nearest to the point xy, or None if none is within tolerance."""
    a, b, owner = _edge_segments(built, edge_ids)
    if not owner:
        return None
    d = distance_to_segments(np.asarray(xy, dtype=float), a, b)
    k = int(d.argmin())
    return (owner[k], float(d[k])) if d[k] <= tolerance else None


def nearest_vertex(built, xy, tolerance):
    """(vertex id, distance [m]) of the nearest vertex within tolerance, or None."""
    if not built.vertices:
        return None
    ids = list(built.vertices)
    pts = np.array([built.vertices[i].xy for i in ids])
    d = np.linalg.norm(pts - np.asarray(xy, dtype=float), axis=1)
    k = int(d.argmin())
    return (ids[k], float(d[k])) if d[k] <= tolerance else None


def point_in_polygon(xy, polygon) -> bool:
    """Even-odd rule: a ray from xy to +x crosses the closed polygon an odd number of times."""
    x, y = float(xy[0]), float(xy[1])
    p, q = polygon, np.roll(polygon, -1, axis=0)
    crosses = (p[:, 1] > y) != (q[:, 1] > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_cross = p[:, 0] + (y - p[:, 1]) * (q[:, 0] - p[:, 0]) / (q[:, 1] - p[:, 1])
    return bool(np.count_nonzero(crosses & (x < x_cross)) % 2)


def face_at(built, xy):
    """Id of the smallest face containing xy (inside its outer loop, outside its holes), or None."""
    best = None
    for face in built.faces.values():
        if not face.loops:
            continue
        inside = point_in_polygon(xy, built.loop_points(face.loops[0])) and not any(
            point_in_polygon(xy, built.loop_points(loop)) for loop in face.loops[1:])
        if inside and (best is None or face.area < best.area):
            best = face
    return None if best is None else best.id


def pick(built, xy, tolerance, kinds=("vertex", "edge", "face")):
    """("vertex" | "edge" | "face", id) under the point xy, or None. Vertices win over edges, edges over faces."""
    if "vertex" in kinds:
        hit = nearest_vertex(built, xy, tolerance)
        if hit is not None:
            return "vertex", hit[0]
    if "edge" in kinds:
        hit = nearest_edge(built, xy, tolerance)
        if hit is not None:
            return "edge", hit[0]
    if "face" in kinds:
        face = face_at(built, xy)
        if face is not None:
            return "face", face
    return None


def edges_in_box(built, x0, y0, x1, y1) -> list:
    """Ids of the edges lying completely inside a box (rubber-band selection)."""
    lo, hi = np.array([min(x0, x1), min(y0, y1)]), np.array([max(x0, x1), max(y0, y1)])
    return [e.id for e in built.edges.values() if np.all((e.points >= lo) & (e.points <= hi))]

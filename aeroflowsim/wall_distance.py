# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exact distance from every cell centre to the nearest no-slip wall (2D, axisymmetric and 3D).

Turbulence models need d, the distance to the nearest wall (Spalart-Allmaras destruction term, SST blending
functions), and y+ needs the distance of the first cell. Serious codes compute it exactly once per mesh (SU2, Fluent
"wall distance"), not by solving a PDE approximation, because the near-wall values must be exact.

Method:
1. The wall faces are segments (2D) or triangles (3D; a quad or polygon face is split into the triangles round its
   centre, as in mesh._face_geometry).
2. A KD-tree on the wall-face centres gives, for each point, its k nearest face centres; the EXACT distance from the
   point to each of these faces (point-segment / point-triangle closest point, Ericson 2005 sec. 5.1) is computed and
   the smallest kept.
3. Exactness check: a face whose centre is further than (best distance + largest face radius) cannot be closer. If the
   k-th nearest centre is still within that bound, k is raised (8, 32, 128, ... all faces) for those points only.
So the result is the exact minimum over all wall faces, at a cost close to k log N per point.

Axisymmetric meshes: the distance in the meridional (x, r) plane is the true 3D distance to the surface of revolution.
"""

import numpy as np
from scipy.spatial import cKDTree


def _wall_elements(mesh, wall_patches):
    """Segments (2D: (n, 2, 2)) or triangles (3D: (n, 3, 3)) of the named wall patches, and the parent face ids."""
    faces = np.concatenate([np.arange(p.start, p.start + p.count) for p in mesh.patches if p.name in wall_patches]
                           ) if wall_patches else np.zeros(0, dtype=np.int64)
    dim = mesh.dim
    nodes = mesh.nodes[:, :dim]
    if dim == 2:
        fn = mesh.face_nodes[faces, :2]
        return nodes[fn], faces
    tris, parent = [], []
    fn_all = mesh.face_nodes[faces]
    counts = np.count_nonzero(fn_all >= 0, axis=1)
    for k in np.unique(counts).tolist():
        sel = np.flatnonzero(counts == k)
        pts = nodes[fn_all[sel, :k]]                    # (m, k, 3)
        if k == 3:
            tris.append(pts)
            parent.append(faces[sel])
            continue
        mid = pts.mean(axis=1)
        for i in range(k):
            tris.append(np.stack([pts[:, i], pts[:, (i + 1) % k], mid], axis=1))
            parent.append(faces[sel])
    return np.concatenate(tris), np.concatenate(parent)


def _segment_distance(P, A, B):
    """Distance from points P (n, 2) to segments A-B (n, 2)."""
    AB = B - A
    t = np.einsum("nk,nk->n", P - A, AB) / np.maximum(np.einsum("nk,nk->n", AB, AB), 1e-300)
    t = np.clip(t, 0.0, 1.0)
    Q = A + t[:, None] * AB
    return np.linalg.norm(P - Q, axis=1)


def _triangle_distance(P, A, B, C):
    """Distance from points P (n, 3) to triangles ABC (each (n, 3)): closest point by Voronoi regions (Ericson 2005,
    'Real-Time Collision Detection', sec. 5.1.5), vectorised."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = np.einsum("nk,nk->n", ab, ap), np.einsum("nk,nk->n", ac, ap)
    bp = P - B
    d3, d4 = np.einsum("nk,nk->n", ab, bp), np.einsum("nk,nk->n", ac, bp)
    cp = P - C
    d5, d6 = np.einsum("nk,nk->n", ab, cp), np.einsum("nk,nk->n", ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    Q = np.empty_like(P)
    done = np.zeros(len(P), dtype=bool)

    def put(mask, value):
        m = mask & ~done
        Q[m] = value[m]
        done[m] = True

    put((d1 <= 0) & (d2 <= 0), A)
    put((d3 >= 0) & (d4 <= d3), B)
    with np.errstate(divide="ignore", invalid="ignore"):
        v = d1 / (d1 - d3)
        put((vc <= 0) & (d1 >= 0) & (d3 <= 0), A + v[:, None] * ab)
        put((d6 >= 0) & (d5 <= d6), C)
        w = d2 / (d2 - d6)
        put((vb <= 0) & (d2 >= 0) & (d6 <= 0), A + w[:, None] * ac)
        w2 = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        put((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), B + w2[:, None] * (C - B))
        denom = 1.0 / (va + vb + vc)
        v3, w3 = vb * denom, vc * denom
        inside = A + v3[:, None] * ab + w3[:, None] * ac
    put(np.ones(len(P), dtype=bool), inside)
    return np.linalg.norm(P - Q, axis=1)


def distances(points, elements):
    """Exact distance from each point (n, dim) to the nearest element (segments or triangles); inf without walls.
    Also returns the index of the nearest element."""
    n = len(points)
    if len(elements) == 0:
        return np.full(n, np.inf), np.full(n, -1)
    centres = elements.mean(axis=1)
    radius = float(np.max(np.linalg.norm(elements - centres[:, None, :], axis=2)))   # largest element radius
    tree = cKDTree(centres)
    best = np.full(n, np.inf)
    which = np.full(n, -1)
    todo = np.arange(n)
    k = min(8, len(elements))
    while len(todo):
        dc, idx = tree.query(points[todo], k=k)
        if k == 1:
            dc, idx = dc[:, None], idx[:, None]
        for j in range(k):
            e = elements[idx[:, j]]
            if elements.shape[1] == 2:
                d = _segment_distance(points[todo], e[:, 0], e[:, 1])
            else:
                d = _triangle_distance(points[todo], e[:, 0], e[:, 1], e[:, 2])
            closer = d < best[todo]
            best[todo[closer]] = d[closer]
            which[todo[closer]] = idx[closer, j]
        if k >= len(elements):
            break
        # a further element could still be closer only if the k-th centre lies within best + radius
        unsure = dc[:, -1] - radius < best[todo]
        todo = todo[unsure]
        k = min(4 * k, len(elements))
    return best, which


def wall_distance(mesh, wall_patches):
    """Distance [m] from every cell centre to the nearest face of the named wall patches (inf without walls)."""
    elements, _parent = _wall_elements(mesh, set(wall_patches))
    return distances(mesh.cell_centres[:, :mesh.dim], elements)[0]


__all__ = ["wall_distance", "distances"]

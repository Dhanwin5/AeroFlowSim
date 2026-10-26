# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Values at points, along lines (exact per cell) and on another mesh.

Point value: the cell that contains the point, and the solver's own linear reconstruction inside it,
    phi(x) = phi_c + grad(phi)_c . (x - x_c)
(least-squares gradient, no limiter: smooth regions are second-order accurate; at a shock the value may
overshoot by the size of the jump across one cell, as any unlimited reconstruction).
"Cell values" mode returns phi_c itself (honest inspection), "node" mode the inverse-distance node values
interpolated inside the cell.

Line sampling: the line is cut at every mesh face it crosses; each piece lies in exactly one cell, so the
value along the piece is that cell's linear reconstruction. The samples are the two ends of every piece:
where two cells meet there are two values at the same position (the jump between the cells' reconstructions
is shown, not hidden). Integrals along the line use these pieces with 2-point Gauss quadrature, which is exact
for the linear value times the linear radius of an axisymmetric surface.

Interpolation onto a new mesh: inverse-distance weighting from the k nearest old cell centres (scipy cKDTree),
k = 4 by default; an old cell centre that coincides with a new one is copied exactly.
"""

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from aeroflowsim.post.fields import boundary_face_values, field_values, node_values

LINEAR, CELL, NODE = "linear", "cell", "node"


def _tree(sol):
    if "_tree" not in sol._cache:
        sol._cache["_tree"] = cKDTree(sol.geom.cell_centres[:, :2])
    return sol._cache["_tree"]


def _cell_polygons(sol):
    """(C, k, 2) corner coordinates of every 2D cell (padded with the first corner) and the corner counts."""
    if "_polygons" not in sol._cache:
        cn = sol.mesh.cell_nodes
        counts = (cn >= 0).sum(axis=1)
        safe = np.where(cn >= 0, cn, cn[:, :1])
        sol._cache["_polygons"] = (sol.mesh.nodes[safe, :2], counts)
    return sol._cache["_polygons"]


def _inside(points, polys, counts):
    """True where the point lies inside (or on the edge of) its polygon (winding by edge cross products)."""
    k = polys.shape[1]
    sign_pos = np.ones(len(points), dtype=bool)
    sign_neg = np.ones(len(points), dtype=bool)
    for i in range(k):
        a = polys[:, i]
        b = np.where((i + 1 < counts)[:, None], polys[:, (i + 1) % k], polys[:, 0])
        valid = i < counts
        cross = (b[:, 0] - a[:, 0]) * (points[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (points[:, 0] - a[:, 0])
        tol = 1e-12 * np.maximum(np.abs(b - a).sum(axis=1), 1e-300) ** 2
        sign_pos &= ~valid | (cross >= -tol)
        sign_neg &= ~valid | (cross <= tol)
    return sign_pos | sign_neg


def locate(sol, points, candidates=12) -> np.ndarray:
    """(n,) index of the cell containing each point (x, y), or -1 outside the mesh."""
    pts = np.atleast_2d(np.asarray(points, dtype=float))[:, :2]
    polys, counts = _cell_polygons(sol)
    k = min(candidates, sol.mesh.n_cells)
    _, idx = _tree(sol).query(pts, k=k)
    idx = idx.reshape(len(pts), k)
    out = np.full(len(pts), -1, dtype=np.int64)
    todo = np.ones(len(pts), dtype=bool)
    for j in range(k):
        c = idx[:, j]
        hit = todo & _inside(pts, polys[c], counts[c])
        out[hit] = c[hit]
        todo &= ~hit
        if not todo.any():
            break
    if todo.any():                                  # rare: a long thin cell whose centre is far away
        for i in np.flatnonzero(todo):
            hit = np.flatnonzero(_inside(np.repeat(pts[i:i + 1], len(polys), 0), polys, counts))
            if len(hit):
                out[i] = hit[0]
    return out


def field_gradient(sol, name):
    """Least-squares gradient (2, C) of a field (boundary values from the boundary condition)."""
    cache = sol._cache.setdefault("gradients_of", {})
    if name not in cache:
        values = field_values(sol, name)
        cache[name] = sol.gradient_of(values, boundary_face_values(sol, name))
    return cache[name]


def values_at(sol, name, points, cells=None, mode=LINEAR) -> np.ndarray:
    """(n,) field values at points (NaN outside the mesh). cells: the containing cells if known."""
    pts = np.atleast_2d(np.asarray(points, dtype=float))[:, :2]
    cells = locate(sol, pts) if cells is None else np.asarray(cells)
    out = np.full(len(pts), np.nan)
    ok = cells >= 0
    c = cells[ok]
    values = field_values(sol, name)
    if mode == CELL:
        out[ok] = values[c]
    elif mode == NODE:
        out[ok] = _node_interpolation(sol, name, pts[ok], c)
    else:
        g = field_gradient(sol, name)
        d = pts[ok] - sol.geom.cell_centres[c, :2]
        out[ok] = values[c] + g[0, c] * d[:, 0] + g[1, c] * d[:, 1]
    return out


def _node_interpolation(sol, name, pts, cells):
    """Inverse-distance mean of the cell's node values at the points (smooth across cells)."""
    nv = node_values(sol, name)
    polys, counts = _cell_polygons(sol)
    cn = sol.mesh.cell_nodes[cells]
    corners = polys[cells]
    d = np.linalg.norm(corners - pts[:, None, :], axis=2)
    w = np.where(cn >= 0, 1.0 / np.maximum(d, 1e-300), 0.0)
    exact = d < 1e-14
    w = np.where(exact.any(axis=1)[:, None], exact.astype(float), w)
    return np.sum(w * nv[np.where(cn >= 0, cn, 0)], axis=1) / np.sum(w, axis=1)


# ---- lines ------------------------------------------------------------------------------------------

@dataclass
class LinePieces:
    """A straight line cut into pieces, one per cell it crosses (pieces outside the mesh are left out)."""

    start: np.ndarray        # (2,) [m]
    end: np.ndarray          # (2,) [m]
    t0: np.ndarray           # (n,) start of each piece as a fraction of the line [0, 1]
    t1: np.ndarray           # (n,) end of each piece
    cells: np.ndarray        # (n,) cell of each piece

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.end - self.start))

    def points(self, t) -> np.ndarray:
        t = np.asarray(t, dtype=float)
        return self.start[None, :] + t[:, None] * (self.end - self.start)[None, :]

    @property
    def normal(self) -> np.ndarray:
        """Unit normal of the line: the direction vector turned 90 deg clockwise ((dy, -dx) / L)."""
        d = (self.end - self.start) / max(self.length, 1e-300)
        return np.array([d[1], -d[0]])


def cut_line(sol, start, end) -> LinePieces:
    """Cut the segment start -> end at every face it crosses (2D meshes)."""
    p0, p1 = np.asarray(start, dtype=float)[:2], np.asarray(end, dtype=float)[:2]
    d = p1 - p0
    mesh = sol.mesh
    fn = mesh.face_nodes[:, :2]
    a, b = mesh.nodes[fn[:, 0], :2], mesh.nodes[fn[:, 1], :2]
    e = b - a
    denom = d[0] * e[:, 1] - d[1] * e[:, 0]
    ok = np.abs(denom) > 1e-300
    w = a - p0
    t = np.where(ok, (w[:, 0] * e[:, 1] - w[:, 1] * e[:, 0]) / np.where(ok, denom, 1.0), np.nan)
    s = np.where(ok, (w[:, 0] * d[1] - w[:, 1] * d[0]) / np.where(ok, denom, 1.0), np.nan)
    hit = ok & (t > 0.0) & (t < 1.0) & (s >= -1e-12) & (s <= 1.0 + 1e-12)
    ts = np.unique(np.concatenate([[0.0, 1.0], t[hit]]))
    keep = np.concatenate([[True], np.diff(ts) > 1e-12])
    ts = ts[keep]
    if ts[-1] < 1.0:
        ts[-1] = 1.0
    mids = 0.5 * (ts[:-1] + ts[1:])
    cells = locate(sol, p0[None, :] + mids[:, None] * d[None, :])
    inside = cells >= 0
    return LinePieces(p0, p1, ts[:-1][inside], ts[1:][inside], cells[inside])


def sample_line(sol, name, start, end, mode=LINEAR):
    """Values along a line: (t, points (n, 2), values) with t the fraction along the line; two samples per piece
    (its ends), so the result is exact per cell. NaN-free: parts outside the mesh are left out."""
    pieces = cut_line(sol, start, end)
    t = np.column_stack([pieces.t0, pieces.t1]).ravel()
    cells = np.repeat(pieces.cells, 2)
    pts = pieces.points(t)
    return t, pts, values_at(sol, name, pts, cells, mode)


def interpolate_cells(old_centres, old_values, new_centres, k=4) -> np.ndarray:
    """Cell values (n_vars, C_old) moved onto new cell centres (n_vars, C_new) by inverse-distance weighting of the
    k nearest old centres (Shepard). Used to start a run on a refined mesh from the old solution."""
    old_values = np.atleast_2d(np.asarray(old_values, dtype=float))
    tree = cKDTree(np.asarray(old_centres, dtype=float)[:, :2])
    k = min(k, len(old_centres))
    dist, idx = tree.query(np.asarray(new_centres, dtype=float)[:, :2], k=k)
    dist, idx = dist.reshape(len(new_centres), k), idx.reshape(len(new_centres), k)
    exact = dist[:, 0] < 1e-14
    w = 1.0 / np.maximum(dist, 1e-300)
    w[exact] = 0.0
    w[exact, 0] = 1.0
    w /= w.sum(axis=1, keepdims=True)
    return np.einsum("vck,ck->vc", old_values[:, idx], w)

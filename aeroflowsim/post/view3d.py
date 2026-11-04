# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""3D post-processing without Qt or VTK: slice planes, iso-surfaces, wall surfaces, probes and 3D streamlines.

Every picture is a triangle surface: points (P, 3) [m], triangles (T, 3) and one value per point. The GUI draws it with
PyVista; the report and the command line can draw or export it without VTK.

Slices and iso-surfaces use MARCHING TETRAHEDRA: every cell is split into tetrahedra (a hexahedron into 6, a prism into
3, a pyramid into 2); in a tetrahedron the scalar s (the signed distance to the plane, or field - level) is linear, so
where s changes sign along an edge the surface crosses it at  t = s_a / (s_a - s_b)  and the surface piece in the
tetrahedron is a triangle (one node on the other side) or a quadrilateral (two and two). Only the cells whose node
values straddle zero are split: the work is proportional to the cells on the surface, not to the whole volume (a slice
of a 719k-cell mesh touches a few thousand cells). Node values come from the cell values by the inverse-distance mean of
post.fields.node_values.
"""

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from aeroflowsim.mesh import HEXAHEDRON, PYRAMID, TETRA, WEDGE

TET_SPLIT = {
    TETRA: [(0, 1, 2, 3)],
    PYRAMID: [(0, 1, 2, 4), (0, 2, 3, 4)],
    WEDGE: [(0, 1, 2, 5), (0, 1, 5, 4), (0, 4, 5, 3)],
    HEXAHEDRON: [(0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6)],
}
EDGES = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))


@dataclass
class Surface:
    """A triangle surface with one value per point."""

    points: np.ndarray       # (P, 3) [m]
    triangles: np.ndarray    # (T, 3) point numbers
    values: np.ndarray       # (P,)

    @property
    def n_triangles(self) -> int:
        return len(self.triangles)


def _empty():
    return Surface(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), np.zeros(0))


def tetrahedra_of(mesh, cells) -> np.ndarray:
    """(n, 4) node numbers of the tetrahedra of the given cells."""
    out = []
    types = mesh.cell_types[cells]
    for t, split in TET_SPLIT.items():
        sel = cells[types == t]
        if len(sel):
            conn = mesh.cell_nodes[sel]
            out += [conn[:, list(tet)] for tet in split]
    return np.vstack(out) if out else np.zeros((0, 4), dtype=np.int64)


def _march(mesh, cells, s_node, colour_node) -> Surface:
    """Zero surface of the node scalar s inside the given cells (marching tetrahedra)."""
    tets = tetrahedra_of(mesh, cells)
    if not len(tets):
        return _empty()
    s = s_node[tets]
    pos = s > 0.0
    mask = (pos * np.array([1, 2, 4, 8])).sum(axis=1)
    pts, vals, tris = [], [], []
    count = 0

    def cut(a, b, rows):
        na, nb = tets[rows, a], tets[rows, b]
        sa, sb = s_node[na], s_node[nb]
        t = (sa / np.where(sa != sb, sa - sb, 1.0))[:, None]
        xyz = mesh.nodes[na] + t * (mesh.nodes[nb] - mesh.nodes[na])
        val = colour_node[na] + t[:, 0] * (colour_node[nb] - colour_node[na])
        return xyz, val

    for m in range(1, 15):
        rows = np.flatnonzero(mask == m)
        if not len(rows):
            continue
        inside = [i for i in range(4) if m & (1 << i)]
        outside = [i for i in range(4) if not m & (1 << i)]
        if len(inside) in (1, 3):
            odd = inside if len(inside) == 1 else outside
            rest = outside if len(inside) == 1 else inside
            edges = [(odd[0], r) for r in rest]
            local = [(0, 1, 2)]
        else:
            a, b = inside
            c, d = outside
            edges = [(a, c), (a, d), (b, d), (b, c)]
            local = [(0, 1, 2), (0, 2, 3)]
        corners = [cut(e0, e1, rows) for e0, e1 in edges]
        n = len(rows)
        for xyz, val in corners:
            pts.append(xyz)
            vals.append(val)
        base = count + np.arange(n)
        for tri in local:
            tris.append(np.column_stack([base + tri[0] * n, base + tri[1] * n, base + tri[2] * n]))
        count += n * len(corners)
    return Surface(np.vstack(pts), np.vstack(tris), np.concatenate(vals))


def slice_plane(mesh, colour_node, origin, normal) -> Surface:
    """The plane through `origin` with `normal`, coloured by the node values colour_node (N,)."""
    normal = np.asarray(normal, dtype=float)
    normal = normal / np.linalg.norm(normal)
    s_node = (mesh.nodes - np.asarray(origin, dtype=float)) @ normal
    return _march(mesh, _straddling(mesh, s_node), s_node, np.asarray(colour_node, dtype=float))


def iso_surface(mesh, field_node, level, colour_node=None) -> Surface:
    """The surface field = level, coloured by colour_node (default: the field itself)."""
    s_node = np.asarray(field_node, dtype=float) - float(level)
    colour = field_node if colour_node is None else colour_node
    return _march(mesh, _straddling(mesh, s_node), s_node, np.asarray(colour, dtype=float))


def _straddling(mesh, s_node) -> np.ndarray:
    """Cells whose node values have both signs (only these can contain the surface)."""
    cn = mesh.cell_nodes
    v = np.where(cn >= 0, s_node[np.maximum(cn, 0)], np.nan)
    return np.flatnonzero((np.nanmin(v, axis=1) < 0.0) & (np.nanmax(v, axis=1) > 0.0))


def patch_surface(mesh, names, colour_node) -> Surface:
    """The boundary faces of the named patches (quads split into two triangles), coloured by node values."""
    faces = [mesh.patch(n).faces for n in names]
    if not faces:
        return _empty()
    fn = mesh.face_nodes[np.concatenate(faces)]
    tri = np.vstack([fn[:, [0, 1, 2]], fn[fn[:, 3] >= 0][:, [0, 2, 3]]])
    used, inverse = np.unique(tri, return_inverse=True)
    return Surface(mesh.nodes[used], inverse.reshape(-1, 3), np.asarray(colour_node, dtype=float)[used])


def probe(mesh, point, fields) -> dict:
    """{name: value} of the cell whose centre is nearest to the point (and "cell": its number)."""
    cell = int(cKDTree(mesh.cell_centres).query(np.asarray(point, dtype=float))[1])
    return {"cell": cell, **{k: float(np.asarray(v)[cell]) for k, v in fields.items()}}


def streamlines(mesh, velocity, seeds, max_steps=2000, k=4):
    """3D streamlines from seed points: [(n, 3) polyline] by second-order Runge-Kutta (Heun) through the cell-centre
    velocity (3, C), interpolated by inverse distance of the k nearest centres. The step is half the local cell size; a
    line stops where it leaves the mesh (farther than two cell sizes from every centre) or the speed is ~0."""
    centres = mesh.cell_centres
    tree = cKDTree(centres)
    h = np.abs(mesh.cell_volumes) ** (1.0 / 3.0)
    vel = np.asarray(velocity, dtype=float).T

    def at(x):
        d, i = tree.query(x, k=k)
        w = 1.0 / np.maximum(d, 1e-300)
        return (vel[i] * w[:, None]).sum(axis=0) / w.sum(), d[0], h[i[0]]

    lines = []
    for x in np.asarray(seeds, dtype=float):
        line = [x.copy()]
        for _ in range(max_steps):
            u, dist, size = at(x)
            speed = np.linalg.norm(u)
            if dist > 2.0 * size or speed < 1e-12:
                break
            dt = 0.5 * size / speed
            u2, _, _ = at(x + dt * u)
            x = x + 0.5 * dt * (u + u2)
            line.append(x.copy())
        lines.append(np.array(line))
    return lines

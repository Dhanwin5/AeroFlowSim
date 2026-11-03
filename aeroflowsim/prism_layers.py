# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Prism inflation layers for 3D meshes: thin layers of prisms (wedges) grown out from wall triangles.

The 3D form of aeroflowsim/inflation_layers.py, used by aeroflowsim/workspace_mesh3d.py: Gmsh first
meshes the surfaces (triangles), this module grows the layers from the wall triangles, and Gmsh then
fills the rest of the volume (outside the outermost layer) with tetrahedra. Fluent Meshing, Pointwise
(T-Rex) and Star-CCM+ grow their prism layers the same way ("extrude the layers first").

How the layers are grown, in plain words:
    Every wall triangle is oriented with its normal pointing INTO the fluid. At every wall node a
    straight "column" of nodes goes into the fluid along the node normal N, one node per layer, at
        H_j = s h (1 + g + g² + ... + g^(j-1)),   j = 1 ... n_layers
    (h = first layer height, g = growth rate, s = the "mitre" stretch below). The three columns of a
    wall triangle make one prism per layer (bottom triangle at layer j-1, top triangle at layer j).

    Node normal N: the average of the normals of the wall triangles around the node, each weighted by
    its corner angle there (so a fine and a coarse triangle count the same). At an edge or corner of
    the wall (e.g. a box edge) the layers would get thinner by the cosine between N and the triangle
    normals, so the heights are stretched by s = 1 / min(N . n_k), at most MAX_MITRE.

    Edge of the wall: where the wall meets another boundary (a symmetry plane, an inlet or outlet
    plane), the column must stay IN that boundary so the layers end cleanly on it: N is projected
    into the plane of every such neighbouring boundary (so a node where two planes meet the wall
    moves along their line of intersection). Only flat neighbouring boundaries are possible this way;
    a curved one is refused with a clear message.

    The normals are then smoothed (each node's normal moves towards the average of its neighbours',
    the projections are applied again) until no prism is inverted; if the layers still fold over (too
    thick for a narrow gap or a tight curve), a clear error says so instead of returning a broken mesh.
"""

import math
from dataclasses import dataclass

import numpy as np

MAX_MITRE = 2.0       # largest stretch 1/cos of the heights at a wall edge or corner [-]
SMOOTHING_PASSES = (0, 2, 5, 10, 20, 50, 100)   # tried in turn until no prism is inverted
SMOOTHING_WEIGHT = 0.5   # each pass: N <- (1 - w) N + w (average of the neighbours' N) [-]


@dataclass
class PrismLayers:
    """Prism layers: the new nodes and cells; node numbers continue after the base mesh's nodes."""

    nodes: np.ndarray        # (P, 3) new nodes [m] (numbered first_node, first_node + 1, ...)
    prisms: np.ndarray       # (T * n_layers, 6) node numbers in VTK wedge order
    top: np.ndarray          # (T, 3) the outermost layer's triangles, normals into the fluid
    columns: np.ndarray      # (W, n_layers + 1) node numbers of every column, from the wall node up
    wall_nodes: np.ndarray   # (W,) the wall node of every column
    side_quads: dict         # {boundary edge (a, b): (n_layers, 4) quads of the layer sides along it}
    heights: np.ndarray      # (W,) total height of every column [m]


def _unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n > 0.0, n, 1.0)


def triangle_normals(nodes, tris) -> np.ndarray:
    """(T, 3) unit normals of triangles (right-hand rule)."""
    a, b, c = (nodes[tris[:, k]] for k in range(3))
    return _unit(np.cross(b - a, c - a))


def node_normals(nodes, tris) -> tuple:
    """Angle-weighted node normals of the triangles' nodes: (wall node numbers (W,), normals (W, 3), stretch (W,))."""
    wall = np.unique(tris)
    index = np.full(int(tris.max()) + 1, -1, dtype=np.int64)
    index[wall] = np.arange(len(wall))
    n_tri = triangle_normals(nodes, tris)
    acc = np.zeros((len(wall), 3))
    for k in range(3):                                 # the corner angle of every triangle at its node k
        p, q, r = nodes[tris[:, k]], nodes[tris[:, (k + 1) % 3]], nodes[tris[:, (k + 2) % 3]]
        u, v = _unit(q - p), _unit(r - p)
        angle = np.arccos(np.clip(np.einsum("ij,ij->i", u, v), -1.0, 1.0))
        np.add.at(acc, index[tris[:, k]], angle[:, None] * n_tri)
    normals = _unit(acc)
    lowest = np.full(len(wall), 1.0)                   # min over the triangles at a node of N . n_k
    for k in range(3):
        np.minimum.at(lowest, index[tris[:, k]], np.einsum("ij,ij->i", normals[index[tris[:, k]]], n_tri))
    stretch = 1.0 / np.clip(lowest, 1.0 / MAX_MITRE, 1.0)
    return wall, normals, stretch


def boundary_edges(tris) -> np.ndarray:
    """(E, 2) edges used by only one triangle (the edge of an open wall), in the triangles' direction."""
    edges = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    key = np.sort(edges, axis=1)
    _, inverse, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    return edges[counts[inverse.reshape(-1)] == 1]


def grow_prisms(nodes, wall_tris, first_height, n_layers, growth, planes=None) -> PrismLayers:
    """Grow n_layers prism layers from wall triangles (normals into the fluid); see the module text.

    nodes      (N, 3) all nodes of the surface mesh [m]
    wall_tris  (T, 3) wall triangles, oriented with their normal pointing into the fluid
    planes     {wall node: [unit normals of the flat neighbouring boundaries it lies on]}: the column
               of that node is kept in those planes
    """
    nodes = np.asarray(nodes, dtype=float)
    wall_tris = np.asarray(wall_tris, dtype=np.int64)
    if len(wall_tris) == 0:
        raise ValueError("There are no wall faces to grow inflation layers from.")
    if not (first_height > 0.0 and n_layers >= 1 and growth >= 1.0):
        raise ValueError("Inflation layers need a positive first-layer height, at least one layer and a growth "
                         "rate of at least 1.")
    planes = planes or {}
    wall, normals0, stretch = node_normals(nodes, wall_tris)
    index = np.full(len(nodes), -1, dtype=np.int64)
    index[wall] = np.arange(len(wall))
    constrained = {int(index[n]): np.asarray(p, dtype=float) for n, p in planes.items() if index[n] >= 0}
    neighbours = _neighbours(index[wall_tris], len(wall))
    offsets = np.r_[0.0, np.cumsum(first_height * growth ** np.arange(n_layers))]     # (n_layers + 1,) [m]
    first_node = len(nodes)
    columns = np.empty((len(wall), n_layers + 1), dtype=np.int64)
    columns[:, 0] = wall
    columns[:, 1:] = first_node + np.arange(len(wall) * n_layers).reshape(len(wall), n_layers)
    local = index[wall_tris]
    for passes in SMOOTHING_PASSES:
        normals = _project(normals0.copy(), constrained)
        for _ in range(passes):
            mean = np.array([normals[nb].mean(axis=0) if len(nb) else normals[k] for k, nb in enumerate(neighbours)])
            normals = _project(_unit((1.0 - SMOOTHING_WEIGHT) * normals + SMOOTHING_WEIGHT * mean), constrained)
        # keep the mitre stretch relative to the smoothed normal, never below 1
        height = stretch[:, None] * offsets[None, :]
        layer_nodes = nodes[wall][:, None, :] + height[:, :, None] * normals[:, None, :]   # (W, n+1, 3)
        if _all_positive(layer_nodes, local):
            break
    else:
        raise ValueError(f"The {n_layers} inflation layers ({offsets[-1]:.3g} m thick) fold over: they are too thick "
                         "for a narrow gap or a tight curve of the wall. Use a smaller first-layer height, fewer "
                         "layers or a smaller growth rate.")
    new_nodes = layer_nodes[:, 1:, :].reshape(-1, 3)
    prisms = []
    for j in range(n_layers):
        lo, hi = columns[local, j], columns[local, j + 1]
        # VTK wedge: (0, 1, 2) with its normal pointing out of the cell (into the wall) = the wall triangle reversed
        prisms.append(np.column_stack([lo[:, 0], lo[:, 2], lo[:, 1], hi[:, 0], hi[:, 2], hi[:, 1]]))
    sides = {}
    for a, b in boundary_edges(wall_tris).tolist():
        ca, cb = columns[index[a]], columns[index[b]]
        sides[(a, b)] = np.column_stack([ca[:-1], cb[:-1], cb[1:], ca[1:]])
    return PrismLayers(new_nodes, np.vstack(prisms), columns[local, -1], columns, wall, sides,
                       stretch * offsets[-1])


def _neighbours(local_tris, n) -> list:
    """For every wall node (local number), the local numbers of the nodes it shares a triangle edge with."""
    pairs = np.vstack([local_tris[:, [0, 1]], local_tris[:, [1, 2]], local_tris[:, [2, 0]]])
    pairs = np.unique(np.sort(np.vstack([pairs, pairs[:, ::-1]]), axis=1), axis=0)
    out = [[] for _ in range(n)]
    for a, b in pairs.tolist():
        out[a].append(b)
        out[b].append(a)
    return [np.asarray(nb, dtype=np.int64) for nb in out]


def _project(normals, constrained):
    """Keep the constrained columns in their planes (remove the component along each plane normal, in turn)."""
    for k, plane_normals in constrained.items():
        v = normals[k]
        basis = []                                  # orthonormal basis of the plane normals (Gram-Schmidt)
        for m in plane_normals:
            for e in basis:
                m = m - np.dot(m, e) * e
            if np.linalg.norm(m) > 1e-9:
                basis.append(m / np.linalg.norm(m))
        for e in basis:
            v = v - np.dot(v, e) * e
        if np.linalg.norm(v) < 1e-9:
            raise ValueError("A wall node lies where the neighbouring boundaries leave no direction for the inflation "
                             "layers to grow (the wall meets them at a sharp corner).")
        normals[k] = v / np.linalg.norm(v)
    return normals


def _all_positive(layer_nodes, local) -> bool:
    """True if every prism of every layer has a positive volume (split into three tetrahedra)."""
    for j in range(layer_nodes.shape[1] - 1):
        a, b, c = (layer_nodes[local[:, k], j] for k in range(3))
        d, e, f = (layer_nodes[local[:, k], j + 1] for k in range(3))
        for p, q, r, s in ((a, b, c, d), (b, c, d, e), (c, d, e, f)):
            if np.any(np.einsum("ij,ij->i", np.cross(q - p, r - p), s - p) <= 0.0):
                return False
    return True


def prism_volume_check(nodes, prisms) -> int:
    """Number of prisms whose decomposition has a non-positive tetrahedron (0 = all valid)."""
    p = nodes[prisms]
    bad = np.zeros(len(prisms), dtype=bool)
    # wedge (0, 1, 2) has its normal outward (into the wall): tetrahedra of the reversed bottom
    for i, j, k, m in ((0, 2, 1, 3), (2, 1, 3, 5), (1, 3, 5, 4)):
        vol = np.einsum("ij,ij->i", np.cross(p[:, j] - p[:, i], p[:, k] - p[:, i]), p[:, m] - p[:, i])
        bad |= vol <= 0.0
    return int(bad.sum())


def mitre_angle(stretch) -> float:
    """The wall turning angle [deg] that a mitre stretch corresponds to (for messages)."""
    return math.degrees(2.0 * math.acos(min(1.0, 1.0 / max(stretch, 1.0))))

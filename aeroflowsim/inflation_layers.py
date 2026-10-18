# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Inflation layers for unstructured 2D meshes: thin quad layers grown out from a wall.

Used by aeroflowsim/gmsh_mesh.py: Gmsh first places the nodes along the wall, this module grows the
layers from those nodes, and Gmsh then fills the rest of the domain (outside the outermost layer)
with triangles. This "extrude the layers first" approach is what most CFD meshers do; it always
gives the same, valid layers (Gmsh's own boundary-layer field failed for many nozzle sizes).

How the layers are grown, in plain words:
    The wall is a chain of nodes W_0 ... W_m. The flow is on the RIGHT-hand side when walking along
    the chain. At every wall node a straight "column" of nodes goes into the flow, one node per
    layer, at the heights
        H_j = h (1 + g + g² + ... + g^(j-1)),   j = 1 ... n_layers
    (h = first layer height, g = growth rate). Neighbouring columns are joined by quads.

    Column direction at a wall node:
      * smooth wall or inward (concave) corner: the average of the normals of the two wall
        segments meeting there, with the heights stretched by 1 / cos(half the turn), so the
        layers stay parallel to both segments ("mitre" joint);
      * sharp corner pointing into the flow (more than FAN_ANGLE, e.g. a wedge tip or trailing
        edge): a "fan" of several columns that turn from one normal to the other, all starting at
        the corner node; the first layer there is made of triangles;
      * an end of an open wall (where it meets a symmetry line, the axis, an inlet or outlet): along
        that boundary, so the layers end cleanly on it.

    Finally every cell is checked: if the layers fold over (too thick for a narrow gap or a
    tight curve), a clear error says so instead of returning a broken mesh.
"""

import math
from dataclasses import dataclass

import numpy as np

from aeroflowsim.mesh import QUAD, TRIANGLE
from aeroflowsim.shapes.profile import count_self_intersections

FAN_ANGLE = 60.0     # corners pointing into the flow sharper than this get a fan [deg]
FAN_STEP = 20.0      # each fan column turns by at most this much [deg]
MAX_MITRE = 3.0      # largest stretch 1/cos(turn/2) at an inward corner [-]
END_FAN_COSINE = 0.7 # a wall meeting its end boundary more than ~45 deg away from normal gets an end fan [-]
SMOOTHING_PASSES = (0, 2, 5, 10, 20, 50, 100, 200, 400)   # tried in turn until the layers do not fold


@dataclass
class Layers:
    """Inflation layers: nodes, cells and their boundary edges (node numbers into `nodes`)."""

    nodes: np.ndarray        # (P, 2) [m]
    cell_types: np.ndarray   # (L,) TRIANGLE or QUAD
    cells: np.ndarray        # (L, 4) node numbers, counter-clockwise (-1 padding for triangles)
    top: np.ndarray          # node numbers of the outermost layer, in wall order
    wall_faces: np.ndarray   # (m, 2) wall edges
    start_faces: np.ndarray  # (n_layers, 2) edges on the boundary at the start of an open wall
    end_faces: np.ndarray    # (n_layers, 2) edges on the boundary at the end of an open wall


def _unit(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def _right_normal(t):
    """Unit normal pointing to the right of the direction t (into the flow)."""
    return np.array([t[1], -t[0]])


def _rotate(v, angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([c * v[0] - s * v[1], s * v[0] + c * v[1]])


def grow_layers(wall, closed, first_height, n_layers, growth, start_direction=None, end_direction=None) -> Layers:
    """Grow n_layers inflation layers from the wall nodes `wall` (m, 2) [m].

    closed            True for a closed body outline (no ends)
    start_direction,
    end_direction     open walls only: unit vectors along the boundary each end lies on, pointing
                      into the flow (e.g. along the symmetry line, away from the body)
    """
    wall = np.asarray(wall, dtype=float)
    m = len(wall)
    heights = first_height * np.cumsum(growth ** np.arange(n_layers))       # H_1 ... H_n [m]
    columns = _columns(wall, closed, start_direction, end_direction)
    for passes in SMOOTHING_PASSES:                                         # smooth more until nothing folds
        directions = _smooth(columns, closed, passes)
        nodes, ids = list(wall), []
        for column, direction in zip(columns, directions):
            # stretch so that the height measured normal to both neighbouring wall segments is kept
            if column["fixed"]:
                scale = column["scale"]
            else:
                reach = min(direction @ column["n_before"], direction @ column["n_after"])
                scale = min(1.0 / max(reach, 1e-12), MAX_MITRE)
            ids.append([column["base"]] + list(range(len(nodes), len(nodes) + n_layers)))
            nodes.extend(wall[column["base"]] + direction * heights[:, None] * scale)
        nodes = np.array(nodes)
        cells, types = _cells(ids, closed, n_layers)
        # Walking along the wall and then up into the flow (which is on the right) goes round every
        # cell clockwise: all areas must be negative. A positive area means the layers folded over.
        folded = _signed_areas(nodes, cells, types) >= 0.0
        top = np.array([column[-1] for column in ids])
        if not np.any(folded) and not count_self_intersections(nodes[top], closed=closed):
            break
    else:
        where = nodes[cells[np.argmax(folded)][0]] if np.any(folded) else nodes[top[0]]
        raise ValueError(f"The inflation layers fold over themselves (near x = {where[0]:.4g} m, y = {where[1]:.4g} m): "
                         "they are too thick for the wall shape there. Use a smaller first layer height, fewer "
                         "layers or a smaller growth rate.")
    quads, triangles = types == QUAD, types == TRIANGLE                     # make every cell counter-clockwise
    cells[quads] = cells[quads][:, [0, 3, 2, 1]]
    cells[triangles, :3] = cells[triangles][:, [0, 2, 1]]
    wall_faces = np.array([[i, (i + 1) % m] for i in range(m if closed else m - 1)], dtype=np.int64)
    side = lambda col: np.column_stack([col[:-1], col[1:]])
    empty = np.zeros((0, 2), dtype=np.int64)
    return Layers(nodes, types, cells, top, wall_faces,
                  empty if closed else side(np.array(ids[0])), empty if closed else side(np.array(ids[-1])))


def _fan(base, first, last, include_first, include_last):
    """Fan columns at node `base` turning from direction `first` to `last` (fixed, not smoothed)."""
    turn = math.atan2(first[0] * last[1] - first[1] * last[0], first @ last)
    k = max(1, math.ceil(abs(math.degrees(turn)) / FAN_STEP))
    steps = range(0 if include_first else 1, k + (1 if include_last else 0))
    return [dict(base=base, direction=_rotate(first, turn * q / k), scale=1.0, fixed=True) for q in steps]


def _columns(wall, closed, start_direction, end_direction):
    """The columns before smoothing: wall node, direction, neighbouring wall normals, fixed or not."""
    m = len(wall)
    columns = []
    for i in range(m):
        has_before, has_after = closed or i > 0, closed or i < m - 1
        t_before = _unit(wall[i] - wall[i - 1]) if has_before else None
        t_after = _unit(wall[(i + 1) % m] - wall[i]) if has_after else None
        if not (has_before and has_after):                                  # an end of an open wall
            along = _unit(np.asarray(start_direction if i == 0 else end_direction, dtype=float))
            n_wall = _right_normal(t_after if has_after else t_before)
            reach = float(along @ n_wall)                                   # cos(angle to the wall normal)
            if reach >= END_FAN_COSINE:                                     # nearly normal: one column
                columns.append(dict(base=i, direction=along, scale=1.0 / reach, fixed=True))
            elif i == 0:                                                    # a sharp edge on the boundary: fan
                columns += _fan(i, along, n_wall, True, False)
            else:
                columns += _fan(i, n_wall, along, False, True)
            continue
        n_b, n_a = _right_normal(t_before), _right_normal(t_after)
        turn = math.atan2(t_before[0] * t_after[1] - t_before[1] * t_after[0], t_before @ t_after)   # [rad]
        if turn > math.radians(FAN_ANGLE):                                  # sharp corner into the flow: fan
            columns += _fan(i, n_b, n_a, True, True)
        else:                                                               # smooth wall or mitre joint
            columns.append(dict(base=i, direction=_unit(n_b + n_a), n_before=n_b, n_after=n_a, fixed=False))
    return columns


def _smooth(columns, closed, passes):
    """Column directions after `passes` rounds of averaging with their neighbours (fixed ones stay).

    Averaging spreads a sudden change of direction (at an inward corner, where neighbouring columns
    would cross) over several columns, so the layers stay valid.
    """
    d = np.array([c["direction"] for c in columns])
    free = np.array([not c["fixed"] for c in columns])
    for _ in range(passes):
        before = np.roll(d, 1, axis=0)
        after = np.roll(d, -1, axis=0)
        if not closed:
            before[0], after[-1] = d[0], d[-1]
        new = _unit(before + 2.0 * d + after)
        d[free] = new[free]
    return d


def _cells(ids, closed, n_layers):
    """Quads between neighbouring columns (a triangle at the wall inside a fan); clockwise order."""
    cells, types = [], []
    for a, b in zip(ids, ids[1:] + (ids[:1] if closed else [])):
        for j in range(n_layers):
            if j == 0 and a[0] == b[0]:                                     # inside a fan: a triangle
                cells.append([a[0], b[1], a[1], -1])
                types.append(TRIANGLE)
            else:
                cells.append([a[j], b[j], b[j + 1], a[j + 1]])
                types.append(QUAD)
    return np.array(cells, dtype=np.int64), np.array(types)


def _signed_areas(nodes, cells, types):
    """Shoelace area of every cell (positive = counter-clockwise)."""
    n_corner = np.where(types == TRIANGLE, 3, 4)
    area = np.zeros(len(cells))
    for k in range(4):
        use = k < n_corner
        a = cells[use, k]
        b = np.where(k + 1 < n_corner[use], cells[use, (k + 1) % 4], cells[use, 0])
        area[use] += nodes[a, 0] * nodes[b, 1] - nodes[b, 0] * nodes[a, 1]
    return 0.5 * area

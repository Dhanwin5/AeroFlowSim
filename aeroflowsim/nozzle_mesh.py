# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Structured 2D mesh of the upper half of an axisymmetric nozzle (axis r = 0 up to the wall).

Input: any WallProfile (aeroflowsim/geometry.py: conical, CSV, later CAD). Output: a face-based
Mesh (aeroflowsim/mesh.py) with quad cells and the patches inlet, outlet, wall and axis.

Grid lines:
    "vertical" lines   at nx + 1 axial stations x_i, from the axis up to the wall
    "horizontal" lines nr + 1 lines that follow the wall shape (j = 0 is the axis, j = nr the wall)
The wall between two stations is a straight line (cells have straight edges), so a corner of the
profile that falls between two stations is cut slightly; the throat is always exactly a station.

Axial spacing (throat clustering): each side of the throat (inlet -> throat, throat -> exit) gets
cells in proportion to its length, spaced with the smooth one-sided tanh stretching

    s(xi) = 1 + tanh(delta (xi - 1)) / tanh(delta),   xi = 0 ... 1 uniform,

which is finest at the throat and grows smoothly towards the ends (no sudden jumps). delta = 0
means uniform spacing. Cells at the throat are about 2 delta / sinh(2 delta) times the uniform size.

Radial spacing:
    no inflation  uniform between axis and wall at every station
    inflation     n_layers thin layers at the wall: first layer height h, each next layer
                  growth times thicker. Heights are measured radially (along the vertical grid
                  lines), so the layers stay smooth even at a sharp throat corner. On a wall at
                  angle a the height perpendicular to the wall is h cos(a), e.g. 0.97 h at 15°:
                  slightly smaller than asked, the safe side for y+ later. The cells between the
                  layers and the axis ("core") grow smoothly from the last layer (first core
                  cell = last layer x growth) towards the axis, so there is no jump in size.
"""

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from aeroflowsim.mesh import QUAD, Mesh

PRESETS = {"Coarse": (100, 20), "Medium": (200, 40), "Fine": (400, 80)}   # (cells along x, across)
CLUSTER_STRENGTHS = {"Mild": 1.0, "Moderate": 2.0, "Strong": 3.0}        # delta of the tanh stretching
MIN_CORE_CELLS = 2   # cells that must remain between the inflation layers and the axis


@dataclass
class Inflation:
    """Thin cell layers along the wall (for boundary layers in viscous flow, Phase 4)."""

    first_height: float   # height of the layer touching the wall [m]
    n_layers: int         # number of layers [-]
    growth: float         # each layer is this many times thicker than the one below [-]

    def heights(self) -> np.ndarray:
        """Height of every layer, starting at the wall [m]."""
        return self.first_height * self.growth ** np.arange(self.n_layers)

    @property
    def thickness(self) -> float:
        """Total thickness of all layers [m]."""
        return float(self.heights().sum())


def total_inflation_thickness(first_height, n_layers, growth) -> float:
    """Total thickness [m] of n_layers layers starting at first_height [m] with the growth rate."""
    return Inflation(first_height, n_layers, growth).thickness


def tanh_stretching(n, delta) -> np.ndarray:
    """n + 1 points from 0 to 1, finest at 0 and growing smoothly (one-sided tanh); delta = 0: uniform."""
    xi = np.linspace(0.0, 1.0, n + 1)
    if delta <= 0.0:
        return xi
    s = 1.0 + np.tanh(delta * (xi - 1.0)) / math.tanh(delta)
    s[0], s[-1] = 0.0, 1.0     # exact end points (no round-off)
    return s


def axial_stations(x_start, x_throat, x_end, nx, delta) -> np.ndarray:
    """nx + 1 axial positions [m] with one exactly at the throat, clustered there by delta."""
    if not x_start < x_throat < x_end:
        raise ValueError("The narrowest point of the profile must lie strictly between the inlet and "
                         "the exit, otherwise this is not a converging-diverging nozzle.")
    n_conv = round(nx * (x_throat - x_start) / (x_end - x_start))   # equal spacing at the throat
    n_conv = min(max(n_conv, 1), nx - 1)
    conv = x_throat - (x_throat - x_start) * tanh_stretching(n_conv, delta)[::-1]
    div = x_throat + (x_end - x_throat) * tanh_stretching(nx - n_conv, delta)
    x = np.concatenate([conv, div[1:]])
    x[n_conv] = x_throat
    return x


def core_sizes(total, n, first, growth) -> np.ndarray:
    """n cell sizes [m] adding up to `total`, starting next to the inflation layers at `first`.

    Room to grow (total >= n first): the sizes grow by a constant factor q (found so they fit
        exactly) towards the axis. If that would need q > 2, equal sizes are used instead.
    Too little room (total < n first, e.g. a narrow throat with many cells across): the sizes
        shrink from `first` by the factor 1/growth per cell - the layer growth rate in reverse -
        and level off at a constant size s_min, so the cells at the axis do not become tiny:
            size_k = s_min + (first - s_min) / growth^k
    Where neither fits, equal sizes are used (the mesh checks then report the size jump).
    """
    sizes = np.full(n, total / n)
    k = np.arange(n)
    if n * first <= total:
        mismatch = lambda q: first * np.sum(q ** k) - total
        if mismatch(2.0) >= 0.0:
            sizes = first * brentq(mismatch, 1.0, 2.0, xtol=1e-14) ** k
    elif growth > 1.0:
        decay = growth ** (-k)                               # 1, 1/g, 1/g², ...
        s_min = (total - first * decay.sum()) / (n - decay.sum())
        if s_min > 0.0:
            sizes = s_min + (first - s_min) * decay
    return sizes * (total / sizes.sum())     # remove the last round-off


def radial_nodes(r_wall, nr, inflation=None) -> np.ndarray:
    """nr + 1 radii [m] from the axis (0) to the wall (r_wall) at one axial station."""
    if inflation is None:
        return r_wall * np.linspace(0.0, 1.0, nr + 1)
    layers = inflation.heights()                             # layer heights, wall first [m]
    r_core = r_wall - layers.sum()                           # top of the core region [m]
    if r_core <= 0.0:
        raise ValueError(f"The inflation layers ({inflation.thickness * 1e3:.4g} mm thick) do not fit "
                         f"where the nozzle radius is {r_wall * 1e3:.4g} mm: they would overlap at the axis. "
                         "Use a smaller first layer height, fewer layers or a smaller growth rate.")
    n_core = nr - inflation.n_layers
    core = core_sizes(r_core, n_core, layers[-1] * inflation.growth, inflation.growth)[::-1]  # axis -> layers
    sizes = np.concatenate([core, layers[::-1]])            # axis -> wall
    r = np.concatenate([[0.0], np.cumsum(sizes)])
    r[-1] = r_wall
    return r


def structured_nozzle_mesh(profile, nx, nr, cluster_delta=CLUSTER_STRENGTHS["Moderate"], inflation=None) -> Mesh:
    """Quad mesh of the half nozzle between the axis and the wall of `profile` (a WallProfile).

    nx             cells along the axis
    nr             cells from the axis to the wall (including any inflation layers)
    cluster_delta  throat clustering strength (0 = uniform axial spacing)
    inflation      Inflation(...) or None
    """
    if nx < 4 or nr < 2:
        raise ValueError("The mesh needs at least 4 cells along x and 2 across.")
    if inflation is not None:
        if inflation.n_layers < 1 or inflation.first_height <= 0.0 or inflation.growth < 1.0:
            raise ValueError("Inflation needs at least 1 layer, a positive first layer height and a "
                             "growth rate of at least 1.")
        if nr - inflation.n_layers < MIN_CORE_CELLS:
            raise ValueError(f"With {inflation.n_layers} inflation layers the mesh needs at least "
                             f"{inflation.n_layers + MIN_CORE_CELLS} cells across (now {nr}).")

    x = axial_stations(profile.x[0], profile.x_throat, profile.x[-1], nx, cluster_delta)   # [m]
    r_wall = profile.radius_at(x)                                                          # [m]
    X = np.repeat(x[:, None], nr + 1, axis=1)                                              # (nx+1, nr+1)
    R = np.array([radial_nodes(r_wall[i], nr, inflation) for i in range(nx + 1)])

    # Node (i, j) has number i (nr + 1) + j. Cells counter-clockwise in the (x, r) plane.
    nid = np.arange((nx + 1) * (nr + 1)).reshape(nx + 1, nr + 1)
    cells = np.stack([nid[:-1, :-1], nid[1:, :-1], nid[1:, 1:], nid[:-1, 1:]], axis=-1).reshape(-1, 4)
    boundary = {
        "inlet": ("inlet", np.column_stack([nid[0, :-1], nid[0, 1:]])),
        "outlet": ("outlet", np.column_stack([nid[-1, :-1], nid[-1, 1:]])),
        "wall": ("wall", np.column_stack([nid[:-1, -1], nid[1:, -1]])),
        "axis": ("axis", np.column_stack([nid[:-1, 0], nid[1:, 0]])),
    }
    info = {
        "generator": "structured_nozzle_mesh",
        "nx": int(nx), "nr": int(nr), "cluster_delta": float(cluster_delta),
        "x_throat": float(profile.x_throat), "r_throat": float(profile.r_throat),
        "inflation": inflation is not None,
    }
    if inflation is not None:
        info.update(first_layer_height=float(inflation.first_height), n_layers=int(inflation.n_layers),
                    growth_rate=float(inflation.growth), inflation_thickness=inflation.thickness)
    nodes = np.column_stack([X.ravel(), R.ravel()])
    return Mesh.from_cells(nodes, QUAD, cells, boundary, dim=2, axisymmetric=True, info=info)

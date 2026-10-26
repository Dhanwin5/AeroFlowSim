# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Simple test meshes built without Gmsh: a rectangle of quads, triangles or both, optionally distorted.

Used by the Euler solver tests and validation cases (2D shock tube, free-stream checks). Every mesh is
a face-based Mesh (aeroflowsim/mesh.py) like those of the real mesh generators."""

import numpy as np

from aeroflowsim.mesh import QUAD, TRIANGLE, Mesh


def rectangle_mesh(nx=8, ny=6, x0=0.0, x1=1.0, y0=0.0, y1=1.0, triangles=False, distort=0.0, seed=1,
              kinds=None, axisymmetric=False, mixed=False, warp=0.0):
    """Rectangle [x0, x1] x [y0, y1] with patches left, right, bottom, top.

    triangles: split every quad along a diagonal (alternating); mixed: only the left half;
    distort: move interior nodes randomly by up to this fraction of a cell width;
    warp: smooth distortion, interior nodes moved by warp x (domain size) x sin(2 pi s) sin(2 pi t) (s, t in
          [0, 1] along the sides): the same curved grid on every refinement level (MMS order studies);
    kinds: patch types {name: type}, default left inlet, right outlet, bottom symmetry, top wall.
    """
    kinds = {"left": "inlet", "right": "outlet", "bottom": "symmetry", "top": "wall", **(kinds or {})}
    xs, ys = np.linspace(x0, x1, nx + 1), np.linspace(y0, y1, ny + 1)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    if distort:
        rng = np.random.default_rng(seed)
        dx, dy = (x1 - x0) / nx, (y1 - y0) / ny
        inner = (slice(1, -1), slice(1, -1))
        X[inner] += distort * dx * rng.uniform(-1, 1, X[inner].shape)
        Y[inner] += distort * dy * rng.uniform(-1, 1, Y[inner].shape)
    if warp:
        S, T = (X - x0) / (x1 - x0), (Y - y0) / (y1 - y0)
        bump = np.sin(2.0 * np.pi * S) * np.sin(2.0 * np.pi * T)
        X, Y = X + warp * (x1 - x0) * bump, Y + warp * (y1 - y0) * bump
    nodes = np.column_stack([X.ravel(), Y.ravel()])
    nid = lambda i, j: i * (ny + 1) + j
    types, cells = [], []
    for i in range(nx):
        for j in range(ny):
            a, b, c, d = nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)
            split = triangles or (mixed and i < nx // 2)
            if split:
                if (i + j) % 2:
                    cells += [[a, b, c, -1], [a, c, d, -1]]
                else:
                    cells += [[a, b, d, -1], [b, c, d, -1]]
                types += [TRIANGLE, TRIANGLE]
            else:
                cells.append([a, b, c, d])
                types.append(QUAD)
    boundary = {
        "left": (kinds["left"], [[nid(0, j), nid(0, j + 1)] for j in range(ny)]),
        "right": (kinds["right"], [[nid(nx, j), nid(nx, j + 1)] for j in range(ny)]),
        "bottom": (kinds["bottom"], [[nid(i, 0), nid(i + 1, 0)] for i in range(nx)]),
        "top": (kinds["top"], [[nid(i, ny), nid(i + 1, ny)] for i in range(nx)]),
    }
    return Mesh.from_cells(nodes, np.array(types), np.array(cells), boundary, axisymmetric=axisymmetric)


def cylinder_front_mesh(n_r=60, n_theta=80, radius=0.5, outer=3.5, stretch=1.0):
    """Structured polar grid in front of a circular cylinder (centre (radius, 0)): the classic blunt-body grid.

    The upper front quarter: angles from 90 deg (top, outflow) to 180 deg (the stagnation line, y = 0), radii
    from the cylinder (radius) to outer x radius. Grid lines follow the bow shock, which is exactly the setting
    in which shock-capturing schemes such as HLLC show the "carbuncle" (Quirk 1994). stretch > 1 packs the
    radial lines towards the wall. Patches: wall (cylinder), farfield (outer circle), symmetry (y = 0),
    outlet (the vertical line above the centre).
    """
    s = np.linspace(0.0, 1.0, n_r + 1)
    if stretch != 1.0:
        s = (stretch**s - 1.0) / (stretch - 1.0)
    r = radius * (1.0 + (outer - 1.0) * s)
    theta = np.linspace(np.pi / 2.0, np.pi, n_theta + 1)
    R, T = np.meshgrid(r, theta, indexing="ij")
    nodes = np.column_stack([(radius + R * np.cos(T)).ravel(), np.abs(R * np.sin(T)).ravel()])
    nid = lambda i, j: i * (n_theta + 1) + j
    cells = [[nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)] for i in range(n_r) for j in range(n_theta)]
    boundary = {
        "wall": ("wall", [[nid(0, j), nid(0, j + 1)] for j in range(n_theta)]),
        "farfield": ("farfield", [[nid(n_r, j), nid(n_r, j + 1)] for j in range(n_theta)]),
        "outlet": ("outlet", [[nid(i, 0), nid(i + 1, 0)] for i in range(n_r)]),
        "symmetry": ("symmetry", [[nid(i, n_theta), nid(i + 1, n_theta)] for i in range(n_r)]),
    }
    mesh = Mesh.from_cells(nodes, QUAD, np.array(cells), boundary)
    if np.any(mesh.cell_volumes <= 0.0):           # cells must be counter-clockwise: flip the node order
        cells = [c[::-1] for c in cells]
        mesh = Mesh.from_cells(nodes, QUAD, np.array(cells), boundary)
    return mesh

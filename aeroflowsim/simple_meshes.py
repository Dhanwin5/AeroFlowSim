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


# ---- 3D boxes (solver verification: free-stream preservation, MMS) -------------------------------------

BOX_KINDS = ("hexahedra", "prisms", "tetrahedra", "hex-prism")


def box_mesh_3d(n=4, kind="hexahedra", lo=(0.0, 0.0, 0.0), hi=(1.0, 1.0, 1.0), warp=0.0, kinds=None, ny=None,
                nz=None):
    """Box [lo, hi] of n x ny x nz cubes, each cube a hexahedron, 2 prisms or 6 tetrahedra.

    kind: "hexahedra"; "prisms" (each cube cut along the diagonal of its xy face, extruded in z);
          "tetrahedra" (Kuhn's split of each cube into 6 tetrahedra along its main diagonal: the same split in
          every cube, so neighbouring cubes share their face triangles); "hex-prism" (hexahedra for x < half the
          box, prisms beyond: they meet on quad faces, so the mesh is conformal - a mixed mesh).
    warp: smooth distortion: interior nodes move by warp x (box size) x sin(2 pi s) sin(2 pi t) sin(2 pi w), the
          same curved grid on every level (MMS studies; quad faces then are non-planar, as in real meshes).
    Patches: xmin, xmax, ymin, ymax, zmin, zmax; types from kinds (default xmin inlet, xmax outlet, others wall).
    """
    from aeroflowsim.mesh import HEXAHEDRON, TETRA, WEDGE
    if kind not in BOX_KINDS:
        raise ValueError(f"Unknown box kind '{kind}'; use one of {', '.join(BOX_KINDS)}.")
    nx, ny, nz = n, ny or n, nz or n
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    axes = [np.linspace(lo[k], hi[k], m + 1) for k, m in enumerate((nx, ny, nz))]
    X, Y, Z = np.meshgrid(*axes, indexing="ij")
    if warp:
        S, T, Q = ((A - lo[k]) / (hi[k] - lo[k]) for k, A in enumerate((X, Y, Z)))
        bump = np.sin(2.0 * np.pi * S) * np.sin(2.0 * np.pi * T) * np.sin(2.0 * np.pi * Q)
        X, Y, Z = (A + warp * (hi[k] - lo[k]) * bump for k, A in enumerate((X, Y, Z)))
    nodes = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])

    def nid(i, j, k):
        return (i * (ny + 1) + j) * (nz + 1) + k

    types, cells = [], []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                # the 8 corners in VTK hexahedron order: bottom (z = k) counter-clockwise, then top
                c = [nid(i, j, k), nid(i + 1, j, k), nid(i + 1, j + 1, k), nid(i, j + 1, k),
                     nid(i, j, k + 1), nid(i + 1, j, k + 1), nid(i + 1, j + 1, k + 1), nid(i, j + 1, k + 1)]
                cell_kind = kind if kind != "hex-prism" else ("hexahedra" if i < nx // 2 else "prisms")
                if cell_kind == "hexahedra":
                    cells.append(c)
                    types.append(HEXAHEDRON)
                elif cell_kind == "prisms":
                    # two triangles of the bottom face along the diagonal 0-2, each extruded to the top face
                    for a, b, d in ((0, 1, 2), (0, 2, 3)):
                        cells.append([c[a], c[b], c[d], c[a + 4], c[b + 4], c[d + 4], -1, -1])
                        types.append(WEDGE)
                else:
                    # Kuhn: one tetrahedron per order of the three axes along the path corner 0 -> corner 6
                    corner = {(0, 0, 0): 0, (1, 0, 0): 1, (1, 1, 0): 2, (0, 1, 0): 3,
                              (0, 0, 1): 4, (1, 0, 1): 5, (1, 1, 1): 6, (0, 1, 1): 7}
                    for order in ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)):
                        p = [0, 0, 0]
                        tet = [c[0]]
                        for axis in order:
                            p[axis] = 1
                            tet.append(c[corner[tuple(p)]])
                        cells.append(tet + [-1] * 4)
                        types.append(TETRA)
    cells, types = np.array(cells), np.array(types)
    _orient_cells(nodes, types, cells)

    kinds = {"xmin": "inlet", "xmax": "outlet", "ymin": "wall", "ymax": "wall", "zmin": "wall", "zmax": "wall",
             **(kinds or {})}
    planes = {"xmin": (0, 0), "xmax": (0, nx), "ymin": (1, 0), "ymax": (1, ny), "zmin": (2, 0), "zmax": (2, nz)}
    boundary_cells = Mesh.from_cells(nodes, types, cells, {"all": ("wall", _all_boundary_faces(types, cells))})
    face_nodes = boundary_cells.face_nodes[boundary_cells.n_interior_faces:]
    centres = boundary_cells.face_centres[boundary_cells.n_interior_faces:]
    boundary = {}
    # sort the boundary faces into the six planes by their (unwarped) position: warp is zero on the box faces
    for name, (axis, index) in planes.items():
        level = axes[axis][index]
        on = np.abs(centres[:, axis] - level) < 1e-9 * max(1.0, float(np.abs(hi - lo).max()))
        f = face_nodes[on]
        boundary[name] = (kinds[name], f)
    return Mesh.from_cells(nodes, types, cells, boundary)


def _all_boundary_faces(types, cells):
    """Node lists (padded with -1) of every face that belongs to one cell only."""
    from aeroflowsim.mesh import _find_faces, MAX_CELL_NODES
    padded = np.full((len(cells), MAX_CELL_NODES), -1, dtype=np.int64)
    padded[:, :cells.shape[1]] = cells
    face_nodes, _owner, neighbour = _find_faces(np.asarray(types, dtype=np.int32), padded)
    return face_nodes[neighbour < 0]


def _orient_cells(nodes, types, cells):
    """Reorder the nodes of any cell whose VTK ordering gives a negative volume (in place)."""
    from aeroflowsim.mesh import HEXAHEDRON, TETRA, WEDGE
    for t, flip in ((TETRA, [0, 2, 1, 3]), (WEDGE, [0, 2, 1, 3, 5, 4]), (HEXAHEDRON, [0, 3, 2, 1, 4, 7, 6, 5])):
        sel = np.flatnonzero(types == t)
        if not len(sel):
            continue
        k = len(flip)
        p = nodes[cells[sel, :k]]
        if t == TETRA:
            vol = np.einsum("ij,ij->i", np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), p[:, 3] - p[:, 0])
            bad = vol < 0.0      # VTK tetrahedron: (1-0) x (2-0) points towards node 3
        else:
            # bottom polygon 0..base-1, top base..k-1. VTK: the right-hand normal of 0-1-2 points to the top for a
            # hexahedron, away from it for a wedge (mesh.CELL_TYPES lists (0, 3, 2, 1) and (0, 1, 2) as outward)
            base = k // 2
            n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
            up = np.einsum("ij,ij->i", n, p[:, base:].mean(axis=1) - p[:, :base].mean(axis=1))
            bad = up < 0.0 if t == HEXAHEDRON else up > 0.0
        rows = sel[bad]
        cells[rows, :k] = cells[rows][:, flip]

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exact wall distance (aeroflowsim/wall_distance.py) against exact distances: flat plate, cylinder, sphere, and the
KD-tree search against brute force over every wall element."""

import numpy as np
from scipy.spatial import ConvexHull

from aeroflowsim.simple_meshes import box_mesh_3d, cylinder_front_mesh, rectangle_mesh
from aeroflowsim.wall_distance import _segment_distance, _triangle_distance, distances, wall_distance


def test_flat_plate_2d():
    mesh = rectangle_mesh(20, 15, distort=0.2)           # bottom = the wall
    d = wall_distance(mesh, ["bottom"])
    assert np.allclose(d, mesh.cell_centres[:, 1], rtol=0, atol=1e-14)


def test_flat_plate_3d():
    mesh = box_mesh_3d(5, "tetrahedra")
    d = wall_distance(mesh, ["ymin"])
    assert np.allclose(d, mesh.cell_centres[:, 1], rtol=0, atol=1e-14)


def test_cylinder():
    """Polar grid round a cylinder of radius 0.5: d = r - R up to the sagitta of the polygonal wall."""
    mesh = cylinder_front_mesh(n_r=20, n_theta=40, radius=0.5, outer=3.0)
    wall = [p.name for p in mesh.patches if p.type == "wall"]
    d = wall_distance(mesh, wall)
    r = np.linalg.norm(mesh.cell_centres[:, :2] - [0.5, 0.0], axis=1)     # centre (radius, 0)
    dtheta = 0.5 * np.pi / 40                     # a quarter circle in 40 cells
    sagitta = 0.5 * (1.0 - np.cos(dtheta))
    assert np.all(np.abs(d - (r - 0.5)) <= sagitta + 1e-12)


def test_sphere_and_brute_force():
    """Points round a triangulated sphere (radius 1): d = |x| - 1 within the facet sagitta, and the KD-tree search
    equals the brute-force minimum over all triangles exactly."""
    rng = np.random.default_rng(3)
    v = rng.normal(size=(400, 3))
    v /= np.linalg.norm(v, axis=1)[:, None]
    tris = v[ConvexHull(v).simplices]
    P = rng.normal(size=(300, 3))
    P *= (1.05 + 2.0 * rng.random(300))[:, None] / np.linalg.norm(P, axis=1)[:, None]
    d, _ = distances(P, tris)
    brute = np.min([_triangle_distance(P, *(np.repeat(t[None, k], len(P), 0) for k in range(3))) for t in tris],
                   axis=0)
    assert np.array_equal(d, brute)
    assert np.all(np.abs(d - (np.linalg.norm(P, axis=1) - 1.0)) < 0.05)


def test_segment_brute_force():
    rng = np.random.default_rng(1)
    segs = rng.random((200, 2, 2))
    P = rng.random((500, 2)) * 1.5 - 0.25
    d, _ = distances(P, segs)
    brute = np.min([_segment_distance(P, np.repeat(s[None, 0], 500, 0), np.repeat(s[None, 1], 500, 0))
                    for s in segs], axis=0)
    assert np.array_equal(d, brute)


def test_no_walls():
    mesh = rectangle_mesh(4, 4)
    assert np.all(np.isinf(wall_distance(mesh, [])))

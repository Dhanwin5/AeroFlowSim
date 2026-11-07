# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""view3d.wall_cut (full 3D release stage): a plane through a triangulated sphere gives a circle, and a linear field is
interpolated exactly; forces_3d equals the solver's numbers (tested in test_results3d_post)."""

import numpy as np

from aeroflowsim.post.view3d import Surface, wall_cut


def _sphere(n=40):
    th, ph = np.meshgrid(np.linspace(0, np.pi, n), np.linspace(0, 2 * np.pi, 2 * n, endpoint=False), indexing="ij")
    pts = np.column_stack([np.cos(th).ravel(), (np.sin(th) * np.cos(ph)).ravel(), (np.sin(th) * np.sin(ph)).ravel()])
    idx = np.arange(n * 2 * n).reshape(n, 2 * n)
    tri = []
    for i in range(n - 1):
        for j in range(2 * n):
            a, b, c, d = idx[i, j], idx[i, (j + 1) % (2 * n)], idx[i + 1, j], idx[i + 1, (j + 1) % (2 * n)]
            tri += [(a, b, d), (a, d, c)]
    return Surface(pts, np.array(tri), 2.0 * pts[:, 0] + 3.0)


def test_cut_of_a_sphere_is_a_circle_with_exact_linear_values():
    s = _sphere()
    points, values = wall_cut(s, (0, 0, 0.0), (0, 0, 1))
    assert len(points) > 50
    assert np.allclose(points[:, 2], 0.0, atol=1e-12)
    assert np.all(np.hypot(points[:, 0], points[:, 1]) <= 1.0 + 1e-12)
    assert np.all(np.hypot(points[:, 0], points[:, 1]) > 0.99)          # polygon of the sphere: near the circle
    assert np.allclose(values, 2.0 * points[:, 0] + 3.0, atol=1e-12)    # linear field: exact
    assert np.all(np.diff(points[:, 0]) >= 0)                            # sorted along x
    empty, _ = wall_cut(s, (0, 0, 2.0), (0, 0, 1))
    assert len(empty) == 0

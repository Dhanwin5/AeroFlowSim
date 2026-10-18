# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the inflation layers grown from a wall (aeroflowsim/inflation_layers.py). No Gmsh needed."""

import math

import numpy as np
import pytest

from aeroflowsim.inflation_layers import _signed_areas, grow_layers
from aeroflowsim.mesh import QUAD, TRIANGLE


def test_flat_wall_layers_have_the_asked_heights_and_end_on_the_side_boundaries():
    wall = np.column_stack([np.linspace(1.0, 0.0, 11), np.zeros(11)])   # walking -x: flow on the right is +y
    layers = grow_layers(wall, False, 1e-3, 5, 1.2, (0.0, 1.0), (0.0, 1.0))
    heights = 1e-3 * np.cumsum(1.2 ** np.arange(5))
    assert np.allclose(layers.nodes[layers.top, 1], heights[-1])
    assert np.all(layers.cell_types == QUAD) and len(layers.cells) == 10 * 5
    assert np.all(_signed_areas(layers.nodes, layers.cells, layers.cell_types) > 0.0)   # counter-clockwise
    assert len(layers.wall_faces) == 10 and len(layers.start_faces) == len(layers.end_faces) == 5
    assert np.allclose(layers.nodes[layers.start_faces[:, 1], 0], 1.0)  # the side faces lie on x = 1


def test_sharp_corner_gets_a_fan_with_triangles_at_the_wall():
    wedge = np.array([(0.0, 0.0), (1.0, -0.18), (1.0, 0.18)])            # counter-clockwise body
    edge = lambda a, b, n: a + (b - a) * np.linspace(0, 1, n, endpoint=False)[:, None]
    wall = np.vstack([edge(wedge[0], wedge[1], 20), edge(wedge[1], wedge[2], 8), edge(wedge[2], wedge[0], 20)])
    layers = grow_layers(wall, True, 1e-3, 4, 1.2)
    assert np.count_nonzero(layers.cell_types == TRIANGLE) >= 3 * 2      # fans at the tip and both base corners
    assert np.all(_signed_areas(layers.nodes, layers.cells, layers.cell_types) > 0.0)


def test_inward_corner_is_smoothed_and_too_thick_layers_give_a_clear_error():
    # An L-shaped wall with the flow inside the corner (like the nozzle inlet corner).
    n = 40
    wall = np.vstack([np.column_stack([np.zeros(n), np.linspace(1.0, 0.0, n, endpoint=False)]),
                      np.column_stack([np.linspace(0.0, 1.0, n), np.zeros(n)])])
    wall = wall[::-1]                                                      # flow on the right = inside the corner
    layers = grow_layers(wall, False, 2e-3, 10, 1.2, (0.0, 1.0), (1.0, 0.0))
    assert np.all(_signed_areas(layers.nodes, layers.cells, layers.cell_types) > 0.0)
    with pytest.raises(ValueError, match="fold over"):
        grow_layers(wall[n - 3:n + 3], False, 0.5, 10, 1.3, (0.0, 1.0), (1.0, 0.0))


def test_closed_circle_layers_follow_the_circle():
    angle = np.linspace(0.0, 2 * math.pi, 120, endpoint=False)
    wall = np.column_stack([np.cos(angle), np.sin(angle)])                # counter-clockwise: flow outside
    layers = grow_layers(wall, True, 1e-3, 3, 1.5)
    radius = np.hypot(*layers.nodes[layers.top].T)
    assert np.allclose(radius, 1.0 + 1e-3 * (1 + 1.5 + 2.25), rtol=1e-4)
    assert len(layers.start_faces) == 0 and len(layers.wall_faces) == 120

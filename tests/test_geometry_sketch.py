# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sketch tools and snapping (aeroflowsim/geometry_model: operations.Sketch, snapping.py): exact
areas and lengths of every sketched entity, closing shapes into faces, a sketched domain around a
body, and the snapping order (corner, sketch point, midpoint, grid)."""

import math

import numpy as np
import pytest

from aeroflowsim.geometry_model import FLUID, SOLID, GeometryDocument, replay
from aeroflowsim.geometry_model import boundaries, snapping
from aeroflowsim.geometry_model.operations import BooleanOp, Sketch


def built(*ops):
    doc = GeometryDocument()
    for op in ops:
        doc.add(op)
    return replay(doc)


def test_rectangle_circle_and_closed_polyline_are_faces_with_exact_areas():
    b = built(Sketch(kind="rectangle", points=[[2.0, 1.0], [0.0, 0.0]], role=FLUID),
              Sketch(kind="circle", points=[[5.0, 0.0], [5.5, 0.0]]),
              Sketch(kind="polyline", points=[[10, 0], [12, 0], [10, 3]], closed=True))
    areas = {f.id: (f.area, f.role) for f in b.faces.values()}
    assert areas["op1:face"] == (pytest.approx(2.0), FLUID)
    assert areas["op2:face"] == (pytest.approx(math.pi * 0.25, rel=1e-12), SOLID)
    assert areas["op3:face"][0] == pytest.approx(3.0)
    assert sorted(e for e in b.edges if e.startswith("op1")) == ["op1:e1", "op1:e2", "op1:e3", "op1:e4"]


def test_arcs_and_open_curves_are_free_edges():
    b = built(Sketch(kind="arc3", points=[[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]),        # half circle through the top
              Sketch(kind="arc", points=[[0.0, 0.0], [2.0, 0.0], [0.0, 5.0]]),           # quarter circle r = 2
              Sketch(kind="spline", points=[[0, 0], [1, 1], [2, 0]]),
              Sketch(kind="polyline", points=[[0, -1], [3, -1], [3, -5]]))
    assert not b.faces
    length = {e: b.edges[e].length for e in b.edges}
    assert length["op1:e1"] == pytest.approx(math.pi, rel=1e-12)
    assert b.edges["op1:e1"].points[:, 1].max() == pytest.approx(1.0)                  # through the top
    assert length["op2:e1"] == pytest.approx(math.pi, rel=1e-12)                        # 2 x pi / 2
    assert b.edges["op3:e1"].kind == "spline"
    assert length["op4:e1"] + length["op4:e2"] == pytest.approx(7.0)


def test_a_sketched_domain_around_a_sketched_body():
    b = built(Sketch(kind="rectangle", points=[[-5, -5], [5, 5]], role=FLUID),
              Sketch(kind="circle", points=[[0, 0], [1, 0]]),
              BooleanOp(kind="subtract", objects=["op1:face"], tools=["op2:face"]))
    (face,) = b.faces.values()
    assert face.area == pytest.approx(100.0 - math.pi, rel=1e-12) and face.role == FLUID
    assert {s.type for s in boundaries.suggestions(b).values()} == {"wall", "farfield"}


def test_bad_sketches_say_what_is_wrong():
    for op, message in ((Sketch(kind="arc3", points=[[0, 0], [1, 1], [2, 2]]), "straight line"),
                        (Sketch(kind="circle", points=[[0, 0]]), "exactly 2 points"),
                        (Sketch(kind="rectangle", points=[[0, 0], [1, 0]]), "opposite corners"),
                        (Sketch(kind="polyline", points=[[0, 0], [0, 0], [1, 1]]), "same place")):
        assert message in built(op).errors()[0]


def test_snapping_order_and_grid():
    b = built(Sketch(kind="rectangle", points=[[0, 0], [2, 1]]))
    point, what = snapping.snap(b, (0.01, 0.02), 0.05)
    assert what == "corner" and point == pytest.approx([0.0, 0.0])
    point, what = snapping.snap(b, (1.02, 0.01), 0.05)
    assert what == "midpoint" and point == pytest.approx([1.0, 0.0])
    point, what = snapping.snap(b, (5.0, 5.0), 0.05, sketch_points=[(5.01, 4.99)])
    assert what == "sketch point"
    point, what = snapping.snap(b, (0.53, 0.47), 0.01, grid=0.25)
    assert what == "grid" and point == pytest.approx([0.5, 0.5])
    point, what = snapping.snap(b, (0.53, 0.47), 0.01)
    assert what == "" and point == pytest.approx([0.53, 0.47])
    assert snapping.grid_step(20.0) == 1.0 and snapping.grid_step(0.008) == pytest.approx(0.0005)

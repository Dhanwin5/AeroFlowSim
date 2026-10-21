# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Drawing with the mouse, without a window: the sketch tools (aeroflowsim/gui/sketch_tools.py) fed
with clicks in world coordinates, the inference snapping (geometry_model/inference.py), typed input,
and the SketchGroup operation they make (exact areas and lengths after replay)."""

import math

import numpy as np
import pytest

from aeroflowsim.geometry_model import FLUID, GeometryDocument, replay
from aeroflowsim.geometry_model.inference import infer
from aeroflowsim.geometry_model.operations import Sketch, SketchGroup
from aeroflowsim.gui import sketch_tools as st

TOL = 1e-4          # pick tolerance [m] (a few pixels)


def built_of(*ops):
    doc = GeometryDocument()
    for op in ops:
        doc.add(op)
    return replay(doc)


def draw(tool, *clicks):
    for xy in clicks:
        tool.click(xy, TOL)
    return tool


# ---- typed input ---------------------------------------------------------------------------------

def test_typed_points_in_mm():
    assert st.parse_typed("12, 5") == pytest.approx([0.012, 0.005])
    assert st.parse_typed("@3;4", last=[0.01, 0.0]) == pytest.approx([0.013, 0.004])
    assert st.parse_typed("10<90", last=[0.0, 0.0]) == pytest.approx([0.0, 0.01])
    assert st.parse_typed("5", last=[0.0, 0.0], cursor=[0.0, -1.0]) == pytest.approx([0.0, -0.005])
    for bad, message in (("abc", "not understood"), ("5", "first point"), ("@1,2", "last point")):
        with pytest.raises(ValueError, match=message):
            st.parse_typed(bad)


# ---- inference -----------------------------------------------------------------------------------

def test_inference_order_and_guides():
    built = built_of(Sketch("op1", kind="rectangle", points=[[0, 0], [0.02, 0.01]], role="fluid"),
                     Sketch("op2", kind="polyline", points=[[0.03, -0.01], [0.03, 0.02]]),
                     Sketch("op3", kind="polyline", points=[[0.025, 0.005], [0.04, 0.005]]))
    assert infer(built, (0.00002, 0.00003), TOL).kind == "endpoint"
    assert infer(built, (0.03002, 0.00498), TOL).kind == "intersection"
    hit = infer(built, (0.01003, 0.0), TOL)
    assert hit.kind == "midpoint" and hit.point == pytest.approx([0.01, 0.0])
    hit = infer(built, (0.0300, 0.015), TOL)
    assert hit.kind == "on curve" and hit.point[0] == pytest.approx(0.03)
    hit = infer(built, (0.02995, 0.01503), TOL, last=np.array([0.05, 0.015]))
    assert hit.kind == "perpendicular" and hit.point == pytest.approx([0.03, 0.015]) and hit.guides
    hit = infer(None, (0.01, 0.0002), TOL, last=np.array([0.0, 0.0]))         # 1.1 deg off horizontal
    assert hit.kind == "angle" and hit.label == "horizontal" and hit.point == pytest.approx([0.01, 0.0])
    hit = infer(None, (0.01, 0.01015), TOL, last=np.array([0.0, 0.0]))        # near 45 deg
    assert hit.label == "45°" and hit.point[0] == pytest.approx(hit.point[1])
    hit = infer(None, (0.0201, 0.0333), TOL, sketch_points=[(0.02, 0.0)])     # lined up with a point
    assert hit.kind == "aligned" and hit.point[0] == pytest.approx(0.02)
    assert infer(None, (0.0123, 0.0456), TOL, grid=0.005).point == pytest.approx([0.01, 0.045])
    assert infer(None, (0.0123, 0.0456), TOL).kind == ""


def test_tangent_snap_to_a_circle():
    built = built_of(Sketch("op1", kind="circle", points=[[0.0, 0.0], [0.01, 0.0]]))
    last = np.array([0.02, 0.0])
    expected = 0.01 * np.array([0.5, math.sqrt(3) / 2])                     # cos(beta) = r / d = 1/2
    hit = infer(built, expected + 0.00003, TOL, last=last)
    assert hit.kind == "tangent" and hit.point == pytest.approx(expected, abs=1e-12)


# ---- tools ------------------------------------------------------------------------------------------

def test_polyline_closes_into_a_face_with_shared_points():
    tool = draw(st.PolylineTool(), (0, 0), (0.03, 0.0), (0.03, 0.02), (0.00001, 0.00002))   # last click snaps
    assert tool.done and tool.closed and len(tool.points) == 3 and len(tool.entities) == 3
    built = built_of(tool.operation(FLUID))
    (face,) = built.faces.values()
    assert face.area == pytest.approx(0.5 * 0.03 * 0.02) and face.role == FLUID
    assert len(built.vertices) == 3                                       # connected exactly, no gaps


def test_open_polyline_finishes_by_hand_and_tangent_arc_continues_smoothly():
    tool = draw(st.PolylineTool(), (0, 0), (0.01, 0.0))
    tool.arc_next = True
    tool.click((0.02, 0.01), TOL)                                         # quarter circle, centre (0.01, 0.01)
    assert tool.finish() and not tool.closed
    arc = tool.entities[1]
    assert arc["type"] == "arc" and tool.points[arc["c"]] == pytest.approx([0.01, 0.01])
    built = built_of(tool.operation())
    lengths = sorted(e.length for e in built.edges.values())
    assert lengths == pytest.approx([0.01, 0.5 * math.pi * 0.01], rel=1e-9) and not built.faces


@pytest.mark.parametrize("tool, clicks, area", [
    (st.RectangleTool, [(0, 0), (0.04, 0.02)], 0.04 * 0.02),
    (st.Rectangle3Tool, [(0, 0), (0.03, 0.03), (0.0, 0.02)], math.hypot(0.03, 0.03) * 0.02 / math.sqrt(2) * 1.0),
    (st.CircleTool, [(0.01, 0.01), (0.02, 0.01)], math.pi * 0.01**2),
])
def test_closed_shapes(tool, clicks, area):
    t = draw(tool(), *clicks)
    assert t.done and t.closed
    (face,) = built_of(t.operation()).faces.values()
    if tool is st.Rectangle3Tool:                                         # side 0.03 sqrt 2, width: distance to the side
        side = math.hypot(0.03, 0.03)
        width = abs(0.03 * 0.02 - 0.03 * 0.0) / side                     # |side x third| / |side|
        area = side * width
    assert face.area == pytest.approx(area, rel=1e-9)


def test_arcs_three_points_and_centre():
    t = draw(st.Arc3Tool(), (0.01, 0.0), (0.0, 0.01), (-0.01, 0.0))        # upper half circle (two OCC arcs)
    built = built_of(t.operation())
    assert sum(e.length for e in built.edges.values()) == pytest.approx(math.pi * 0.01, rel=1e-9)
    assert built.bbox()[3] == pytest.approx(0.01)
    t = draw(st.Arc3Tool(), (0.01, 0.0), (0.0, -0.01), (-0.01, 0.0))       # lower half circle
    assert built_of(t.operation()).bbox()[1] == pytest.approx(-0.01)
    t = draw(st.ArcTool(), (0, 0), (0.01, 0.0), (0.0, 0.05))                # end projected onto r = 1 cm
    (edge,) = built_of(t.operation()).edges.values()
    assert edge.length == pytest.approx(0.5 * math.pi * 0.01, rel=1e-9)
    t = draw(st.ArcTool(), (0, 0), (0.01, 0.0), (0.0, -0.01))               # three quarters (two OCC arcs)
    assert sum(e.length for e in built_of(t.operation()).edges.values()) == pytest.approx(1.5 * math.pi * 0.01)
    with pytest.raises(ValueError, match="straight line"):
        draw(st.Arc3Tool(), (0, 0), (0.01, 0.0), (0.02, 0.0))


def test_typing_while_drawing():
    tool = st.PolylineTool()
    tool.typed("0, 0")
    tool.move((0.05, 0.0001), TOL)                                        # cursor direction: along x
    tool.typed("20")
    tool.typed("10<90")
    tool.typed("@-20, 0")
    tool.typed("0,0")
    assert tool.done and tool.closed
    (face,) = built_of(tool.operation()).faces.values()
    assert face.area == pytest.approx(0.02 * 0.01)
    circle = st.CircleTool()
    circle.typed("5, 5")
    circle.typed("2.5")                                                   # a single number: the radius
    assert circle.entities[0]["r"] == pytest.approx(0.0025)


def test_spline_and_construction_line_and_preview():
    t = draw(st.SplineTool(), (0, 0), (0.01, 0.01), (0.02, 0.0))
    t.move((0.03, 0.01), TOL)
    assert len(t.preview().lines[0]) == 120                               # smooth rubber band through the cursor
    assert t.finish()
    (edge,) = built_of(t.operation()).edges.values()
    assert edge.kind == "spline"
    c = draw(st.ConstructionTool(), (0, 0), (0.01, 0.01))
    built = built_of(c.operation())
    assert not built.edges and len(built.construction) == 1             # drawn, not built
    p = st.PolylineTool()
    p.click((0, 0), TOL)
    p.move((0.010, 0.0001), TOL)
    preview = p.preview()
    assert preview.marker[1] == "angle" and "horizontal" in preview.label and "L 10 mm" in preview.label


def test_sketch_group_errors_are_clear():
    for entities, message in (([{"type": "line", "p": [0, 0]}], "no length"),
                              ([{"type": "line", "p": [0, 5]}], "point 5"),
                              ([{"type": "blob"}], "unknown sketch entity")):
        op = SketchGroup("op1", points=[[0, 0], [1, 0]], entities=entities)
        assert message in replay(GeometryDocument([op])).errors()[0]

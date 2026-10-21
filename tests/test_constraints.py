# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The sketch constraint solver (aeroflowsim/geometry_model/constraints.py) on known sketches:
a rectangle fully constrained by its dimensions, driving a dimension, tangency, angles, equal,
point on curve, degrees of freedom, and conflicting constraints."""

import math

import numpy as np
import pytest

from aeroflowsim.geometry_model import GeometryDocument, replay
from aeroflowsim.geometry_model.constraints import solve
from aeroflowsim.geometry_model.operations import SketchGroup

LINES = [{"type": "line", "p": [k, (k + 1) % 4]} for k in range(4)]


def skewed_quad():
    """A rough, hand-drawn quadrilateral (about 30 x 20 mm)."""
    return np.array([[0.0, 0.0], [0.031, 0.001], [0.029, 0.021], [-0.001, 0.019]])


def rectangle_constraints(w=0.03, h=0.02):
    return [{"type": "fix", "p": 0, "at": [0.0, 0.0]},
            {"type": "horizontal", "e": 0}, {"type": "vertical", "e": 1},
            {"type": "horizontal", "e": 2}, {"type": "vertical", "e": 3},
            {"type": "length", "e": 0, "value": w}, {"type": "length", "e": 1, "value": h}]


def test_a_rectangle_fully_constrained_by_two_dimensions():
    result = solve(skewed_quad(), LINES, rectangle_constraints())
    assert result.dof == 0 and result.status == "fully constrained" and not result.conflicting
    assert result.points == pytest.approx(np.array([[0, 0], [0.03, 0], [0.03, 0.02], [0, 0.02]]), abs=1e-12)


def test_changing_a_dimension_drives_the_shape_and_free_sketches_stay_near_the_drawing():
    result = solve(skewed_quad(), LINES, rectangle_constraints(w=0.05))
    assert result.points[1] == pytest.approx([0.05, 0.0], abs=1e-12)
    free = solve(skewed_quad(), LINES, [{"type": "horizontal", "e": 0}])
    assert free.dof == 7 and free.status == "7 degrees of freedom left"
    assert np.abs(free.points - skewed_quad()).max() < 0.001                  # moved only a little
    assert free.points[0][1] == pytest.approx(free.points[1][1], abs=1e-12)


def test_conflicting_and_redundant_constraints_are_found():
    clash = rectangle_constraints() + [{"type": "distance", "p": [0, 2], "value": 0.01}]   # diagonal < side
    result = solve(skewed_quad(), LINES, clash)
    assert result.conflicting
    assert result.status == "conflicting"
    repeat = rectangle_constraints() + [{"type": "parallel", "e": [0, 2]}]                  # already true
    result = solve(skewed_quad(), LINES, repeat)
    assert not result.conflicting and result.redundant >= 1 and result.dof == 0
    doc = GeometryDocument([SketchGroup("op1", points=skewed_quad().tolist(), entities=LINES, constraints=clash)])
    assert "cannot all be met" in replay(doc).errors()[0]


def test_tangent_arc_equal_angle_and_point_on():
    # A line along x and an arc whose centre should sit 5 mm above it, tangent to it.
    pts = [[0.0, 0.0], [0.02, 0.0], [0.01, 0.006], [0.017, 0.006], [0.01, 0.013]]
    ents = [{"type": "line", "p": [0, 1]}, {"type": "arc", "p": [3, 4], "c": 2}]
    cons = [{"type": "fix", "p": 0, "at": [0, 0]}, {"type": "horizontal", "e": 0},
            {"type": "tangent", "e": [0, 1]}, {"type": "radius", "e": 1, "value": 0.005}]
    result = solve(pts, ents, cons)
    centre = result.points[2]
    assert not result.conflicting and abs(centre[1]) == pytest.approx(0.005, abs=1e-12)
    assert np.linalg.norm(result.points[3] - centre) == pytest.approx(0.005, abs=1e-12)   # arc ends on the circle
    two = [[0, 0], [0.02, 0.0], [0.0, 0.0001], [0.01, 0.012]]
    lines = [{"type": "line", "p": [0, 1]}, {"type": "line", "p": [2, 3]}]
    result = solve(two, lines, [{"type": "fix", "p": 0, "at": [0, 0]}, {"type": "horizontal", "e": 0},
                                {"type": "coincident", "p": [0, 2]}, {"type": "angle", "e": [0, 1], "value": 60.0},
                                {"type": "equal", "e": [0, 1]}])
    d = result.points[3] - result.points[2]
    assert math.degrees(math.atan2(d[1], d[0])) == pytest.approx(60.0, abs=1e-9)
    assert np.linalg.norm(d) == pytest.approx(np.linalg.norm(result.points[1] - result.points[0]), rel=1e-12)
    circle = solve([[0, 0], [0.011, 0.002]], [{"type": "circle", "c": 0, "r": 0.009}],
                   [{"type": "fix", "p": 0, "at": [0, 0]}, {"type": "point_on", "p": 1, "e": 0},
                    {"type": "radius", "e": 0, "value": 0.01}])
    assert np.linalg.norm(circle.points[1]) == pytest.approx(0.01, abs=1e-12) and circle.entities[0]["r"] == pytest.approx(0.01)


def test_a_constrained_sketch_replays_exactly_and_shows_its_dimensions():
    op = SketchGroup("op1", points=skewed_quad().tolist(), entities=LINES, constraints=rectangle_constraints(),
                     role="fluid")
    built = replay(GeometryDocument([op]))
    (face,) = built.faces.values()
    assert face.area == pytest.approx(0.03 * 0.02, rel=1e-12)
    assert built.sketch_status["op1"] == "fully constrained"
    texts = sorted(d["text"] for d in built.dimensions)
    assert texts == ["20", "30"]                                          # shown in mm


# ---- in the workspace: auto-constraints while drawing, constraints from a selection --------------------

from aeroflowsim.gui import geometry_logic as logic          # noqa: E402  (no Qt in these modules)
from aeroflowsim.gui.sketch_tools import PolylineTool, Rectangle3Tool, RectangleTool   # noqa: E402


def drawn_rectangle(w=0.03, h=0.02):
    tool = RectangleTool()
    tool.click(np.array([0.0, 0.0]), 1e-9)
    tool.click(np.array([w, h]), 1e-9)
    doc = GeometryDocument()
    tool.add_to(doc, role="fluid")
    return doc


def test_drawing_captures_horizontal_vertical_tangent_and_right_angles():
    op = drawn_rectangle().operations[0]
    assert sorted(c["type"] for c in op.params["constraints"]) == ["horizontal"] * 2 + ["vertical"] * 2
    tool = PolylineTool()
    for xy in ((0.0, 0.0), (0.02, 0.0)):
        tool.click(np.array(xy), 1e-9)
    tool.arc_next = True
    tool.click(np.array([0.03, 0.01]), 1e-9)
    kinds = [c["type"] for c in tool.operation().params["constraints"]]
    assert kinds == ["horizontal", "tangent"]
    turned = Rectangle3Tool()
    for xy in ((0.0, 0.0), (0.02, 0.01), (0.0, 0.03)):
        turned.click(np.array(xy), 1e-9)
    assert [c["type"] for c in turned.operation().params["constraints"]] == ["perpendicular"] * 3
    built = replay(_doc(turned.operation()))
    assert not built.errors() and built.sketch_status["op1"] == "5 degrees of freedom left"


def _doc(op):
    doc = GeometryDocument()
    doc.add(op)
    return doc


def test_constraints_from_a_selection_and_driving_a_dimension():
    doc = drawn_rectangle()
    built = replay(doc)
    bottom = next(e for e in built.edges.values() if np.allclose(e.points[:, 1], 0.0))
    op_id, c = logic.constraint_for("dimension", [("edge", bottom.id)], built, doc)
    assert op_id == "op1" and c["type"] == "length" and c["value"] == pytest.approx(0.03)
    doc = logic.add_constraint(doc, op_id, {**c, "value": 0.05})        # 30 -> 50 mm: the shape follows
    built = replay(doc)
    assert sum(f.area for f in built.faces.values()) == pytest.approx(0.05 * 0.02, rel=1e-12)
    assert [d["text"] for d in built.dimensions] == ["50"]
    corner = min(built.vertices.values(), key=lambda v: v.xy.sum())                 # bottom left
    op_id, fix = logic.constraint_for("fix", [("vertex", corner.id)], built, doc)
    doc = logic.add_constraint(doc, op_id, fix)
    left = min(built.edges.values(), key=lambda e: np.ptp(e.points[:, 0]) + e.points[:, 0].mean())
    _, height = logic.constraint_for("dimension", [("edge", left.id)], built, doc)
    doc = logic.add_constraint(doc, "op1", height)
    built = replay(doc)
    assert built.sketch_status["op1"] == "fully constrained"
    index = len(doc.find("op1").params["constraints"]) - 1
    built = replay(logic.set_constraint(doc, "op1", index, 0.01))                  # height 20 -> 10 mm
    assert sum(f.area for f in built.faces.values()) == pytest.approx(0.05 * 0.01, rel=1e-12)
    built = replay(logic.set_constraint(doc, "op1", index, remove=True))
    assert built.sketch_status["op1"] == "1 degree of freedom left"
    with pytest.raises(ValueError, match="two lines"):
        logic.constraint_for("parallel", [("edge", bottom.id)], built, doc)


def test_tangent_at_a_shared_end_point_counts_as_one_equation():
    # A vertical line, then a tangent arc starting at its top end: tangency removes one freedom
    # (it is not "redundant", and it holds after a dimension moves things).
    pts = [[0.0, 0.0], [0.0, 0.01], [0.01, 0.01], [-0.0, 0.02]]           # line 0-1, arc 1 -> 3 about 2
    ents = [{"type": "line", "p": [0, 1]}, {"type": "arc", "p": [3, 1], "c": 2}]
    free = solve(pts, ents, [])
    result = solve(pts, ents, [{"type": "tangent", "e": [0, 1]}, {"type": "radius", "e": 1, "value": 0.012}])
    assert result.redundant == 0 and result.dof == free.dof - 2
    t = result.points[1] - result.points[0]
    radius = result.points[1] - result.points[2]
    assert t @ radius == pytest.approx(0.0, abs=1e-15)

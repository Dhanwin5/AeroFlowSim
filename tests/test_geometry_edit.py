# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Editing operations (aeroflowsim/geometry_model/edit_operations.py): split face and edge, trim,
extend, offset, chamfer, pattern, fill, merge, deleting an edge between faces - exact areas and
lengths, names that survive, clear messages."""

import math

import numpy as np
import pytest

from aeroflowsim.geometry_model import FLUID, SOLID, GeometryDocument, replay
from aeroflowsim.geometry_model.edit_operations import (
    Chamfer, Extend, Fill, MergeFaces, Offset, Pattern, SplitEdge, SplitFace, Trim)
from aeroflowsim.geometry_model.operations import Delete, NameBoundary, SketchGroup


def doc_of(*ops):
    doc = GeometryDocument()
    for op in ops:
        doc.add(op)
    return doc


def rectangle(x0=0.0, y0=0.0, w=0.02, h=0.01, role=FLUID):
    pts = [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]]
    return SketchGroup(points=pts, entities=[{"type": "line", "p": [k, (k + 1) % 4]} for k in range(4)], role=role)


def line(a, b):
    return SketchGroup(points=[list(a), list(b)], entities=[{"type": "line", "p": [0, 1]}])


def test_split_face_along_a_drawn_line_keeps_roles_and_names():
    doc = doc_of(rectangle(), NameBoundary(edges=["op1:e1"], name="floor", kind="wall"),
                 line((0.006, -0.005), (0.008, 0.015)))
    doc.add(SplitFace(curves=["op3:e1"]))
    built = replay(doc)
    assert not built.errors()
    faces = sorted(built.faces.values(), key=lambda f: f.centroid[0])
    assert [f.id for f in faces] == ["op1:face#1", "op1:face#2"] and all(f.role == FLUID for f in faces)
    assert sum(f.area for f in faces) == pytest.approx(0.02 * 0.01, rel=1e-12)
    assert faces[0].area == pytest.approx(0.007 * 0.01, rel=1e-12)            # the cut runs through x = 7 mm mid-height
    assert not [e for e in built.edges.values() if not e.faces]                # the line's outside parts are gone
    floor = [e for e in built.edges if built.names.get(e) and built.names[e].name == "floor"]
    assert len(floor) == 2                                                     # both pieces keep the name
    shared = [e for e in built.edges.values() if len(e.faces) == 2]
    assert len(shared) == 1 and shared[0].id not in built.boundary_edges()     # the cut is inside the fluid
    miss = doc_of(rectangle(), line((0.03, 0.0), (0.04, 0.01)))
    miss.add(SplitFace(curves=["op2:e1"]))
    assert "do not cut across" in replay(miss).errors()[0]


def test_split_edge_and_delete_the_edge_between_two_faces():
    doc = doc_of(rectangle(), NameBoundary(edges=["op1:e1"], name="floor", kind="wall"))
    doc.add(SplitEdge(edge="op1:e1", x=0.005, y=-0.001))
    built = replay(doc)
    pieces = sorted(e.length for e in built.edges.values() if e.id.startswith("op1:e1"))
    assert pieces == pytest.approx([0.005, 0.015]) and all(built.names[e].name == "floor"
                                                          for e in built.edges if e.startswith("op1:e1"))
    two = doc_of(rectangle(), line((0.01, -0.005), (0.01, 0.015)))
    two.add(SplitFace(curves=["op2:e1"]))
    cut = next(e.id for e in replay(two).edges.values() if len(e.faces) == 2)
    two.add(Delete(targets=[cut]))                                             # deleting the cut merges again
    (face,) = replay(two).faces.values()
    assert face.area == pytest.approx(0.0002, rel=1e-12)


def test_trim_removes_the_piece_between_crossings_then_split():
    # A line sticking out of a rectangle: trim both outer ends, then split the face along what remains.
    doc = doc_of(rectangle(role=SOLID), line((0.01, -0.005), (0.01, 0.015)))
    doc.add(Trim(x=0.01, y=-0.004))
    doc.add(Trim(x=0.01, y=0.014))
    built = replay(doc)
    assert not built.errors()
    inner = [e for e in built.edges.values() if e.id.startswith("op2:e1")]
    assert len(inner) == 1 and inner[0].length == pytest.approx(0.01)        # only the part inside is left
    assert len(built.faces) == 1 and built.edges["op1:e1"].length == pytest.approx(0.02)   # others untouched
    doc.add(SplitFace(curves=[inner[0].id]))
    built = replay(doc)
    assert sorted(round(f.area, 12) for f in built.faces.values()) == pytest.approx([0.0001, 0.0001])
    assert all(f.role == SOLID for f in built.faces.values())
    # Trimming a side of the rectangle opens it: no face is left, three curves remain.
    opened = doc_of(rectangle())
    opened.add(Trim(x=0.02, y=0.005))
    built = replay(opened)
    assert not built.faces and len(built.edges) == 3


def test_extend_a_line_to_the_next_curve():
    doc = doc_of(line((0.0, 0.0), (0.0, 0.01)), line((0.005, 0.0), (0.005, 0.03)))
    doc.operations[0].params["points"] = [[-0.01, 0.02], [-0.002, 0.02]]      # a horizontal line ending short
    doc.add(Extend(edge="op1:e1", x=-0.002, y=0.02))
    built = replay(doc)
    assert built.edges["op1:e1"].length == pytest.approx(0.015)              # now up to x = 5 mm
    no_hit = doc_of(line((0.0, 0.0), (0.01, 0.0)))
    no_hit.add(Extend(edge="op1:e1", x=0.01, y=0.0))
    assert "meets no other curve" in replay(no_hit).errors()[0]


def test_offset_of_a_closed_loop_and_of_an_arc():
    doc = doc_of(rectangle(role=SOLID))
    doc.add(Offset(edges=[f"op1:e{k}" for k in range(1, 5)], distance=0.002, role=FLUID))
    built = replay(doc)
    outer = next(f for f in built.faces.values() if f.id.startswith("op2"))
    # Outward offset of a rectangle with mitred (sharp) corners: (w + 2d)(h + 2d).
    assert outer.area == pytest.approx(0.024 * 0.014, rel=1e-12)
    inward = doc_of(rectangle(role=SOLID))
    inward.add(Offset(edges=[f"op1:e{k}" for k in range(1, 5)], distance=-0.002))
    face = next(f for f in replay(inward).faces.values() if f.id.startswith("op2"))
    assert face.area == pytest.approx(0.016 * 0.006, rel=1e-12)
    arc = SketchGroup(points=[[0.01, 0.0], [0.0, 0.01], [0.0, 0.0]], entities=[{"type": "arc", "p": [0, 1], "c": 2}])
    doc = doc_of(arc)
    doc.add(Offset(edges=["op1:e1"], distance=0.003))                       # left of a ccw arc = inward
    built = replay(doc)
    assert built.edges["op2:e1"].length == pytest.approx(0.5 * math.pi * 0.007, rel=1e-9)
    assert built.edges["op2:e1"].kind == "arc"


def test_offset_with_a_round_join_at_a_line_arc_corner():
    pts = [[0.0, 0.0], [0.01, 0.0], [0.01, 0.01], [0.0, 0.01]]           # line, then a semicircle back? -> L shape
    l_shape = SketchGroup(points=pts[:3], entities=[{"type": "line", "p": [0, 1]}, {"type": "line", "p": [1, 2]}])
    doc = doc_of(l_shape)
    doc.add(Offset(edges=["op1:e1", "op1:e2"], distance=-0.001))           # to the right: outside the corner
    built = replay(doc)
    lengths = sorted(e.length for e in built.edges.values() if e.id.startswith("op2"))
    assert lengths == pytest.approx([0.011, 0.011])                          # lines mitred at the corner


def test_chamfer_pattern_fill_and_merge():
    doc = doc_of(rectangle())
    doc.add(Chamfer(edges=["op1:e1", "op1:e2"], d1=0.002, d2=0.001))
    (face,) = replay(doc).faces.values()
    assert face.area == pytest.approx(0.0002 - 0.5 * 0.002 * 0.001, rel=1e-12)
    pattern = doc_of(rectangle(role=SOLID))
    pattern.add(Pattern(targets=["op1:face"], kind="linear", count=4, dx=0.03, dy=0.0))
    built = replay(pattern)
    assert len(built.faces) == 4 and built.bbox()[2] == pytest.approx(0.11)
    circular = doc_of(rectangle(x0=0.01, role=SOLID))
    circular.add(Pattern(targets=["op1:face"], kind="circular", count=4, angle=90.0))
    assert len(replay(circular).faces) == 4
    loose = SketchGroup(points=[[0, 0], [0.01, 0], [0.0, 0.01]],
                        entities=[{"type": "line", "p": [0, 1], "construction": False}])
    doc = doc_of(line((0, 0), (0.01, 0)), line((0.01, 0), (0, 0.01)), line((0, 0.01), (0, 0)))
    doc.add(Fill(edges=["op1:e1", "op2:e1", "op3:e1"], role=FLUID))
    (face,) = replay(doc).faces.values()
    assert face.area == pytest.approx(0.5e-4) and face.role == FLUID
    merge = doc_of(rectangle(), rectangle(x0=0.02))
    merge.add(MergeFaces(faces=["op1:face", "op2:face"]))
    (face,) = replay(merge).faces.values()
    assert face.area == pytest.approx(0.0004, rel=1e-12)
    assert loose.type == "sketch_group"

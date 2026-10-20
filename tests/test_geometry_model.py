# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the geometry workspace model (aeroflowsim/geometry_model/): history and replay,
every operation, exact areas after booleans and enclosures, stable edge ids (lineage),
boundary names, suggestions and checks, and the picking maths (a click -> an edge id).
"""

import math

import numpy as np
import pytest

from aeroflowsim.discovery import load_case
from aeroflowsim.geometry_model import (
    FLUID, SOLID, GeometryDocument, ReplayContext, operation_from_dict, replay, template_document)
from aeroflowsim.geometry_model import boundaries, picking
from aeroflowsim.geometry_model.operations import (
    BooleanOp, Delete, Enclosure, NameBoundary, Refinement, SetRole, TemplateShape, Transform)
from aeroflowsim.parameters import defaults, validate

EXTERNAL = load_case("external_2d")
NOZZLE = load_case("nozzle_axi")
REL = 1e-9          # exact geometry: relative tolerance for areas [-]


def context(case, **changes):
    params = validate(case.parameters(), {**defaults(case.parameters()), **changes})
    return ReplayContext(case, params)


def body(shape="Diamond airfoil", **changes):
    """A document with only the shape-library body (a solid face) and its context."""
    return GeometryDocument([TemplateShape("op1")]), context(EXTERNAL, shape=shape, **changes)


def rhombus_area(chord=1.0, t=0.1):
    return 0.5 * chord * t * chord


# ---- templates and replay --------------------------------------------------------------------------

def test_template_documents_reproduce_the_template_geometry():
    doc = template_document(EXTERNAL)
    assert [op.type for op in doc.operations] == ["template_shape", "template_enclosure"]
    assert doc.is_template_only()
    built = replay(doc, context(EXTERNAL))
    (face,) = built.faces.values()
    assert face.role == FLUID
    assert face.area == pytest.approx(math.pi * 20.0**2 - rhombus_area(), rel=REL)   # circle R = 20 L minus diamond
    assert set(built.patches()) == {"wall", "farfield"}
    noz = replay(template_document(NOZZLE), context(NOZZLE))
    assert noz.axisymmetric
    assert set(noz.patches()) == {"wall", "inlet", "outlet", "axis"}
    assert next(iter(noz.faces.values())).area == pytest.approx(2.52964e-6, rel=1e-5)   # validation/report.md


def test_replay_is_deterministic():
    doc = template_document(EXTERNAL)
    doc.add(Transform(kind="rotate", angle=7.0))
    a, b = replay(doc, context(EXTERNAL)), replay(doc, context(EXTERNAL))
    assert list(a.edges) == list(b.edges) and list(a.vertices) == list(b.vertices)
    for edge_id in a.edges:
        assert np.array_equal(a.edges[edge_id].points, b.edges[edge_id].points)
    assert {k: v.area for k, v in a.faces.items()} == {k: v.area for k, v in b.faces.items()}


def test_history_round_trips_through_json(tmp_path):
    doc = template_document(EXTERNAL)
    doc.add(Transform(kind="move", dx=1.0, targets=["op1:body"]))
    doc.add(NameBoundary(edges=["op1:body.1"], name="upper_wall", kind="wall", inflation=True))
    doc.add(Refinement(shape="circle", radius=2.0, size=0.05))
    path = tmp_path / "history.json"
    doc.save(path)
    again = GeometryDocument.load(path)
    assert again == doc
    assert again.next_number == 6 and not again.is_template_only()
    with pytest.raises(ValueError, match="unknown geometry operation"):
        operation_from_dict({"type": "teleport", "id": "op9"})
    with pytest.raises(ValueError, match="unknown setting"):
        Transform(spin=3)


def test_editing_an_earlier_operation_reruns_the_later_ones():
    doc = template_document(EXTERNAL)
    doc.add(NameBoundary(edges=["op1:body.2"], name="lower_wall", kind="wall"))
    built = replay(doc, context(EXTERNAL))
    assert built.names["op1:body.2"].name == "lower_wall"
    # A different far-field radius (an earlier operation's input) keeps the later name.
    bigger = replay(doc, context(EXTERNAL, domain_radius=40.0))
    assert bigger.names["op1:body.2"].name == "lower_wall"
    assert next(iter(bigger.faces.values())).area == pytest.approx(math.pi * 40.0**2 - rhombus_area(), rel=REL)


def test_a_failing_operation_stops_the_replay_with_a_message():
    doc = template_document(EXTERNAL)
    doc.add(Transform(kind="scale", factor=-1.0))
    doc.add(Refinement(size=0.1))
    built = replay(doc, context(EXTERNAL))
    assert built.failed_operation == "op3"
    assert any("scale factor must be positive" in text for text in built.errors())
    assert built.regions == []                 # the refinement after it was not applied
    assert built.faces                         # the geometry up to the failure is still there


# ---- transforms ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind, params, scale", [
    ("move", dict(dx=2.0, dy=-1.0), 1.0),
    ("rotate", dict(angle=30.0, cx=0.5), 1.0),
    ("scale", dict(factor=2.0), 4.0),
    ("mirror", dict(angle=90.0, cx=3.0), 1.0),
])
def test_transforms_keep_ids_and_change_areas_as_expected(kind, params, scale):
    doc, ctx = body()
    before = replay(doc, ctx)
    doc.add(Transform(kind=kind, **params))
    after = replay(doc, ctx)
    assert set(after.edges) == set(before.edges)                     # stable ids
    assert after.faces["op1:body"].area == pytest.approx(scale * before.faces["op1:body"].area, rel=REL)
    if kind == "move":
        shift = after.faces["op1:body"].centroid - before.faces["op1:body"].centroid
        assert shift == pytest.approx([2.0, -1.0])


def test_rotate_about_a_point_is_an_angle_of_attack():
    doc, ctx = body()
    doc.add(Transform(kind="rotate", angle=-10.0, cx=0.25))       # 10 deg nose up about the quarter chord
    built = replay(doc, ctx)
    nose = min((v.xy for v in built.vertices.values()), key=lambda p: p[0])
    expected = np.array([0.25 - 0.25 * math.cos(math.radians(10)), 0.25 * math.sin(math.radians(10))])
    assert nose == pytest.approx(expected, abs=1e-12)


def test_copy_makes_new_ids():
    doc, ctx = body()
    doc.add(Transform(kind="move", dy=2.0, copy=True))
    built = replay(doc, ctx)
    assert set(built.faces) == {"op1:body", "op1:body@op2"}
    assert "op1:body.1@op2" in built.edges and "op1:body.1" in built.edges


# ---- booleans, roles, delete, enclosures --------------------------------------------------------

def test_circle_minus_cylinder_is_exact_and_names_follow_the_pieces():
    doc, ctx = body("Circular cylinder", **{"cylinder.diameter": 2.0})
    doc.add(Enclosure(kind="circle", radius=5.0))     # R = 5 L = 10 m around a D = 2 m cylinder
    built = replay(doc, ctx)
    (face,) = built.faces.values()
    assert face.role == FLUID and len(face.loops) == 2
    assert face.area == pytest.approx(math.pi * (10.0**2 - 1.0**2), rel=1e-6)   # spline circle: 1e-6
    sugg = boundaries.suggestions(built)
    assert not sugg                                   # every edge already has its default name
    assert set(built.patches()) == {"wall", "farfield"}


@pytest.mark.parametrize("kind, area", [
    ("circle", math.pi * 20.0**2),
    ("rectangle", (10.0 + 1.0 + 20.0) * 2 * 10.0),
    ("c_domain", 0.5 * math.pi * 20.0**2 + 2 * 20.0 * (0.5 + 20.0)),
])
def test_enclosures_minus_a_diamond_are_exact(kind, area):
    doc, ctx = body()
    doc.add(Enclosure(kind=kind))
    built = replay(doc, ctx)
    (face,) = built.faces.values()
    assert face.area == pytest.approx(area - rhombus_area(), rel=REL)
    assert {b.type for b in built.names.values()} == {"wall", "farfield"}
    assert not boundaries.boundary_problems(built)


@pytest.mark.parametrize("kind", ["circle", "rectangle", "c_domain"])
def test_half_enclosures_have_a_symmetry_line(kind):
    doc, ctx = body()
    full = replay(doc.copy(), ctx)
    doc.add(Enclosure(kind=kind, half=True))
    half = replay(doc, ctx)
    doc2 = doc.copy()
    doc2.operations[-1].params["half"] = False
    whole = replay(doc2, ctx)
    assert next(iter(half.faces.values())).area == pytest.approx(0.5 * next(iter(whole.faces.values())).area,
                                                                 rel=REL)
    sym = [e for e in half.boundary_edges() if half.names[e].type == "symmetry"]
    assert len(sym) == 2                              # in front of and behind the body
    assert all(boundaries.on_axis(half.edges[e], half.size) for e in sym)
    assert full.faces["op1:body"].role == SOLID


def test_axisymmetric_body_gets_an_axis_and_a_volume_of_revolution():
    doc, ctx = body("Conical nose cone")
    doc.add(Enclosure(kind="circle", radius=10.0))
    built = replay(doc, ctx)
    assert built.axisymmetric
    assert {built.names[e].type for e in built.boundary_edges()} == {"wall", "farfield", "axis"}
    # Pappus: volume of revolution of the half domain = 2 pi A y_centroid; the sphere minus the body.
    (face,) = built.faces.values()
    volume = 2.0 * math.pi * face.area * face.centroid[1]
    profile = ctx.template_geometry()
    L = profile.bbox[2] - profile.bbox[0]
    assert volume == pytest.approx(4.0 / 3.0 * math.pi * (10.0 * L)**3 - profile.volume_of_revolution(), rel=1e-6)


def test_set_role_and_boolean_union():
    doc, ctx = body()
    doc.add(Transform(kind="move", dx=0.5, copy=True))                       # two overlapping diamonds
    doc.add(BooleanOp(kind="union", objects=["op1:body"], tools=["op1:body@op2"]))
    doc.add(SetRole(faces=["op1:body"], role=FLUID))
    built = replay(doc, ctx)
    assert list(built.faces) == ["op1:body"] and built.faces["op1:body"].role == FLUID
    # union area = 2 rhombi - overlap (a rhombus of half the size: area / 4)
    assert built.faces["op1:body"].area == pytest.approx(2 * rhombus_area() - rhombus_area() / 4, rel=REL)


def test_delete_a_face_and_refuse_to_delete_a_face_edge():
    doc, ctx = body()
    doc.add(Transform(kind="move", dy=3.0, copy=True))
    doc.add(Delete(targets=["op1:body"]))
    built = replay(doc, ctx)
    assert list(built.faces) == ["op1:body@op2"]
    bad = GeometryDocument([TemplateShape("op1"), Delete("op2", targets=["op1:body.1"])])
    assert "cannot be deleted on its own" in replay(bad, ctx).errors()[0]


def test_enclosure_without_a_body_is_an_error():
    doc = template_document(NOZZLE)
    doc.add(Enclosure())
    built = replay(doc, context(NOZZLE))
    assert "there is none" in built.errors()[0]


# ---- names, suggestions and checks ----------------------------------------------------------------

def test_user_names_override_defaults_and_bad_names_are_refused():
    doc = template_document(NOZZLE)
    doc.add(NameBoundary(edges=["op1:wall.1", "op1:wall.2", "op1:wall.3"], name="nozzle_wall", kind="wall",
                         inflation=True))
    built = replay(doc, context(NOZZLE))
    assert set(built.patches()) == {"nozzle_wall", "inlet", "outlet", "axis"}
    assert all(built.names[e].inflation for e in built.patches()["nozzle_wall"][1])
    bad = template_document(NOZZLE)
    bad.add(NameBoundary(edges=["op1:inlet"], name="2 bad", kind="inlet"))
    assert "not a valid boundary name" in replay(bad, context(NOZZLE)).errors()[0]
    bad.operations[-1].params.update(name="in", kind="sideways")
    assert "not a boundary type" in replay(bad, context(NOZZLE)).errors()[0]


def test_missing_and_conflicting_names_are_reported():
    doc = template_document(NOZZLE)
    doc.add(NameBoundary(edges=["op1:inlet"], name="wall", kind="inlet"))       # same name, other type
    built = replay(doc, context(NOZZLE))
    assert any("different types" in text for _, text in boundaries.boundary_problems(built))
    stale = template_document(NOZZLE)
    stale.add(NameBoundary(edges=["op7:gone"], name="x", kind="wall"))
    assert any("no longer exist" in text for _, text in replay(stale, context(NOZZLE)).messages)


def test_suggestions_for_a_cut_out_body_without_default_names():
    doc, ctx = body()
    doc.add(Enclosure(kind="rectangle"))
    built = replay(doc, ctx)
    for edge_id in list(built.names):            # pretend nothing had a default name
        del built.names[edge_id]
    sugg = boundaries.suggestions(built)
    assert {b.type for b in sugg.values()} == {"wall", "farfield"}
    assert sum(b.type == "wall" for b in sugg.values()) == 4
    assert boundaries.boundary_problems(built)[0][0] == "error"


# ---- picking: a click position -> an edge id (no window needed) ---------------------------------

def test_picking_finds_vertices_edges_and_faces():
    doc, ctx = body()
    doc.add(Enclosure(kind="rectangle"))
    built = replay(doc, ctx)
    tol = 0.01
    # Halfway along the upper front edge of the diamond (0,0) -> (0.5, 0.05), slightly above it.
    hit = picking.pick(built, (0.25, 0.026), tol)
    assert hit[0] == "edge" and built.edges[hit[1]].sources[0].startswith("op1:body")
    # The diamond's nose is a vertex.
    kind, vertex = picking.pick(built, (0.001, 0.0), tol)
    assert kind == "vertex" and np.allclose(built.vertices[vertex].xy, [0.0, 0.0])
    # Far from every edge, inside the fluid: the face.
    assert picking.pick(built, (5.0, 5.0), tol) == ("face", "op2:domain")
    # Inside the body (a hole of the fluid face): nothing.
    assert picking.pick(built, (0.5, 0.0), tol) is None
    assert picking.nearest_edge(built, (100.0, 100.0), tol) is None
    top = picking.nearest_edge(built, (5.0, 10.003), tol)
    assert top[0] == "op2:farfield.top" and top[1] == pytest.approx(0.003)


def test_rubber_band_selection():
    doc, ctx = body()
    built = replay(doc, ctx)
    assert sorted(picking.edges_in_box(built, -0.1, -0.1, 1.1, 0.1)) == sorted(built.edges)
    assert picking.edges_in_box(built, -0.1, 0.0, 1.1, 0.1) == [e for e in built.edges
                                                               if built.edges[e].points[:, 1].min() >= 0.0]


def test_distance_to_segments_formula():
    a, b = np.array([[0.0, 0.0], [0.0, 0.0]]), np.array([[1.0, 0.0], [0.0, 1.0]])
    assert picking.distance_to_segments(np.array([0.5, 0.2]), a, b) == pytest.approx([0.2, 0.5])
    assert picking.distance_to_segments(np.array([2.0, 0.0]), a, b) == pytest.approx([1.0, 2.0])

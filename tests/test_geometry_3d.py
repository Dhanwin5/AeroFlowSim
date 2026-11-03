# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the 3D geometry workspace model (aeroflowsim/geometry_model/: operations3d.py, kernel3d.py, built3d.py)."""

import json
import math

import pytest

pytest.importorskip("gmsh")

from aeroflowsim.geometry_model import GeometryDocument, ReplayContext, replay  # noqa: E402
from aeroflowsim.geometry_model.document import FORMAT, FORMAT_3D  # noqa: E402
from aeroflowsim.geometry_model.operations import Sketch  # noqa: E402
from aeroflowsim.geometry_model.operations3d import (  # noqa: E402
    Boolean3D, Box, Cone, Cylinder, Delete3D, Enclosure3D, Extrude, ImportSolid, NameFaces, Refinement3D, Revolve,
    SetRole3D, Sphere, Transform3D)

PI = math.pi


def doc3(*ops):
    return GeometryDocument(list(ops), dimension=3)


# ---- the document: format, old 2D files ---------------------------------------------------------

def test_old_2d_history_loads_and_saves_unchanged():
    old = {"format": 1, "axisymmetric": False, "next_number": 3,
           "operations": [{"id": "op1", "type": "sketch", "suppressed": False, "kind": "circle",
                           "points": [[0.0, 0.0], [1.0, 0.0]], "role": "fluid"}]}
    doc = GeometryDocument.from_dict(old)
    assert doc.dimension == 2
    saved = doc.to_dict()
    assert "dimension" not in saved and saved["format"] == FORMAT == 1      # byte-for-byte as before 3D existed
    assert saved == GeometryDocument.from_dict(saved).to_dict()
    assert json.loads(doc.to_json())["operations"][0]["kind"] == "circle"


def test_3d_document_round_trip_and_version(tmp_path):
    doc = doc3(Box("op1"), Sphere("op2", radius=0.02), NameFaces("op3", faces=["op2:surface"], name="ball"))
    path = tmp_path / "history.json"
    doc.save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == FORMAT_3D == 2 and data["dimension"] == 3
    again = GeometryDocument.load(path)
    assert again == doc and again.dimension == 3 and again.next_number == 4
    with pytest.raises(ValueError, match="newer"):
        GeometryDocument.from_dict({**data, "format": 99})


def test_2d_and_3d_operations_do_not_mix():
    with pytest.raises(ValueError, match="cannot contain"):
        GeometryDocument([Box("op1")])                                  # a 3D operation in a 2D document
    with pytest.raises(ValueError, match="cannot contain"):
        doc3(Sketch("op1", kind="circle", points=[[0, 0], [1, 0]]))
    with pytest.raises(ValueError):
        GeometryDocument([], dimension=4)


# ---- bodies ------------------------------------------------------------------------------------

def test_primitives_volumes_areas_and_face_ids():
    built = replay(doc3(Box("op1", dx=1, dy=2, dz=3), Cylinder("op2", x=5, ax=0, az=2, radius=0.5),
                        Sphere("op3", xc=10, radius=1), Cone("op4", x=20, ax=1, r1=0.5, r2=0)), triangulate=False)
    b = built.bodies
    assert b["op1"].volume == pytest.approx(6.0, rel=1e-12) and b["op1"].area == pytest.approx(22.0, rel=1e-12)
    assert b["op2"].volume == pytest.approx(PI * 0.25 * 2, rel=1e-12)
    assert b["op3"].volume == pytest.approx(4 / 3 * PI, rel=1e-12)
    assert b["op4"].volume == pytest.approx(PI * 0.25 / 3, rel=1e-12)
    assert {f for f in built.faces if f.startswith("op1:")} == {f"op1:{s}" for s in
                                                                 ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")}
    assert {f for f in built.faces if f.startswith("op2:")} == {"op2:side", "op2:base", "op2:top"}
    assert built.faces["op2:top"].centroid[2] == pytest.approx(2.0)
    assert {f for f in built.faces if f.startswith("op4:")} == {"op4:side", "op4:base"}     # a sharp tip: no top
    assert built.faces["op3:surface"].kind == "sphere"
    assert all(built.names[f].type == "wall" for f in built.faces)        # faces of solid bodies: walls by default
    assert all(body.role == "solid" for body in b.values())


def test_revolve_and_extrude():
    built = replay(doc3(Revolve("op1", points=[[0, 0], [1, 0], [1, 0.2], [0, 0.4]], angle=90)), triangulate=False)
    body = built.bodies["op1"]
    assert body.volume == pytest.approx(PI / 3 * (0.04 + 0.08 + 0.16) / 4, rel=1e-12)
    assert {"op1:start", "op1:end", "op1:edge2", "op1:edge3", "op1:edge4"} == set(built.faces)  # edge1 is on the axis
    assert built.names["op1:start"].type == "symmetry"
    built = replay(doc3(Extrude("op1", points=[[0, 0], [1, 0], [0, 1]], z0=0.5, length=2)), triangulate=False)
    assert built.bodies["op1"].volume == pytest.approx(1.0, rel=1e-12)
    assert built.faces["op1:top"].centroid[2] == pytest.approx(2.5)
    assert built.faces["op1:side2"].area == pytest.approx(2 * math.sqrt(2), rel=1e-12)   # the hypotenuse


def test_revolve_wall_profile_file_makes_a_nozzle(tmp_path):
    csv = tmp_path / "wall.csv"
    csv.write_text("x_mm,r_mm\n0,10\n10,10\n20,4\n35,6\n50,8\n", encoding="utf-8")
    built = replay(doc3(Revolve("op1", profile="wall", file="wall.csv", role="fluid")),
                   ReplayContext(folder=tmp_path), triangulate=False)
    assert not built.errors(), built.messages
    names = {f: built.names[f].name for f in built.boundary_faces()}
    assert sorted(set(names.values())) == ["inlet", "outlet", "wall"]
    assert built.faces["op1:inlet"].area == pytest.approx(PI * 0.01 ** 2, rel=1e-9)
    assert built.bodies["op1"].role == "fluid"


def test_booleans_keep_ids_and_volumes():
    built = replay(doc3(Box("op1"), Sphere("op2", xc=0.1, yc=0.1, zc=0.1, radius=0.04),
                        Boolean3D("op3", kind="subtract", objects=["op1"], tools=["op2"])), triangulate=False)
    assert list(built.bodies) == ["op1"]
    assert built.bodies["op1"].volume == pytest.approx(1e-3 - 4 / 3 * PI * 0.04 ** 3 / 8, rel=1e-12)
    assert "op2:surface" in built.faces and "op1:xmax" in built.faces      # the cut-out keeps the sphere's id
    with pytest.raises(AssertionError):
        assert not replay(doc3(Box("op1"), Boolean3D("op2", objects=["op1"], tools=["nothing"]))).errors()


def test_pieces_after_a_boolean_get_numbered():
    built = replay(doc3(Box("op1", dx=1, dy=1, dz=1), Box("op2", x0=0.4, y0=-1, z0=-1, dx=0.2, dy=3, dz=3),
                        Boolean3D("op3", kind="subtract", objects=["op1"], tools=["op2"])), triangulate=False)
    assert sorted(built.bodies) == ["op1#1", "op1#2"]                      # the box cut in two
    assert {"op1:ymin#1", "op1:ymin#2", "op2:xmin", "op2:xmax"} <= set(built.faces)


def test_transform_keeps_face_ids_and_copy_gets_new_ids():
    for kind in ("move", "rotate", "scale", "mirror"):
        built = replay(doc3(Box("op1"), Transform3D("op2", kind=kind, dx=1, angle=30, factor=2, ax=1, ay=0, az=0,
                                                    cx=5)), triangulate=False)
        assert set(built.faces) == {f"op1:{s}" for s in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")}, kind
    built = replay(doc3(Box("op1"), Transform3D("op2", kind="move", dx=1, copy=True)), triangulate=False)
    assert sorted(built.bodies) == ["op1", "op1@op2"] and "op1:xmin@op2" in built.faces
    assert built.faces["op1:xmin@op2"].centroid[0] == pytest.approx(1.0)


def test_set_role_delete_and_failed_operation_message():
    built = replay(doc3(Box("op1"), Sphere("op2", xc=1), SetRole3D("op3", bodies=["op2"], role="fluid"),
                        Delete3D("op4", bodies=["op1"])), triangulate=False)
    assert list(built.bodies) == ["op2"] and built.bodies["op2"].role == "fluid"
    built = replay(doc3(Box("op1"), Delete3D("op2", bodies=["op9"]), Sphere("op3")), triangulate=False)
    assert built.failed_operation == "op2" and "op9" in built.errors()[0]
    assert "op3" not in built.bodies                                       # later steps are not run


# ---- enclosure, names, refinement ---------------------------------------------------------------

def test_enclosures_around_a_sphere():
    r = 0.5
    for kind, volume in (("box", 16 * 11 * 11), ("sphere", 4 / 3 * PI * 10 ** 3),
                         ("cylinder", PI * 10 ** 2 * 16)):
        built = replay(doc3(Sphere("op1", radius=r), Enclosure3D("op2", kind=kind, upstream=5, downstream=10, lateral=5,
                                                                 radius=10)), triangulate=False)
        assert list(built.bodies) == ["op2"] and built.bodies["op2"].role == "fluid"
        assert built.fluid_volume() == pytest.approx(volume - 4 / 3 * PI * r ** 3, rel=1e-10), kind
        patches = built.patches()
        assert patches["wall"] == ("wall", ["op1:surface"]) and patches["farfield"][0] == "farfield"
        assert built.reference_length() == pytest.approx(1.0, rel=1e-3)
    built = replay(doc3(Sphere("op1", radius=r), Enclosure3D("op2", kind="box", half=True)), triangulate=False)
    assert built.fluid_volume() == pytest.approx(0.5 * (16 * 11 * 11 - 4 / 3 * PI * r ** 3), rel=1e-10)
    assert built.patches()["symmetry"] == ("symmetry", ["op2:symmetry"])
    with pytest.raises(AssertionError):                                   # no solid body to enclose
        assert not replay(doc3(Sphere("op1", role="fluid"), Enclosure3D("op2"))).errors()


def test_names_follow_the_faces_after_upstream_edits():
    names = [NameFaces("op4", faces=["op2:surface"], name="ball", kind="wall", inflation=True)]
    for radius in (0.3, 0.2):
        built = replay(doc3(Sphere("op2", radius=radius), Enclosure3D("op3"), *names), triangulate=False)
        b = built.names["op2:surface"]
        assert (b.name, b.type, b.inflation, b.origin) == ("ball", "wall", True, "user")
    built = replay(doc3(Sphere("op2"), Enclosure3D("op3"),
                        NameFaces("op4", faces=["op9:gone"], name="lost")), triangulate=False)
    assert any("no longer exist" in text for _, text in built.messages)
    with pytest.raises(AssertionError):
        assert not replay(doc3(Sphere("op1"), NameFaces("op2", faces=["op1:surface"], name="1bad"))).errors()


def test_refinement_regions():
    built = replay(doc3(Sphere("op1"), Refinement3D("op2", shape="sphere", radius=0.2, size=0.01),
                        Refinement3D("op3", shape="cylinder", x1=2, y1=0, z1=0, radius=0.1, size=0.02)),
                   triangulate=False)
    assert [(r.shape, r.size) for r in built.regions] == [("sphere", 0.01), ("cylinder", 0.02)]
    assert replay(doc3(Refinement3D("op1", shape="box", x1=-1)), triangulate=False).errors()


def test_drawing_triangulation_and_edges():
    built = replay(doc3(Cylinder("op1", ax=1, radius=0.2)))
    side = built.faces["op1:side"]
    assert side.triangles is not None and side.triangles.shape[1:] == (3, 3)
    assert "E(op1:base|op1:side)" in built.edges and "E(op1:side|op1:top)" in built.edges
    assert built.edges["E(op1:base|op1:side)"].length == pytest.approx(2 * PI * 0.2, rel=1e-9)
    assert built.bbox() == pytest.approx((0, -0.2, -0.2, 1, 0.2, 0.2), abs=1e-6)


def test_import_step_and_iges_round_trip(tmp_path):
    from aeroflowsim.geometry_model.export import export_step
    doc = doc3(Box("op1", dx=0.1, dy=0.2, dz=0.3), Cylinder("op2", x=0.05, y=0.1, z=0.3, ax=0, az=0.1, radius=0.02),
               Boolean3D("op3", kind="union", objects=["op1"], tools=["op2"]))
    original = replay(doc, triangulate=False).bodies["op1"]
    path = tmp_path / "part.step"
    export_step(doc, None, path)
    built = replay(doc3(ImportSolid("op1", file=str(path))), triangulate=False)
    assert built.bodies["op1"].volume == pytest.approx(original.volume, rel=1e-10)
    ids = sorted(built.faces)
    assert ids == sorted(replay(doc3(ImportSolid("op1", file=str(path))), triangulate=False).faces)  # same every time
    assert len(ids) == 8 and all(i.startswith("op1:face") for i in ids)   # 6 box faces, cylinder side and top
    with_unit = replay(doc3(ImportSolid("op1", file=str(path), unit="mm")), triangulate=False)   # numbers taken as mm
    assert with_unit.bodies["op1"].volume == pytest.approx(original.volume * 1e-9, rel=1e-8)
    assert replay(doc3(ImportSolid("op1", file="missing.step")), triangulate=False).errors()

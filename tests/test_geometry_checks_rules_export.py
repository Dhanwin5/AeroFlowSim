# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Geometry validity checks (aeroflowsim/checks.py), the suggested-sizes smart rule
(aeroflowsim/smart_rules.py) and geometry export (STEP / DXF / CSV round trips)."""

import csv
import math

import pytest

from aeroflowsim.checks import run_geometry_checks
from aeroflowsim.discovery import load_case
from aeroflowsim.geometry_model import GeometryDocument, ReplayContext, replay, template_document
from aeroflowsim.geometry_model.export import export_geometry
from aeroflowsim.geometry_model.operations import (Enclosure, ImportFile, NameBoundary, Sketch, Transform)
from aeroflowsim.parameters import defaults, validate
from aeroflowsim import smart_rules

EXTERNAL = load_case("external_2d")
NOZZLE = load_case("nozzle_axi")
GEO2D = load_case("geometry_2d")


def ctx(case, **changes):
    return ReplayContext(case, validate(case.parameters(), {**defaults(case.parameters()), **changes}))


def levels(built, settings=None):
    return {r.name: r.level for r in run_geometry_checks(built, settings)}


def test_checks_of_a_good_geometry_are_all_fine():
    c = ctx(EXTERNAL)
    built = replay(template_document(EXTERNAL), c)
    settings = EXTERNAL.workspace_settings(c.params, built)
    result = levels(built, settings)
    assert set(result.values()) == {"info"}
    assert {"Geometry steps", "Closed loops", "Self-intersections", "Body inside the domain", "Boundary names",
            "Smallest feature"} <= set(result)


def test_checks_find_each_problem():
    body_only = replay(GeometryDocument([Sketch("op1", kind="circle", points=[[0, 0], [1, 0]])]))
    assert levels(body_only)["Body inside the domain"] == "error"
    unnamed = replay(GeometryDocument([Sketch("op1", kind="rectangle", points=[[0, 0], [1, 1]], role="fluid"),
                                       Sketch("op2", kind="polyline", points=[[2, 0], [3, 0]])]))
    result = levels(unnamed)
    assert result["Boundary names"] == "error" and result["Closed loops"] == "warning"
    below = GeometryDocument([Sketch("op1", kind="rectangle", points=[[0, -1], [1, 1]], role="fluid")],
                             axisymmetric=True)
    assert levels(replay(below))["Axisymmetric rules"] == "error"
    failed = template_document(EXTERNAL)
    failed.add(Transform(kind="scale", factor=0.0))
    assert levels(replay(failed, ctx(EXTERNAL)))["Geometry steps"] == "error"
    c = ctx(EXTERNAL, surface_size=0.4)                       # wall cells as long as the diamond's edges
    built = replay(template_document(EXTERNAL), c)
    assert levels(built, EXTERNAL.workspace_settings(c.params, built))["Smallest feature"] == "warning"


def test_suggested_sizes_have_reasons_and_inputs_to_apply():
    c = ctx(EXTERNAL, edge_refinement=False)
    doc = template_document(EXTERNAL)
    doc.operations[1].suppressed = True
    doc.add(Enclosure(kind="circle", radius=8.0))
    built = replay(doc, c)
    context = smart_rules.SizeContext(c.params, EXTERNAL.size_inputs(c.params, built), document=doc)
    found = {s.title: s for s in smart_rules.suggestions(built, context)}
    assert set(found) == {"Wall cell size", "Largest cell size", "Corner refinement", "Enclosure"}
    assert all(s.reason for s in found.values())
    assert found["Wall cell size"].inputs == {"surface_size": pytest.approx(0.01)}      # L / 100, L = 1 m chord
    assert found["Largest cell size"].inputs["farfield_size"] == pytest.approx(1.1)      # domain diagonal 22.6 m / 20
    assert found["Corner refinement"].inputs == {"edge_refinement": True}
    assert found["Enclosure"].operation.id == "op3" and found["Enclosure"].operation.params["radius"] == 20.0
    supersonic = smart_rules.SizeContext(c.params, context.sizes, mach=2.0, document=doc)
    rect = next(s for s in smart_rules.suggestions(built, supersonic) if s.title == "Enclosure").operation
    assert rect.params["kind"] == "rectangle" and rect.params["upstream"] == 2.0
    assert rect.params["height"] >= math.tan(math.asin(0.5)) * 8.0


def test_nozzle_feature_size_sets_the_wall_cells():
    c = ctx(NOZZLE)
    built = replay(template_document(NOZZLE), c)
    context = smart_rules.SizeContext(c.params, NOZZLE.size_inputs(c.params, built))
    wall = next(s for s in smart_rules.suggestions(built, context) if s.title == "Wall cell size")
    shortest = min(built.edges[e].length for e in built.patches()["wall"][1])
    L = built.reference_length()
    d_throat = 2.0 * c.template_geometry().r_throat
    assert wall.inputs["surface_size"] == pytest.approx(min(L / 100, shortest / 4) / d_throat, rel=0.05)


def test_step_dxf_and_csv_round_trips(tmp_path):
    doc = GeometryDocument([Sketch("op1", kind="rectangle", points=[[0, 0], [0.04, 0.02]], role="fluid"),
                            Sketch("op2", kind="circle", points=[[0.02, 0.01], [0.025, 0.01]])])
    from aeroflowsim.geometry_model.operations import BooleanOp
    doc.add(BooleanOp(kind="subtract", objects=["op1:face"], tools=["op2:face"]))
    built = replay(doc)
    doc_named = doc.copy()
    doc_named.add(NameBoundary(edges=["op2:e1"], name="hole", kind="wall"))
    exact = 0.04 * 0.02 - math.pi * 0.005**2
    for name in ("plate.step", "plate.dxf"):
        export_geometry(doc_named, ReplayContext(), replay(doc_named), tmp_path / name)
        fmt = "step" if name.endswith("step") else "dxf"
        again = replay(GeometryDocument([ImportFile("op1", format=fmt, file=name, role="fluid")]),
                       ReplayContext(folder=tmp_path))
        (face,) = again.faces.values()
        assert face.area == pytest.approx(exact, rel=1e-6), name
    export_geometry(doc_named, ReplayContext(), replay(doc_named), tmp_path / "plate.csv")
    rows = list(csv.DictReader(open(tmp_path / "plate.csv", encoding="utf-8")))
    assert {r["boundary"] for r in rows} == {"", "hole"} and len(rows) == sum(len(e.points) for e in built.edges.values())
    with pytest.raises(ValueError, match="Choose a file"):
        export_geometry(doc, ReplayContext(), built, tmp_path / "plate.obj")

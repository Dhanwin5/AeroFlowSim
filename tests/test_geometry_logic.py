# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The logic of the geometry workspace page (aeroflowsim/gui/geometry_logic.py), without a window:
mm conversion, operations pre-filled from a selection, boundary renaming / types / suggestions,
point editing and the History texts."""

import numpy as np
import pytest

from aeroflowsim.discovery import load_case
from aeroflowsim.geometry_model import GeometryDocument, ReplayContext, replay, template_document
from aeroflowsim.geometry_model.operations import Enclosure, ImportFile, Transform
from aeroflowsim.gui import geometry_logic as logic
from aeroflowsim.parameters import defaults, validate

NOZZLE = load_case("nozzle_axi")
EXTERNAL = load_case("external_2d")


def ctx(case, **changes):
    return ReplayContext(case, validate(case.parameters(), {**defaults(case.parameters()), **changes}))


def built_of(doc, case=NOZZLE, **changes):
    return replay(doc, ctx(case, **changes))


def test_lengths_are_shown_in_mm_and_read_back_in_metres():
    field = next(f for f in logic.FIELDS["fillet"] if f.key == "radius")
    assert field.unit == "mm"
    assert logic.to_text(field, 0.0025) == "2.5"
    assert logic.from_text(field, "2,5") == pytest.approx(0.0025)
    with pytest.raises(ValueError, match="not a number"):
        logic.from_text(field, "two")
    angle = next(f for f in logic.FIELDS["transform"] if f.key == "angle")
    assert logic.from_text(angle, "-4") == -4.0 and angle.unit == "°"


def test_fields_shown_only_for_their_choice():
    fields = {f.key: f for f in logic.FIELDS["transform"]}
    assert logic.shown(fields["dx"], {"kind": "move"}) and not logic.shown(fields["dx"], {"kind": "rotate"})
    assert logic.shown(fields["angle"], {"kind": "mirror"}) and logic.shown(fields["copy"], {"kind": "scale"})


def test_operations_are_prefilled_from_the_selection():
    doc = template_document(NOZZLE)
    built = built_of(doc, Rcu_ratio=0.0, Rcd_ratio=0.0)
    throat = next(v for v in built.vertices.values() if set(v.edges) == {"op1:wall.2", "op1:wall.3"})
    fillet = logic.operation_for("fillet", [("vertex", throat.id)], built)
    assert sorted(fillet.params["edges"]) == ["op1:wall.2", "op1:wall.3"] and fillet.params["radius"] > 0
    name = logic.operation_for("name_boundary", [("edge", "op1:wall.1"), ("edge", "op1:wall.2")], built)
    assert name.params["name"] == "wall" and name.params["kind"] == "wall"
    move = logic.operation_for("transform", [("edge", "op1:inlet")], built)
    assert move.params["targets"] == ["op1:nozzle"]                     # an edge selects its face
    with pytest.raises(ValueError, match="Select"):
        logic.operation_for("fillet", [], built)
    with pytest.raises(ValueError, match="two or more faces"):
        logic.operation_for("boolean", [("face", "op1:nozzle")], built)
    box = logic.operation_for("refinement", [("edge", "op1:wall.2")], built)
    assert box.params["x1"] > box.params["x0"] and box.params["size"] > 0


def test_rename_type_and_inflation_of_a_boundary():
    doc = template_document(NOZZLE)
    built = built_of(doc)
    renamed = logic.rename_boundary(doc, built, "wall", "nozzle_wall")
    after = built_of(renamed)
    assert "nozzle_wall" in after.patches() and "wall" not in after.patches()
    typed = logic.set_boundary_type(renamed, after, "nozzle_wall", "wall", inflation=True)
    rows = {r[0]: r for r in logic.boundary_rows(built_of(typed))}
    assert rows["nozzle_wall"][3] == "yes" and rows["nozzle_wall"][4] == "you"
    with pytest.raises(ValueError, match="no boundary called"):
        logic.rename_boundary(doc, built, "nothing", "x")


def test_accepting_suggestions_names_an_imported_nozzle_domain():
    from pathlib import Path
    data = Path(__file__).resolve().parent / "data"
    doc = GeometryDocument([ImportFile("op1", format="dxf", file="nozzle_domain.dxf")], axisymmetric=True)
    built = replay(doc, ReplayContext(folder=data))
    assert logic.boundary_rows(built)[-1][0] == "(no name)"
    accepted = logic.accept_suggestions(doc, built)
    after = replay(accepted, ReplayContext(folder=data))
    assert {"axis", "inlet", "outlet"} <= set(after.patches())
    assert logic.accept_suggestions(accepted, after) is None          # nothing left to suggest


def test_points_of_an_import_are_edited_in_metres():
    pts = [[0.0, 0.0], [1.0, 0.0], [0.5, 0.5]]
    op = ImportFile("op1", format="coordinates", points=pts, unit="mm")
    assert logic.has_points(op)
    assert np.allclose(logic.points_of(op), np.array(pts) * 1e-3)
    moved = logic.with_points(op, [[0.0, 0.0], [2e-3, 0.0], [0.5e-3, 0.5e-3]])
    assert moved.params["points"][1] == [2.0, 0.0] and op.params["points"][1] == [1.0, 0.0]


def test_selection_rows_and_history_states():
    doc = template_document(EXTERNAL)
    doc.add(Transform(kind="scale", factor=-2.0))
    doc.add(Enclosure())
    built = built_of(doc, EXTERNAL)
    states = [s for _, _, s in logic.history_rows(doc, built)]
    assert states == ["template", "template", "failed", "not run"]
    rows = dict((r[0], r[1]) for r in logic.selection_rows(built, [("face", "op2:domain")]))
    assert rows["Role"] == "fluid" and float(rows["Area"]) > 0
    rows = dict((r[0], r[1]) for r in logic.selection_rows(built, [("edge", "op1:body.1"), ("edge", "op1:body.2")]))
    assert rows["Selected edges"] == "2"

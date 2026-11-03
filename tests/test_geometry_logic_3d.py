# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The logic of the 3D geometry page (the 3D section of aeroflowsim/gui/geometry_logic.py) and of the 3D Mesh step
(aeroflowsim/gui/logic.py), without a window."""

import numpy as np
import pytest

pytest.importorskip("gmsh")

from aeroflowsim.geometry_model import GeometryDocument, ReplayContext, replay  # noqa: E402
from aeroflowsim.geometry_model.operations3d import (  # noqa: E402
    Box, Enclosure3D, Revolve, Sphere, TemplateBody, TemplateEnclosure3D)
from aeroflowsim.gui import geometry_logic as logic  # noqa: E402
from aeroflowsim.gui.logic import cells_cut_by_plane, mesh_section, worst_cell  # noqa: E402


def doc3(*ops):
    return GeometryDocument(list(ops), dimension=3)


@pytest.fixture(scope="module")
def ball():
    doc = doc3(Sphere("op1", radius=0.5), Enclosure3D("op2", upstream=2, downstream=3, lateral=2))
    return doc, replay(doc)


def test_selection_click_toggle_and_box(ball):
    _, built = ball
    a, b = ("face", "op1:surface"), ("face", "op2:upstream")
    assert logic.toggle_selection([], a, False) == [a]
    assert logic.toggle_selection([a], b, True) == [a, b]
    assert logic.toggle_selection([a, b], a, True) == [b]                 # Shift on a selected face removes it
    assert logic.toggle_selection([a], None, False) == [] and logic.toggle_selection([a], None, True) == [a]
    projected = {"inside": [[1, 1], [2, 2]], "half": [[1, 1], [9, 9]], "out": [[8, 8], [9, 9]]}
    assert logic.faces_in_rectangle(projected, (0, 0, 5, 5)) == ["inside"]               # left to right: fully in
    assert logic.faces_in_rectangle(projected, (5, 5, 0, 0), touching=True) == ["inside", "half"]
    assert logic.bodies_of([a], built) == ["op2"] and logic.faces_of_3d([("body", "op2")], built) == \
        built.bodies["op2"].faces


def test_visibility_and_section_plane(ball):
    _, built = ball
    v = logic.Visibility()
    v.hide(["op1:surface"])
    assert "op1:surface" not in v.visible(built)
    v.isolate(["op1:surface"], built)
    assert v.visible(built) == ["op1:surface"]
    v.isolate([], built)                                                      # nothing selected: unchanged
    assert v.visible(built) == ["op1:surface"]
    v.show_all()
    assert len(v.visible(built)) == len(built.faces)
    origin, normal = logic.section_plane(built, "y", 0.5)
    assert normal.tolist() == [0.0, 1.0, 0.0] and origin[1] == pytest.approx(0.0, abs=1e-6)
    assert logic.section_plane(built, "none", 0.5) is None


def test_new_operations_from_the_selection(ball):
    _, built = ball
    sel = [("face", "op1:surface")]
    name = logic.operation_for_3d("name_faces", sel, built)
    assert name.params["faces"] == ["op1:surface"] and name.params["name"] == "wall"
    ref = logic.operation_for_3d("refinement_3d", sel, built)
    assert ref.params["xc"] == pytest.approx(0.0, abs=1e-3) and ref.params["size"] == pytest.approx(0.02)
    for kind, _, _ in logic.BODIES_3D:
        assert logic.operation_for_3d(kind, [], built).dimension == 3
    with pytest.raises(ValueError, match="two bodies"):
        logic.operation_for_3d("boolean_3d", sel, built)
    with pytest.raises(ValueError, match="Select the faces"):
        logic.operation_for_3d("name_faces", [], built)
    assert logic.operation_for_3d("delete_3d", sel, built).params["bodies"] == ["op2"]


def test_point_fields_in_mm():
    field = logic.FIELDS["extrude"][0]
    assert logic.from_text(field, "0 0; 100 0; 0, 50") == [[0.0, 0.0], [0.1, 0.0], [0.0, 0.05]]
    assert logic.to_text(field, [[0.0, 0.0], [0.1, 0.0]]) == "0 0; 100 0"
    for bad in ("0 0; 1", "0 0; 1 1", "a b; 1 1; 2 2"):
        with pytest.raises(ValueError):
            logic.from_text(field, bad)


def test_boundary_names_rename_type_layers_and_undo_state(ball):
    doc, built = ball
    rows = {r[0]: r for r in logic.boundary_rows_3d(built)}
    assert rows["wall"][1:4] == ("wall", 1, "") and rows["farfield"][2] == 6
    renamed = logic.rename_boundary_3d(doc, built, "wall", "ball")
    assert doc.operations[-1].type != "name_faces"                            # the old document is unchanged
    again = replay(renamed)
    assert again.names["op1:surface"].name == "ball" and again.names["op1:surface"].origin == "user"
    layered = replay(logic.set_boundary_type_3d(renamed, again, "ball", "wall", inflation=True))
    assert layered.names["op1:surface"].inflation
    with pytest.raises(ValueError):
        logic.rename_boundary_3d(doc, built, "nothing", "x")


def test_suggestions_for_a_fluid_nozzle(tmp_path):
    doc = doc3(Revolve("op1", points=[[0.0, 0.0], [0.05, 0.0], [0.05, 0.008], [0.02, 0.004], [0.0, 0.01]],
                       role="fluid"))
    built = replay(doc, ReplayContext(folder=tmp_path))
    assert any(r[0] == logic.UNNAMED for r in logic.boundary_rows_3d(built))
    named = logic.accept_suggestions_3d(doc, built)
    after = replay(named, ReplayContext(folder=tmp_path))
    kinds = {b.name: b.type for b in after.names.values()}
    assert kinds == {"inlet": "inlet", "outlet": "outlet", "wall": "wall"}
    assert after.names["op1:edge2"].name == "outlet" and after.names["op1:edge5"].name == "inlet"
    assert logic.accept_suggestions_3d(named, after) is None


def test_texts_for_properties_dimensions_and_history(ball):
    doc, built = ball
    rows = dict((r[0], r[1:]) for r in logic.selection_rows_3d(built, [("face", "op1:surface")]))
    assert rows["Kind"][0] == "sphere" and rows["Boundary"][0] == "wall (wall)"
    assert rows["Area"][1] == "mm²"
    summary = dict((r[0], r[1:]) for r in logic.summary_rows_3d(built))
    assert summary["Fluid bodies"][0] == "1" and summary["Reference length L"][0] == "1000"
    template = doc3(TemplateBody("op1"), TemplateEnclosure3D("op2"), Box("op3"))
    rows = logic.history_rows_3d(template, replay(doc3(Box("op3"))))
    assert [r[2] for r in rows] == ["template", "template", "ok"]


def test_mesh_cut_and_worst_cell():
    from aeroflowsim.mesh import HEXAHEDRON, Mesh
    # two unit cubes side by side along x
    nodes = np.array([[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1, 2)], dtype=float)

    def hexa(i):
        b = [i, i + 1, i + 4, i + 3]
        return b + [n + 6 for n in b]
    cells = [hexa(0), hexa(1)]
    mesh = Mesh.from_cells(nodes, HEXAHEDRON, cells, {"all": ("wall", np.array([
        [0, 1, 4, 3], [1, 2, 5, 4], [6, 7, 10, 9], [7, 8, 11, 10], [0, 1, 7, 6], [1, 2, 8, 7], [3, 4, 10, 9],
        [4, 5, 11, 10], [0, 3, 9, 6], [2, 5, 11, 8]]))})
    assert mesh.cell_volumes.min() == pytest.approx(1.0)
    origin, normal = mesh_section(mesh, "x", 0.25)                           # x = 0.5: through the first cube
    assert cells_cut_by_plane(mesh, origin, normal).tolist() == [0]
    origin, normal = mesh_section(mesh, "x", 0.5)                            # x = 1: the shared face, both cubes
    assert cells_cut_by_plane(mesh, origin, normal).tolist() == [0, 1]
    assert mesh_section(mesh, "off", 0.5) is None
    assert worst_cell([0.1, 0.9, 0.3], "Skewness") == 1 and worst_cell([5.0, 1.0], "Smallest angle") == 1


def test_3d_size_suggestions(ball):
    from aeroflowsim.smart_rules import SizeContext, suggestions_3d
    _, built = ball
    context = SizeContext({"inflation": False}, {"surface": ("surface_size", 1.0), "max": ("farfield_size", 1.0)})
    tips = {s.title: s for s in suggestions_3d(built, context)}
    assert tips["Wall cell size"].inputs == {"surface_size": 0.025}            # L / 40, L = 1 m
    assert tips["Largest cell size"].inputs == {"farfield_size": 0.46}          # diagonal 9.27 m / 20 < 2 L

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cell zones in the desktop GUI (full 3D release stage): a zone as the region of a start patch (Run step)."""

import pytest

pytest.importorskip("PySide6")


def test_start_patch_dialog_offers_the_cell_zones(qtbot, tmp_path):
    from aeroflowsim.gui.post_panels import InitialisationDialog
    from aeroflowsim.project import Project
    from aeroflowsim.units import UnitPreferences
    project = Project.create("cases/imported_mesh", tmp_path / "z.afsproj")
    dialog = InitialisationDialog(None, project, UnitPreferences(), zones=["inner", "plume"])
    qtbot.addWidget(dialog)
    items = [dialog.region.itemText(i) for i in range(dialog.region.count())]
    assert items == ["Box", "Circle", "Zone inner", "Zone plume"]
    dialog.region.setCurrentText("Zone plume")
    dialog.p.setText("200000")
    dialog.add()
    assert dialog.patches[-1] == {"region": {"type": "zone", "name": "plume"}, "values": {"p": 200000.0}}
    assert "zone plume" in dialog.table.item(0, 0).text()


def test_internal_3d_flow_hides_the_free_stream_inputs():
    """external_3d with an inlet (a nozzle) does not use the free stream: hidden in the Setup panel; values kept."""
    from aeroflowsim.case import get_hidden_inputs
    from aeroflowsim.discovery import load_case
    from aeroflowsim.gui.panel_model import PanelModel
    from aeroflowsim.simple_meshes import box_mesh_3d
    case = load_case("external_3d")
    nozzle = box_mesh_3d(2)                                    # xmin inlet, xmax outlet
    external = box_mesh_3d(2, kinds={"xmin": "farfield", "xmax": "farfield"})
    model = PanelModel(case.parameters(), "setup")
    values = {p.name: p.default for p in case.parameters()}
    assert get_hidden_inputs(case, values, external) == set() and get_hidden_inputs(case, values, None) == set()
    assert "mach" in model.visible(values)
    model.hidden = get_hidden_inputs(case, values, nozzle)
    assert model.hidden == {"mach", "p_inf", "T_inf", "alpha", "beta"}
    assert "mach" not in model.visible(values) and "gas" in model.visible(values)


def test_geometry_dialog_lengths_follow_the_display_unit():
    """View > Units: the geometry dialogs (2D and 3D) show and read lengths in the chosen unit; mm by default."""
    from aeroflowsim.gui import geometry_logic as gl
    from aeroflowsim.units import UnitPreferences
    field = gl.Field("x", "x", "length")
    try:
        gl.set_length_unit(None)
        assert field.unit == "mm" and gl.to_text(field, 0.25) == "250" and gl.from_text(field, "250") == 0.25
        prefs = UnitPreferences()
        prefs.choices["length"] = "m"
        gl.set_length_unit(prefs.unit_for("m"))
        assert field.unit == "m" and gl.to_text(field, 0.25) == "0.25" and gl.from_text(field, "0.25") == 0.25
    finally:
        gl.set_length_unit(None)


def test_3d_edge_tools_from_the_selection(qtbot):
    """Edge size / fillet / chamfer need picked edges (Edges filter); the 3D view picks edges when the filter is on."""
    pytest.importorskip("gmsh")
    from aeroflowsim.geometry_model import GeometryDocument, replay
    from aeroflowsim.geometry_model.operations3d import Box
    from aeroflowsim.gui import geometry_logic as gl
    from aeroflowsim.gui.geometry3d_view import Geometry3DView
    built = replay(GeometryDocument([Box("b", dx=1.0, dy=1.0, dz=1.0)], dimension=3))
    edge = next(iter(built.edges))
    with pytest.raises(ValueError, match="Edges"):
        gl.operation_for_3d("fillet_3d", [("face", "b:xmin")], built)
    op = gl.operation_for_3d("fillet_3d", [("edge", edge)], built)
    assert op.params["edges"] == [edge] and op.params["radius"] == pytest.approx(0.1)
    assert gl.operation_for_3d("edge_size_3d", [("edge", edge)], built).params["size"] == pytest.approx(0.05)
    assert gl.operation_for_3d("split_body_3d", [("body", "b")], built).params["bodies"] == ["b"]
    view = Geometry3DView()
    qtbot.addWidget(view)
    view.show_geometry(built, selection=[("edge", edge)])
    assert len(view.edge_ids) == 12 and view.edge_actor is not None
    view.pick_kind = "edge"
    got = []
    view.picked.connect(lambda kind, entity, add: got.append(kind))
    view.pick_at(1, 1)                                     # a corner of the window: nothing there
    assert got == [""]

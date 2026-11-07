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

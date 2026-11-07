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

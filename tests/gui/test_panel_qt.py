# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Qt input panel: widgets per type, show_if, messages and the value_changed signal."""

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLineEdit

from aeroflowsim.discovery import load_case
from aeroflowsim.gui.panel import InputPanel, NumberEdit
from aeroflowsim.gui.panel_model import PanelModel
from aeroflowsim.parameters import defaults


def _panel(qtbot, case_name, step=None, **kwargs):
    case = load_case(case_name)
    panel = InputPanel(PanelModel(case.parameters(), step), defaults(case.parameters()), **kwargs)
    qtbot.addWidget(panel)
    panel.show()
    return panel


def test_widgets_match_the_schema_types(qtbot):
    panel = _panel(qtbot, "nozzle_axi")
    assert isinstance(panel.rows["d_throat"].editor, NumberEdit)
    assert isinstance(panel.rows["nx"].editor, NumberEdit)
    assert isinstance(panel.rows["throat_clustering"].editor, QCheckBox)
    assert isinstance(panel.rows["mesh_type"].editor, QComboBox)
    assert isinstance(panel.rows["profile_csv"].editor, QLineEdit)
    assert panel.rows["d_throat"].editor.text() == "0.00028"
    assert "Allowed range" in panel.rows["d_throat"].editor.toolTip()


def test_typing_a_bad_value_shows_a_message_and_emits_the_change(qtbot):
    panel = _panel(qtbot, "nozzle_axi")
    row = panel.rows["d_throat"]
    row.editor.setText("5")
    with qtbot.waitSignal(panel.value_changed) as signal:
        row.editor.editingFinished.emit()
    assert signal.args == ["d_throat", 5.0]
    assert row.error.isVisibleTo(panel) and "outside the allowed range" in row.error.text()
    row.editor.setText("abc")
    row.editor.editingFinished.emit()
    assert "must be a number" in row.error.text()
    row.editor.setText("0.0003")
    row.editor.editingFinished.emit()
    assert not row.error.isVisibleTo(panel)
    assert panel.values()["d_throat"] == 0.0003


def test_show_if_hides_and_shows_rows(qtbot):
    panel = _panel(qtbot, "nozzle_axi")
    assert not panel.rows["nx"].editor.isVisibleTo(panel)
    combo = panel.rows["mesh_preset"].editor
    combo.setCurrentIndex(combo.findData("Custom"))
    assert panel.rows["nx"].editor.isVisibleTo(panel)
    source = panel.rows["geometry_source"].editor
    source.setCurrentIndex(source.findData("Custom profile (CSV)"))
    assert panel.rows["profile_csv"].editor.isVisibleTo(panel)
    assert not panel.rows["d_throat"].editor.isVisibleTo(panel)


def test_arrow_keys_step_a_number_within_its_range(qtbot):
    panel = _panel(qtbot, "nozzle_axi")
    editor = panel.rows["nr"].editor           # int 40
    with qtbot.waitSignal(panel.value_changed):
        qtbot.keyClick(editor, Qt.Key_Up)
    assert panel.values()["nr"] == 41


def test_set_values_does_not_emit_and_updates_widgets(qtbot):
    panel = _panel(qtbot, "nozzle_axi")
    with qtbot.assertNotEmitted(panel.value_changed):
        panel.set_values({"mesh_type": "Triangles (Gmsh)", "d_exit": 0.001})
    assert panel.rows["mesh_type"].editor.currentData() == "Triangles (Gmsh)"
    assert panel.rows["d_exit"].editor.text() == "0.001"
    assert panel.rows["surface_size"].editor.isVisibleTo(panel)


def test_shape_library_inputs_appear_in_the_geometry_step(qtbot):
    panel = _panel(qtbot, "external_2d", step="geometry")
    assert "mesh_type" not in panel.rows and "surface_size" not in panel.rows
    shape = panel.rows["shape"].editor
    shape.setCurrentIndex(shape.findData("NACA 4-digit airfoil"))
    digits = panel.rows["naca4.digits"].editor
    assert digits.isVisibleTo(panel)
    digits.setText("12")
    digits.editingFinished.emit()
    assert panel.rows["naca4.digits"].error.isVisibleTo(panel)


@pytest.mark.parametrize("width", [420, 300, 240])      # the default Inputs dock, a narrow one, a very narrow one
def test_values_stay_visible_in_a_narrow_panel(qtbot, width):
    """Long labels wrap instead of pushing the boxes out of view: no sideways scrolling needed."""
    panel = _panel(qtbot, "external_2d", step="geometry")
    width = max(width, panel.minimumSizeHint().width())        # the dock cannot be made narrower than this
    assert panel.minimumSizeHint().width() < 360
    panel.resize(width, 700)
    qtbot.waitUntil(lambda: panel.width() == width)
    QApplication.processEvents()
    assert not panel.scroll.horizontalScrollBar().isVisible()
    viewport = panel.scroll.viewport()
    shown = [row for row in panel.rows.values() if row.editor.isVisibleTo(panel)]
    assert any(isinstance(row.editor, NumberEdit) for row in shown)
    for row in shown:
        editor = row.editor
        box = QRect(editor.mapTo(viewport, QPoint(0, 0)), editor.size())
        assert viewport.rect().contains(box), f"{row.spec.name} is not fully inside the panel"
        if isinstance(editor, NumberEdit):            # the whole number fits in its box
            text_width = editor.fontMetrics().horizontalAdvance(editor.text())
            assert text_width < editor.width() - 8, f"{row.spec.name}: {editor.text()!r} is cut off"
    assert all(row.label.wordWrap() for row in panel.rows.values())


def test_file_input_uses_the_file_handler(qtbot):
    stored = []
    panel = _panel(qtbot, "nozzle_axi", file_handler=lambda name, path: stored.append(path) or "geometry/p.csv")
    panel._edited("profile_csv", panel.file_handler("profile_csv", "C:/somewhere/p.csv"))
    assert stored == ["C:/somewhere/p.csv"]
    assert panel.values()["profile_csv"] == "geometry/p.csv"


def test_option_needing_a_missing_package_is_greyed_out(qtbot, monkeypatch):
    import aeroflowsim.gui.panel_model as panel_model
    monkeypatch.setattr(panel_model, "module_available", lambda name: name != "gmsh")
    panel = _panel(qtbot, "nozzle_axi")
    combo = panel.rows["mesh_type"].editor
    index = combo.findData("Triangles (Gmsh)")
    assert "(not installed)" in combo.itemText(index)
    assert not combo.model().item(index).isEnabled()
    assert panel.rows["mesh_type"].hint.isVisibleTo(panel)
    assert 'pip install -e ".[mesh]"' in panel.rows["mesh_type"].hint.text()


def test_details_area_follows_click_and_keyboard_focus(qtbot):
    panel = _panel(qtbot, "nozzle_axi")
    assert "Click an input" in panel.details.help.text()
    row = panel.rows["d_throat"]
    qtbot.mouseClick(row.label, Qt.LeftButton)                   # clicking the label
    assert "Throat diameter" in panel.details.title.text()
    assert "Allowed range" in panel.details.facts.text() and "m" in panel.details.facts.text()
    assert row.editor.toolTip()                                  # the hover tooltip is still there
    panel.rows["d_exit"].editor.setFocus(Qt.TabFocusReason)      # reaching a box with the keyboard
    qtbot.waitUntil(lambda: "Exit diameter" in panel.details.title.text(), timeout=2000)
    editor = panel.rows["d_exit"].editor
    editor.setText("5")
    editor.editingFinished.emit()
    assert "outside the allowed range" in panel.details.problem.text()   # Details shows the problem too
    combo = panel.rows["mesh_type"].editor
    qtbot.mouseClick(combo, Qt.LeftButton)
    qtbot.keyClick(combo.view(), Qt.Key_Escape)
    assert "Options" in panel.details.facts.text()

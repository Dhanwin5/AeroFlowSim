# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The gas dropdown of the Setup inputs and the custom-gas form, driven like a user would."""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialogButtonBox, QMessageBox

from aeroflowsim.gui import gas_dialog
from aeroflowsim.gui.gas_dialog import CustomGasDialog
from aeroflowsim.gui.gas_logic import form_from_gas
from aeroflowsim.gui.main_window import MainWindow
from aeroflowsim.project import Project


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))           # the user's gas library goes here
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "appdata"))
    w = MainWindow(QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    qtbot.addWidget(w)
    w.show()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    yield w
    w.runner.shutdown()


def _choose(row, data):
    row.editor.setCurrentIndex(row.editor.findData(data))


def test_pick_a_library_gas_see_its_sources_and_undo(qtbot, window, tmp_path):
    window.load_project(Project.create("quasi1d_nozzle", tmp_path / "Q.afsproj"))
    window.go_to("setup")
    panel = window.panels["setup"]
    row = panel.rows["gas"]
    texts = [row.editor.itemText(i) for i in range(row.editor.count())]
    assert texts[0] == "N2 - Nitrogen" and "Kr - Krypton" in texts and texts[-1] == "New custom gas..."
    panel.show_details("gas")
    facts = panel.details.facts.text()
    assert "1.4" in facts and "296.8" in facts and "Cengel" in facts             # values with their sources
    _choose(row, "Kr")
    assert window.project.values["gas"] == "Kr"
    panel.show_details("gas")
    assert "Krypton" in panel.details.facts.text() and "1.66667" in panel.details.facts.text()
    rows = {r[0]: r for r in window.pages["setup"].derived.rows()}
    assert not rows["Design exit Mach number"][1].startswith("3.986")           # gamma 5/3 changes the design
    window.act["undo"].trigger()
    assert window.project.values["gas"] == "N2" and row.editor.currentData() == "N2"


def test_make_a_custom_gas_and_reuse_it_in_another_project(qtbot, window, tmp_path, monkeypatch):
    def fake_exec(dialog):
        dialog.edits["name"].setText("Lab gas")
        dialog.edits["gamma"].setText("1.3")
        dialog._save()
        return True
    monkeypatch.setattr(CustomGasDialog, "exec", fake_exec)
    window.load_project(Project.create("quasi1d_nozzle", tmp_path / "A.afsproj"))
    row = window.panels["setup"].rows["gas"]
    _choose(row, "<new custom gas>")                                            # "New custom gas..."
    value = window.project.values["gas"]
    assert value == "gases/Lab gas.toml" and (window.project.folder / value).is_file()
    assert any((tmp_path / "appdata").rglob("Lab gas.toml"))                    # saved in the user library
    assert window.project.case.gas(window.project.params()).gamma_value == 1.3
    window.save()
    window.load_project(Project.create("quasi1d_nozzle", tmp_path / "B.afsproj"))
    row = window.panels["setup"].rows["gas"]
    mine = [row.editor.itemData(i) for i in range(row.editor.count()) if "(my gases)" in row.editor.itemText(i)]
    assert len(mine) == 1
    _choose(row, mine[0])
    assert window.project.values["gas"] == "gases/Lab gas.toml"                # copied into project B
    assert (window.project.folder / "gases" / "Lab gas.toml").is_file()
    assert "(custom, in this project)" in row.editor.currentText()


def test_the_form_checks_its_values(qtbot):
    dialog = CustomGasDialog(form_from_gas("N2"))
    qtbot.addWidget(dialog)
    save = dialog.buttons.button(QDialogButtonBox.Save)
    assert save.isEnabled() and dialog.edits["molar_mass"].text() == "28.0134"
    dialog.edits["gamma"].setText("2.5")
    assert not save.isEnabled() and "gamma must lie" in dialog.problem.text()
    dialog.combos["heat"].setCurrentText("cp")
    assert dialog.edits["cp"].isVisibleTo(dialog) and not dialog.edits["gamma"].isVisibleTo(dialog)
    assert save.isEnabled()
    dialog.combos["law"].setCurrentText("Power law")
    assert dialog.grid.labelForField(dialog.edits["S"]).text().startswith("Exponent")
    assert gas_dialog.form_to_toml is not None


def test_gas_library_window_lists_every_gas_and_adds_custom_ones(qtbot, window, monkeypatch):
    from aeroflowsim.gui.gas_dialog import GasLibraryDialog
    dialog = GasLibraryDialog(window)
    qtbot.addWidget(dialog)
    assert dialog.list.count() == 11 and "Cengel" in dialog.facts.text()
    dialog.list.setCurrentRow(10)
    assert "APPROXIMATION" in dialog.facts.text()                              # the R-236fa note
    def fake_exec(form_dialog):
        form_dialog.edits["name"].setText("Wet N2")
        form_dialog._save()
        return True
    monkeypatch.setattr(CustomGasDialog, "exec", fake_exec)
    dialog.new_gas()
    assert dialog.list.count() == 12 and dialog.list.currentItem().text() == "Wet N2 (my gases)"
    assert window.act["gases"] in window.menuBar().actions()[3].menu().actions()

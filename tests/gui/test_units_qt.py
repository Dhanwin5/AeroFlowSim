# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""View > Units in the window: inputs, tables, the key-results card and plots change their units;
the project (inputs, fingerprints, results) never changes."""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from aeroflowsim.gui.main_window import MainWindow
from aeroflowsim.gui.units_dialog import UnitsDialog
from aeroflowsim.project import Project, run_project
from aeroflowsim.units import SI, UnitPreferences


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    w = MainWindow(QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    qtbot.addWidget(w)
    w.show()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    yield w
    w.runner.shutdown()


def test_switching_units_changes_what_is_shown_never_the_project(qtbot, window, tmp_path):
    project = Project.create("quasi1d_nozzle", tmp_path / "U.afsproj", values={"max_iter": 3000})
    run_project(project)
    window.load_project(Project.open(project.folder))
    before = (dict(window.project.values), window.project.fingerprint("run"), window.project.statuses())
    setup = window.panels["setup"]
    assert setup.rows["p0"].label.text() == "Total (chamber) pressure [kPa]" and setup.rows["p0"].editor.text() == "500"
    setup.rows["p0"].editor.editingFinished.emit()                  # Enter without a change: no edit at all
    assert window.undo.count() == 0 and not window.project.dirty
    window.go_to("results")
    tiles = {t[0]: t[1:] for t in window.pages["results"].card._content[1]}
    assert tiles["Thrust (vacuum)"][1] == "mN" and tiles["Mass flow"][1] == "mg/s"
    numbers = {r[0]: r[1:] for r in window.pages["results"].numbers.rows()}
    assert numbers["mdot"][1] == "mg/s" and numbers["F_vacuum"][1] == "mN" and numbers["p_exit"][1] == "kPa"
    window.set_units(UnitPreferences({**SI, "temperature": "°C"}), save=False)
    assert window.panels["setup"].rows["T0"].editor.text() == "20" and window.panels["setup"].rows["p0"].editor.text() == "500000"
    numbers_si = {r[0]: r[1:] for r in window.pages["results"].numbers.rows()}
    assert numbers_si["mdot"][1] == "kg/s" and numbers_si["T_exit"][1] == "°C"
    assert float(numbers_si["F_vacuum"][0]) * 1e3 == pytest.approx(float(numbers["F_vacuum"][0]), rel=1e-5)
    assert window.pages["results"].field.itemText(window.pages["results"].field.findData("T")).endswith("[°C]")
    assert {t[0]: t[1:] for t in window.pages["results"].card._content[1]}["Thrust (vacuum)"][1] == "N"
    assert (dict(window.project.values), window.project.fingerprint("run"), window.project.statuses()) == before
    assert not window.project.dirty
    lines = [window.checks.item(i).text() for i in range(window.checks.count())]
    condensation = next(line for line in lines if "Condensation" in line)
    assert "°C" in condensation and "kPa" not in condensation and " Pa" in condensation   # SI pressure, degC


def test_units_dialog_presets_and_remembered_choice(qtbot, window, tmp_path):
    dialog = UnitsDialog(window.units, window)
    qtbot.addWidget(dialog)
    assert dialog.boxes["length"].currentText() == "mm"                # small-propulsion defaults
    dialog.apply(SI)
    assert dialog.preferences() == UnitPreferences(SI)
    window.set_units(dialog.preferences())
    again = MainWindow(window.settings)                                 # a new window reads the settings
    qtbot.addWidget(again)
    assert again.units == UnitPreferences(SI)
    again.runner.shutdown()
    assert window.act["units"] in window.menuBar().actions()[2].menu().actions()


def test_reopening_a_2d_project_after_a_1d_one(qtbot, window, tmp_path):
    """The Geometry page once kept the replay key of the 2D geometry while showing a 1D template, so the
    same 2D project opened again was not replayed (no geometry: crash)."""
    axi = Project.create("nozzle_axi", tmp_path / "A.afsproj")
    q1d = Project.create("quasi1d_nozzle", tmp_path / "Q.afsproj")
    for folder in (axi.folder, q1d.folder, axi.folder):
        window.load_project(Project.open(folder))
    assert window.pages["geometry"].built is not None and window.pages["geometry"].built.faces

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Smoke tests of the desktop GUI, driven like a user would (offscreen, no window on the screen)."""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from aeroflowsim.gui.main_window import MainWindow
from aeroflowsim.project import Project

from .conftest import needs_rendering

JOB_MS = 180_000


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)   # never the user's own preferences
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.show()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    yield w
    w.runner.shutdown()


def _open(window, tmp_path, template, **values):
    project = Project.create(template, tmp_path / f"{template}.afsproj", values=values or None)
    window.load_project(project)
    return project


def _wait_job(qtbot, window):
    if window.runner.busy:
        with qtbot.waitSignal(window.runner.ended, timeout=JOB_MS):
            pass


def test_window_opens_on_the_welcome_page_with_every_template(window):
    page = window.pages["welcome"]
    assert window.stack.currentWidget() is page
    assert page.templates.count() >= 5
    assert not window.strip.isVisible()
    assert "AeroFlowSim" in window.windowTitle()


def test_nozzle_project_geometry_mesh_and_picking(qtbot, window, tmp_path):
    _open(window, tmp_path, "nozzle_axi")
    geometry = window.pages["geometry"]
    assert geometry.preview is not None and {c.name for c in geometry.preview.curves} == {"wall", "inlet", "outlet", "axis"}
    assert window.strip.chips["mesh"].status == "none"
    assert window.strip.chips["run"].status == "disabled"          # mesh-only template
    window.go_to("mesh")
    window.generate_mesh()
    assert window.strip.chips["mesh"].progress.isVisible()          # progress shown in the strip
    _wait_job(qtbot, window)
    assert window.mesh is not None and window.mesh.n_cells == 8000
    assert window.strip.chips["mesh"].status == "ok"
    assert window.mesh_checks
    page = window.pages["mesh"]
    page.colour.setCurrentText("Non-orthogonality")
    assert page.view.grid is not None and page.view.grid.n_cells == 8000
    needs_rendering(page.view)
    centre = window.mesh.cell_centres[1234]
    x, y = page.view.display_point(centre[:2])
    page.view.pick(int(round(x)), int(round(y)))
    assert window.properties_title.text() == "<b>Cell #1234</b>"


def test_geometry_change_marks_mesh_outdated_then_auto_remeshes(qtbot, window, tmp_path):
    _open(window, tmp_path, "nozzle_axi")
    window.generate_mesh()
    _wait_job(qtbot, window)
    panel = window.panels["geometry"]
    editor = panel.rows["d_exit"].editor
    editor.setText("0.001")
    editor.editingFinished.emit()
    assert window.strip.chips["mesh"].status == "outdated"
    qtbot.waitUntil(lambda: window.runner.busy, timeout=5_000)       # small mesh: rebuilt automatically
    _wait_job(qtbot, window)
    assert window.strip.chips["mesh"].status == "ok"


def test_undo_and_redo_of_an_input(qtbot, window, tmp_path):
    _open(window, tmp_path, "nozzle_axi")
    row = window.panels["geometry"].rows["d_exit"]
    row.editor.setText("0.0012")
    row.editor.editingFinished.emit()
    assert window.project.values["d_exit"] == 0.0012 and "*" in window.windowTitle()
    window.act["undo"].trigger()
    assert window.project.values["d_exit"] == 0.000911 and row.editor.text() == "0.000911"
    window.act["redo"].trigger()
    assert window.project.values["d_exit"] == 0.0012
    window.save()
    assert "*" not in window.windowTitle()
    assert Project.open(window.project.folder).values["d_exit"] == 0.0012


def test_run_shows_results_and_reopening_keeps_them(qtbot, window, tmp_path):
    project = _open(window, tmp_path, "quasi1d_nozzle", n_cells=60)
    window.run_case()                       # meshes first, then runs
    _wait_job(qtbot, window)                # mesh
    qtbot.waitUntil(lambda: window.runner.busy or window.results is not None, timeout=10_000)
    _wait_job(qtbot, window)                # run
    assert window.results is not None
    assert window.current_step == "results"
    assert window.strip.chips["results"].status == "ok"
    rows = window.pages["results"].numbers.rows()
    assert rows[0][:2] == ("converged", "yes")
    window.close_project()
    window.open_project(str(project.folder))
    assert window.results is not None and window.strip.chips["results"].status == "ok"
    row = window.panels["setup"].rows["p_back"].editor
    row.setText("200000")
    row.editingFinished.emit()
    assert window.strip.chips["results"].status == "outdated"
    window.go_to("results")
    assert "OUT OF DATE" in window.pages["results"].banner.text()


def test_a_running_mesh_job_can_be_cancelled(qtbot, window, tmp_path):
    pytest.importorskip("gmsh")
    _open(window, tmp_path, "external_2d", shape="Circular cylinder", surface_size=0.0008, farfield_size=0.5)
    window.generate_mesh()
    qtbot.wait(2500)
    assert window.runner.busy
    with qtbot.waitSignal(window.runner.ended, timeout=10_000) as signal:
        window.cancel_job()
    assert signal.args[0].status == "cancelled"
    assert window.strip.chips["mesh"].status == "none"


def test_theme_switch_is_remembered(window):
    window.act["dark"].trigger()
    assert window.dark and window.settings.value("theme") == "dark"
    window.act["dark"].trigger()
    assert window.settings.value("theme") == "light"


def test_results_card_shows_the_nozzle_key_results(qtbot, window, tmp_path):
    _open(window, tmp_path, "quasi1d_nozzle", n_cells=60)
    window.run_case()
    _wait_job(qtbot, window)
    qtbot.waitUntil(lambda: window.runner.busy or window.results is not None, timeout=10_000)
    _wait_job(qtbot, window)
    card = window.pages["results"].card
    assert card.isVisible()
    text = " ".join(card.tile_texts())
    for title in ("Exit Mach number", "Exit pressure", "Mass flow", "Thrust (vacuum)", "Specific impulse (vacuum)"):
        assert title in text
    m_exit = window.results["result"].key_numbers["M_exit"][0]
    assert f"{m_exit:.4g}" in text and "Converged" in card.status.text()

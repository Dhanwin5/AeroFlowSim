# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Smoke tests of the desktop GUI, driven like a user would (offscreen, no window on the screen)."""

import math

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QMessageBox, QPushButton

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
    assert geometry.built is not None and set(geometry.built.patches()) == {"wall", "inlet", "outlet", "axis"}
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


def _real_double_click(widget, pos):
    """Press, release, double-click, release: the event sequence of a real mouse (qtbot.mouseDClick
    sends only the double-click event, which does not make a list 'activate' its item)."""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    pos = QPointF(pos)
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick,
                 QEvent.MouseButtonRelease):
        buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else Qt.LeftButton
        QApplication.sendEvent(widget, QMouseEvent(kind, pos, widget.mapToGlobal(pos), Qt.LeftButton, buttons,
                                                   Qt.NoModifier))


def test_double_click_on_a_template_creates_a_project(qtbot, window, tmp_path, monkeypatch):
    import aeroflowsim.project as project_module
    monkeypatch.setattr(project_module, "default_projects_dir", lambda: tmp_path / "Projects")
    page = window.pages["welcome"]
    item = next(page.templates.item(i) for i in range(page.templates.count())
                if page.templates.item(i).data(0x0100) == "demo_heat1d")
    page.templates.setCurrentItem(item)
    _real_double_click(page.templates.viewport(), page.templates.visualItemRect(item).center())
    assert window.project is not None and window.project.case.name == "demo_heat1d"
    assert window.project.folder.parent == tmp_path / "Projects"
    assert page.templates.wordWrap()


def test_new_project_dialog_preselects_the_highlighted_template(qtbot, window, monkeypatch):
    from aeroflowsim.gui import main_window as mw
    seen = {}

    class FakeDialog:
        def __init__(self, title, parent=None, templates=None, template=None, name=""):
            seen["template"] = template

        def exec(self):
            return False

    monkeypatch.setattr(mw, "ProjectPlaceDialog", FakeDialog)
    page = window.pages["welcome"]
    for i in range(page.templates.count()):
        if page.templates.item(i).data(0x0100) == "sod_shock_tube":
            page.templates.setCurrentRow(i)
    next(b for b in page.findChildren(QPushButton) if b.text() == "New project...").click()
    assert seen["template"] == "sod_shock_tube"


def test_dialog_preselects_its_template(qtbot):
    from aeroflowsim.discovery import find_cases
    from aeroflowsim.gui.dialogs import ProjectPlaceDialog
    dialog = ProjectPlaceDialog("New project", templates=find_cases()[0], template="quasi1d_nozzle")
    qtbot.addWidget(dialog)
    assert dialog.template() == "quasi1d_nozzle" and dialog.name.text() == "My Quasi-1D nozzle"


def test_input_boxes_line_up_in_one_column(qtbot, window, tmp_path):
    _open(window, tmp_path, "quasi1d_nozzle")
    panel = window.panels["setup"]
    window.go_to("setup")
    qtbot.wait(50)
    lefts = {row.editor.mapTo(panel, row.editor.rect().topLeft()).x() for row in panel.rows.values()
             if row.editor.isVisibleTo(panel)}
    assert len(lefts) == 1, lefts                               # every box starts at the same x


def test_dark_theme_restyles_everything(qtbot, window, tmp_path):
    import matplotlib
    from aeroflowsim.gui.theme import TOKENS
    project = _open(window, tmp_path, "quasi1d_nozzle", n_cells=60)
    window.run_case()
    _wait_job(qtbot, window)
    qtbot.waitUntil(lambda: window.runner.busy or window.results is not None, timeout=10_000)
    _wait_job(qtbot, window)
    window.set_dark(True)
    dark = TOKENS[True]
    section = next(iter(window.panels["setup"].sections.values())).header
    assert section.palette().color(section.foregroundRole()).name() == dark["text"]   # heading readable
    chip_title = window.strip.chips["mesh"].title
    assert chip_title.palette().color(chip_title.foregroundRole()).name() == dark["text"]
    assert matplotlib.rcParams["figure.facecolor"] == dark["plot_bg"]
    fig = window.pages["results"].field_plot.figure
    assert matplotlib.colors.to_hex(fig.get_facecolor()) == dark["plot_bg"]           # plots redrawn dark
    window.set_dark(False)
    assert matplotlib.colors.to_hex(window.pages["results"].field_plot.figure.get_facecolor()) == "#ffffff"
    assert project.folder.exists()


def test_quasi1d_setup_shows_derived_numbers_and_geometry_units(qtbot, window, tmp_path):
    _open(window, tmp_path, "quasi1d_nozzle")
    window.go_to("setup")
    rows = {r[0]: r for r in window.pages["setup"].derived.rows()}
    assert rows["Design exit Mach number"][1].startswith("3.986")
    assert rows["Throat area"][2] == "mm²" and rows["Choked mass flow"][2] == "mg/s"
    window.go_to("geometry")
    dims = {r[0]: r for r in window.pages["geometry"].summary.rows()}
    assert dims["d throat"][1:] == ("280", "µm") and dims["d inlet"][1:] == ("2", "mm")
    assert dims["area ratio"][2] == ""



# ---- geometry workspace ----------------------------------------------------------------------------------

def test_workspace_click_name_undo_and_save(qtbot, window, tmp_path):
    from aeroflowsim.geometry_model.operations import NameBoundary
    project = _open(window, tmp_path, "nozzle_axi")
    page = window.pages["geometry"]
    assert page.toolbar.isVisible() and page.history.count() == 1
    # Select the inlet edge as a click would (picked signal), then name it like the dialog does.
    page.on_picked("edge", "op1:inlet", False)
    assert page.selection == [("edge", "op1:inlet")]
    assert window.properties.rows()[0][1] == "op1:inlet"
    document = page.document.copy()
    document.add(NameBoundary(edges=["op1:inlet"], name="chamber", kind="inlet"))
    page.commit(document, "name the inlet")
    assert "chamber" in page.built.patches() and page.history.count() == 2
    assert window.strip.chips["mesh"].status == "none" and project.dirty
    window.undo.undo()
    assert "chamber" not in page.built.patches() and page.history.count() == 1
    window.undo.redo()
    window.save()
    assert project.history_path.is_file()
    needs_rendering(page.view)
    page.view.fit()
    edge = page.built.edges["op1:inlet"]
    x, y = page.view.display_point(edge.midpoint)
    page.view.pick_at(int(round(x)), int(round(y)))
    assert page.selection == [("edge", "op1:inlet")]


def test_one_dimensional_template_keeps_the_read_only_drawing(qtbot, window, tmp_path):
    _open(window, tmp_path, "quasi1d_nozzle")
    page = window.pages["geometry"]
    assert not page.toolbar.isVisible() and page.preview is not None and page.built is None


def test_sketch_typed_and_clicked_points(qtbot, window, tmp_path, monkeypatch):
    from aeroflowsim.gui import geometry_forms
    from aeroflowsim.gui.steps import geometry as geometry_step
    _open(window, tmp_path, "geometry_2d")
    page = window.pages["geometry"]
    assert page.document.operations == [] and page.built.empty

    class Accept:                                      # the role dialog: keep the defaults, press OK
        def __init__(self, op, *args, **kwargs):
            self.result_op = op

        def exec(self):
            return True

    monkeypatch.setattr(geometry_step, "OperationDialog", Accept)
    page.start_sketch("rectangle")
    assert page.sketch_bar.isVisibleTo(page) and page.view.mode == "click"
    for text in ("-50, -50", "50; 50"):
        page.sketch_entry.setText(text)
        page.type_sketch_point()
    assert page.sketch_kind is None and "op1:face" in page.built.faces          # finished after 2 corners
    assert page.built.faces["op1:face"].area == pytest.approx(0.01)
    page.start_sketch("circle")
    page.on_sketch_click(0.0, 0.0, 1e-3)
    page.on_sketch_click(0.01, 0.0, 1e-3)
    assert page.built.faces["op2:face"].area == pytest.approx(math.pi * 1e-4, rel=1e-9)
    assert window.undo.count() == 2
    assert geometry_forms.OperationDialog is not Accept


def test_geometry_checks_suggestions_and_export(qtbot, window, tmp_path):
    _open(window, tmp_path, "external_2d", edge_refinement=False)
    page = window.pages["geometry"]
    sections = [window.checks.item(i).text() for i in range(window.checks.count())]
    assert any("Geometry" in s for s in sections) and any("Boundary names" in s for s in sections)
    found = {s.title: s for s in page.suggestions()}
    assert {"Wall cell size", "Largest cell size", "Corner refinement"} <= set(found)
    page.apply_suggestion(found["Corner refinement"])
    assert window.project.values["edge_refinement"] is True
    window.undo.undo()
    assert window.project.values["edge_refinement"] is False
    from aeroflowsim.geometry_model.export import export_geometry
    export_geometry(page.document, window.project.replay_context(), page.built, tmp_path / "g.dxf")
    assert (tmp_path / "g.dxf").stat().st_size > 1000

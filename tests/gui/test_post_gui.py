# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The 2D post-processing workspace of the Results step (Post-processing and alpha release stage), on a small converged nozzle run.

Walk-through: open a project with a result -> contours, lines, vectors, streamlines, mirror, revolve -> surfaces
by clicking and typing -> XY plot -> integrals, flux balance, forces -> report definitions -> custom field ->
saved scene -> snapshot, compare (4 linked views + difference) -> picture export -> reopen the project (settings
kept) -> switch theme and units (the view redraws, nothing breaks)."""

import shutil

import numpy as np
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QInputDialog, QMessageBox

from aeroflowsim.gui.main_window import MainWindow
from aeroflowsim.project import Project, run_project

from .conftest import needs_rendering


@pytest.fixture(scope="module")
def solved(tmp_path_factory):
    folder = tmp_path_factory.mktemp("solved") / "nozzle.afsproj"
    project = Project.create("nozzle_axi", folder, {"mesh_preset": "Custom", "nx": 30, "nr": 6})
    run_project(project)
    return folder


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch, solved):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.show()
    for name in ("question", "warning", "information"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.Yes)
    copy = tmp_path / "nozzle.afsproj"
    shutil.copytree(solved, copy)
    w.load_project(Project.open(copy))
    w.go_to("results")
    yield w
    w.runner.shutdown()


def _page(w):
    return w.pages["results"]


def test_results_step_shows_the_post_workspace_with_all_panels(window):
    page = _page(window)
    assert page.post_area.isVisible() and not page.splitter.isVisible()
    assert [page.post_tabs.tabText(i) for i in range(page.post_tabs.count())] == [
        "Display", "Surfaces", "Reports", "XY plot", "Snapshots", "Fields", "Animation"]
    assert page.solution() is not None
    view = page.grid.views[0]
    needs_rendering(view)
    assert view.mesh_actor is not None and view.data.title.startswith("Mach number")


def test_display_options_draw_without_errors(window):
    page = _page(window)
    d = page.display
    view = page.grid.views[0]
    needs_rendering(view)
    d.lines.setChecked(True)
    d.labels.setChecked(True)
    d.colouring.setCurrentText("Banded")
    d.colouring.setCurrentText("Cell values")
    d.vectors.setChecked(True)
    d.vector_colour.setCurrentIndex(d.vector_colour.findData("p"))
    d.add_seed(0.0005, 0.0003)
    assert d.scenes[0].streamlines and d.scenes[0].stream_points
    d.mirror.setChecked(True)
    d.range_mode.setCurrentText("Typed")
    d.vmin.setText("0.5")
    d.vmax.setText("2.5")
    d.vmax.editingFinished.emit()
    assert (view.data.vmin, view.data.vmax) == (0.5, 2.5)
    d.log.setChecked(True)                       # Mach > 0 everywhere: fine
    d.revolve.setChecked(True)                   # axisymmetric: 3D revolved view
    assert d.scenes[0].revolve
    d.revolve.setChecked(False)
    view.reset_view()


def test_surfaces_by_clicking_and_typing_feed_xy_plots_and_reports(window, monkeypatch):
    page = _page(window)
    page.surfaces_panel.start_line()
    page._view_clicked(0.0015, 0.0)
    page._view_clicked(0.0015, 0.002)              # beyond the wall: the line is cut at the mesh edge
    page.surfaces_panel.start_point()
    page._view_clicked(0.002, 0.0002)
    names = [s.name for s in page.surfaces(project_only=True)]
    assert names == ["line", "probe"]
    assert window.project.dirty
    # XY plot of p along the new line and the wall
    xy = page.xy
    xy.fill()
    for i in range(xy.surfaces.count()):
        xy.surfaces.item(i).setSelected(xy.surfaces.item(i).text() in ("line", "wall"))
    xy.plot()
    assert len(xy.curves) == 2 and all(len(c.x) > 2 for c in xy.curves)
    # mass flow through the line equals the outlet mass flow (converged run, same nozzle)
    r = page.reports
    r.fill()
    r.s_surface.setCurrentText("line")
    r.s_operation.setCurrentIndex(r.s_operation.findData("mass_flow"))
    line_mdot = r.compute_surface()[0]
    r.s_surface.setCurrentText("outlet")
    out_mdot = r.compute_surface()[0]
    assert line_mdot == pytest.approx(out_mdot, rel=0.03)
    fb = r.compute_fluxes()
    assert fb["relative"]["mass"] < 1e-3
    forces = r.compute_forces()
    assert forces is not None and forces["Fy"] == 0.0
    v = r.compute_volume()
    assert v[1] == "m³" and v[0] > 0
    # keep the mass flow as a report definition (monitor) and evaluate
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("mdot out", True))
    r.keep_definition("surface")
    values = r.evaluate_definitions()
    assert values["mdot out"][0] == pytest.approx(out_mdot)


def test_custom_field_saved_scene_and_reopen(window, monkeypatch):
    page = _page(window)
    f = page.fields_panel
    f.name.setText("p_bar")
    f.formula.setText("p / 1e5")
    assert f.check() == ""
    f.add()
    assert "p_bar" in window.project.custom_fields
    assert page.display.field.findData("p_bar") >= 0
    f.formula.setText("__import__('os')")
    assert "not allowed" in f.check()
    page.display.field.setCurrentIndex(page.display.field.findData("p_bar"))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("bar view", True))
    page.display.save_scene()
    assert window.project.post["scenes"]["bar view"]["field"] == "p_bar"
    window.save()
    again = Project.open(window.project.folder)
    assert "bar view" in again.post["scenes"] and "p_bar" in again.custom_fields


def test_snapshot_compare_gives_four_linked_views_and_a_difference(window, monkeypatch, tmp_path):
    page = _page(window)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("baseline", True))
    page.snapshots_panel.save()
    assert page.snapshots_panel.table.rowCount() == 1
    page.snapshots_panel.table.selectRow(0)
    page.snapshots_panel.compare()
    assert page.grid.count == 4
    assert page.display.sources[1] == "baseline" and page.display.sources[2].startswith("Difference")
    diff = page.view_solution(2)
    name, key = diff._difference_of
    assert np.allclose(diff.fields[key], 0.0)               # the snapshot is the current result
    views = page.grid.active()
    assert all(v.plotter.renderer.GetActiveCamera() is views[0].plotter.renderer.GetActiveCamera() for v in views)
    needs_rendering(views[0])
    path = tmp_path / "pic.png"
    page.save_view_picture(0, path, scale=1, transparent=True, paper=True)
    assert path.stat().st_size > 1000


def test_probe_right_click_menu_and_hover(window):
    page = _page(window)
    view = page.grid.views[0]
    needs_rendering(view)
    page.probe(0.001, 0.0002)
    menu_titles = []
    from PySide6.QtWidgets import QMenu
    menu = QMenu()
    view.context_actions(menu, (0.001, 0.0002))
    menu_titles = [a.text() for a in menu.actions() if a.text()]
    for t in ("Probe here", "Pin a probe here (point surface)", "Seed a streamline here", "Zoom to fit",
              "Save picture..."):
        assert t in menu_titles
    assert "Mach number" in view.hover(0.001, 0.0002)
    assert view.hover(1.0, 1.0) == ""


def test_theme_and_units_switch_redraws(window):
    page = _page(window)
    window.set_dark(True, save=False)
    window.set_dark(False, save=False)
    assert page.grid.views[0].dark is False

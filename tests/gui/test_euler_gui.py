# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The 2D Euler solver in the desktop GUI: boundary-condition table, live monitors, 2D results, restart."""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from aeroflowsim.gui.boundary_logic import rows, with_type, with_value, without
from aeroflowsim.gui.main_window import MainWindow
from aeroflowsim.project import Project

from .conftest import needs_rendering

JOB_MS = 180_000


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.show()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    yield w
    w.runner.shutdown()


def _wait_job(qtbot, window):
    if window.runner.busy:
        with qtbot.waitSignal(window.runner.ended, timeout=JOB_MS):
            pass


def _mesh(qtbot, window, tmp_path, **values):
    project = Project.create("nozzle_axi", tmp_path / "N.afsproj", values={"mesh_preset": "Coarse", **values})
    window.load_project(project)
    _wait_job(qtbot, window)
    window.generate_mesh()
    _wait_job(qtbot, window)
    return project


def test_boundary_table_lists_the_mesh_patches_and_edits_are_undoable(qtbot, window, tmp_path):
    project = Project.create("nozzle_axi", tmp_path / "N.afsproj", values={"mesh_preset": "Coarse"})
    window.load_project(project)
    table = window.panels["setup"].rows["boundaries"].editor
    if window.mesh is None:
        assert "Make the mesh first" in table.message.text()
    _wait_job(qtbot, window)
    window.generate_mesh()
    _wait_job(qtbot, window)
    names = [r.name for r in table.rows]
    assert sorted(names) == ["axis", "inlet", "outlet", "wall"]
    inlet = next(r for r in table.rows if r.name == "inlet")
    assert inlet.condition.type == "total_pressure_inlet" and inlet.condition.values["p0"] == 5e5
    # The default follows the p0 input until the user changes the boundary itself
    p0 = window.panels["setup"].rows["p0"].editor
    p0.setText("300")                                  # kPa (the default display unit)
    p0.editingFinished.emit()
    inlet = next(r for r in table.rows if r.name == "inlet")
    assert inlet.condition.values["p0"] == pytest.approx(3e5) and not inlet.changed
    table._edit(with_type(table.table, next(r for r in table.rows if r.name == "outlet"), "supersonic_outlet"))
    assert project.values["boundaries"] == {"outlet": {"type": "supersonic_outlet"}}
    assert next(r for r in table.rows if r.name == "outlet").changed
    window.undo.undo()
    assert project.values["boundaries"] == {}
    assert not next(r for r in table.rows if r.name == "outlet").changed


def test_boundary_logic_keeps_shared_values_when_the_type_changes():
    from aeroflowsim.euler.boundary import BoundaryCondition
    effective = [("far", "farfield", BoundaryCondition("far_field", {"mach": 3.0, "p": 5e4}), False)]
    row = rows({}, effective)[0]
    assert {s.name for s in row.specs} == {"mach", "p", "T", "flow_angle"} and row.suits
    table = with_type({}, row, "supersonic_inlet")
    assert table["far"]["type"] == "supersonic_inlet" and table["far"]["mach"] == 3.0
    table = with_value(table, rows(table, [("far", "farfield", BoundaryCondition.from_dict(table["far"]), True)])[0],
                       "p", 2e4)
    assert table["far"]["p"] == 2e4
    assert without(table, row) == {}


def test_nozzle_run_shows_monitors_2d_field_wall_pressure_and_restarts(qtbot, window, tmp_path):
    project = _mesh(qtbot, window, tmp_path, max_iter=60)
    window.run_case()
    _wait_job(qtbot, window)
    assert window.results is not None and window.current_step == "results"
    run = window.pages["run"]
    assert run._extra["equations"] and set(run._extra["monitors"]) >= {"thrust", "thrust_wall", "mdot_in", "mdot_out"}
    page = window.pages["results"]
    assert page.field_stack.currentWidget() is page.flow_view and page.field.currentData() == "M"
    assert page.flow_plot_choice.count() == 2         # wall pressure and the convergence history
    titles = [t for t, *_ in __import__("aeroflowsim.gui.logic", fromlist=["x"]).key_result_tiles(
        window.results["result"])]
    assert "Specific impulse (vacuum)" in titles and "Discharge coefficient" in titles
    page.cell_picked(0)
    labels = [window.properties.item(r, 0).text() for r in range(window.properties.rowCount())]
    assert "Mach number" in labels and "Pressure" in labels
    first_mdot = window.results["result"].key_numbers["mdot"][0]
    # Restart: continue the previous result for a few more iterations
    window.apply_values({"initialisation": "Previous result (restart)", "max_iter": 5})
    window.run_case()
    _wait_job(qtbot, window)
    result = window.results["result"]
    assert result.info["initialisation"] == "Previous result (restart)" and result.iterations == 5
    assert abs(result.key_numbers["mdot"][0] / first_mdot - 1.0) < 0.02


def test_results_of_an_older_mesh_are_not_painted_on_a_new_mesh(qtbot, window, tmp_path):
    """Run on the coarse mesh, then mesh finer: the Results step says the results belong to the old mesh
    (it once tried to paint 2,000 values onto 8,000 cells and crashed when the colour map changed)."""
    from aeroflowsim.gui.logic import results_mesh_mismatch
    _mesh(qtbot, window, tmp_path, max_iter=5)
    window.run_case()
    _wait_job(qtbot, window)
    window.apply_values({"mesh_preset": "Medium"})
    _wait_job(qtbot, window)                     # automatic re-mesh (8,000 cells)
    if window.mesh.n_cells != 8000:
        window.generate_mesh()
        _wait_job(qtbot, window)
    assert window.mesh.n_cells == 8000
    result = window.results["result"]
    assert "older mesh (2,000 cells)" in results_mesh_mismatch(result, window.mesh)
    page = window.pages["results"]
    window.go_to("results")
    page._shown = None
    page.refresh()
    page.flow_cmap.setCurrentText("viridis")    # the colour-map change that crashed
    page.cell_picked(0)                          # no values of the old mesh shown for a new-mesh cell
    page.save_vtu()                              # does nothing (no dialog)
    assert not page.vtu_button.isEnabled()
    assert page.flow_view.mesh_actor is None     # the view shows the message, not a field


def test_stop_keeps_the_flow_of_that_moment(qtbot, window, tmp_path):
    _mesh(qtbot, window, tmp_path, max_iter=1_000_000)
    window.run_case()
    qtbot.waitUntil(lambda: window.runner.task is not None and len(window.runner.task.iterations) >= 10,
                    timeout=60_000)
    window.cancel_job()
    _wait_job(qtbot, window)
    assert window.results is not None
    result = window.results["result"]
    assert result.info["status"] == "stopped" and not result.converged
    assert window.strip.chips["results"].status == "ok"          # results of the current inputs, not converged
    window.go_to("run")
    assert "Stopped by you" in window.pages["run"].banner.text()
    window.go_to("results")
    assert window.pages["results"].flow_view.mesh_actor is not None   # the field is drawn


def test_angle_of_attack_on_an_axisymmetric_body_is_refused_before_the_run(qtbot, window, tmp_path, monkeypatch):
    pytest.importorskip("gmsh")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]) or QMessageBox.Ok)
    project = Project.create("external_2d", tmp_path / "C.afsproj",
                             values={"shape": "Conical nose cone", "domain_shape": "Rectangle", "upstream": 1.0,
                                     "downstream": 1.0, "height": 2.0, "surface_size": 0.05, "farfield_size": 0.5,
                                     "alpha": 10.0})
    window.load_project(project)
    _wait_job(qtbot, window)
    window.generate_mesh()
    _wait_job(qtbot, window)
    names = [c.name for c in window.setup_checks() if c.level == "error"]
    assert names == ["Axisymmetric free stream"]
    window.run_case()
    assert not window.runner.busy and window.current_step == "setup"
    assert warnings and "cannot have an angle of attack" in warnings[-1]


def test_results_view_draws_the_field_in_both_themes(qtbot, window, tmp_path):
    _mesh(qtbot, window, tmp_path, max_iter=10)
    window.run_case()
    _wait_job(qtbot, window)
    page = window.pages["results"]
    needs_rendering(page.flow_view)
    for dark in (True, False):
        window.set_dark(dark)
        window.go_to("results")
        assert page.flow_view.mesh_actor is not None
        page.flow_cmap.setCurrentText("viridis")
        page.flow_auto.setChecked(False)
        page.flow_min.setText("0")
        page.flow_max.setText("2")
        page.draw_field(keep_camera=True)
        assert tuple(page.flow_view.mesh_actor.mapper.scalar_range) == (0.0, 2.0)
        page.flow_auto.setChecked(True)

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Flow animation in the Results step (gui/animation_panel.py). Walk-through: open a project with a result -> the
Animation tab -> play, step, slider -> the views show the frame with a fixed colour range -> leave the tab (the final
result again) -> change the recording settings (saved in the project) -> save a GIF -> switch units and theme while a
frame is shown -> an old project without frames -> a 1D Sod result plays its snapshots in the field plot."""

import shutil

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox

from aeroflowsim.gui.main_window import MainWindow
from aeroflowsim.post.animation import ANIMATION_FILE, RANGE_FRAME
from aeroflowsim.project import Project, run_project

from .conftest import needs_rendering


@pytest.fixture(scope="module")
def solved(tmp_path_factory):
    folder = tmp_path_factory.mktemp("anim_gui") / "nozzle.afsproj"
    project = Project.create("nozzle_axi", folder, {"mesh_preset": "Custom", "nx": 30, "nr": 6, "max_iter": 30})
    run_project(project)
    return folder


def _window(qtbot, tmp_path, monkeypatch, folder):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.show()
    for name in ("question", "warning", "information"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.Yes)
    w.load_project(Project.open(folder))
    w.go_to("results")
    return w


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch, solved):
    copy = tmp_path / "nozzle.afsproj"
    shutil.copytree(solved, copy)
    w = _window(qtbot, tmp_path, monkeypatch, copy)
    yield w
    w.runner.shutdown()


def test_play_step_and_leave_the_animation_tab(window, qtbot):
    page = window.pages["results"]
    panel = page.animation_panel
    page.post_tabs.setCurrentWidget(panel)
    bar = panel.bar
    anim = page.animation()
    assert anim is not None and anim.n >= 3 and bar.slider.maximum() == anim.n - 1
    assert bar.index == anim.n - 1 and not page.showing_frame()             # starts on the final result
    view = page.grid.views[0]
    needs_rendering(view)
    bar.seek(0)
    assert page.showing_frame() and page.view_solution(0).name == "frame 1"
    assert bar.label.text().startswith("Iteration 0")
    lo, hi = page.frame_range("M")
    assert view.data.vmin == pytest.approx(lo) and view.data.vmax == pytest.approx(hi)   # fixed over all frames
    bar.range_mode.setCurrentText(RANGE_FRAME)
    assert view.data.vmax <= hi + 1e-12
    view.zoom_to_body()                                                     # the zoom stays while frames change
    zoomed = view.plotter.camera.parallel_scale
    bar.step(1)
    assert bar.index == 1
    assert view.plotter.camera.parallel_scale == pytest.approx(zoomed)
    bar.toggle()
    assert bar.playback.playing and bar.timer.isActive()
    qtbot.waitUntil(lambda: bar.index >= 3 or bar.index == 0, timeout=3000)
    bar.pause()
    page.post_tabs.setCurrentWidget(page.display)                           # leave the tab: the final result again
    assert not panel.active and not page.showing_frame() and page.view_solution(0) is page.solution()
    window.set_dark(True, save=False)                                       # theme switch while a frame is chosen
    window.set_dark(False, save=False)


def test_recording_settings_and_gif_export(window, monkeypatch, tmp_path):
    page = window.pages["results"]
    panel = page.animation_panel
    page.post_tabs.setCurrentWidget(panel)
    panel.every.setValue(5)
    panel.record.setChecked(False)
    assert window.project.post["animation"] == {"record": False, "every": 5}
    assert not panel.every.isEnabled()
    target = tmp_path / "flow.gif"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    panel.save()
    assert target.is_file() and target.stat().st_size > 1000


def test_old_project_without_frames(qtbot, tmp_path, monkeypatch, solved):
    copy = tmp_path / "old.afsproj"
    shutil.copytree(solved, copy)
    (copy / "results" / ANIMATION_FILE).unlink()
    w = _window(qtbot, tmp_path, monkeypatch, copy)
    try:
        page = w.pages["results"]
        page.post_tabs.setCurrentWidget(page.animation_panel)
        assert page.animation() is None and not page.animation_panel.save_button.isEnabled()
        assert "no recorded frames" in page.animation_panel.note.text()
        assert not page.showing_frame()
    finally:
        w.runner.shutdown()


def test_sod_snapshots_play_in_the_field_plot(qtbot, tmp_path, monkeypatch):
    folder = tmp_path / "sod.afsproj"
    run_project(Project.create("sod_shock_tube", folder, {"n_cells": 100}))
    w = _window(qtbot, tmp_path, monkeypatch, folder)
    try:
        page = w.pages["results"]
        bar = page.bar1d
        assert bar.isVisible() and bar.animation.n >= 2
        bar.seek(1)
        assert bar.label.text().startswith("t = ")
        assert page.field_plot.figure.axes[0].get_title().startswith("t = ")
    finally:
        w.runner.shutdown()

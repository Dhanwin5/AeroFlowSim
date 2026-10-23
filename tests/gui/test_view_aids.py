# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""View aids of the geometry workspace: our own icons (both themes), the adaptive grid, the 3D
switch and the revolve preview, the right-click menu contents."""

import numpy as np
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from aeroflowsim.geometry_model.snapping import MAJOR_EVERY, visible_grid
from aeroflowsim.gui.icons import DRAWINGS, icon
from aeroflowsim.gui.main_window import MainWindow
from aeroflowsim.project import Project


@pytest.mark.parametrize("dark", [False, True])
def test_every_icon_draws_in_both_themes(qtbot, dark):
    for name in DRAWINGS:
        pixmap = icon(name, dark).pixmap(24, 24)
        assert not pixmap.isNull(), name
        image = pixmap.toImage()
        painted = sum(image.pixelColor(x, y).alpha() > 0 for x in range(24) for y in range(24))
        assert painted > 10, f"icon '{name}' is (almost) empty"
    assert icon("no such icon").isNull()


def test_grid_follows_the_zoom():
    step, xs, ys, x_major, y_major = visible_grid(0.0, 0.04, 0.0, 0.02)
    assert step == pytest.approx(0.001)                   # 2 cm high -> about 20 lines of 1 mm
    assert xs[0] <= 0.0 and xs[-1] >= 0.04 and np.allclose(np.diff(xs), step)
    assert all(m == (round(x / step) % MAJOR_EVERY == 0) for x, m in zip(xs, x_major))
    assert visible_grid(0, 40, 0, 20)[0] == pytest.approx(1.0)


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    w = MainWindow(QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    qtbot.addWidget(w)
    w.show()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    yield w
    w.runner.shutdown()


def test_3d_switch_revolve_preview_and_context_menu(qtbot, window, tmp_path):
    window.load_project(Project.create("nozzle_axi", tmp_path / "N.afsproj"))
    page = window.pages["geometry"]
    view = page.view
    assert view.toggles["grid"].isChecked() and view._grid_actors
    assert "wall" in view.legend_label.text() and "axis" in view.legend_label.text()
    assert view.toggles["revolve"].isEnabled()                       # axisymmetric template
    view.toggles["revolve"].setChecked(True)
    assert view.view3d and view.toggles["view3d"].isChecked()
    assert len(view._revolve_actors) == 5                            # 3 wall pieces, inlet, outlet (not the axis)
    view.toggles["view3d"].setChecked(False)
    assert not view.view3d and not view.toggles["revolve"].isChecked() and not view._revolve_actors
    texts = lambda kind: [a.text() for a in page.context_actions(kind) if a is not None]
    assert "Name" in texts("edge") and "Fillet" in texts("vertex") and "Transform" in texts("face")
    assert "Import" in texts("")
    window.set_dark(True, save=False)                                # icons and grid follow the theme
    assert view._grid_actors and not page.icon_targets[0][0].icon().isNull()


def test_mouse_drawing_box_selection_pan_and_zoom(qtbot, window, tmp_path):
    """The view's own mouse handling (what the Qt event filter calls), in VTK pixels."""
    from aeroflowsim.geometry_model.operations import Sketch
    from .conftest import needs_rendering
    project = Project.create("geometry_2d", tmp_path / "D.afsproj")
    window.load_project(project)
    page, view = window.pages["geometry"], window.pages["geometry"].view
    doc = project.geometry_document()
    doc.add(Sketch(kind="rectangle", points=[[0, 0], [0.1, 0.04]], role="fluid"))
    window.edit_geometry(doc, "rectangle")
    needs_rendering(view)
    view._show_box(0.012, 0.058, 0.002, 0.038)                            # zoomed in: a pixel is small, as for a user
    px = lambda xy: view.display_point(xy)[:2]
    # Draw a rectangle by press - drag - release (two corners in one move).
    page.start_sketch("rectangle")
    (x0, y0), (x1, y1) = px((0.02, 0.01)), px((0.05, 0.03))
    view.mouse_press(x0, y0)
    view.mouse_move(x1, y1)
    view.mouse_release(x1, y1)
    face = page.built.faces["op2:face"]
    loop = page.built.loop_points(face.loops[0])
    assert face.area == pytest.approx(0.03 * 0.02, rel=0.02), (loop.min(axis=0), loop.max(axis=0), view.metres_per_pixel())
    page.cancel_sketch()
    # Box selection from left to right around the new rectangle: its 4 edges, 4 corners and the face.
    (bx0, by0), (bx1, by1) = px((0.015, 0.005)), px((0.055, 0.035))
    view.mouse_press(bx0, by0)
    view.mouse_move(bx1, by1)
    view.mouse_release(bx1, by1)
    kinds = [k for k, _ in page.selection]
    assert kinds.count("edge") == 4 and kinds.count("face") == 1
    # Zoom about the cursor keeps the point under it; Shift + drag pans.
    cx, cy = px((0.07, 0.02))
    before = view.world_point(cx, cy)
    view.zoom_at(cx, cy, 0.5)
    assert view.world_point(cx, cy) == pytest.approx(before, abs=1e-9)
    scale = view.plotter.camera.parallel_scale
    view.mouse_press(cx, cy, shift=True)
    view.mouse_move(cx + 50, cy)
    view.mouse_release(cx + 50, cy)
    assert view.world_point(cx + 50, cy) == pytest.approx(before, abs=1e-6)   # the grabbed point followed
    assert view.plotter.camera.parallel_scale == scale


def test_axes_triad_stays_in_2d_and_3d(qtbot, window, tmp_path):
    window.load_project(Project.create("nozzle_axi", tmp_path / "T.afsproj"))
    view = window.pages["geometry"].view
    assert view.plotter.renderer.axes_enabled                        # the xyz triad in the corner
    view.toggles["view3d"].setChecked(True)
    assert view.plotter.renderer.axes_enabled
    view.toggles["view3d"].setChecked(False)
    assert view.plotter.renderer.axes_enabled


@pytest.mark.parametrize("dark", [False, True])
def test_unchecked_check_box_is_empty_in_both_themes(qtbot, dark):
    """Fusion's dark style once drew an UNchecked box as a filled blue square (fixed in the theme)."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QCheckBox
    from aeroflowsim.gui.theme import CHECK_BLUE, apply_theme
    apply_theme(dark)
    try:
        boxes = {}
        for checked in (False, True):
            box = QCheckBox("x", checked=checked)
            qtbot.addWidget(box)
            box.resize(60, 24)
            boxes[checked] = box.grab().toImage()
        blue = QColor(CHECK_BLUE)
        def blue_pixels(image):
            return sum(abs(image.pixelColor(x, y).red() - blue.red()) < 30
                       and abs(image.pixelColor(x, y).blue() - blue.blue()) < 30
                       and abs(image.pixelColor(x, y).green() - blue.green()) < 30
                       for x in range(min(24, image.width())) for y in range(image.height()))
        assert blue_pixels(boxes[False]) < 5, "an unchecked box must not be filled blue"
        assert blue_pixels(boxes[True]) > 30, "a checked box is blue with a tick"
    finally:
        apply_theme(False)

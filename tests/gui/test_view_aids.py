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

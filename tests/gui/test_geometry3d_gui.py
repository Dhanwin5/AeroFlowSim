# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""GUI tests of the 3D geometry workspace and the 3D Mesh step (template external_3d), walking through what a user
does: open a 3D project, click and box-select faces, hide / isolate / section, add a body, a boolean, name faces,
undo / redo, save and reopen, mesh (with prism layers), cancel a mesh job, switch theme and units, open a 2D
project afterwards."""

import pytest

pytest.importorskip("gmsh")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from aeroflowsim.geometry_model.operations3d import Boolean3D, Box, Sphere  # noqa: E402
from aeroflowsim.gui import geometry_logic as logic  # noqa: E402
from aeroflowsim.gui.main_window import MainWindow  # noqa: E402
from aeroflowsim.project import Project  # noqa: E402

from .conftest import needs_rendering  # noqa: E402

JOB_MS = 120_000
COARSE = {"surface_size": 0.15, "farfield_size": 2.0, "curvature_cells": 12, "upstream": 2.0, "downstream": 3.0,
          "lateral": 2.0}


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


def _open(window, tmp_path, template="external_3d", **values):
    project = Project.create(template, tmp_path / f"{template}.afsproj", values={**COARSE, **values}
                             if template == "external_3d" else values or None)
    window.load_project(project)
    return project


def _geometry(window):
    window.go_to("geometry")
    page = window.pages["geometry"]
    assert page.is_3d
    return page.page3d


def _pixel(view, xyz):
    """The VTK display pixel of a world point."""
    from vtkmodules.vtkRenderingCore import vtkCoordinate
    c = vtkCoordinate()
    c.SetCoordinateSystemToWorld()
    c.SetValue(*xyz)
    x, y = c.GetComputedDisplayValue(view.plotter.renderer)
    return int(x), int(y)


def _wait_job(qtbot, window):
    if window.runner.busy:
        with qtbot.waitSignal(window.runner.ended, timeout=JOB_MS):
            pass


def test_3d_project_shows_the_3d_workspace(qtbot, window, tmp_path):
    _open(window, tmp_path)
    page = _geometry(window)
    built = page.built
    assert built is not None and built.dimension == 3
    assert {"op1:surface", "op2:upstream"} <= set(built.faces)
    rows = {r[0]: r for r in logic.boundary_rows_3d(built)}
    assert rows["wall"][1] == "wall" and rows["farfield"][2] == 6
    assert page.history.count() == 2 and "Template body" in page.history.item(0).text()
    assert not [c for c in window.geometry_checks() if c.level == "error"]


def test_click_box_select_hide_isolate_and_section(qtbot, window, tmp_path):
    _open(window, tmp_path)
    page = _geometry(window)
    view = page.view
    needs_rendering(view)
    view.set_view("+z")
    qtbot.wait(50)
    w, h = view.plotter.renderer.GetSize()
    view.pick_at(w // 2, h // 2)                          # the middle of the view: the top far-field face
    assert page.selection and page.selection[0][0] == "face"
    first = page.selection[0][1]
    page.hide_selected()
    assert first in page.visibility.hidden and not page.selection
    view.pick_at(w // 2, h // 2)                          # now the next face behind it
    assert page.selection and page.selection[0][1] != first
    page.show_all()
    assert not page.visibility.hidden
    view.select_box((0, 0), (w, h))                       # left to right round everything: every visible face
    assert len(page.selection) == len(page.built.faces)
    page.set_selection([("face", "op1:surface")])
    page.isolate_selected()
    assert page.visibility.visible(page.built) == ["op1:surface"]
    page.show_all()
    page.section_axis.setCurrentText("y")                 # cut the box open: the sphere is drawn and clickable
    assert page.section() is not None
    view.set_view("-y")
    qtbot.wait(50)
    view.pick_at(*_pixel(view, (0.0, 0.0, 0.0)))          # where the sphere's centre is on the screen
    assert page.selection == [("face", "op1:surface")]
    page.section_axis.setCurrentText("off")


def test_add_bodies_boolean_name_undo_redo_and_reopen(qtbot, window, tmp_path):
    project = _open(window, tmp_path)
    page = _geometry(window)
    doc = page.document.copy()
    doc.add(Box(x0=-0.02, y0=-0.02, z0=0.03, dx=0.04, dy=0.04, dz=0.04), 1)       # a box on top of the sphere
    window.edit_geometry(doc, "add box")
    page.refresh()
    box_id = page.document.operations[1].id
    assert box_id in page.built.bodies or any(b.startswith("op") for b in page.built.bodies)
    doc = page.document.copy()
    doc.add(Boolean3D(kind="union", objects=["op1"], tools=[box_id]), 2)
    window.edit_geometry(doc, "union")
    page.refresh()
    assert not page.built.errors(), page.built.messages
    sphere_area = page.built.faces["op1:surface"].area
    # name the sphere's surface "nose" by its stable face id
    page.set_selection([("face", "op1:surface")])
    op = logic.operation_for_3d("name_faces", page.selection, page.built)
    op.params["name"] = "nose"
    doc = page.document.copy()
    doc.add(op)
    window.edit_geometry(doc, "name nose")
    page.refresh()
    assert page.built.names["op1:surface"].name == "nose"
    window.undo.undo()
    page.refresh()
    assert page.built.names["op1:surface"].name == "wall"
    window.undo.redo()
    page.refresh()
    assert page.built.names["op1:surface"].name == "nose"
    # an upstream change (the template's diameter) keeps the name on the same face
    window.set_inputs({"diameter": 0.12}, "diameter")
    page.refresh()
    assert page.built.names["op1:surface"].name == "nose"
    assert page.built.faces["op1:surface"].area > sphere_area                  # the bigger sphere
    window.save()
    again = Project.open(project.folder)
    assert again.edited_geometry is not None and again.edited_geometry.dimension == 3
    assert any(o.type == "name_faces" for o in again.edited_geometry.operations)


def test_accept_suggestions_rename_type_and_prism_layers(qtbot, window, tmp_path):
    _open(window, tmp_path)
    page = _geometry(window)
    doc = logic.rename_boundary_3d(page.document, page.built, "wall", "ball")
    window.edit_geometry(doc, "rename")
    page.refresh()
    assert {r[0] for r in logic.boundary_rows_3d(page.built)} == {"ball", "farfield"}
    doc = logic.set_boundary_type_3d(page.document, page.built, "ball", "wall", inflation=True)
    window.edit_geometry(doc, "layers")
    page.refresh()
    assert page.built.names["op1:surface"].inflation
    assert logic.accept_suggestions_3d(page.document, page.built) is None        # everything is named
    page.boundaries.selectRow(0)
    assert page.selection                                                         # the table selects its faces


def test_3d_mesh_step_shows_the_mesh_quality_and_cut(qtbot, window, tmp_path):
    _open(window, tmp_path, inflation=True, first_layer_height=0.002, n_layers=2)
    window.go_to("mesh")
    window.generate_mesh()
    _wait_job(qtbot, window)
    mesh = window.mesh
    assert mesh is not None and mesh.dim == 3
    page = window.pages["mesh"]
    page.refresh()
    assert "Smallest dihedral angle" in [page.colour.itemText(i) for i in range(page.colour.count())]
    page.colour.setCurrentText("Skewness (equivolume for tetrahedra)")
    page.cut.setCurrentText("y")
    assert page.view.grid is not None and page.view.cut_cells > 0
    rows = dict((r[0], r[1]) for r in page.summary.rows())
    assert "prisms" in " ".join(rows).lower() or any("prism" in str(v).lower() for v in rows.values())
    page.show_worst()
    assert "Cell" in window.properties_title.text()
    assert page.histogram.figure is not None
    names = {c.name for c in window.mesh_checks}
    assert {"Cell volumes", "First layer height", "Dihedral angle"} <= names
    assert window.strip.chips["run"].status != "disabled"                # 3D Euler stage: the Run step is there
    assert window.project.case.has_solver


def test_cancel_a_long_3d_mesh_job(qtbot, window, tmp_path):
    _open(window, tmp_path, surface_size=0.01, farfield_size=0.2)            # a big mesh (a few seconds)
    window.go_to("mesh")
    window.generate_mesh()
    assert window.runner.busy
    with qtbot.waitSignal(window.runner.ended, timeout=JOB_MS):
        window.cancel_job()
    assert window.project.status("mesh") != "ok"


def test_theme_units_and_a_2d_project_afterwards(qtbot, window, tmp_path):
    _open(window, tmp_path)
    page = _geometry(window)
    window.set_dark(True)
    window.set_dark(False)
    rows = dict((r[0], r[1:]) for r in logic.summary_rows_3d(page.built, window.units))
    assert rows["Fluid volume"][1].endswith("³")
    # the old 2D template still shows the 2D workspace, and back again
    window.load_project(Project.create("external_2d", tmp_path / "flat.afsproj"))
    window.go_to("geometry")
    geometry = window.pages["geometry"]
    assert not geometry.is_3d and geometry.built is not None and geometry.built.axisymmetric is not None
    assert hasattr(geometry.built, "vertices")                                   # a 2D BuiltGeometry
    _open(window, tmp_path / "again")
    assert _geometry(window).built.dimension == 3

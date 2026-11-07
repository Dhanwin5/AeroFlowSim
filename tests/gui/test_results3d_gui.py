# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The 3D run from the GUI: mesh, run, the 3D Results view (walls, slice, iso-surface, streamlines, probe), continue
the run (numbering carries on), reopen the project (results still current), export .vtu / CSV."""

import pytest

pytest.importorskip("gmsh")

from aeroflowsim.project import Project  # noqa: E402

from .test_geometry3d_gui import COARSE, _wait_job, window  # noqa: E402,F401

RUN = {**COARSE, "half_domain": True, "quarter_domain": True, "mach": 3.0, "max_iter": 25}


def test_3d_run_results_continue_and_reopen(qtbot, window, tmp_path):  # noqa: F811
    project = Project.create("external_3d", tmp_path / "sphere.afsproj", values=RUN)
    window.load_project(project)
    window.run_case()
    _wait_job(qtbot, window)                       # the mesh
    _wait_job(qtbot, window)                       # the run that follows it
    assert window.results is not None and window.mesh.dim == 3
    first = window.results["result"].iterations
    assert first == 25
    window.go_to("results")
    page = window.pages["results"]
    page.refresh()
    panel = page.panel3d
    assert panel is not None and panel.isVisible() and panel.sol.mesh.dim == 3
    for mode in ("Slice plane", "Iso-surface", "Streamlines", "Walls"):
        panel.display.setCurrentText(mode)
        surfaces, lines = panel.surfaces()
        assert any(s.n_triangles for s in surfaces) or lines, mode
    panel.axis.setCurrentText("z")
    panel.display.setCurrentText("Slice plane")
    panel._picked((-0.08, 0.02, 0.02))
    assert "Cell" in panel.probe_text.text()
    # continue: Run again carries on from iteration 25 up to the raised maximum
    project.values["max_iter"] = 40
    window.run_case()
    _wait_job(qtbot, window)
    assert window.results["result"].iterations == 40
    assert window.results["result"].info["continued_from"] == 25
    # export
    from aeroflowsim.post.export import fields_csv, fields_vtu
    fields_vtu(panel.sol, tmp_path / "r.vtu")
    text = fields_csv(panel.sol, tmp_path / "r.csv").read_text(encoding="utf-8")
    assert "z [m]" in text and "w [" in text
    # reopen: the result is still current
    window.save_project() if hasattr(window, "save_project") else project.save()
    again = Project.open(tmp_path / "sphere.afsproj")
    assert again.status("results") == "ok"
    # full 3D release stage: the post-processing tabs (Patches, XY plot, Reports, Snapshots)
    assert [panel.tabs.tabText(i) for i in range(panel.tabs.count())] == ["View", "Patches", "XY plot", "Reports",
                                                                        "Snapshots"]
    assert panel.shown_patches() == ["wall"]                 # the walls are drawn by default
    panel.xy_normal.setCurrentText("z")
    panel.xy_position.setText("0.001")
    points, values = panel.plot_cut()
    assert len(points) > 5 and abs(points[:, 2] - 0.001).max() < 1e-12
    project.post["report_definitions"] = [{"name": "drag", "kind": "force", "walls": ["wall"], "force": "Cd"}]
    values, fb = panel.evaluate_reports()
    assert values["drag"][0] == pytest.approx(panel.sol.key_numbers["Cd"][0], rel=1e-9)   # = the solver's own Cd
    panel.save_snapshot("first")
    assert panel.snapshot_list.count() == 1
    rows = panel.compare_snapshot("first")
    assert any(r[0] == "Cd" and abs(r[4]) < 1e-9 for r in rows)

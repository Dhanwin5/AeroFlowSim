# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Smoke tests of the Streamlit GUI, using Streamlit's built-in headless tester (no browser).

AppTest runs app.py like a real user session: we can read widgets and press buttons.
"""

from pathlib import Path

import pytest

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def test_app_starts_with_demo_case_and_input_form():
    at = _app()
    assert at.sidebar.selectbox[0].value == "demo_heat1d"
    labels = [box.label for box in at.number_input]
    assert len(labels) == 8
    assert "Rod length [m]" in labels


def test_generate_mesh_shows_node_and_cell_counts():
    at = _app()
    at.button(key="generate_mesh").click().run()
    assert not at.exception, at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Nodes"] == "41"
    assert metrics["Cells"] == "40"


def test_changed_input_changes_mesh():
    at = _app()
    at.number_input(key="demo_heat1d:n_nodes").set_value(11).run()
    at.button(key="generate_mesh").click().run()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Cells"] == "10"


def test_run_then_results_tab_shows_key_numbers():
    at = _app()
    at.button(key="run").click().run()
    job = at.session_state["job"]
    job.wait(timeout=60)
    at.run()  # redraw after the background run has finished
    assert not at.exception, at.exception
    assert job.status == "finished"
    table = at.dataframe[0].value
    assert "T_max" in list(table["Quantity"])
    assert "max |T − T_exact|" in list(table["Quantity"])
    # Contours: a steady 1D case offers the shape view only (drawn without error above).
    assert at.radio(key="contour_view").options == ["Shape view"]


def test_sod_contours_offer_xt_diagram_with_wave_paths():
    at = _app()
    at.sidebar.selectbox[0].set_value("sod_shock_tube").run()
    at.number_input(key="sod_shock_tube:n_cells").set_value(100).run()
    at.button(key="run").click().run()
    at.session_state["job"].wait(timeout=60)
    at.run()
    assert not at.exception, at.exception
    view = at.radio(key="contour_view")
    assert view.options == ["Shape view", "x-t diagram"]
    view.set_value("x-t diagram").run()
    assert not at.exception, at.exception
    assert at.checkbox(key="contour_lines").value is True
    at.checkbox(key="contour_auto").uncheck().run()      # manual colour range
    assert not at.exception, at.exception


def _nozzle_app():
    at = _app()
    at.sidebar.selectbox[0].set_value("quasi1d_nozzle").run()
    assert not at.exception, at.exception
    return at


def test_nozzle_setup_shows_geometry_preview():
    at = _nozzle_app()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Throat diameter [mm]"] == "0.28"
    assert metrics["Exit diameter [mm]"] == "0.911"
    labels = [box.label for box in at.number_input]
    assert "Throat diameter [m]" in labels
    assert "Wall profile CSV (path)" not in [box.label for box in at.text_input]   # hidden for "parametric"


def test_nozzle_csv_source_and_bad_file_message(tmp_path):
    at = _nozzle_app()
    at.selectbox(key="quasi1d_nozzle:geometry_source").set_value("Custom profile (CSV)").run()
    assert not at.exception, at.exception
    assert "Throat diameter [m]" not in [box.label for box in at.number_input]   # cone inputs hidden
    assert {m.label: m.value for m in at.metric}["Area ratio A_exit/A_throat [-]"] == "10.59"

    bad = tmp_path / "bad.csv"
    bad.write_text("x_mm,r_mm\n0,1\n1,1\n0.5,0.2\n2,0.4\n3,0.5\n", encoding="utf-8")
    at.text_input(key="quasi1d_nozzle:profile_csv").set_value(str(bad)).run()
    assert not at.exception, at.exception
    errors = " ".join(e.value for e in at.error)
    assert "Line 4" in errors and "must increase" in errors
    at.button(key="generate_mesh").click().run()          # the mesh tab shows the problem, no crash
    assert not at.exception, at.exception
    assert any("Could not build the mesh" in e.value for e in at.error)


def test_nozzle_short_run_offers_shape_view():
    at = _nozzle_app()
    at.number_input(key="quasi1d_nozzle:n_cells").set_value(60).run()
    at.number_input(key="quasi1d_nozzle:max_iter").set_value(300).run()
    at.button(key="run").click().run()
    job = at.session_state["job"]
    job.wait(timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert job.status == "finished"
    assert job.result.shape is not None
    table = at.dataframe[0].value
    assert {"mdot", "F_vacuum", "Isp_vacuum", "M_exit"} <= set(table["Quantity"])
    assert at.radio(key="contour_view").options == ["Shape view"]


def test_inputs_are_grouped_under_headings_from_schema():
    at = _nozzle_app()
    headings = [m.value for m in at.markdown]
    for group in ("**Geometry**", "**Operating conditions**", "**Gas**", "**Mesh**", "**Solver**"):
        assert group in headings, group
    assert any("AeroFlowSim" in c.value for c in at.sidebar.caption)


def test_bad_value_shows_message_under_its_box():
    at = _nozzle_app()
    at.selectbox(key="quasi1d_nozzle:geometry_source").set_value("Custom profile (CSV)").run()
    at.text_input(key="quasi1d_nozzle:profile_csv").set_value("   ").run()   # empty file path
    assert not at.exception, at.exception
    assert any("please give a file" in e.value for e in at.error)


def test_results_tab_shows_validity_checks_box():
    at = _app()
    at.button(key="run").click().run()
    at.session_state["job"].wait(timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert "**Validity checks**" in [m.value for m in at.markdown]
    assert any("Convergence" in s.value and "orders of magnitude" in s.value for s in at.success)


def test_dropdowns_are_pick_only_without_a_text_cursor():
    """Every dropdown is pick-from-list only (filter_mode=None): no blinking text cursor, no typing."""
    from streamlit.proto.Selectbox_pb2 import Selectbox
    no_typing = Selectbox.DESCRIPTOR.fields_by_name["filter_mode"].enum_type.values_by_name["FILTER_MODE_NONE"].number
    at = _app()
    at.button(key="run").click().run()          # demo case: a few seconds
    at.session_state["job"].wait(timeout=60)
    at.run()                                    # Results tab: field and colour-map dropdowns
    boxes = list(at.selectbox)
    labels = {box.label for box in boxes}
    assert {"Case", "Saved settings", "Field", "Colour map"} <= labels
    for box in boxes:
        assert box.proto.filter_mode == no_typing, box.label
    at = _nozzle_app()                          # a "choice" input from schema.toml
    choice = at.selectbox(key="quasi1d_nozzle:geometry_source")
    assert choice.proto.filter_mode == no_typing


def test_nozzle_axi_mesh_tab_updates_with_presets_and_inflation():
    at = _app()
    at.sidebar.selectbox[0].set_value("nozzle_axi").run()
    assert "Prompt 7" in " ".join(i.value for i in at.info)          # Run tab: no solver yet
    assert not [b for b in at.button if b.key == "run"]
    at.button(key="generate_mesh").click().run()
    assert not at.exception, at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Cells"] == "8,000" and metrics["Faces"] == "16,240"
    assert "Total inflation thickness [m]" not in metrics
    # Results tab: the mesh quality checks, all fine for the default mesh.
    assert any("Cell volumes" in s.value for s in at.success)
    # Switching the preset and turning inflation on update the mesh without pressing the button again.
    at.selectbox(key="nozzle_axi:mesh_preset").set_value("Coarse").run()
    assert {m.label: m.value for m in at.metric}["Cells"] == "2,000"
    at.checkbox(key="nozzle_axi:inflation").check().run()
    assert not at.exception, at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Total inflation thickness [m]"] == "2.596e-05"
    assert float(metrics["Smallest cell [µm]"]) < 1.0
    assert any("Inflation layers" in s.value for s in at.success)
    at.selectbox(key="mesh_color_by").set_value("Non-orthogonality").run()
    assert not at.exception, at.exception


def _external_app():
    at = _app()
    at.sidebar.selectbox[0].set_value("external_2d").run()
    assert not at.exception, at.exception
    return at


def test_external_case_shows_shape_preview_and_switches_shape_inputs():
    at = _external_app()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Reference length [m]"] == "1" and metrics["Body type"] == "planar"
    assert at.selectbox(key="external_2d:shape").value == "Diamond airfoil"
    assert "Thickness ratio t/c [-]" in [b.label for b in at.number_input]
    at.selectbox(key="external_2d:shape").set_value("Conical nose cone").run()
    assert not at.exception, at.exception
    labels = [b.label for b in at.number_input]
    assert "Cone half-angle [deg]" in labels and "Thickness ratio t/c [-]" not in labels
    assert "Afterbody length [m]" not in labels                       # nested show_if: flat base
    assert {m.label: m.value for m in at.metric}["Body type"] == "axisymmetric"


def test_external_mesh_tab_opens_on_the_body_and_rebuilds_small_meshes():
    pytest.importorskip("gmsh")
    at = _external_app()
    at.button(key="generate_mesh").click().run()
    assert not at.exception, at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert int(metrics["Cells"].replace(",", "")) > 5000 and "Smallest angle [deg]" in metrics
    at.toggle(key="mesh_full_domain").set_value(True).run()            # the "full domain" switch
    assert not at.exception, at.exception
    at.checkbox(key="external_2d:half_domain").check().run()           # small mesh: rebuilt automatically
    cells = int({m.label: m.value for m in at.metric}["Cells"].replace(",", ""))
    assert cells < int(metrics["Cells"].replace(",", ""))
    at.number_input(key="external_2d:surface_size").set_value(0.0001).run()   # about 120,000 cells: not rebuilt
    assert any("not rebuilt automatically" in i.value for i in at.info)
    assert int({m.label: m.value for m in at.metric}["Cells"].replace(",", "")) == cells


def test_nozzle_axi_triangle_mesh_type():
    pytest.importorskip("gmsh")
    at = _app()
    at.sidebar.selectbox[0].set_value("nozzle_axi").run()
    at.selectbox(key="nozzle_axi:mesh_type").set_value("Triangles (Gmsh)").run()
    assert not at.exception, at.exception
    assert "Estimated cells" in {m.label for m in at.metric}
    at.button(key="generate_mesh").click().run()
    assert not at.exception, at.exception
    assert "wall (wall" in " ".join(c.value for c in at.caption)


def test_without_gmsh_the_gui_says_how_to_install_it(monkeypatch):
    import aeroflowsim.gui.streamlit_panel as panel
    import aeroflowsim.parameters as parameters
    missing = lambda name: name != "gmsh" and parameters.importlib.util.find_spec(name) is not None
    monkeypatch.setattr(parameters, "module_available", missing)     # as if Gmsh were not installed
    monkeypatch.setattr(panel, "module_available", missing)
    at = _app()
    at.sidebar.selectbox[0].set_value("external_2d").run()
    assert not at.exception, at.exception
    assert any('pip install -e ".[mesh]"' in w.value for w in at.warning)
    assert at.button(key="generate_mesh").disabled
    at.sidebar.selectbox[0].set_value("nozzle_axi").run()
    assert any("needs gmsh" in c.value for c in at.caption)           # the dropdown option is marked
    at.selectbox(key="nozzle_axi:mesh_type").set_value("Triangles (Gmsh)").run()
    assert any('pip install -e ".[mesh]"' in e.value for e in at.error)
    assert not any("Geometry problem" in e.value for e in at.error)

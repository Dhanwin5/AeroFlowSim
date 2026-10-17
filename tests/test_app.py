# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Smoke tests of the Streamlit GUI, using Streamlit's built-in headless tester (no browser).

AppTest runs app.py like a real user session: we can read widgets and press buttons.
"""

from pathlib import Path

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

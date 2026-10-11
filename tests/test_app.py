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

"""Streamlit GUI for AeroFlowSim: Setup / Mesh / Run / Results.

Start with:   .venv\\Scripts\\python.exe -m streamlit run app.py

How Streamlit works (in plain words): this whole file is re-run from top to bottom every time
the user clicks or types something. Values that must survive between re-runs (the mesh, the
running job, input values) are kept in st.session_state, a dictionary that Streamlit keeps alive.

This file only draws the screen. All real work is done by the case (through the contract in
aeroflowsim/case_template.py) and by helper modules in aeroflowsim/ that know nothing about Streamlit.
"""

import io
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from aeroflowsim.case_template import get_geometry
from aeroflowsim.discovery import find_cases
from aeroflowsim.geometry import profile_summary
from aeroflowsim.job import RunJob
from aeroflowsim.mesh import Mesh1D, Mesh2D
from aeroflowsim.parameters import defaults, is_shown, validate
from aeroflowsim.plots import field_figure, mesh_figure, profile_figure, residual_figure
from aeroflowsim.runner import fields_csv_text, max_errors, plot_fields
from aeroflowsim.settings import list_settings, load_settings, save_settings, settings_dir
from aeroflowsim.visualise import COLORMAPS, contour_2d, figure_png, shape_view, xt_diagram

PROJECT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PROJECT_DIR / "assets"     # logo images
UPLOADS_DIR = PROJECT_DIR / "uploads"   # files uploaded in the Setup tab (not committed to git)

st.set_page_config(page_title="AeroFlowSim", page_icon=str(ASSETS_DIR / "icon.png"), layout="wide")
state = st.session_state  # short name


# ---------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------

def widget_key(case_name, param_name):
    """Session-state key of one input box, e.g. 'demo_heat1d:L'."""
    return f"{case_name}:{param_name}"


def float_step(p):
    """Step for the +/- buttons of a float input: about 1/10 of the default's order of magnitude."""
    size = abs(p.default) if p.default != 0 else (p.max - p.min) / 10.0
    if size <= 0.0:
        return 1.0
    return 10.0 ** (math.floor(math.log10(size)) - 1)


def current_values(case_name, param_list):
    """The values currently typed in the Setup tab: {name: value}."""
    return {p.name: state[widget_key(case_name, p.name)] for p in param_list}


def set_inputs(case_name, values):
    """Put values into the Setup input boxes (only allowed inside a button callback)."""
    for name, value in values.items():
        state[widget_key(case_name, name)] = value


def progress_fraction(params, iteration, residual):
    """Rough 0..1 progress: the further of 'iterations used' and 'orders of magnitude converged'."""
    fraction = 0.0
    if params.get("max_iter"):
        fraction = iteration / params["max_iter"]
    tol = params.get("tol")
    if tol and 0.0 < tol < 1.0 and residual > 0.0:
        fraction = max(fraction, math.log10(residual) / math.log10(tol))
    return min(max(fraction, 0.0), 1.0)


# ---------------------------------------------------------------------------------------------
# Sidebar: choose ONE case
# ---------------------------------------------------------------------------------------------

st.sidebar.image(str(ASSETS_DIR / "logo.png"), width="stretch")   # the logo shows the name
cases, problems = find_cases()
for name, problem in problems.items():
    st.sidebar.warning(f"Case '{name}' is broken: {problem}")
if not cases:
    st.error("No cases found in the cases/ folder.")
    st.stop()

case_name = st.sidebar.selectbox("Case", list(cases), format_func=lambda n: cases[n].NAME)
case = cases[case_name]
param_list = case.parameters()
st.sidebar.caption(case.DESCRIPTION)
st.sidebar.caption(f"Folder: `cases/{case_name}/`")

# When the user switches case, forget the mesh and run of the previous case.
if state.get("case_name") != case_name:
    for key in ("mesh", "mesh_params", "mesh_error", "job", "run_params", "run_mesh", "job_shown_done"):
        state.pop(key, None)
    state.case_name = case_name

# First visit of this case: fill the input boxes with the default values.
for name, value in defaults(param_list).items():
    state.setdefault(widget_key(case_name, name), value)

st.title(case.NAME)
setup_tab, mesh_tab, run_tab, results_tab = st.tabs(["Setup", "Mesh", "Run", "Results"])


# ---------------------------------------------------------------------------------------------
# Setup tab: input form built from case.parameters(), plus save / load settings
# ---------------------------------------------------------------------------------------------

def on_reset():
    set_inputs(case_name, defaults(param_list))


def on_load(file_name):
    try:
        set_inputs(case_name, load_settings(case_name, file_name, param_list))
        state.settings_message = ("success", f"Loaded settings '{file_name}'.")
    except Exception as error:
        state.settings_message = ("error", f"Could not load '{file_name}': {error}")


def on_upload(param_name):
    """Save an uploaded file to uploads/<case>/ and put its path into the file input box."""
    uploaded = state.get(f"upload:{case_name}:{param_name}")
    if uploaded is None:
        return
    folder = UPLOADS_DIR / case_name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(uploaded.name).name   # keep only the file name, never a folder part
    path.write_bytes(uploaded.getvalue())
    state[widget_key(case_name, param_name)] = path.relative_to(PROJECT_DIR).as_posix()


def input_widget(p):
    """One input box for parameter p, drawn according to its kind (number, choice or file)."""
    key = widget_key(case_name, p.name)
    if p.kind == "choice":
        st.selectbox(p.label, p.options, key=key, help=p.help)
    elif p.kind == "file":
        st.text_input(f"{p.label} (path)", key=key,
                      help=f"{p.help}  \nA path relative to the project folder, or upload a file below.")
        st.file_uploader(f"Upload {p.label.lower()}", type=["csv"], key=f"upload:{case_name}:{p.name}",
                         on_change=on_upload, args=(p.name,))
    else:
        label = f"{p.label} [{p.unit}]"
        help_text = f"{p.help}  \nAllowed range: {p.min:g} to {p.max:g} {p.unit}."
        if p.is_integer:
            st.number_input(label, min_value=int(p.min), max_value=int(p.max), step=1,
                            key=key, help=help_text)
        else:
            st.number_input(label, min_value=float(p.min), max_value=float(p.max),
                            step=float_step(p), format="%g", key=key, help=help_text)


def geometry_preview(values):
    """Setup tab: the wall profile and its key numbers, or a clear message on what to fix."""
    try:
        profile = get_geometry(case, validate(param_list, values))
    except ValueError as error:
        st.error(f"Geometry problem: {error}")
        return
    if profile is None:
        return
    st.subheader("Geometry preview")
    s = profile_summary(profile)
    cols = st.columns(4)
    cols[0].metric("Throat diameter [mm]", f"{s['d_throat'][0] * 1e3:.4g}")
    cols[1].metric("Exit diameter [mm]", f"{s['d_exit'][0] * 1e3:.4g}")
    cols[2].metric("Area ratio A_exit/A_throat [-]", f"{s['area_ratio'][0]:.4g}")
    cols[3].metric("Length [mm]", f"{s['length'][0] * 1e3:.4g}")
    st.plotly_chart(profile_figure(profile), key="profile_plot")


with setup_tab:
    st.subheader("Inputs")
    values_now = current_values(case_name, param_list)
    shown = [p for p in param_list if is_shown(p, values_now)]   # e.g. hide the CSV path for "parametric"
    columns = st.columns(2)
    for i, p in enumerate(shown):
        with columns[i % 2]:
            input_widget(p)
    st.button("Reset to defaults", on_click=on_reset)
    if hasattr(case, "geometry"):
        geometry_preview(values_now)

    st.subheader("Settings files")
    st.caption(f"Stored as YAML files in `cases/{case_name}/{settings_dir(case_name).name}/`")
    save_col, load_col = st.columns(2)
    with save_col:
        file_name = st.text_input("File name", value="my_settings")
        if st.button("Save settings"):
            try:
                path = save_settings(case_name, file_name, param_list,
                                     current_values(case_name, param_list))
                state.settings_message = ("success", f"Saved to {path.name}.")
            except Exception as error:
                state.settings_message = ("error", f"Could not save: {error}")
    with load_col:
        saved = list_settings(case_name)
        chosen = st.selectbox("Saved settings", saved, index=None,
                              placeholder="none saved yet" if not saved else "choose a file")
        st.button("Load settings", on_click=on_load, args=(chosen,), disabled=chosen is None)
    if "settings_message" in state:
        kind, text = state.pop("settings_message")
        (st.success if kind == "success" else st.error)(text)


# Check the inputs once; the other tabs need valid values.
try:
    params = validate(param_list, current_values(case_name, param_list))
    params_error = ""
except ValueError as error:
    params, params_error = None, str(error)


def make_mesh():
    """Build the mesh from the current inputs and remember which inputs it was built with.

    Returns True on success. A ValueError (e.g. a bad geometry file) is kept in
    state.mesh_error and shown in the Mesh and Run tabs instead of crashing the app.
    """
    state.pop("mesh_error", None)
    try:
        state.mesh = case.build_mesh(params)
    except ValueError as error:
        state.pop("mesh", None)
        state.mesh_error = str(error)
        return False
    state.mesh_params = dict(params)
    return True


# ---------------------------------------------------------------------------------------------
# Mesh tab
# ---------------------------------------------------------------------------------------------

with mesh_tab:
    if params_error:
        st.error(params_error)
    if st.button("Generate mesh", type="primary", key="generate_mesh", disabled=params is None):
        make_mesh()
    if "mesh_error" in state:
        st.error(f"Could not build the mesh: {state.mesh_error}")
    mesh = state.get("mesh")
    if mesh is None:
        st.info("Press **Generate mesh** to build the mesh from the Setup inputs.")
    else:
        if state.mesh_params != params:
            st.warning("The Setup inputs changed since this mesh was made. Press **Generate mesh** again.")
        col1, col2, col3 = st.columns(3)
        col1.metric("Nodes", mesh.n_nodes)
        col2.metric("Cells", mesh.n_cells)
        if hasattr(mesh, "dx"):
            col3.metric("Spacing min / max [m]", f"{mesh.dx.min():.4g} / {mesh.dx.max():.4g}")
        st.plotly_chart(mesh_figure(mesh), key="mesh_plot")


# ---------------------------------------------------------------------------------------------
# Run tab: Run / Stop, live progress and residual plot
# ---------------------------------------------------------------------------------------------

def on_run():
    """Start a new run in the background (the mesh is (re)built first if needed)."""
    if state.get("mesh") is None or state.get("mesh_params") != params:
        if not make_mesh():
            return   # the error is shown in the Run tab
    job = RunJob()
    job.start(case, params, state.mesh)
    state.job, state.run_params, state.run_mesh = job, dict(params), state.mesh
    state.job_shown_done = False


def on_stop():
    state.job.stop()


def live_view():
    """Progress bar, residual plot and status. While running, Streamlit re-draws this every 0.3 s."""
    job = state.get("job")
    if job is None:
        st.info("Press **Run** to start the solver.")
        return
    iterations, residuals = job.snapshot()
    run_params = state.run_params
    if iterations:
        fraction = progress_fraction(run_params, iterations[-1], residuals[-1])
        st.progress(fraction, text=f"Iteration {iterations[-1]:,}   |   residual {residuals[-1]:.3e}"
                                   f"   |   {job.current_elapsed_s():.1f} s")
        st.plotly_chart(residual_figure(iterations, residuals, run_params.get("tol")),
                        key="residual_plot")
    if job.status == "running":
        st.caption("Running…")
    elif job.status == "finished":
        if job.result.converged:
            st.success(f"Converged after {job.result.iterations:,} iterations "
                       f"({job.elapsed_s:.2f} s). See the **Results** tab.")
        else:
            st.warning(f"Not converged: stopped at the iteration limit ({job.result.iterations:,}). "
                       "Results are available but not fully converged.")
    elif job.status == "stopped":
        st.warning(f"Stopped by the user after {len(iterations):,} iterations. "
                   "(A stopped run has no results to show.)")
    elif job.status == "failed":
        st.error(f"The solver failed: {job.error}")
    # When the run has just ended, re-draw the whole page once so the buttons and the
    # Results tab update (inside this fragment only this function is re-drawn).
    if not job.running and not state.get("job_shown_done", True):
        state.job_shown_done = True
        st.rerun()


with run_tab:
    if params_error:
        st.error(params_error)
    if "mesh_error" in state:
        st.error(f"Could not build the mesh: {state.mesh_error}")
    job = state.get("job")
    running = job is not None and job.running
    col_run, col_stop, _ = st.columns([1, 1, 6])
    col_run.button("Run", type="primary", on_click=on_run, disabled=running or params is None,
                   key="run")
    col_stop.button("Stop", on_click=on_stop, disabled=not running, key="stop")
    # A "fragment" is a part of the page that can refresh on its own on a timer.
    st.fragment(live_view, run_every=0.3 if running else None)()


# ---------------------------------------------------------------------------------------------
# Results tab
# ---------------------------------------------------------------------------------------------

def available_views(result, mesh):
    """The contour-style views this result supports, in the order shown."""
    views = []
    if isinstance(mesh, Mesh1D):
        views.append("Shape view")      # works for every 1D result (constant height if no shape)
    if result.snapshots is not None:
        views.append("x-t diagram")     # unsteady cases that stored snapshots
    if isinstance(mesh, Mesh2D):
        views.append("2D contour")      # future 2D cases
    return views


def contours_section(result, reference_lines, mesh):
    """Colour pictures of a field: view, field, colour map and range chosen by the user."""
    views = available_views(result, mesh)
    if not views:
        return
    st.subheader("Contours")
    view = st.radio("View", views, horizontal=True, key="contour_view")
    # The x-t diagram shows the stored snapshots; the other views show the final fields.
    fields = result.snapshots.fields if view == "x-t diagram" else result.fields
    col_field, col_cmap = st.columns(2)
    key = col_field.selectbox("Field", list(fields), key="contour_field",
                              format_func=lambda k: f"{fields[k].label} [{fields[k].unit}]")
    cmap = col_cmap.selectbox("Colour map", COLORMAPS, key="contour_cmap")
    f = fields[key]

    vmin = vmax = None   # None = automatic (data minimum / maximum)
    if not st.checkbox("Automatic colour range", value=True, key="contour_auto"):
        col_min, col_max = st.columns(2)
        data_min, data_max = float(f.values.min()), float(f.values.max())
        # The key includes the field, so each field starts from its own data range.
        vmin = col_min.number_input(f"Minimum [{f.unit}]", value=data_min, format="%g",
                                    key=f"contour_min:{key}")
        vmax = col_max.number_input(f"Maximum [{f.unit}]", value=data_max, format="%g",
                                    key=f"contour_max:{key}")
        if vmax <= vmin:
            st.warning("Maximum must be larger than minimum; using the automatic range.")
            vmin = vmax = None

    if view == "Shape view":
        x = mesh.positions(len(f.values))                              # [m]
        r = result.shape.radius_at(x) if result.shape is not None else None
        fig = shape_view(x, r, f.values, f.label, f.unit, cmap=cmap, vmin=vmin, vmax=vmax,
                         note=result.shape_note)
    elif view == "x-t diagram":
        lines = []
        if reference_lines and st.checkbox("Show exact wave paths", value=True, key="contour_lines"):
            lines = reference_lines
        x = mesh.positions(f.values.shape[1])                          # [m]
        fig = xt_diagram(x, result.snapshots.times, f.values, f.label, f.unit,
                         cmap=cmap, vmin=vmin, vmax=vmax, lines=lines)
    else:
        col_a, col_b = st.columns(2)
        show_mesh = col_a.checkbox("Show mesh lines", key="contour_mesh")
        mirror = col_b.checkbox("Mirror about the axis", key="contour_mirror")
        fig = contour_2d(mesh.x, mesh.y, f.values, f.label, f.unit, cmap=cmap,
                         vmin=vmin, vmax=vmax, show_mesh=show_mesh, mirror=mirror)

    st.pyplot(fig)
    st.download_button("Download contour PNG", figure_png(fig), mime="image/png",
                       file_name=f"{case_name}_{view.split()[0].lower()}_{key}.png",
                       on_click="ignore", key="contour_png")


with results_tab:
    job = state.get("job")
    if job is None or job.status != "finished":
        st.info("No results yet. Run the case in the **Run** tab.")
    else:
        result, reference, mesh = job.result, job.reference, state.run_mesh
        if state.run_params != params:
            st.caption("Note: these results were computed with earlier Setup inputs.")

        keys = list(result.fields)
        key = st.selectbox("Field", keys, format_func=lambda k: f"{result.fields[k].label} "
                                                             f"[{result.fields[k].unit}]")
        ref_field = reference.get(key) if reference else None
        st.plotly_chart(field_figure(mesh, result.fields[key], ref_field), key="field_plot")
        if ref_field is None:
            st.caption("No reference solution available for this field.")

        # Table of key numbers: solver status, the case's own key numbers, and errors vs reference.
        rows = [
            {"Quantity": "converged", "Value": "yes" if result.converged else "no", "Unit": ""},
            {"Quantity": "iterations", "Value": f"{result.iterations:,}", "Unit": "-"},
            {"Quantity": "final residual", "Value": f"{result.residuals[-1]:.3e}", "Unit": "-"},
            {"Quantity": "run time", "Value": f"{job.elapsed_s:.3g}", "Unit": "s"},
        ]
        rows += [{"Quantity": name, "Value": f"{value:.6g}", "Unit": unit}
                 for name, (value, unit) in result.key_numbers.items()]
        rows += [{"Quantity": f"max |{name} − {name}_exact|", "Value": f"{err:.3e}", "Unit": unit}
                 for name, (err, unit) in max_errors(result, reference).items()]
        st.subheader("Key numbers")
        st.dataframe(pd.DataFrame(rows), hide_index=True)

        # Downloads: CSV with every field (+ reference); PNG of the selected field (matplotlib).
        png = io.BytesIO()
        plot_fields(png, case, mesh, result, reference, keys=[key])
        col_csv, col_png, _ = st.columns([1, 1, 4])
        col_csv.download_button("Download CSV", fields_csv_text(mesh, result, reference),
                                file_name=f"{case_name}_fields.csv", mime="text/csv",
                                on_click="ignore")
        col_png.download_button("Download PNG", png.getvalue(),
                                file_name=f"{case_name}_{key}.png", mime="image/png",
                                on_click="ignore")

        contours_section(result, job.reference_lines, mesh)

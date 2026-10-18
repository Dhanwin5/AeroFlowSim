# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Streamlit GUI for AeroFlowSim: Setup / Mesh / Run / Results.

Start with:   .venv\\Scripts\\python.exe -m streamlit run app.py

How Streamlit works (in plain words): this whole file is re-run from top to bottom every time
the user clicks or types something. Values that must survive between re-runs (the mesh, the
running job, input values) are kept in st.session_state, a dictionary that Streamlit keeps alive.

This file only draws the screen. All real work is done by the case (through the contract in
aeroflowsim/case.py) and by helper modules in aeroflowsim/ that know nothing about Streamlit.
The Setup-tab input panel is built automatically from each case's schema.toml by
aeroflowsim/gui/panel.py, so adding a case needs no change here.
"""

import io
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from aeroflowsim import __version__
from aeroflowsim.case import get_derived, get_geometry
from aeroflowsim.checks import run_mesh_checks
from aeroflowsim.discovery import find_cases
from aeroflowsim.geometry import profile_summary
from aeroflowsim.gui.panel import current_values, init_inputs, input_panel, set_inputs
from aeroflowsim.job import RunJob
from aeroflowsim.mesh import Mesh, Mesh1D, Mesh2D
from aeroflowsim.mesh_quality import quality_summary
from aeroflowsim.parameters import defaults, validate
from aeroflowsim.plots import (QUALITY_COLORINGS, face_mesh_figure, field_figure, mesh_figure, profile_figure,
                               residual_figure)
from aeroflowsim.vtk import save_mesh_files
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
st.sidebar.caption(f"AeroFlowSim {__version__} · pre-release, under development")
cases, problems = find_cases()
for name, problem in problems.items():
    st.sidebar.warning(f"Case '{name}' is broken: {problem}")
if not cases:
    st.error("No cases found in the cases/ folder.")
    st.stop()

case_name = st.sidebar.selectbox("Case", list(cases), format_func=lambda n: cases[n].title,
                                 filter_mode=None)   # pick from the list only, no typing
case = cases[case_name]
param_list = case.parameters()
st.sidebar.caption(case.description)
st.sidebar.caption(f"Folder: `cases/{case_name}/`")

# When the user switches case, forget the mesh and run of the previous case.
if state.get("case_name") != case_name:
    for key in ("mesh", "mesh_params", "mesh_error", "mesh_files", "job", "run_params", "run_mesh",
                "job_shown_done"):
        state.pop(key, None)
    state.case_name = case_name

# First visit of this case: fill the input boxes with the default values.
init_inputs(case)

st.title(case.title)
setup_tab, mesh_tab, run_tab, results_tab = st.tabs(["Setup", "Mesh", "Run", "Results"])


# ---------------------------------------------------------------------------------------------
# Setup tab: input panel built from schema.toml, plus save / load settings
# ---------------------------------------------------------------------------------------------

def on_reset():
    set_inputs(case, defaults(param_list))


def on_load(file_name):
    try:
        set_inputs(case, load_settings(case_name, file_name, param_list))
        state.settings_message = ("success", f"Loaded settings '{file_name}'.")
    except Exception as error:
        state.settings_message = ("error", f"Could not load '{file_name}': {error}")


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


def derived_values(values):
    """Setup tab: read-only numbers that follow from the inputs (the case's derived() function)."""
    try:
        numbers = get_derived(case, validate(param_list, values))
    except ValueError:
        return   # the input panel already shows what is wrong
    if not numbers:
        return
    cols = st.columns(len(numbers))
    for col, (label, (value, unit)) in zip(cols, numbers.items()):
        text = value if isinstance(value, str) else f"{value:.4g}"
        col.metric(f"{label} [{unit}]" if unit else label, text)
    st.caption("Calculated from the inputs above (read-only).")


with setup_tab:
    st.subheader("Inputs")
    input_panel(case, UPLOADS_DIR, PROJECT_DIR)   # built from cases/<case>/schema.toml
    derived_values(current_values(case))
    st.button("Reset to defaults", on_click=on_reset)
    if hasattr(case, "geometry"):
        geometry_preview(current_values(case))

    st.subheader("Settings files")
    st.caption(f"Stored as YAML files in `cases/{case_name}/{settings_dir(case_name).name}/`")
    save_col, load_col = st.columns(2)
    with save_col:
        file_name = st.text_input("File name", value="my_settings")
        if st.button("Save settings"):
            try:
                path = save_settings(case_name, file_name, param_list,
                                     current_values(case))
                state.settings_message = ("success", f"Saved to {path.name}.")
            except Exception as error:
                state.settings_message = ("error", f"Could not save: {error}")
    with load_col:
        saved = list_settings(case_name)
        chosen = st.selectbox("Saved settings", saved, index=None, filter_mode=None,
                              placeholder="none saved yet" if not saved else "choose a file")
        st.button("Load settings", on_click=on_load, args=(chosen,), disabled=chosen is None)
    if "settings_message" in state:
        kind, text = state.pop("settings_message")
        (st.success if kind == "success" else st.error)(text)


# Check the inputs once; the other tabs need valid values.
try:
    params = validate(param_list, current_values(case))
    params_error = ""
except ValueError as error:
    params, params_error = None, str(error)


def make_mesh():
    """Build the mesh from the current inputs and remember which inputs it was built with.

    Returns True on success. A ValueError (e.g. a bad geometry file) is kept in
    state.mesh_error and shown in the Mesh and Run tabs instead of crashing the app.
    """
    state.pop("mesh_error", None)
    state.pop("mesh_files", None)
    try:
        state.mesh = case.build_mesh(params)
    except ValueError as error:
        state.pop("mesh", None)
        state.mesh_error = str(error)
        return False
    state.mesh_params = dict(params)
    if isinstance(state.mesh, Mesh):   # face-based mesh: save mesh.npz + mesh.vtu in cases/<case>/mesh/
        state.mesh_files = save_mesh_files(state.mesh, case.folder)
    return True


def face_mesh_view(mesh):
    """Mesh tab for a face-based mesh: summary box, zoomable picture, quality colours, .vtu download."""
    q = quality_summary(mesh)
    with st.container(border=True):
        st.markdown("**Mesh summary**")
        cols = st.columns(4)
        cols[0].metric("Cells", f"{mesh.n_cells:,}")
        cols[1].metric("Faces", f"{mesh.n_faces:,}")
        cols[2].metric("Nodes", f"{mesh.n_nodes:,}")
        cols[3].metric("Memory (approx.) [MB]", f"{mesh.memory_bytes() / 1e6:.3g}")
        cols = st.columns(4)
        cols[0].metric("Smallest cell [µm]", f"{q['min_cell_size'] * 1e6:.4g}")
        cols[1].metric("Max aspect ratio [-]", f"{q['max_aspect_ratio']:.3g}")
        cols[2].metric("Max non-orthogonality [deg]", f"{q['max_non_orthogonality']:.3g}")
        cols[3].metric("Max neighbour volume ratio [-]", f"{q['max_volume_ratio']:.3g}")
        st.caption("Patches: " + ", ".join(f"{p.name} ({p.type}, {p.count} faces)" for p in mesh.patches)
                   + ". Full quality checks: **Results** tab.")
    color_by = st.selectbox("Colour cells by", ["Nothing"] + list(QUALITY_COLORINGS), key="mesh_color_by",
                            filter_mode=None)
    st.plotly_chart(face_mesh_figure(mesh, None if color_by == "Nothing" else color_by), key="mesh_plot",
                    config={"scrollZoom": True})
    st.caption("Zoom: drag a box or use the mouse wheel; double-click to see the whole mesh. "
               "Click a legend entry to hide or show it.")
    files = state.get("mesh_files")
    if files:
        npz, vtu = files
        st.download_button("Download .vtu (ParaView)", vtu.read_bytes(), file_name=f"{case_name}_mesh.vtu",
                           mime="application/xml", on_click="ignore", key="download_vtu")
        st.caption(f"Also saved in `{vtu.relative_to(PROJECT_DIR).as_posix()}` and "
                   f"`{npz.relative_to(PROJECT_DIR).as_posix()}`.")


# ---------------------------------------------------------------------------------------------
# Mesh tab
# ---------------------------------------------------------------------------------------------

with mesh_tab:
    if params_error:
        st.error(params_error)
    if st.button("Generate mesh", type="primary", key="generate_mesh", disabled=params is None):
        make_mesh()
    elif state.get("mesh") is not None and params is not None and state.mesh_params != params:
        make_mesh()   # the Setup inputs changed since the last mesh: update it automatically
    if "mesh_error" in state:
        st.error(f"Could not build the mesh: {state.mesh_error}")
    mesh = state.get("mesh")
    if mesh is None:
        st.info("Press **Generate mesh** to build the mesh from the Setup inputs.")
    elif state.mesh_params != params:
        st.warning("The Setup inputs are not valid; this mesh was made with earlier inputs.")
    if isinstance(mesh, Mesh):
        face_mesh_view(mesh)
    elif mesh is not None:
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


def run_tab_view():
    """Run / Stop buttons and the live view (or the case's message if it has no solver yet)."""
    if params_error:
        st.error(params_error)
    if "mesh_error" in state:
        st.error(f"Could not build the mesh: {state.mesh_error}")
    if not case.has_solver:
        st.info(case.solver_message)
        return
    job = state.get("job")
    running = job is not None and job.running
    col_run, col_stop, _ = st.columns([1, 1, 6])
    col_run.button("Run", type="primary", on_click=on_run, disabled=running or params is None,
                   key="run")
    col_stop.button("Stop", on_click=on_stop, disabled=not running, key="stop")
    # A "fragment" is a part of the page that can refresh on its own on a timer.
    st.fragment(live_view, run_every=0.3 if running else None)()


with run_tab:
    run_tab_view()


# ---------------------------------------------------------------------------------------------
# Results tab
# ---------------------------------------------------------------------------------------------

CHECK_STYLE = {"info": ("✅", st.success), "warning": ("⚠️", st.warning), "error": ("❌", st.error)}


def validity_box(checks):
    """The "Validity checks" box: one coloured line per check (see aeroflowsim/checks.py)."""
    with st.container(border=True):
        st.markdown("**Validity checks**")
        if not checks:
            st.caption("No checks apply to this case.")
        for check in checks:
            icon, show = CHECK_STYLE[check.level]
            show(f"**{check.name}:** {check.message}", icon=icon)   # the message includes the value


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
    key = col_field.selectbox("Field", list(fields), key="contour_field", filter_mode=None,
                              format_func=lambda k: f"{fields[k].label} [{fields[k].unit}]")
    cmap = col_cmap.selectbox("Colour map", COLORMAPS, key="contour_cmap", filter_mode=None)
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
    if not case.has_solver:   # mesh-only case: the results are the mesh quality checks
        if state.get("mesh") is None:
            st.info("No mesh yet. Press **Generate mesh** in the **Mesh** tab.")
        else:
            st.caption("This case has no solver yet: these are the mesh quality checks.")
            validity_box(run_mesh_checks(case, state.mesh_params, state.mesh))
    elif job is None or job.status != "finished":
        st.info("No results yet. Run the case in the **Run** tab.")
    else:
        result, reference, mesh = job.result, job.reference, state.run_mesh
        if state.run_params != params:
            st.caption("Note: these results were computed with earlier Setup inputs.")
        validity_box(job.checks)

        keys = list(result.fields)
        key = st.selectbox("Field", keys, filter_mode=None, format_func=lambda k: f"{result.fields[k].label} "
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

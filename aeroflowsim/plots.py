# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Interactive Plotly figures used by the GUI (mesh, residual history, solution fields).

These functions only build figures; they do not show them. The GUI (app.py) displays them,
and tests can check them without a browser. Nothing here imports the GUI.
"""

import numpy as np
import plotly.graph_objects as go

from aeroflowsim import mesh_quality
from aeroflowsim.mesh import Mesh, Mesh1D, Mesh2D
from aeroflowsim.mesh_quality import QUALITY_COLORINGS  # noqa: F401  (used by app.py through this module)
from aeroflowsim.runner import COLOR_MUTED, COLOR_NUMERICAL, COLOR_REFERENCE
from aeroflowsim.visualise import length_unit

MAX_PLOT_POINTS = 5000  # residual curves longer than this are thinned so the browser stays fast


def _layout(fig, title, x_title, y_title, height=380):
    """Shared look: clean white background, light grid, legend on top, hover across traces."""
    fig.update_layout(
        title=title, height=height, template="plotly_white", hovermode="x unified",
        margin=dict(l=60, r=20, t=60, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0),
    )
    fig.update_xaxes(title=x_title, gridcolor="rgba(137,135,129,0.25)", zeroline=False)
    fig.update_yaxes(title=y_title, gridcolor="rgba(137,135,129,0.25)", zeroline=False)
    return fig


def mesh_figure(mesh):
    """Picture of the mesh: 1D = nodes as dots along x; 2D = grid lines."""
    fig = go.Figure()
    if isinstance(mesh, Mesh1D):
        x = mesh.x  # [m]
        # Short vertical ticks at every node make the cell boundaries easy to see.
        tick_x = np.repeat(x, 3)
        tick_y = np.tile([-0.3, 0.3, np.nan], len(x))
        fig.add_trace(go.Scatter(x=tick_x, y=tick_y, mode="lines", hoverinfo="skip",
                                 line=dict(color=COLOR_MUTED, width=1), showlegend=False))
        fig.add_trace(go.Scatter(x=x, y=np.zeros_like(x), mode="markers", name="nodes",
                                 marker=dict(color=COLOR_NUMERICAL, size=8),
                                 customdata=np.arange(len(x)),
                                 hovertemplate="node %{customdata}<br>x = %{x:.4g} m<extra></extra>"))
        fig.update_yaxes(visible=False, range=[-1, 1])
        title = f"1D mesh: {mesh.n_nodes} nodes, {mesh.n_cells} cells"
        _layout(fig, title, "x [m]", "", height=250)
        fig.update_layout(hovermode="closest")
        return fig
    if isinstance(mesh, Mesh2D):
        # All grid lines as one trace (lines separated by NaN gaps) - fast even for big meshes.
        xs, ys = [], []
        for i in range(mesh.x.shape[0]):     # lines of constant i
            xs += list(mesh.x[i, :]) + [np.nan]
            ys += list(mesh.y[i, :]) + [np.nan]
        for j in range(mesh.x.shape[1]):     # lines of constant j
            xs += list(mesh.x[:, j]) + [np.nan]
            ys += list(mesh.y[:, j]) + [np.nan]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", hoverinfo="skip", showlegend=False,
                                 line=dict(color=COLOR_NUMERICAL, width=1)))
        fig.update_yaxes(scaleanchor="x", scaleratio=1)  # true aspect ratio
        title = f"2D mesh: {mesh.n_nodes} nodes, {mesh.n_cells} cells"
        _layout(fig, title, "x [m]", "y [m]", height=450)
        fig.update_layout(hovermode="closest")
        return fig
    if isinstance(mesh, Mesh):
        return face_mesh_figure(mesh)
    raise TypeError(f"Cannot plot a mesh of type {type(mesh).__name__}.")


# Colours of the boundary patch types in the mesh picture.
PATCH_COLORS = {"inlet": "#1f77b4", "outlet": "#ff7f0e", "wall": "#222222", "axis": "#2ca02c",
                "farfield": "#9467bd", "symmetry": "#17becf"}

# Quality metrics the cells can be coloured by: label -> (function of the mesh, unit).
def _face_lines(mesh, faces, scale):
    """x, y of the given 2D faces (edges) as one polyline with NaN gaps (fast to draw)."""
    ends = mesh.nodes[mesh.face_nodes[faces, :2]] * scale        # (n, 2, 3)
    gap = np.full((len(faces), 1), np.nan)
    x = np.hstack([ends[:, :, 0], gap]).ravel()
    y = np.hstack([ends[:, :, 1], gap]).ravel()
    return x, y


def face_mesh_figure(mesh, color_by=None, full_domain=True):
    """Zoomable picture of a 2D face-based Mesh, in mm (small meshes) or m.

    Interior faces are thin grey lines; every boundary patch has its own colour (and legend
    entry). color_by = one of QUALITY_COLORINGS: every cell gets a coloured dot at its centre,
    with the value shown when the mouse is over it. full_domain=False: for a body in a free stream
    (mesh.info has "body_bbox"), the view opens zoomed on the body. For axisymmetric and half
    domains the view never shows the empty region below the axis / symmetry line (y < 0).
    """
    if mesh.dim != 2:
        raise ValueError("Only 2D meshes can be drawn here; open 3D meshes in ParaView (.vtu).")
    unit, scale = length_unit(float(np.ptp(mesh.nodes[:, :2], axis=0).max()))   # m -> unit
    Scatter = go.Scattergl if mesh.n_faces > 2000 else go.Scatter  # WebGL for big meshes
    fig = go.Figure()
    x, y = _face_lines(mesh, np.arange(mesh.n_interior_faces), scale)
    fig.add_trace(Scatter(x=x, y=y, mode="lines", name="cells", hoverinfo="skip",
                          line=dict(color="rgba(90,90,90,0.55)", width=0.7)))
    for p in mesh.patches:
        x, y = _face_lines(mesh, p.faces, scale)
        fig.add_trace(Scatter(x=x, y=y, mode="lines", name=f"{p.name} ({p.type})", hoverinfo="skip",
                              line=dict(color=PATCH_COLORS.get(p.type, COLOR_NUMERICAL), width=3)))
    if color_by is not None:
        function, q_unit = QUALITY_COLORINGS[color_by]
        values = function(mesh)
        c = mesh.cell_centres * scale
        fig.add_trace(Scatter(
            x=c[:, 0], y=c[:, 1], mode="markers", name=color_by, showlegend=False,
            marker=dict(size=5, color=values, colorscale="Viridis",
                        colorbar=dict(title=f"{color_by} [{q_unit}]", thickness=14)),
            customdata=np.column_stack([np.arange(mesh.n_cells), values]),
            hovertemplate="cell %{customdata[0]}<br>" + color_by + " = %{customdata[1]:.4g} " + q_unit
                          + f"<br>x = %{{x:.4f}} {unit}, y = %{{y:.4f}} {unit}<extra></extra>"))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)               # true shape
    upper_only = mesh.axisymmetric or mesh.info.get("half_domain")
    if upper_only:                                                # nothing to see below the axis
        fig.update_yaxes(minallowed=0.0)
    bbox = mesh.info.get("body_bbox")
    if bbox is not None and not full_domain:                      # open zoomed on the body
        x0, y0, x1, y1 = (v * scale for v in bbox)
        margin = 0.6 * max(x1 - x0, y1 - y0)
        fig.update_xaxes(range=[x0 - margin, x1 + margin])
        fig.update_yaxes(range=[0.0 if upper_only else y0 - margin, y1 + margin])
    y_title = f"r [{unit}]" if mesh.axisymmetric else f"y [{unit}]"
    _layout(fig, f"2D mesh: {mesh.n_cells:,} cells, {mesh.n_faces:,} faces", f"x [{unit}]", y_title, height=520)
    fig.update_layout(hovermode="closest", dragmode="zoom", margin=dict(l=60, r=20, t=50, b=90),
                      legend=dict(orientation="h", yanchor="top", y=-0.14, xanchor="left", x=0.0))
    return fig


def residual_figure(iterations, residuals, tol=None):
    """Convergence history on a logarithmic y-axis (optionally with the tolerance line)."""
    iterations = np.asarray(iterations)
    residuals = np.asarray(residuals, dtype=float)
    if len(iterations) > MAX_PLOT_POINTS:
        # Keep evenly spaced points plus the last one, so the curve still ends at the latest value.
        keep = np.unique(np.r_[np.linspace(0, len(iterations) - 1, MAX_PLOT_POINTS).astype(int),
                               len(iterations) - 1])
        iterations, residuals = iterations[keep], residuals[keep]
    # A residual of exactly 0 cannot be drawn on a log axis; replace it by a tiny number.
    residuals = np.maximum(residuals, 1e-300)
    fig = go.Figure(go.Scatter(x=iterations, y=residuals, mode="lines", name="residual",
                               line=dict(color=COLOR_NUMERICAL, width=2),
                               hovertemplate="iteration %{x}<br>residual %{y:.3e}<extra></extra>"))
    if tol is not None:
        fig.add_hline(y=tol, line=dict(color=COLOR_MUTED, dash="dot", width=1),
                      annotation_text=f"tolerance {tol:.0e}", annotation_position="bottom right")
    fig.update_yaxes(type="log", exponentformat="power")
    _layout(fig, "Convergence history", "iteration [-]", "normalised residual [-]")
    fig.update_layout(showlegend=False)
    return fig


def field_figure(mesh, field, ref_field=None):
    """One solution field along x: numerical (line + dots) and the reference (dashed), if any."""
    fig = go.Figure()
    x = mesh.positions(len(field.values))  # nodes or cell centres [m]
    fig.add_trace(go.Scatter(x=x, y=field.values, mode="lines+markers", name="numerical",
                             line=dict(color=COLOR_NUMERICAL, width=2), marker=dict(size=8),
                             hovertemplate="%{y:.6g} " + field.unit + "<extra>numerical</extra>"))
    if ref_field is not None:
        fig.add_trace(go.Scatter(x=mesh.positions(len(ref_field.values)), y=ref_field.values, mode="lines", name="reference (exact)",
                                 line=dict(color=COLOR_REFERENCE, width=2, dash="dash"),
                                 hovertemplate="%{y:.6g} " + field.unit + "<extra>reference</extra>"))
    _layout(fig, field.label, "x [m]", f"{field.label} [{field.unit}]", height=450)
    return fig


def profile_figure(profile, n_points=600):
    """Wall profile r(x) of a duct / nozzle, mirrored about the axis, with the throat marked.

    profile: aeroflowsim.geometry.WallProfile. The curve is drawn with the profile's own interpolation
    (so a CSV profile shows the smooth PCHIP curve), and the given points are drawn as dots.
    """
    x = np.linspace(profile.x[0], profile.x[-1], n_points)       # [m]
    r = profile.radius_at(x)                                      # [m]
    x_mm, r_mm = x * 1e3, r * 1e3                                 # plotted in mm (easier to read)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x_mm, y=r_mm, mode="lines", name="wall",
                             line=dict(color=COLOR_NUMERICAL, width=2),
                             hovertemplate="x = %{x:.4f} mm<br>r = %{y:.4f} mm<extra></extra>"))
    fig.add_trace(go.Scatter(x=x_mm, y=-r_mm, mode="lines", showlegend=False, hoverinfo="skip",
                             line=dict(color=COLOR_NUMERICAL, width=2)))
    fig.add_trace(go.Scatter(x=profile.x * 1e3, y=profile.r * 1e3, mode="markers", name="given points",
                             marker=dict(color=COLOR_NUMERICAL, size=4),
                             hovertemplate="x = %{x:.4f} mm<br>r = %{y:.4f} mm<extra>point</extra>"))
    xt, rt = profile.x_throat * 1e3, profile.r_throat * 1e3
    fig.add_trace(go.Scatter(x=[xt, xt], y=[-rt, rt], mode="lines+markers", name="throat",
                             line=dict(color=COLOR_REFERENCE, width=2, dash="dot"),
                             hovertemplate=f"throat: x = {xt:.4f} mm, d = {2 * rt:.4f} mm<extra></extra>"))
    tangents = [(label, x, r) for label, x, r in profile.marks if label != "throat"]
    if tangents:   # e.g. where the rounded-throat arcs meet the cones
        fig.add_trace(go.Scatter(
            x=[x * 1e3 for _, x, _ in tangents], y=[r * 1e3 for _, _, r in tangents], mode="markers",
            name="arc tangent points", marker=dict(color=COLOR_REFERENCE, size=9, symbol="diamond"),
            text=[label for label, _, _ in tangents],
            hovertemplate="%{text}<br>x = %{x:.4f} mm<br>r = %{y:.4f} mm<extra></extra>"))
    fig.add_hline(y=0.0, line=dict(color=COLOR_MUTED, dash="dashdot", width=1))   # axis
    fig.update_yaxes(scaleanchor="x", scaleratio=1)                               # true shape
    _layout(fig, "Wall profile (mirrored about the axis)", "x [mm]", "r [mm]", height=380)
    fig.update_layout(hovermode="closest")
    return fig


def shape_figure(profile):
    """Outline of a body (a ShapeProfile) with its points, corners and refined points marked.

    Axisymmetric bodies are drawn as their full silhouette, with the axis as a dash-dot line.
    """
    unit, scale = length_unit(profile.reference_length)
    closed = profile.closed_points() * scale
    p = profile.points * scale
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=closed[:, 0], y=closed[:, 1], mode="lines+markers", name="outline",
                             line=dict(color=COLOR_NUMERICAL, width=2), marker=dict(size=3),
                             hovertemplate=f"x = %{{x:.5g}} {unit}<br>y = %{{y:.5g}} {unit}<extra></extra>"))
    if np.any(profile.corners):
        fig.add_trace(go.Scatter(x=p[profile.corners, 0], y=p[profile.corners, 1], mode="markers",
                                 name="sharp corners", marker=dict(color=COLOR_REFERENCE, size=9, symbol="diamond"),
                                 hovertemplate=f"corner: x = %{{x:.5g}} {unit}, y = %{{y:.5g}} {unit}<extra></extra>"))
    smooth_refine = profile.refine & ~profile.corners
    if np.any(smooth_refine):
        fig.add_trace(go.Scatter(x=p[smooth_refine, 0], y=p[smooth_refine, 1], mode="markers",
                                 name="leading/trailing edge (refined)",
                                 marker=dict(color=COLOR_REFERENCE, size=9, symbol="circle-open"),
                                 hovertemplate=f"x = %{{x:.5g}} {unit}, y = %{{y:.5g}} {unit}<extra></extra>"))
    if profile.axisymmetric:
        fig.add_hline(y=0.0, line=dict(color=COLOR_MUTED, dash="dashdot", width=1))   # axis
    fig.update_yaxes(scaleanchor="x", scaleratio=1)                                   # true shape
    kind = "axisymmetric" if profile.axisymmetric else "planar"
    _layout(fig, f"{profile.name} ({kind}, {profile.n_points} points)", f"x [{unit}]",
            f"r [{unit}]" if profile.axisymmetric else f"y [{unit}]", height=380)
    fig.update_layout(hovermode="closest")
    return fig

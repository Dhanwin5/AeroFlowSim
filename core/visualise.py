"""Contour-style pictures shared by all cases: shape view, x-t diagram and 2D contour.

Every function returns a matplotlib Figure. The GUI shows it (st.pyplot) and offers it as a
PNG download (figure_png); the command line saves it the same way. Nothing here imports the GUI.

The figures are built with matplotlib.figure.Figure directly instead of matplotlib.pyplot:
pyplot keeps every figure in a global list (and needs closing), which is easy to get wrong in
a web app that redraws the page on every click. A plain Figure is freed like any Python object.

Common options of every function:
    cmap         colour map name, e.g. "viridis", "coolwarm" (see COLORMAPS)
    vmin, vmax   colour range; None = the data minimum / maximum
"""

import io

import numpy as np
from matplotlib.figure import Figure

# Plot colours (also used by the line plots in core/runner.py)
COLOR_NUMERICAL = "#2a78d6"
COLOR_REFERENCE = "#eb6834"
COLOR_MUTED = "#898781"

# Colour maps offered in the GUI. viridis..cividis are perceptually uniform (equal steps in
# value look like equal steps in colour); coolwarm / RdBu_r suit fields with a sign change.
COLORMAPS = ["viridis", "plasma", "inferno", "magma", "cividis", "coolwarm", "RdBu_r", "turbo"]

# Colours that stay visible on top of a colour map: overlay lines cycle through these.
OVERLAY_COLORS = ["white", "black", "#eb6834", "#00c2c7", "#ff4fd8"]


def style_axes(ax):
    """Light grid and muted axes so the data stands out."""
    ax.grid(True, color=COLOR_MUTED, alpha=0.3, linewidth=0.5)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(COLOR_MUTED)


def figure_png(fig, dpi=120) -> bytes:
    """The figure as PNG file content (for download buttons and saving to disk)."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi)
    return buffer.getvalue()


def _color_range(values, vmin, vmax):
    """Colour range: the given limits, or the data min / max where a limit is None."""
    values = np.asarray(values, dtype=float)
    lo = float(np.nanmin(values)) if vmin is None else float(vmin)
    hi = float(np.nanmax(values)) if vmax is None else float(vmax)
    if hi <= lo:                       # constant field: widen a little so the colour bar works
        pad = abs(lo) * 1e-6 if lo != 0.0 else 1e-12
        lo, hi = lo - pad, hi + pad
    return lo, hi


def _draw_quad_field(ax, X, Y, F, cmap, vmin, vmax, mirror):
    """Colour a structured (possibly curved) grid: X, Y node coordinates of shape (ni, nj).

    F on the nodes (shape (ni, nj))       -> smooth colours between nodes ("gouraud")
    F on the cells (shape (ni-1, nj-1))   -> one colour per cell ("flat")
    pcolormesh with 2D X, Y draws each quadrilateral where it really is, so curved grids
    (e.g. a nozzle mesh following the wall) are drawn correctly.
    """
    if F.shape == X.shape:
        shading = "gouraud"
    elif F.shape == (X.shape[0] - 1, X.shape[1] - 1):
        shading = "flat"
    else:
        raise ValueError(f"Field shape {F.shape} fits neither the nodes {X.shape} "
                         f"nor the cells of the grid.")
    mesh = ax.pcolormesh(X, Y, F, shading=shading, cmap=cmap, vmin=vmin, vmax=vmax)
    if mirror:
        ax.pcolormesh(X, -Y, F, shading=shading, cmap=cmap, vmin=vmin, vmax=vmax)
    return mesh


def contour_2d(X, Y, field, name, unit, cmap="viridis", vmin=None, vmax=None,
               show_mesh=False, mirror=False, title=None):
    """Colour picture of a field on a 2D structured grid (curved grids allowed).

    X, Y   node coordinates [m], 2D arrays of shape (ni, nj) (e.g. Mesh2D.x, Mesh2D.y)
    field  values on the nodes (ni, nj) or on the cells (ni-1, nj-1)
    show_mesh   draw the grid lines on top
    mirror      also draw the mirror image about the axis y = 0 (for axisymmetric cases)
    """
    X, Y, F = np.asarray(X, float), np.asarray(Y, float), np.asarray(field, float)
    lo, hi = _color_range(F, vmin, vmax)
    fig = Figure(figsize=(8, 4.5), layout="constrained")
    ax = fig.subplots()
    quad = _draw_quad_field(ax, X, Y, F, cmap, lo, hi, mirror)
    if show_mesh:
        for sign in ((1, -1) if mirror else (1,)):
            # Lines of constant j run along i, lines of constant i run along j.
            ax.plot(X, sign * Y, color="k", linewidth=0.4, alpha=0.5)
            ax.plot(X.T, sign * Y.T, color="k", linewidth=0.4, alpha=0.5)
    if mirror:
        ax.axhline(0.0, color=COLOR_MUTED, linestyle="-.", linewidth=0.8)  # symmetry axis
    fig.colorbar(quad, ax=ax, label=f"{name} [{unit}]")
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(title or name)
    return fig


def shape_view(x, r_of_x, field, name, unit, cmap="viridis", vmin=None, vmax=None, title=None,
               note=None):
    """A 1D result drawn inside the outline of the duct / rod, coloured by the field along x.

    x       positions of the field values [m] (nodes or cell centres)
    r_of_x  wall radius at those positions [m] (array like x), or None for a constant height
            (cases without a radius, e.g. a rod or a shock tube)
    field   field values at x (1D)
    note    second title line (default "1D result: varies along x only")

    The outline is mirrored about the axis. Since the result is 1D, the colour varies along x
    only; it is drawn on a small 2D grid (radius from -r to +r) with the same code as contour_2d.
    """
    x = np.asarray(x, float)
    F = np.asarray(field, float)
    if r_of_x is None:
        r = np.full_like(x, 0.05 * (x[-1] - x[0]))   # constant display height: 5 % of the length
    else:
        r = np.asarray(r_of_x, float) * np.ones_like(x)
    eta = np.array([-1.0, 1.0])                       # from the lower wall (-r) to the upper wall (+r)
    X = np.repeat(x[:, None], len(eta), axis=1)       # (n_x, 2)
    Y = r[:, None] * eta[None, :]                     # (n_x, 2)
    F2 = np.repeat(F[:, None], len(eta), axis=1)      # same value across the radius

    lo, hi = _color_range(F, vmin, vmax)
    fig = Figure(figsize=(8, 3.5), layout="constrained")
    ax = fig.subplots()
    quad = _draw_quad_field(ax, X, Y, F2, cmap, lo, hi, mirror=False)
    # Outline: upper and lower walls plus the two end caps.
    ax.plot(np.r_[x, x[::-1], x[0]], np.r_[r, -r[::-1], r[0]], color="k", linewidth=1.2)
    ax.axhline(0.0, color=COLOR_MUTED, linestyle="-.", linewidth=0.8)   # axis
    fig.colorbar(quad, ax=ax, label=f"{name} [{unit}]")
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("r [m]")
    ax.set_title((title or name) + "\n" + (note or "1D result: varies along x only"), fontsize=11)
    return fig


def xt_diagram(x, t, field_xt, name, unit, cmap="viridis", vmin=None, vmax=None,
               lines=None, levels=64, title=None):
    """Filled contours of a field over position (horizontal) and time (vertical).

    x         positions [m], shape (n_x,)
    t         times [s], shape (n_t,) (need not be evenly spaced)
    field_xt  values, shape (n_t, n_x): one row per time
    lines     optional list of core.results.Line to draw on top (e.g. exact wave paths)
    levels    number of colour bands
    """
    x, t, F = np.asarray(x, float), np.asarray(t, float), np.asarray(field_xt, float)
    if F.shape != (len(t), len(x)):
        raise ValueError(f"field_xt has shape {F.shape}, expected (n_t, n_x) = {(len(t), len(x))}.")
    lo, hi = _color_range(F, vmin, vmax)
    fig = Figure(figsize=(8, 5.5), layout="constrained")
    ax = fig.subplots()
    # Values outside a chosen range are drawn with the end colours ("extend") instead of left white.
    filled = ax.contourf(x, t, np.clip(F, lo, hi), levels=np.linspace(lo, hi, levels + 1), cmap=cmap)
    for k, line in enumerate(lines or []):
        ax.plot(line.x, line.y, line.style, color=OVERLAY_COLORS[k % len(OVERLAY_COLORS)],
                linewidth=1.5, label=line.label)
    if lines:
        # Grey legend box, so that white and black overlay lines both stay visible in it.
        ax.legend(loc="upper left", fontsize=8, facecolor="0.65", framealpha=0.9)
    ax.set_xlim(x[0], x[-1])
    ax.set_ylim(t[0], t[-1])
    cbar = fig.colorbar(filled, ax=ax, label=f"{name} [{unit}]")
    cbar.set_ticks(np.linspace(lo, hi, 6))
    ax.set_xlabel("x [m]")
    ax.set_ylabel("t [s]")
    ax.set_title(title or f"{name}: x-t diagram")
    return fig

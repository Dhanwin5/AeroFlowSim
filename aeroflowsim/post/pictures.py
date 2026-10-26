# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Paper-style pictures of 2D results with matplotlib only (no Qt, no VTK): used by the report, the command line
and the showcase. Cells are split into triangles (fan from the first corner) and coloured smoothly from the node
values (post/fields.py); boundaries are drawn on top; mirror about y = 0 for axisymmetric / half domains."""

import numpy as np

from aeroflowsim.post.fields import field_info, node_values


def _triangles(mesh):
    cn = mesh.cell_nodes
    counts = (cn >= 0).sum(axis=1)
    tris = []
    for k in range(1, cn.shape[1] - 1):
        use = counts > k + 1
        tris.append(np.column_stack([cn[use, 0], cn[use, k], cn[use, k + 1]]))
    return np.concatenate(tris)


def field_picture(sol, name, cmap="turbo", mirror=False, levels=None, title=None, size=(7.0, 3.6), vmin=None,
                  vmax=None, unit_convert=None):
    """A matplotlib Figure of a field (light paper style). unit_convert(values, unit) -> (values, unit)."""
    from matplotlib.figure import Figure
    from matplotlib.tri import Triangulation
    info = field_info(sol, name)
    v = node_values(sol, name)
    unit = info.unit
    if unit_convert is not None:
        v, unit = unit_convert(v, unit)
    xy = sol.mesh.nodes[:, :2]
    tri = _triangles(sol.mesh)
    fig = Figure(figsize=size, dpi=110, layout="constrained")
    fig.set_facecolor("white")
    ax = fig.add_subplot()
    lo = float(np.nanmin(v)) if vmin is None else vmin
    hi = float(np.nanmax(v)) if vmax is None else vmax
    if hi <= lo:
        hi = lo + 1e-12
    lv = np.linspace(lo, hi, 41)
    copies = [1.0, -1.0] if mirror else [1.0]
    for sign in copies:
        t = Triangulation(xy[:, 0], sign * xy[:, 1], tri)
        cs = ax.tricontourf(t, v, levels=lv, cmap=cmap, extend="both")
        if levels:
            ax.tricontour(t, v, levels=levels, colors="k", linewidths=0.5)
    for p in sol.mesh.patches:
        f = sol.mesh.face_nodes[np.arange(p.start, p.start + p.count), :2]
        for sign in copies:
            seg = np.stack([xy[f[:, 0]], xy[f[:, 1]]], axis=1) * np.array([1.0, sign])
            from matplotlib.collections import LineCollection
            ax.add_collection(LineCollection(seg, colors="k", linewidths=0.8))
    ax.set_aspect("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("r [m]" if sol.axisymmetric else "y [m]")
    bar = fig.colorbar(cs, ax=ax, orientation="horizontal", shrink=0.7, pad=0.02)
    bar.set_label(f"{info.label} [{unit}]" if unit not in ("", "-") else info.label)
    ax.set_title(title or info.label)
    return fig


def mesh_picture(mesh, size=(7.0, 3.2)):
    """The mesh edges (thin) and the named boundaries (coloured, with a legend)."""
    from matplotlib.collections import LineCollection
    from matplotlib.figure import Figure
    colours = {"inlet": "#1f77b4", "outlet": "#d62728", "wall": "#222222", "axis": "#7f7f7f", "symmetry": "#9467bd",
               "farfield": "#2ca02c"}
    xy = mesh.nodes[:, :2]
    fig = Figure(figsize=size, dpi=110, layout="constrained")
    ax = fig.add_subplot()
    f = mesh.face_nodes[:, :2]
    ax.add_collection(LineCollection(np.stack([xy[f[:, 0]], xy[f[:, 1]]], axis=1), colors="#b0b0b0", linewidths=0.2))
    for p in mesh.patches:
        g = mesh.face_nodes[np.arange(p.start, p.start + p.count), :2]
        ax.add_collection(LineCollection(np.stack([xy[g[:, 0]], xy[g[:, 1]]], axis=1),
                                         colors=colours.get(p.type, "k"), linewidths=1.6, label=f"{p.name} ({p.type})"))
    ax.autoscale()
    ax.set_aspect("equal")
    ax.legend(fontsize=7, loc="best")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("r [m]" if mesh.axisymmetric else "y [m]")
    ax.set_title(f"Mesh: {mesh.n_cells:,} cells")
    return fig

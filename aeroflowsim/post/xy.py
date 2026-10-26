# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""XY plots: any field along one or more surfaces, against position or another field, with reference data.

Fluent's XY plot, improved: the data along a line are the exact per-cell values (two samples per cell, see
sampling.py), several fields and several surfaces can share a plot, reference data come from a CSV file
(experiment, theory) with their own legend entry, the same plot of snapshots or other projects can be overlaid,
axes can be logarithmic, and the figure can be saved in the light "paper" style whatever the GUI theme
(PNG / SVG / PDF) together with a CSV of the plotted numbers.

The figure is built with matplotlib's object interface (no pyplot, no Qt), so the GUI, the report and scripts
draw the same thing.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from aeroflowsim.post.fields import boundary_face_values, field_info, field_values
from aeroflowsim.post.sampling import CELL, LINEAR, values_at
from aeroflowsim.post.surfaces import evaluate_surface

X_CHOICES = {"x": "Position x", "y": "Position y (radius)", "s": "Arc length along the surface"}


def surface_samples(sol, surface, name, mode=LINEAR):
    """(s, x, y, values) along a surface: segment ends for lines and iso-lines (exact per cell), face centres for
    boundaries (the boundary condition's face state), the point itself for a probe."""
    data = evaluate_surface(sol, surface)
    if data.n == 0:
        return np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0)
    if surface.type == "point":
        v = values_at(sol, name, data.seeds, data.cells, mode)
        return np.zeros(1), data.seeds[:, 0], data.seeds[:, 1], v
    if data.on_boundary:
        mid = 0.5 * (data.a + data.b)
        s0, s1 = data.arc_length()
        if mode == CELL:
            v = field_values(sol, name)[data.cells]
        else:
            v = boundary_face_values(sol, name)[data.faces]
        return 0.5 * (s0 + s1), mid[:, 0], mid[:, 1], v
    s0, s1 = data.arc_length()
    s = np.column_stack([s0, s1]).ravel()
    pts = np.stack([data.a, data.b], axis=1).reshape(-1, 2)
    cells = np.repeat(data.cells, 2)
    return s, pts[:, 0], pts[:, 1], values_at(sol, name, pts, cells, mode)


@dataclass
class Curve:
    x: np.ndarray
    y: np.ndarray
    label: str
    style: str = "line"          # line, markers (reference data), dashed (other result)


@dataclass
class XYPlot:
    """Settings of one XY plot (stored in the project, key xy_plots)."""

    name: str = "XY plot"
    fields: list = field(default_factory=lambda: ["p"])
    surfaces: list = field(default_factory=list)        # surface names
    x_axis: str = "x"                                    # x, y, s, or a field name
    log_x: bool = False
    log_y: bool = False
    reference_csv: str = ""                              # path (relative to the project) of reference data
    reference_label: str = "Reference"
    mode: str = LINEAR                                   # linear (per cell) or cell (cell values)

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d):
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in dict(d).items() if k in known})


def curves(sol, plot, surfaces, label_prefix="") -> list:
    """The curves of an XY plot for one solution. surfaces: {name: Surface}."""
    out = []
    for sname in plot.surfaces:
        surface = surfaces[sname]
        for f in plot.fields:
            s, x, y, values = surface_samples(sol, surface, f, plot.mode)
            if plot.x_axis in X_CHOICES:
                xs = {"x": x, "y": y, "s": s}[plot.x_axis]
            else:
                xs = surface_samples(sol, surface, plot.x_axis, plot.mode)[3]
            order = np.argsort(xs, kind="stable") if plot.x_axis != "s" else np.arange(len(xs))
            label = f"{label_prefix}{field_info(sol, f).label} on {sname}" if len(plot.fields) > 1 or len(plot.surfaces) > 1 \
                else f"{label_prefix}{field_info(sol, f).label}"
            out.append(Curve(xs[order], values[order], label))
    return out


def read_reference_csv(path):
    """(x, y, column names) from a two-column CSV with a header (lines starting with # are comments)."""
    xs, ys, header = [], [], None
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.reader(line for line in fh if not line.lstrip().startswith("#")):
            if not row:
                continue
            if header is None:
                try:
                    float(row[0])
                except ValueError:
                    header = row
                    continue
                header = ["x", "y"]
            xs.append(float(row[0]))
            ys.append(float(row[1]))
    if not xs:
        raise ValueError(f"{Path(path).name} has no numbers (two columns x, y expected).")
    return np.array(xs), np.array(ys), header


def axis_label(sol, name, convert=None) -> str:
    if name in X_CHOICES:
        unit = "m"
        label = {"x": "x", "y": "r" if sol.axisymmetric else "y", "s": "s (along the surface)"}[name]
    else:
        info = field_info(sol, name)
        label, unit = info.label, info.unit
    if convert is not None:
        unit = convert(np.zeros(1), unit)[1]
    return f"{label} [{unit}]" if unit and unit != "-" else label


PAPER = {"face": "white", "text": "#111111", "grid": "#d0d0d0", "colours":
         ["#1f4e9c", "#c0392b", "#2e8540", "#8e44ad", "#d68910", "#17a2b8", "#555555"]}
DARK = {"face": "#1e1f22", "text": "#e6e6e6", "grid": "#3a3c40", "colours":
        ["#6ea8fe", "#ff7b72", "#7ee787", "#d2a8ff", "#ffa657", "#79c0ff", "#bbbbbb"]}


def xy_figure(curve_list, xlabel, ylabel, log_x=False, log_y=False, style="paper", title="", figure=None,
              size=(6.4, 4.0)):
    """A matplotlib Figure of the curves. style "paper" (light, for saving) or "dark"."""
    from matplotlib.figure import Figure
    st = PAPER if style == "paper" else DARK
    fig = figure or Figure(figsize=size, dpi=100)
    fig.clear()
    fig.set_facecolor(st["face"])
    ax = fig.add_subplot(111)
    ax.set_facecolor(st["face"])
    k = 0
    for c in curve_list:
        if c.style == "markers":
            ax.plot(c.x, c.y, "o", ms=4, mfc="none", color=st["text"], label=c.label)
        else:
            ax.plot(c.x, c.y, "--" if c.style == "dashed" else "-", lw=1.4, color=st["colours"][k % 7], label=c.label)
            k += 1
    if log_x:
        ax.set_xscale("log")
    if log_y:
        ax.set_yscale("log")
    ax.set_xlabel(xlabel, color=st["text"])
    ax.set_ylabel(ylabel, color=st["text"])
    if title:
        ax.set_title(title, color=st["text"], fontsize=10)
    ax.grid(True, color=st["grid"], lw=0.6)
    ax.tick_params(colors=st["text"])
    for spine in ax.spines.values():
        spine.set_color(st["text"])
    if curve_list:
        leg = ax.legend(fontsize=8, frameon=False)
        for t in leg.get_texts():
            t.set_color(st["text"])
    fig.tight_layout()
    return fig


def save_figure(fig, path, dpi=200):
    """Save PNG / SVG / PDF (by the file extension)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, facecolor=fig.get_facecolor())
    return path


def curves_csv(curve_list, path, xlabel, ylabel):
    """The plotted numbers: one block of columns (x, y) per curve."""
    from aeroflowsim.post.export import table_csv
    n = max((len(c.x) for c in curve_list), default=0)
    header, cols = [], []
    for c in curve_list:
        header += [f"{c.label}: {xlabel}", f"{c.label}: {ylabel}"]
        pad = n - len(c.x)
        cols += [np.concatenate([c.x, np.full(pad, np.nan)]), np.concatenate([c.y, np.full(pad, np.nan)])]
    rows = [["" if np.isnan(v) else float(v) for v in row] for row in np.column_stack(cols)] if cols else []
    return table_csv(path, header, rows, "AeroFlowSim XY plot data")

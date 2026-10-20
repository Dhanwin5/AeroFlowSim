# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Matplotlib plots inside the Qt window (1D fields, residual history, 1D mesh).

matplotlib draws into a Figure; FigureCanvasQTAgg is a Qt widget that shows a Figure, and the
standard matplotlib toolbar under it gives zoom, pan and "save picture" for free. The figure
builders below only build Figures (no Qt), like aeroflowsim/visualise.py, whose contour, shape and
x-t figures are shown here unchanged. 2D/3D fields and meshes use VTK (aeroflowsim/gui/vtk_view.py).
"""

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.colors import LogNorm
from matplotlib.figure import Figure
from matplotlib.ticker import NullFormatter
from PySide6.QtWidgets import QVBoxLayout, QWidget

from aeroflowsim.visualise import COLOR_MUTED, COLOR_NUMERICAL, COLOR_REFERENCE, style_axes

MAX_PLOT_POINTS = 5000   # longer residual histories are thinned (the curve still ends at the last value)


class PlotCanvas(QWidget):
    """A matplotlib Figure with the standard toolbar (zoom, pan, save). set_figure() replaces it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = self.toolbar = None
        self.set_figure(Figure(figsize=(6, 3.5), layout="constrained"))

    def set_figure(self, figure):
        for widget in (self.toolbar, self.canvas):
            if widget is not None:
                self._layout.removeWidget(widget)
                widget.deleteLater()
        self.figure = figure
        self.canvas = FigureCanvasQTAgg(figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self._layout.addWidget(self.canvas, 1)
        self._layout.addWidget(self.toolbar)
        self.canvas.draw_idle()


def _figure(height=3.5):
    fig = Figure(figsize=(7, height), layout="constrained")
    return fig, fig.add_subplot()


def residual_figure(iterations, residuals, tol=None, figure=None):
    """Convergence history on a log axis, with the tolerance as a dotted line. Reuses `figure` if given."""
    if figure is None:
        figure = Figure(figsize=(7, 3.5), layout="constrained")
    figure.clear()
    ax = figure.add_subplot()
    it = np.asarray(iterations)
    res = np.maximum(np.asarray(residuals, dtype=float), 1e-300)   # 0 cannot be drawn on a log axis
    if len(it) > MAX_PLOT_POINTS:
        keep = np.unique(np.r_[np.linspace(0, len(it) - 1, MAX_PLOT_POINTS).astype(int), len(it) - 1])
        it, res = it[keep], res[keep]
    if len(it):
        ax.semilogy(it, res, color=COLOR_NUMERICAL, lw=1.6)
    if tol:
        ax.axhline(tol, color=COLOR_MUTED, ls=":", lw=1)
        ax.annotate(f"tolerance {tol:.0e}", (1.0, tol), xycoords=("axes fraction", "data"), ha="right",
                    va="bottom", fontsize=8, color=COLOR_MUTED)
    ax.set_xlabel("iteration [-]")
    ax.set_ylabel("normalised residual [-]")
    ax.set_title("Convergence history")
    style_axes(ax)
    return figure


def field_figure(mesh, field, ref_field=None):
    """One field along x: numerical (line + dots) and the reference (dashed), if any."""
    fig, ax = _figure(4.0)
    x = mesh.positions(len(field.values))
    ax.plot(x, field.values, "-o", color=COLOR_NUMERICAL, ms=3, lw=1.6, label="numerical")
    if ref_field is not None:
        ax.plot(mesh.positions(len(ref_field.values)), ref_field.values, "--", color=COLOR_REFERENCE, lw=1.6,
                label="reference (exact)")
    ax.set_xlabel("x [m]")
    ax.set_ylabel(f"{field.label} [{field.unit}]")
    ax.set_title(field.label)
    ax.legend(loc="best", frameon=False)
    style_axes(ax)
    return fig


def mesh1d_figure(mesh, edges=True):
    """A 1D mesh: every cell drawn as a coloured band, the colour = the cell width.

    The 2D quality measures (aspect ratio, non-orthogonality, ...) do not exist for a line of 1D
    cells; the cell width is what matters (e.g. the clustering at a nozzle throat). A logarithmic
    colour scale is used when the widths differ by more than a factor of 10.
    """
    fig, ax = _figure(2.6)
    width = np.diff(mesh.x)                                       # cell widths [m]
    norm = LogNorm(width.min(), width.max()) if width.max() > 10.0 * width.min() else None
    bands = ax.pcolormesh(mesh.x, [-0.3, 0.3], width[None, :], cmap="viridis", norm=norm, shading="flat")
    if edges:                                                     # nodes as ticks under the band (density visible,
        ax.vlines(mesh.x, -0.42, -0.33, color=COLOR_MUTED, lw=0.5)   # colours of tiny cells not covered)
    bar = fig.colorbar(bands, ax=ax, orientation="horizontal", pad=0.25, aspect=50, label="cell width [m]")
    ticks = [width.min(), float(np.sqrt(width.min() * width.max())), width.max()]   # smallest, middle, largest
    bar.set_ticks(ticks, labels=[f"{t:.3g}" for t in ticks])
    bar.ax.xaxis.set_minor_formatter(NullFormatter())             # no crowded extra labels
    ax.set_ylim(-0.5, 0.4)
    ax.set_yticks([])
    ax.set_xlabel("x [m]")
    ax.set_title(f"1D mesh: {mesh.n_nodes} nodes, {mesh.n_cells} cells (colour = cell width)")
    style_axes(ax)
    return fig

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the shared contour-style views (aeroflowsim/visualise.py) and the snapshot recorder."""

import numpy as np
import pytest
from matplotlib.collections import QuadMesh
from matplotlib.figure import Figure

from aeroflowsim.geometry import WallProfile
from aeroflowsim.results import Field, Line, SnapshotRecorder
from aeroflowsim.visualise import contour_2d, figure_png, shape_view, xt_diagram

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def curved_grid(ni=21, nj=9):
    """A curved structured grid: x = xi, y = eta (1 + 0.3 sin(pi xi)) - like a bumped duct."""
    xi, eta = np.meshgrid(np.linspace(0.0, 1.0, ni), np.linspace(0.0, 1.0, nj), indexing="ij")
    X = xi                                          # [m]
    Y = eta * (1.0 + 0.3 * np.sin(np.pi * xi))      # [m]
    return X, Y


def quad_meshes(fig):
    return [c for c in fig.axes[0].collections if isinstance(c, QuadMesh)]


def test_contour_2d_on_curved_grid_with_analytic_field():
    X, Y = curved_grid()
    F = X**2 + Y                                    # analytic field on the nodes
    fig = contour_2d(X, Y, F, "Test field", "-", cmap="plasma", vmin=0.0, vmax=2.0)
    assert isinstance(fig, Figure)
    quad = quad_meshes(fig)[0]
    # The drawn quadrilaterals sit exactly on the curved grid nodes (not on a rectangle).
    coords = quad.get_coordinates()                 # shape (ni, nj, 2)
    assert np.allclose(coords[..., 0], X) and np.allclose(coords[..., 1], Y)
    assert quad.norm.vmin == 0.0 and quad.norm.vmax == 2.0
    assert quad.get_cmap().name == "plasma"
    assert figure_png(fig).startswith(PNG_SIGNATURE)


def test_contour_2d_mesh_overlay_mirror_and_cell_values():
    X, Y = curved_grid()
    Fc = np.ones((X.shape[0] - 1, X.shape[1] - 1))  # one value per cell
    fig = contour_2d(X, Y, Fc, "Cells", "-", show_mesh=True, mirror=True)
    assert len(quad_meshes(fig)) == 2               # upper half and mirrored lower half
    assert np.allclose(quad_meshes(fig)[1].get_coordinates()[..., 1], -Y)
    assert len(fig.axes[0].lines) >= X.shape[0] + X.shape[1]   # grid lines drawn
    with pytest.raises(ValueError):
        contour_2d(X, Y, np.ones(5), "bad", "-")


def test_shape_view_constant_height_and_profile():
    x = np.linspace(0.0, 2.0, 30)                   # [m]
    f = np.sin(x)
    fig = shape_view(x, None, f, "Density", "kg/m³")
    assert isinstance(fig, Figure)
    assert "1D result: varies along x only" in fig.axes[0].get_title()
    nozzle = WallProfile(x=[0.0, 1.0, 2.0], r=[0.3, 0.1, 0.25])
    fig = shape_view(x, nozzle.radius_at(x), f, "Density", "kg/m³", cmap="coolwarm")
    coords = quad_meshes(fig)[0].get_coordinates()
    assert np.allclose(coords[:, 1, 1], nozzle.radius_at(x))   # upper wall follows r(x)
    assert figure_png(fig).startswith(PNG_SIGNATURE)


def test_xt_diagram_with_overlay_lines():
    x = np.linspace(0.0, 1.0, 50)                   # [m]
    t = np.linspace(0.0, 0.2, 40)                   # [s]
    F = np.exp(-((x[None, :] - 0.5 - 1.0 * t[:, None]) / 0.05) ** 2)   # pulse moving at 1 m/s
    lines = [Line("pulse path", x=0.5 + 1.0 * t, y=t), Line("other", x=[0.5, 0.3], y=[0.0, 0.2], style="--")]
    fig = xt_diagram(x, t, F, "Pulse", "-", cmap="inferno", vmin=0.0, vmax=1.0, lines=lines)
    assert isinstance(fig, Figure)
    labels = [text.get_text() for text in fig.axes[0].get_legend().get_texts()]
    assert labels == ["pulse path", "other"]
    assert fig.axes[0].get_xlim() == (0.0, 1.0) and fig.axes[0].get_ylim() == (0.0, 0.2)
    assert figure_png(xt_diagram(x, t, F, "Pulse", "-")).startswith(PNG_SIGNATURE)
    with pytest.raises(ValueError):
        xt_diagram(x, t, F.T, "Pulse", "-")


def test_snapshot_recorder_limits_memory_and_keeps_first_and_last():
    recorder = SnapshotRecorder(max_snapshots=200)
    n_steps = 10_000
    for step in range(n_steps + 1):
        recorder.add(step, 0.001 * step, {"a": Field(values=np.full(3, float(step)), unit="-", label="A")})
    recorder.add_final(n_steps, 0.001 * n_steps, {"a": Field(values=np.full(3, -1.0), unit="-", label="A")})
    snaps = recorder.snapshots()
    assert len(snaps.times) <= 200
    assert len(snaps.times) > 50                    # still plenty of detail
    assert snaps.times[0] == 0.0 and snaps.times[-1] == pytest.approx(10.0)
    assert np.all(np.diff(snaps.times) > 0.0)
    assert np.all(snaps.fields["a"].values[-1] == -1.0)   # final state as given
    assert snaps.fields["a"].values.shape == (len(snaps.times), 3)


def test_wall_profile_checks():
    with pytest.raises(ValueError):
        WallProfile(x=[0.0, 0.0], r=[1.0, 1.0])     # x not increasing
    with pytest.raises(ValueError):
        WallProfile(x=[0.0, 1.0], r=[1.0, -1.0])    # negative radius


def test_shape_view_custom_note():
    x = np.linspace(0.0, 1.0, 10)
    fig = shape_view(x, 0.1 + 0.0 * x, x, "Mach number", "-", note="quasi-1D: varies along x only")
    assert "quasi-1D: varies along x only" in fig.axes[0].get_title()

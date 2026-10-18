# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the structured axisymmetric nozzle mesh generator (aeroflowsim/nozzle_mesh.py)."""

import math

import numpy as np
import pytest

from aeroflowsim import mesh_quality
from aeroflowsim.geometry import WallProfile, conical_nozzle
from aeroflowsim.nozzle_mesh import (Inflation, axial_stations, core_sizes, structured_nozzle_mesh,
                                     tanh_stretching, total_inflation_thickness)

DEG = math.pi / 180.0
NOZZLE = conical_nozzle(0.002, 0.00133, 30 * DEG, 0.00028, 15 * DEG, 0.000911)   # default N2 thruster


def node_grid(mesh):
    """Node coordinates as (nx+1, nr+1) arrays X, R (the generator numbers nodes i (nr+1) + j)."""
    nx, nr = mesh.info["nx"], mesh.info["nr"]
    return mesh.nodes[:, 0].reshape(nx + 1, nr + 1), mesh.nodes[:, 1].reshape(nx + 1, nr + 1)


def test_cell_counts_patches_and_axisymmetric_flag():
    mesh = structured_nozzle_mesh(NOZZLE, 30, 8)
    assert mesh.n_cells == 240 and mesh.axisymmetric and mesh.dim == 2
    counts = {p.name: (p.type, p.count) for p in mesh.patches}
    assert counts == {"inlet": ("inlet", 8), "outlet": ("outlet", 8), "wall": ("wall", 30), "axis": ("axis", 30)}
    assert np.all(mesh.cell_volumes > 0)
    assert np.allclose(mesh.face_centres[mesh.patch("axis").faces, 1], 0.0)
    assert np.allclose(mesh.face_centres[mesh.patch("inlet").faces, 0], 0.0)
    # The wall nodes lie exactly on the profile.
    X, R = node_grid(mesh)
    assert np.allclose(R[:, -1], NOZZLE.radius_at(X[:, -1]), rtol=0, atol=1e-15)


def test_throat_is_a_station_and_clustering_is_smooth():
    x = axial_stations(0.0, 0.3, 1.0, 100, 2.0)
    assert len(x) == 101 and 0.3 in x and x[0] == 0.0 and x[-1] == 1.0
    dx = np.diff(x)
    i = int(np.flatnonzero(x == 0.3)[0])
    assert dx[i - 1] == pytest.approx(dx[i], rel=0.05)          # same size on both sides of the throat
    assert dx.min() == pytest.approx(min(dx[i - 1], dx[i]))     # smallest cells at the throat
    assert np.max(dx[1:] / dx[:-1]) < 1.2 and np.min(dx[1:] / dx[:-1]) > 1 / 1.2   # no jumps
    assert np.allclose(tanh_stretching(10, 0.0), np.linspace(0, 1, 11))           # off = uniform


def test_inflation_first_layer_height_and_growth_rate_match_the_inputs():
    inflation = Inflation(first_height=1e-6, n_layers=10, growth=1.2)
    mesh = structured_nozzle_mesh(NOZZLE, 60, 30, inflation=inflation)
    X, R = node_grid(mesh)
    layers = -np.diff(R[:, ::-1], axis=1)[:, :10]             # radial heights from the wall inwards
    assert np.allclose(layers[:, 0], 1e-6, rtol=1e-9)
    assert np.allclose(layers[:, 1:] / layers[:, :-1], 1.2, rtol=1e-9)
    assert mesh.info["inflation_thickness"] == pytest.approx(1e-6 * (1.2**10 - 1) / 0.2)
    assert total_inflation_thickness(1e-6, 10, 1.2) == pytest.approx(mesh.info["inflation_thickness"])
    # The first core cell continues the growth: no size jump between layers and core.
    core_first = -np.diff(R[:, ::-1], axis=1)[:, 10]
    assert np.allclose(core_first / layers[:, -1], 1.2, rtol=1e-6)
    assert np.nanmax(mesh_quality.volume_ratio(mesh)) < 2.0


def test_core_cells_level_off_instead_of_becoming_tiny_at_the_axis():
    sizes = core_sizes(total=1.0, n=50, first=0.1, growth=1.2)   # too little room: must shrink
    assert sizes.sum() == pytest.approx(1.0) and sizes[0] == pytest.approx(0.1, rel=1e-6)
    assert np.all(np.diff(sizes) <= 0) and sizes[-1] > 0.4 * 1.0 / 50   # not tiny at the axis
    grow = core_sizes(total=1.0, n=10, first=0.05, growth=1.2)  # room to grow
    assert grow.sum() == pytest.approx(1.0) and grow[0] == pytest.approx(0.05)
    assert np.allclose(grow[1:] / grow[:-1], grow[1] / grow[0])


def test_inflation_that_does_not_fit_is_refused_with_a_clear_message():
    with pytest.raises(ValueError, match="overlap"):
        structured_nozzle_mesh(NOZZLE, 40, 30, inflation=Inflation(1e-5, 20, 1.3))
    with pytest.raises(ValueError, match="cells across"):
        structured_nozzle_mesh(NOZZLE, 40, 10, inflation=Inflation(1e-6, 10, 1.2))


def test_smooth_csv_like_profile_and_bad_profile():
    x = np.linspace(0.0, 0.01, 11)
    r = 0.002 + 0.003 * ((x - 0.004) / 0.006) ** 2
    mesh = structured_nozzle_mesh(WallProfile(x, r, "pchip"), 50, 10)
    assert np.all(mesh.cell_volumes > 0) and mesh.info["x_throat"] == pytest.approx(0.004)
    with pytest.raises(ValueError, match="strictly between"):
        structured_nozzle_mesh(WallProfile([0, 1], [1, 2]), 10, 4)    # widest at the exit, no throat

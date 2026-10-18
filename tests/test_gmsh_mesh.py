# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the Gmsh meshes (aeroflowsim/gmsh_mesh.py): every mesh passes the Mesh format tests
(face closure, owner/neighbour, outward normals, patches), half domains, inflation layers,
quad-dominant meshes, the nozzle (structured vs triangles), .msh and .vtu files.

Tests that need Gmsh are skipped when it is not installed (pytest.importorskip), so the fast tests
also pass without it; the "not installed" message is tested in both situations.
"""

import math
import sys

import numpy as np
import pytest

from aeroflowsim import gmsh_mesh
from aeroflowsim.discovery import load_case
from aeroflowsim.mesh import DEPTH_2D, QUAD, TRIANGLE, Mesh
from aeroflowsim.parameters import defaults
from aeroflowsim.vtk import save_mesh_files

ROUND_OFF = 1e-9
EXTERNAL = load_case("external_2d")
NOZZLE = load_case("nozzle_axi")
EXT_DEFAULTS = defaults(EXTERNAL.parameters())
NOZ_DEFAULTS = defaults(NOZZLE.parameters())
SHAPES = EXTERNAL.schema.inputs[0].options


@pytest.fixture
def gmsh():
    return pytest.importorskip("gmsh")


def external(**changes):
    return EXTERNAL.build_mesh({**EXT_DEFAULTS, **changes})


def assert_valid_mesh(mesh, patch_names):
    """The checks of tests/test_mesh_format.py, for any mesh."""
    assert {p.name for p in mesh.patches} == set(patch_names)
    assert np.all(mesh.cell_volumes > 0.0)
    n = mesh.n_interior_faces
    assert np.all(mesh.neighbour[:n] >= 0) and np.all(mesh.neighbour[n:] == -1)
    assert np.all(mesh.owner[:n] < mesh.neighbour[:n])
    assert sum(p.count for p in mesh.patches) == mesh.n_faces - n
    total = np.zeros((mesh.n_cells, 3))                    # face closure: outward area vectors sum to 0
    S = mesh.face_area_vectors
    np.add.at(total, mesh.owner, S)
    np.add.at(total, mesh.neighbour[:n], -S[:n])
    assert np.abs(total).max() < ROUND_OFF * np.abs(S).max()
    c = mesh.cell_centres                                   # normals: owner -> neighbour, out of the domain
    assert np.all(np.einsum("ij,ij->i", mesh.face_normals[:n], c[mesh.neighbour[:n]] - c[mesh.owner[:n]]) > 0)
    assert np.all(np.einsum("ij,ij->i", mesh.face_normals[n:], mesh.face_centres[n:] - c[mesh.owner[n:]]) > 0)


def test_missing_gmsh_gives_a_clear_install_message(monkeypatch):
    monkeypatch.setitem(sys.modules, "gmsh", None)          # makes "import gmsh" fail, as if not installed
    with pytest.raises(ValueError, match=r'pip install -e "\.\[mesh\]"'):
        gmsh_mesh._import_gmsh()


@pytest.mark.parametrize("shape", SHAPES)
def test_every_shape_meshes_in_a_full_or_half_domain(gmsh, shape):
    profile = EXTERNAL.geometry({**EXT_DEFAULTS, "shape": shape})
    if not profile.axisymmetric:
        mesh = external(shape=shape)
        assert_valid_mesh(mesh, {"wall", "farfield"})
        assert not mesh.axisymmetric and set(np.unique(mesh.cell_types)) == {TRIANGLE}
    if profile.is_symmetric():
        mesh = external(shape=shape, half_domain=True)
        assert_valid_mesh(mesh, {"wall", "farfield", "axis" if profile.axisymmetric else "symmetry"})
        assert mesh.nodes[:, 1].min() >= 0.0 and mesh.axisymmetric == profile.axisymmetric
        assert mesh.info["reference_length"] == profile.reference_length


def test_asymmetric_body_cannot_use_a_half_domain(gmsh):
    with pytest.raises(ValueError, match="not symmetric"):
        external(**{"shape": "NACA 4-digit airfoil", "naca4.digits": "2412", "half_domain": True})


def test_rectangle_domain_area_is_exact(gmsh):
    mesh = external(**{"shape": "Wedge", "domain_shape": "Rectangle"})
    assert_valid_mesh(mesh, {"wall", "farfield"})
    exact = (1.0 + 10.0 + 20.0) * 20.0 - math.tan(math.radians(10.0))   # rectangle - wedge [m²]
    assert mesh.cell_volumes.sum() / DEPTH_2D == pytest.approx(exact, rel=1e-12)


@pytest.mark.parametrize("shape, half", [("Wedge", False), ("NACA 4-digit airfoil", True),
                                         ("Conical nose cone", True), ("Circular cylinder", False)])
def test_inflation_layers_have_the_asked_first_height(gmsh, shape, half):
    mesh = external(shape=shape, half_domain=half, inflation=True, first_layer_height=1e-4)
    patches = {"wall", "farfield"} | ({"axis" if shape == "Conical nose cone" else "symmetry"} if half else set())
    assert_valid_mesh(mesh, patches)
    assert QUAD in mesh.cell_types and mesh.info["inflation"]
    wall = mesh.patch("wall").faces
    quads = mesh.owner[wall][mesh.cell_types[mesh.owner[wall]] == QUAD]
    height = mesh.cell_volumes[quads] / mesh.face_areas[wall][mesh.cell_types[mesh.owner[wall]] == QUAD]
    assert np.median(height) == pytest.approx(1e-4, rel=0.02)          # cell area / wall length


def test_quad_dominant_mesh_is_mostly_quads(gmsh):
    mesh = external(cell_type="Quad-dominant (recombined)")
    assert_valid_mesh(mesh, {"wall", "farfield"})
    assert np.count_nonzero(mesh.cell_types == QUAD) > 0.9 * mesh.n_cells


def test_estimate_is_close_to_the_real_cell_count(gmsh):
    for changes in ({}, {"shape": "Circular cylinder", "half_domain": True}, {"inflation": True}):
        p = {**EXT_DEFAULTS, **changes}
        assert EXTERNAL.estimated_cells(p) == pytest.approx(EXTERNAL.build_mesh(p).n_cells, rel=0.35)


def test_msh_and_vtu_files_are_written(gmsh, tmp_path):
    msh = tmp_path / "mesh.msh"
    profile = EXTERNAL.geometry(EXT_DEFAULTS)
    settings = EXTERNAL.settings(EXT_DEFAULTS, profile)
    settings.msh_path = msh
    mesh = gmsh_mesh.external_mesh(profile, EXTERNAL.domain(EXT_DEFAULTS, profile), settings)
    assert msh.read_text(encoding="utf-8").startswith("$MeshFormat")
    npz, vtu = save_mesh_files(mesh, tmp_path)
    assert Mesh.load(npz).n_cells == mesh.n_cells
    assert f'NumberOfCells="{mesh.n_cells}"' in vtu.read_text(encoding="utf-8")


# ---- nozzle -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("rounded", [False, True])
def test_structured_and_triangle_nozzle_meshes_have_the_same_area_and_volume(gmsh, rounded):
    p = {**NOZ_DEFAULTS, "Rcu_ratio": 1.5 if rounded else 0.0, "Rcd_ratio": 0.4 if rounded else 0.0}
    structured = NOZZLE.build_mesh(p)
    triangles = NOZZLE.build_mesh({**p, "mesh_type": "Triangles (Gmsh)"})
    assert_valid_mesh(triangles, {"inlet", "outlet", "wall", "axis"})
    assert triangles.axisymmetric and TRIANGLE in triangles.cell_types
    assert triangles.cell_volumes.sum() == pytest.approx(structured.cell_volumes.sum(), rel=1e-3)
    assert triangles.axi_cell_volumes.sum() == pytest.approx(structured.axi_cell_volumes.sum(), rel=1e-3)


def test_triangle_nozzle_with_inflation_and_quads(gmsh):
    mesh = NOZZLE.build_mesh({**NOZ_DEFAULTS, "mesh_type": "Triangles (Gmsh)", "inflation": True,
                              "Rcu_ratio": 1.5, "Rcd_ratio": 0.4})
    assert_valid_mesh(mesh, {"inlet", "outlet", "wall", "axis"})
    assert mesh.info["inflation_thickness"] == pytest.approx(1e-6 * (1.2**10 - 1) / 0.2)
    mesh = NOZZLE.build_mesh({**NOZ_DEFAULTS, "mesh_type": "Triangles (Gmsh)",
                              "cell_type": "Quad-dominant (recombined)"})
    assert_valid_mesh(mesh, {"inlet", "outlet", "wall", "axis"})
    assert np.count_nonzero(mesh.cell_types == QUAD) > 0.8 * mesh.n_cells

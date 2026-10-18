# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the face-based Mesh format (aeroflowsim/mesh.py): faces, owner/neighbour, normals,
geometry, 3D cells, save/load, and clear errors for bad input."""

import numpy as np
import pytest

from aeroflowsim import mesh_quality
from aeroflowsim.mesh import HEXAHEDRON, PYRAMID, QUAD, TETRA, TRIANGLE, WEDGE, Mesh

ROUND_OFF = 1e-12


def boundary_patch(mesh_faces):
    """Put every given face into one 'wall' patch (helper for the hand-made test cells)."""
    return {"wall": ("wall", mesh_faces)}


def all_outer_faces(cell_type, cell_nodes):
    """The boundary faces of a single cell = all of its own faces."""
    from aeroflowsim.mesh import CELL_TYPES
    faces = []
    for local in CELL_TYPES[cell_type].faces:
        faces.append(list(np.asarray(cell_nodes)[list(local)]) + [-1] * (4 - len(local)))
    return np.array(faces)


def single_cell(cell_type, nodes):
    cells = np.arange(len(nodes))[None, :]
    return Mesh.from_cells(nodes, cell_type, cells, boundary_patch(all_outer_faces(cell_type, cells[0])))


def closure(mesh):
    """For every cell: the sum of its outward (normal x area) vectors (should be zero)."""
    total = np.zeros((mesh.n_cells, 3))
    S = mesh.face_area_vectors
    np.add.at(total, mesh.owner, S)
    inner = mesh.neighbour >= 0
    np.add.at(total, mesh.neighbour[inner], -S[inner])
    return total


def grid_mesh(nx=4, ny=3, skew=0.0):
    """A small 2D quad mesh on [0, 1] x [0, 1] (optionally sheared) with four patches."""
    x, y = np.meshgrid(np.linspace(0, 1, nx + 1), np.linspace(0, 1, ny + 1), indexing="ij")
    x = x + skew * y
    nodes = np.column_stack([x.ravel(), y.ravel()])
    nid = lambda i, j: i * (ny + 1) + j
    cells = [[nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)] for i in range(nx) for j in range(ny)]
    boundary = {
        "inlet": ("inlet", [[nid(0, j), nid(0, j + 1)] for j in range(ny)]),
        "outlet": ("outlet", [[nid(nx, j), nid(nx, j + 1)] for j in range(ny)]),
        "bottom": ("symmetry", [[nid(i, 0), nid(i + 1, 0)] for i in range(nx)]),
        "top": ("wall", [[nid(i, ny), nid(i + 1, ny)] for i in range(nx)]),
    }
    return Mesh.from_cells(nodes, QUAD, cells, boundary)


def test_2d_grid_counts_volumes_and_closure():
    mesh = grid_mesh(4, 3)
    assert (mesh.n_cells, mesh.n_nodes) == (12, 20)
    assert mesh.n_interior_faces == 3 * 3 + 4 * 2          # vertical + horizontal interior edges
    assert mesh.n_faces == mesh.n_interior_faces + 2 * 3 + 2 * 4
    assert np.allclose(mesh.cell_volumes, 1.0 / 12.0)        # area x 1 m depth [m³]
    assert np.allclose(mesh.cell_volumes.sum(), 1.0)
    assert np.abs(closure(mesh)).max() < ROUND_OFF


def test_every_interior_face_has_two_cells_and_boundary_faces_one_patch():
    mesh = grid_mesh(5, 4, skew=0.3)
    n = mesh.n_interior_faces
    assert np.all(mesh.neighbour[:n] >= 0) and np.all(mesh.neighbour[n:] == -1)
    assert np.all(mesh.owner[:n] < mesh.neighbour[:n])      # owner = lower cell number
    patch_of_face = mesh.face_patch_index()
    assert np.all(patch_of_face[:n] == -1) and np.all(patch_of_face[n:] >= 0)
    assert sum(p.count for p in mesh.patches) == mesh.n_faces - n
    # Every cell has exactly 4 faces in total (owner + neighbour appearances).
    appearances = np.bincount(mesh.owner, minlength=mesh.n_cells) + \
        np.bincount(mesh.neighbour[:n], minlength=mesh.n_cells)
    assert np.all(appearances == 4)


def test_normals_point_from_owner_to_neighbour_and_out_of_the_domain():
    mesh = grid_mesh(5, 4, skew=0.3)
    n = mesh.n_interior_faces
    c = mesh.cell_centres
    inner = np.einsum("ij,ij->i", mesh.face_normals[:n], c[mesh.neighbour[:n]] - c[mesh.owner[:n]])
    outer = np.einsum("ij,ij->i", mesh.face_normals[n:], mesh.face_centres[n:] - c[mesh.owner[n:]])
    assert np.all(inner > 0) and np.all(outer > 0)
    assert np.allclose(np.linalg.norm(mesh.face_normals, axis=1), 1.0)
    # Unsheared grid: the inlet (x = 0) normal points in -x, the top wall normal in +y.
    mesh = grid_mesh(5, 4)
    assert np.allclose(mesh.face_normals[mesh.patch("inlet").faces], [-1, 0, 0])
    assert np.allclose(mesh.face_normals[mesh.patch("top").faces], [0, 1, 0])


def test_sheared_cells_have_exact_area_centroid_and_non_orthogonality():
    mesh = grid_mesh(1, 1, skew=0.5)        # one parallelogram: base 1, height 1, shear 0.5
    assert np.isclose(mesh.cell_volumes[0], 1.0)
    assert np.allclose(mesh.cell_centres[0], [0.75, 0.5, 0.0])
    assert mesh_quality.aspect_ratio(mesh)[0] == pytest.approx(np.hypot(1.0, 0.5) / 1.0)


def test_mixed_triangles_and_quads():
    # A unit square split into one quad (left half) and two triangles (right half).
    nodes = [[0, 0], [0.5, 0], [1, 0], [1, 1], [0.5, 1], [0, 1]]
    cells = [[0, 1, 4, 5], [1, 2, 3, -1], [1, 3, 4, -1]]
    boundary = {"all": ("wall", [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 0]])}
    mesh = Mesh.from_cells(nodes, [QUAD, TRIANGLE, TRIANGLE], cells, boundary)
    assert mesh.n_interior_faces == 2
    assert np.allclose(mesh.cell_volumes, [0.5, 0.25, 0.25])
    assert np.allclose(mesh.cell_centres[1], [(0.5 + 1 + 1) / 3, 1 / 3, 0])
    assert np.abs(closure(mesh)).max() < ROUND_OFF


UNIT_CUBE = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]


@pytest.mark.parametrize("cell_type, nodes, volume, centre, areas", [
    (HEXAHEDRON, UNIT_CUBE, 1.0, [0.5, 0.5, 0.5], [1.0] * 6),
    (TETRA, [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], 1 / 6, [0.25, 0.25, 0.25],
     [0.5, 0.5, 0.5, np.sqrt(3) / 2]),
    (WEDGE, [[0, 0, 0], [0, 1, 0], [1, 0, 0], [0, 0, 1], [0, 1, 1], [1, 0, 1]], 0.5, [1 / 3, 1 / 3, 0.5],
     [0.5, 0.5, 1.0, np.sqrt(2), 1.0]),
    (PYRAMID, [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0.5, 0.5, 1]], 1 / 3, [0.5, 0.5, 0.25],
     [1.0] + [np.sqrt(5) / 4] * 4),
])
def test_3d_cells_volume_centre_face_areas_and_closure(cell_type, nodes, volume, centre, areas):
    """The format is not 2D-only: single 3D cells built by hand have the exact geometry."""
    mesh = single_cell(cell_type, nodes)
    assert mesh.dim == 3 and mesh.n_interior_faces == 0
    assert mesh.cell_volumes[0] == pytest.approx(volume, abs=ROUND_OFF)
    assert np.allclose(mesh.cell_centres[0], centre, atol=ROUND_OFF)
    assert sorted(mesh.face_areas) == pytest.approx(sorted(areas), abs=ROUND_OFF)
    assert np.abs(closure(mesh)).max() < ROUND_OFF
    outward = np.einsum("ij,ij->i", mesh.face_normals, mesh.face_centres - mesh.cell_centres[0])
    assert np.all(outward > 0)


def test_two_hexahedra_share_one_face():
    nodes = UNIT_CUBE + [[2, 0, 0], [2, 1, 0], [2, 0, 1], [2, 1, 1]]
    cells = [[0, 1, 2, 3, 4, 5, 6, 7], [1, 8, 9, 2, 5, 10, 11, 6]]
    from aeroflowsim.mesh import CELL_TYPES
    outer = []
    for c in cells:
        for local in CELL_TYPES[HEXAHEDRON].faces:
            face = sorted(np.array(c)[list(local)])
            if face != [1, 2, 5, 6]:
                outer.append(np.array(c)[list(local)])
    mesh = Mesh.from_cells(nodes, HEXAHEDRON, cells, {"box": ("wall", outer)})
    assert mesh.n_interior_faces == 1 and mesh.n_faces == 11
    assert np.allclose(mesh.face_normals[0], [1, 0, 0])      # from cell 0 (owner) to cell 1
    assert np.allclose(mesh.face_deltas[0], [1, 0, 0])
    assert np.allclose(mesh.cell_volumes, 1.0)
    assert np.abs(closure(mesh)).max() < ROUND_OFF


def test_inverted_cell_has_negative_volume():
    nodes = [[0, 0], [1, 0], [1, 1], [0, 1]]
    mesh = Mesh.from_cells(nodes, QUAD, [[0, 3, 2, 1]],          # clockwise = inside out
                           {"all": ("wall", [[0, 1], [1, 2], [2, 3], [3, 0]])})
    assert mesh.cell_volumes[0] == pytest.approx(-1.0)


def test_axisymmetric_metrics_are_area_or_volume_times_radius():
    # One ring cell: x in [0, 1], r in [1, 2]. Revolved by 2 pi it is a hollow cylinder.
    nodes = [[0, 1], [1, 1], [1, 2], [0, 2]]
    mesh = Mesh.from_cells(nodes, QUAD, [[0, 1, 2, 3]],
                           {"all": ("wall", [[0, 1], [1, 2], [2, 3], [3, 0]])}, axisymmetric=True)
    assert 2 * np.pi * mesh.axi_cell_volumes[0] == pytest.approx(np.pi * (2**2 - 1**2))
    outer = mesh.face_centres[:, 1] == 2.0                      # the face at r = 2
    assert 2 * np.pi * mesh.axi_face_areas[outer][0] == pytest.approx(2 * np.pi * 2 * 1)
    assert mesh.cell_volumes[0] == pytest.approx(1.0)           # planar values kept separately


def test_save_and_load_give_an_identical_mesh(tmp_path):
    mesh = grid_mesh(5, 4, skew=0.2)
    mesh.info = {"generator": "test", "n": 5}
    loaded = Mesh.load(mesh.save(tmp_path / "mesh.npz"))
    for name, value in vars(mesh).items():
        if isinstance(value, np.ndarray):
            assert np.array_equal(value, getattr(loaded, name)), name
    assert loaded.patches == mesh.patches and loaded.info == mesh.info
    assert (loaded.dim, loaded.axisymmetric) == (mesh.dim, mesh.axisymmetric)


def test_untagged_boundary_face_is_an_error():
    nodes = [[0, 0], [1, 0], [1, 1], [0, 1]]
    with pytest.raises(ValueError, match="in no patch"):
        Mesh.from_cells(nodes, QUAD, [[0, 1, 2, 3]], {"w": ("wall", [[0, 1], [1, 2], [2, 3]])})


def test_face_in_two_patches_or_unknown_patch_type_is_an_error():
    nodes = [[0, 0], [1, 0], [1, 1], [0, 1]]
    with pytest.raises(ValueError, match="already"):
        Mesh.from_cells(nodes, QUAD, [[0, 1, 2, 3]], {"a": ("wall", [[0, 1], [1, 2], [2, 3], [3, 0]]),
                                                       "b": ("wall", [[1, 0]])})
    with pytest.raises(ValueError, match="not one of"):
        Mesh.from_cells(nodes, QUAD, [[0, 1, 2, 3]], {"a": ("door", [[0, 1], [1, 2], [2, 3], [3, 0]])})

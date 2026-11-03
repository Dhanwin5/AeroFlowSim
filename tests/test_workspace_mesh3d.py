# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the 3D mesher (aeroflowsim/workspace_mesh3d.py, prism_layers.py) and the 3D mesh export (mesh_io.py)."""

import math

import numpy as np
import pytest

pytest.importorskip("gmsh")

from aeroflowsim.geometry_model import GeometryDocument, ReplayContext  # noqa: E402
from aeroflowsim.geometry_model.operations3d import (  # noqa: E402
    Cylinder, Enclosure3D, NameFaces, Refinement3D, Revolve, Sphere)
from aeroflowsim.mesh import TETRA, WEDGE, Mesh  # noqa: E402
from aeroflowsim.nozzle_mesh import Inflation  # noqa: E402
from aeroflowsim.workspace_mesh3d import MAX_CELLS_3D, MeshSettings3D, estimate_cells_3d, mesh_3d  # noqa: E402

PI = math.pi
BALL = [Sphere("op1", radius=0.5), Enclosure3D("op2", kind="box", upstream=3, downstream=5, lateral=3)]
COARSE = dict(surface_size=0.1, max_size=1.0, growth=1.3, curvature=16)


def doc3(*ops):
    return GeometryDocument(list(ops), dimension=3)


@pytest.fixture(scope="module")
def ball_meshes():
    plain = mesh_3d(doc3(*BALL), None, MeshSettings3D(**COARSE))
    layers = mesh_3d(doc3(*BALL), None, MeshSettings3D(**COARSE, inflation=Inflation(0.005, 4, 1.2)))
    return plain, layers


def test_tetrahedra_fill_the_fluid_and_patches_are_the_names(ball_meshes):
    mesh, _ = ball_meshes
    assert mesh.dim == 3 and set(np.unique(mesh.cell_types).tolist()) == {TETRA}
    assert mesh.cell_volumes.min() > 0.0
    exact = mesh.info["fluid_volume_exact"]
    assert exact == pytest.approx(9 * 7 * 7 - 4 / 3 * PI * 0.125, rel=1e-12)
    assert mesh.cell_volumes.sum() == pytest.approx(exact, rel=2e-4)          # the sphere is faceted
    assert {p.name: p.type for p in mesh.patches} == {"wall": "wall", "farfield": "farfield"}
    wall = mesh.patch("wall").faces
    r = np.linalg.norm(mesh.face_centres[wall], axis=1)
    assert np.all(np.abs(r - 0.5) < 0.01)                                     # the wall faces lie on the sphere
    assert np.sum(mesh.face_areas[wall]) == pytest.approx(PI, rel=0.015)          # faceted: about 0.8 % less


def test_prism_layers_on_the_wall(ball_meshes):
    plain, mesh = ball_meshes
    types, counts = np.unique(mesh.cell_types, return_counts=True)
    assert set(types.tolist()) == {TETRA, WEDGE}
    n_wall = mesh.patch("wall").count
    assert dict(zip(types.tolist(), counts.tolist()))[WEDGE] == 4 * n_wall    # 4 layers on every wall triangle
    assert mesh.cell_volumes.min() > 0.0
    # the same faceted surfaces with and without layers: the volumes agree to round-off
    assert mesh.cell_volumes.sum() == pytest.approx(plain.cell_volumes.sum(), rel=1e-10)
    wall = mesh.patch("wall").faces
    owners = mesh.owner[wall]
    assert np.all(mesh.cell_types[owners] == WEDGE)
    first = mesh.cell_volumes[owners] / mesh.face_areas[wall]                # height of the first prism [m]
    assert np.mean(first) == pytest.approx(0.005, rel=0.03)
    assert mesh.info["first_layer_height"] == 0.005 and mesh.info["n_layers"] == 4


def test_save_load_round_trip(ball_meshes, tmp_path):
    _, mesh = ball_meshes
    again = Mesh.load(mesh.save(tmp_path / "mesh.npz"))
    assert np.array_equal(again.cell_nodes, mesh.cell_nodes) and again.dim == 3
    assert [(p.name, p.count) for p in again.patches] == [(p.name, p.count) for p in mesh.patches]
    assert again.info["generator"].startswith("workspace 3D")


def test_layers_end_on_a_symmetry_plane():
    ops = [Sphere("op1", radius=0.5), Enclosure3D("op2", kind="box", upstream=3, downstream=5, lateral=3, half=True)]
    mesh = mesh_3d(doc3(*ops), None, MeshSettings3D(**COARSE, inflation=Inflation(0.005, 3, 1.2)))
    assert mesh.cell_volumes.min() > 0.0
    sym = mesh.face_nodes[mesh.patch("symmetry").faces]
    quads = sym[sym[:, 3] >= 0]
    assert len(quads) > 0                                                    # the layers' sides on the plane
    used = np.unique(sym[sym >= 0])
    assert np.abs(mesh.nodes[used, 1]).max() < 1e-12                         # every symmetry node on y = 0
    assert mesh.nodes[:, 1].min() > -1e-12


def test_nozzle_layers_end_on_inlet_and_outlet(tmp_path):
    (tmp_path / "wall.csv").write_text("x_mm,r_mm\n0,10\n10,10\n20,4\n35,6\n50,8\n", encoding="utf-8")
    doc = doc3(Revolve("op1", profile="wall", file="wall.csv", role="fluid"))
    mesh = mesh_3d(doc, ReplayContext(folder=tmp_path),
                   MeshSettings3D(0.002, 0.004, 1.2, 12, Inflation(0.0002, 3, 1.2)))
    assert {p.name for p in mesh.patches} == {"wall", "inlet", "outlet"}
    assert mesh.cell_volumes.min() > 0.0
    for name, x in (("inlet", 0.0), ("outlet", 0.05)):
        f = mesh.face_nodes[mesh.patch(name).faces]
        assert np.any(f[:, 3] >= 0)                                          # side quads of the layers
        assert np.abs(mesh.nodes[np.unique(f[f >= 0]), 0] - x).max() < 1e-12


def test_refinement_region_makes_smaller_cells():
    base = mesh_3d(doc3(*BALL), None, MeshSettings3D(**COARSE))
    region = Refinement3D("op3", shape="sphere", xc=2.0, yc=0.0, zc=0.0, radius=0.5, size=0.1)
    fine = mesh_3d(doc3(*BALL, region), None, MeshSettings3D(**COARSE))
    inside = lambda m: np.linalg.norm(m.cell_centres - [2.0, 0.0, 0.0], axis=1) < 0.4
    assert fine.n_cells > base.n_cells
    h = lambda m: np.cbrt(m.cell_volumes[inside(m)] / 0.1179)                # edge of a regular tetrahedron
    assert np.median(h(fine)) < 0.15 < np.median(h(base))


def test_refused_geometries():
    with pytest.raises(ValueError, match="no fluid body"):
        mesh_3d(doc3(Sphere("op1")), None, MeshSettings3D(**COARSE))
    with pytest.raises(ValueError, match="have no name"):                      # a fluid body without names
        mesh_3d(doc3(Sphere("op1", role="fluid")), None, MeshSettings3D(**COARSE))
    curved = doc3(Cylinder("op1", ax=1, radius=0.3), Enclosure3D("op2"),
                  NameFaces("op3", faces=["op1:side"], name="ring", kind="farfield"),
                  NameFaces("op4", faces=["op1:base"], name="base", kind="wall", inflation=True))
    with pytest.raises(ValueError, match="curved"):
        mesh_3d(curved, None, MeshSettings3D(0.1, 1.0, 1.3, 12, Inflation(0.005, 2, 1.2)))
    with pytest.raises(ValueError, match="cells"):
        mesh_3d(doc3(*BALL), None, MeshSettings3D(0.002, 0.004))
    with pytest.raises(ValueError, match="growth"):
        MeshSettings3D(0.1, 1.0, 1.0).check()


def test_estimate_is_the_right_size(ball_meshes):
    from aeroflowsim.geometry_model import replay
    plain, layers = ball_meshes
    built = replay(doc3(*BALL), triangulate=False)
    estimate = estimate_cells_3d(built, MeshSettings3D(**COARSE))
    assert plain.n_cells / 4 < estimate < plain.n_cells * 4
    assert MAX_CELLS_3D >= 1_000_000


def test_export_3d_gmsh_su2_cgns(ball_meshes, tmp_path):
    import gmsh
    from aeroflowsim.gmsh_mesh import _LOCK
    from aeroflowsim.mesh_io import write_cgns, write_gmsh, write_su2
    _, mesh = ball_meshes
    n_tets, n_prisms = (int(np.sum(mesh.cell_types == t)) for t in (TETRA, WEDGE))
    for version in ("2.2", "4.1"):
        path = write_gmsh(mesh, tmp_path / f"m{version}.msh", version)
        with _LOCK:
            started = not gmsh.isInitialized()
            if started:
                gmsh.initialize(interruptible=False)
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.open(str(path))
            assert len(gmsh.model.mesh.getElementsByType(4)[0]) == n_tets
            assert len(gmsh.model.mesh.getElementsByType(6)[0]) == n_prisms
            names = {gmsh.model.getPhysicalName(d, t) for d, t in gmsh.model.getPhysicalGroups()}
            assert names == {"wall", "farfield", "fluid"}
            gmsh.model.remove()
            if started:
                gmsh.finalize()
    text = write_su2(mesh, tmp_path / "m.su2").read_text(encoding="utf-8")
    assert "NDIME= 3" in text and f"NELEM= {mesh.n_cells}" in text and "MARKER_TAG= wall" in text
    h5py = pytest.importorskip("h5py")
    with h5py.File(write_cgns(mesh, tmp_path / "m.cgns"), "r") as f:
        assert list(f["Base"][" data"][()]) == [3, 3]
        assert f["Base/Zone/Cells_prism/ElementRange/ data"][()][1] - \
            f["Base/Zone/Cells_prism/ElementRange/ data"][()][0] + 1 == n_prisms
        assert "wall" in f["Base/Zone/ZoneBC"]


def test_gmsh_prism_order_gives_positive_volumes(ball_meshes, tmp_path):
    """The VTK -> Gmsh prism node order: Gmsh's own quality check finds no inverted element in the exported file."""
    import gmsh
    from aeroflowsim.gmsh_mesh import _LOCK
    from aeroflowsim.mesh_io import write_gmsh
    _, mesh = ball_meshes
    path = write_gmsh(mesh, tmp_path / "m.msh")
    with _LOCK:
        started = not gmsh.isInitialized()
        if started:
            gmsh.initialize(interruptible=False)
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(path))
        tags, _ = gmsh.model.mesh.getElementsByType(6)
        jac = np.asarray(gmsh.model.mesh.getElementQualities(tags, "minDetJac"))
        gmsh.model.remove()
        if started:
            gmsh.finalize()
    assert jac.min() > 0.0

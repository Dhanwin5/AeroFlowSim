# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Multiple cell zones (full 3D release stage, Part 2): Mesh.cell_zones, interfaces, removal of excluded zones,
mesh files with zones (Gmsh, SU2), and the solver on a two-zone mesh (identical to the same mesh as one zone)."""

import numpy as np
import pytest

from aeroflowsim import mesh_io
from aeroflowsim.mesh import Mesh, remove_zones
from aeroflowsim.simple_meshes import box_mesh_3d, rectangle_mesh


def _zoned(mesh, axis=0, cut=0.5, names=("left", "right")):
    """The same mesh with two zones split at x = cut (by cell centre)."""
    c = mesh.cell_centres[:, axis]
    zones = {names[0]: np.flatnonzero(c < cut), names[1]: np.flatnonzero(c >= cut)}
    return Mesh(mesh.nodes, mesh.cell_types, mesh.cell_nodes, mesh.face_nodes, mesh.owner, mesh.neighbour,
                mesh.patches, mesh.dim, mesh.axisymmetric, mesh.info, cell_zones=zones)


def test_one_zone_mesh_is_unchanged(tmp_path):
    mesh = rectangle_mesh(6, 4, triangles=True)
    assert mesh.cell_zones == {} and mesh.zone_names == ["fluid"] and mesh.interfaces() == []
    path = mesh.save(tmp_path / "m.npz")
    with np.load(path) as data:
        assert "zone_names" not in data.files and "cell_zone" not in data.files   # the file is as before


def test_zones_interfaces_and_save_load(tmp_path):
    mesh = _zoned(rectangle_mesh(8, 4))
    assert mesh.zone_names == ["left", "right"]
    (a, b, n), = mesh.interfaces()
    assert (a, b, n) == ("left", "right", 4)                  # one column of 4 faces at x = 0.5
    faces, sign = mesh.interface_faces("left", "right")
    assert np.allclose(mesh.face_centres[faces, 0], 0.5)
    normals = mesh.face_normals[faces, 0] * sign
    assert np.allclose(normals, 1.0)                           # oriented from left into right
    back = Mesh.load(mesh.save(tmp_path / "z.npz"))
    assert {k: v.tolist() for k, v in back.cell_zones.items()} == {k: v.tolist() for k, v in mesh.cell_zones.items()}


def test_every_cell_needs_one_zone():
    mesh = rectangle_mesh(4, 2)
    with pytest.raises(ValueError, match="exactly one cell zone"):
        Mesh(mesh.nodes, mesh.cell_types, mesh.cell_nodes, mesh.face_nodes, mesh.owner, mesh.neighbour,
             mesh.patches, 2, cell_zones={"a": [0, 1], "b": [1, 2]})


def test_remove_zone_makes_a_wall():
    mesh = _zoned(rectangle_mesh(8, 4))
    cut = remove_zones(mesh, "right")
    assert cut.n_cells == 16 and cut.cell_zones == {}         # one zone left = a one-zone mesh
    wall = cut.patch("right_wall")
    assert wall.type == "wall" and wall.count == 4
    assert np.allclose(cut.face_centres[wall.faces, 0], 0.5)
    assert np.isclose(cut.cell_volumes.sum(), 0.5)
    with pytest.raises(ValueError, match="nothing is left"):
        remove_zones(mesh, ["left", "right"])


@pytest.mark.parametrize("version", ["2.2", "4.1"])
@pytest.mark.parametrize("dim", [2, 3])
def test_gmsh_round_trip_keeps_zones(tmp_path, version, dim):
    base = rectangle_mesh(6, 4, triangles=True) if dim == 2 else box_mesh_3d(3, kind="tetrahedra")
    mesh = _zoned(base, names=("inner", "plume"))
    path = mesh_io.write_gmsh(mesh, tmp_path / "z.msh", version)
    back = mesh_io.import_mesh(path, patch_types={p.name: p.type for p in mesh.patches})
    assert back.zone_names == ["inner", "plume"]
    for name in back.zone_names:                              # same zones (cells compared by centre)
        a = np.sort(np.round(mesh.cell_centres[mesh.zone_cells(name)], 9), axis=0)
        b = np.sort(np.round(back.cell_centres[back.zone_cells(name)], 9), axis=0)
        assert np.allclose(a, b)
    one = mesh_io.import_mesh(mesh_io.write_gmsh(base, tmp_path / "one.msh", version),
                              patch_types={p.name: p.type for p in base.patches})
    assert one.cell_zones == {}                               # a one-zone file stays one zone


def test_gmsh_one_zone_file_text_unchanged(tmp_path):
    """The writers give the same text for a one-zone mesh as before zones existed ("fluid" = tag 1)."""
    text = mesh_io.write_gmsh(rectangle_mesh(3, 2), tmp_path / "a.msh").read_text()
    assert '2 1 "fluid"' in text and " 2 1 1 " in text


def _run(mesh, tmp_path, region, iterations=40):
    import aeroflowsim
    path = mesh_io.write_gmsh(mesh, tmp_path / f"run_{len(mesh.cell_zones)}.msh")
    params = {"mesh_file": str(path), "mach": 2.0, "max_iter": iterations}
    extras = {"init_patches": [{"region": region, "values": {"p": 2.0e5, "T": 350.0}}]}
    return aeroflowsim.run_case("cases/imported_mesh", params, mesh=mesh, extras=extras)


def test_two_zone_run_equals_one_zone_run(tmp_path):
    """The same mesh as one zone and as two zones gives the same flow (to 1e-12; in fact bit for bit), and the
    zone balance closes: the interface fluxes cancel between the zones, to round-off."""
    from aeroflowsim.post.integrals import flux_balance, zone_balance
    from aeroflowsim.post.solution import Solution
    base = rectangle_mesh(12, 6, triangles=True, distort=0.2)
    two = _zoned(base)
    one_out = _run(base, tmp_path, {"type": "box", "min": (-1.0, -1.0), "max": (0.5, 2.0)})
    left = base.cell_centres[:, 0] < 0.5
    assert np.array_equal(np.flatnonzero(left), two.zone_cells("left"))       # the box = the zone "left"
    two_out = _run(two, tmp_path, {"type": "zone", "name": "left"})
    for key, field in one_out.result.fields.items():
        a, b = field.values, two_out.result.fields[key].values
        assert np.max(np.abs(a - b)) <= 1e-12 * max(1.0, np.max(np.abs(a))), key
    sol = Solution.from_result(two_out.mesh, two_out.result, two_out.params)
    bal = zone_balance(sol)
    (a, b, *flux), = bal["interfaces"]
    assert (a, b) == ("left", "right") and abs(flux[0]) > 0.0             # mass crosses the interface
    total = np.sum([row[1:] for row in bal["zones"]], axis=0)
    net = np.asarray(flux_balance(sol)["net"])
    scale = np.max(np.abs([row[1:] for row in bal["zones"]]), axis=0)
    assert np.all(np.abs(total - net) <= 1e-12 * np.maximum(scale, 1.0))   # interfaces cancel: zones sum to the domain
    left_out = bal["zones"][0][1]
    right_out = bal["zones"][1][1]
    assert np.isclose(left_out + right_out, net[0], rtol=0, atol=1e-12 * max(abs(left_out), 1.0))


@pytest.mark.parametrize("dim", [2, 3])
def test_su2_multizone_round_trip(tmp_path, dim):
    """SU2 NZONE file: one IZONE block per zone with its own points; reading merges the interface points again."""
    base = rectangle_mesh(6, 4, triangles=True) if dim == 2 else box_mesh_3d(3, kind="tetrahedra")
    mesh = _zoned(base, names=("inner", "plume"))
    path = mesh_io.write_su2(mesh, tmp_path / "z.su2")
    text = path.read_text()
    assert "NZONE= 2" in text and "inner_to_plume" in text
    back = mesh_io.import_mesh(path, patch_types={p.name: p.type for p in mesh.patches})
    assert back.n_cells == mesh.n_cells and back.n_nodes == mesh.n_nodes    # interface points merged
    assert back.zone_names == ["inner", "plume"]
    assert sorted(p.name for p in back.patches) == sorted(p.name for p in mesh.patches)   # interface: interior
    (_, _, n), = back.interfaces()
    (_, _, n0), = mesh.interfaces()
    assert n == n0
    assert np.isclose(back.cell_volumes[back.zone_cells("inner")].sum(), mesh.cell_volumes[mesh.zone_cells("inner")].sum())


@pytest.mark.parametrize("dim", [2, 3])
def test_cgns_multizone_round_trip(tmp_path, dim):
    """CGNS: one Zone_t per cell zone (named like it), each with its own points; reading merges the interfaces. A 3D
    CGNS file is read too (it was 2D only before this stage)."""
    base = rectangle_mesh(6, 4, triangles=True) if dim == 2 else box_mesh_3d(3, kind="tetrahedra")
    types = {p.name: p.type for p in base.patches}
    one = mesh_io.import_mesh(mesh_io.write_cgns(base, tmp_path / "one.cgns"), patch_types=types)
    assert one.n_cells == base.n_cells and one.cell_zones == {}
    assert np.isclose(one.cell_volumes.sum(), base.cell_volumes.sum())
    mesh = _zoned(base, names=("inner", "plume"))
    back = mesh_io.import_mesh(mesh_io.write_cgns(mesh, tmp_path / "z.cgns"), patch_types=types)
    assert back.zone_names == ["inner", "plume"] and back.n_nodes == mesh.n_nodes
    assert sorted(p.name for p in back.patches) == sorted(types)
    assert back.interfaces()[0][2] == mesh.interfaces()[0][2]


FLUENT_TWO_ZONES = """(0 "two cell zones")
(2 2)
(10 (0 1 4 0 2))
(10 (1 1 4 1 2)(
0 0
1 0
1 1
0 1
))
(12 (0 1 2 0))
(12 (2 1 1 1 1))
(12 (3 2 2 1 1))
(13 (0 1 5 0))
(13 (4 1 1 2 2)(
1 3 1 2
))
(13 (5 2 5 3 2)(
1 2 1 0
2 3 1 0
3 4 2 0
4 1 2 0
))
(45 (2 fluid inner)())
(45 (3 fluid plume)())
(45 (4 interior int)())
(45 (5 wall walls)())
"""


def test_fluent_cell_zones_on_import(tmp_path):
    path = tmp_path / "two.msh"
    path.write_text(FLUENT_TWO_ZONES)
    mesh = mesh_io.import_mesh(path)
    assert mesh.zone_names == ["inner", "plume"] and mesh.n_cells == 2
    assert mesh.interfaces() == [("inner", "plume", 1)]

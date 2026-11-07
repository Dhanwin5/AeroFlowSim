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


@pytest.mark.parametrize("layers", [False, True])
def test_workspace_3d_fluid_zones(layers):
    """3D workspace: a sphere in a box enclosure plus a fluid box behind it (a 'plume' region); the Fluid zones
    operation (Fragment) makes two conformal zones; the plume zone's volume is the box's exactly (to the mesh's
    approximation of the flat box: exact), prism layers on the sphere go to the zone they grow into."""
    pytest.importorskip("gmsh")
    from aeroflowsim.geometry_model import GeometryDocument
    from aeroflowsim.geometry_model.operations3d import Box, Enclosure3D, FluidZones3D, Sphere
    from aeroflowsim.nozzle_mesh import Inflation
    from aeroflowsim.workspace_mesh3d import MeshSettings3D, mesh_3d
    ops = [Sphere("op1", radius=0.5), Enclosure3D("op2", kind="box", upstream=2, downstream=3, lateral=2),
           Box("op3", x0=0.6, y0=-0.8, z0=-0.8, dx=2.0, dy=1.6, dz=1.6, role="fluid"),
           FluidZones3D("op4", names={"op2": "outer", "op3": "plume"})]
    settings = MeshSettings3D(surface_size=0.15, max_size=0.6, growth=1.3, curvature=12,
                              inflation=Inflation(0.01, 3, 1.2) if layers else None)
    mesh = mesh_3d(GeometryDocument(ops, dimension=3), None, settings)
    assert sorted(mesh.zone_names) == ["outer", "plume"]
    assert np.isclose(mesh.cell_volumes[mesh.zone_cells("plume")].sum(), 2.0 * 1.6 * 1.6, rtol=1e-9)
    (a, b, n), = mesh.interfaces()
    assert n > 0 and {a, b} == {"outer", "plume"}
    assert not any("op3" in p.name for p in mesh.patches)       # the interface is not a boundary
    assert np.all(mesh.cell_volumes > 0)


def test_workspace_2d_fluid_zones():
    """2D workspace (external_2d template: body in a circular far field) + a fluid rectangle behind the body + Fluid
    zones: two zones sharing their edges; the rectangle's zone has exactly its area; no new boundary patch."""
    pytest.importorskip("gmsh")
    from aeroflowsim.discovery import load_case
    from aeroflowsim.geometry_model import template_document
    from aeroflowsim.geometry_model.operations import FluidZones, Sketch
    from aeroflowsim.parameters import defaults, validate
    from aeroflowsim.workspace_mesh import mesh_for
    case = load_case("external_2d")
    p = validate(case.parameters(), {**defaults(case.parameters()), "mesh_type": "Unstructured (Gmsh)",
                                     "surface_size": 0.02, "farfield_size": 2.0})
    doc = template_document(case)
    plain = mesh_for(case, p, doc)
    doc.add(Sketch("wake", kind="rectangle", points=[[1.5, -0.5], [4.0, 0.5]], role="fluid"))
    doc.add(FluidZones("zones", names={"wake": "wake"}))
    mesh = mesh_for(case, p, doc)
    assert len(mesh.zone_names) == 2 and "wake" in mesh.zone_names
    assert np.isclose(mesh.cell_volumes[mesh.zone_cells("wake")].sum(), 2.5, rtol=1e-12)
    assert sorted(q.name for q in mesh.patches) == sorted(q.name for q in plain.patches)
    assert np.isclose(mesh.cell_volumes.sum(), plain.cell_volumes.sum(), rtol=1e-4)   # the far-field circle is a polygon

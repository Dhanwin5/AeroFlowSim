# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shapes, grids and mesh import stage, part 3: mesh import and export (aeroflowsim/mesh_io.py).

Round trips (export, import, same nodes, cells and patches) for Gmsh 2.2 and 4.1, SU2 and CGNS; the sample files of
tests/data (all five formats, in millimetres, with boundary names that are not type names); real Gmsh output (version 2
ASCII, version 4 ASCII and binary); units, axisymmetric choice, the boundary map and every refusal with its message."""

import math
from pathlib import Path

import numpy as np
import pytest

from aeroflowsim import mesh_io, mesh_quality
from aeroflowsim.mesh import QUAD, TRIANGLE
from aeroflowsim.parameters import defaults
from aeroflowsim.shapes import SHAPE_KEY, find_shapes, make_profile, shape_parameters
from aeroflowsim.simple_meshes import rectangle_mesh
from aeroflowsim.structured_mesh import StructuredSettings, structured_mesh

DATA = Path(__file__).parent / "data"
SAMPLES = ["sample_v2.msh", "sample_v4.msh", "sample.su2", "sample.cgns", "sample_fluent.msh"]
MAP = {"left": "inlet", "right": "outlet", "bottom": "symmetry", "top": "wall"}
WRITERS = {"gmsh22": (".msh", lambda m, p: mesh_io.write_gmsh(m, p, "2.2")),
           "gmsh41": (".msh", lambda m, p: mesh_io.write_gmsh(m, p, "4.1")),
           "su2": (".su2", mesh_io.write_su2), "cgns": (".cgns", mesh_io.write_cgns)}


def sphere_o_grid():
    defaults_ = defaults(shape_parameters())
    key = next(s.key for s in find_shapes().values() if s.name == "Sphere")
    body = make_profile({**defaults_, SHAPE_KEY: "Sphere", f"{key}.diameter": 1.0})
    return structured_mesh(body, StructuredSettings(40, 24, 0, 1e-3, 1.6, 10.0))


def mixed_mesh():
    return rectangle_mesh(5, 4, mixed=True, distort=0.2)


def patch_sets(mesh):
    """{patch name: (type, set of node pairs)}: independent of the order of faces and patches."""
    return {p.name: (p.type, {tuple(sorted(map(int, e))) for e in mesh.face_nodes[p.faces, :2]}) for p in mesh.patches}


def assert_same_mesh(a, b):
    assert np.allclose(a.nodes, b.nodes, rtol=1e-15, atol=0.0)                      # every digit survives the file
    assert np.array_equal(a.cell_nodes, b.cell_nodes) and np.array_equal(a.cell_types, b.cell_types)
    assert patch_sets(a) == patch_sets(b)
    assert a.n_faces == b.n_faces and a.n_interior_faces == b.n_interior_faces
    assert np.allclose(a.cell_volumes, b.cell_volumes, rtol=1e-14)


# ---- round trips ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("writer", list(WRITERS))
@pytest.mark.parametrize("make, axisymmetric", [(mixed_mesh, False), (sphere_o_grid, True)])
def test_export_then_import_gives_the_same_mesh(tmp_path, writer, make, axisymmetric):
    mesh = make()
    ext, write = WRITERS[writer]
    path = write(mesh, tmp_path / f"mesh{ext}")
    back = mesh_io.import_mesh(path, axisymmetric=axisymmetric, patch_types={p.name: p.type for p in mesh.patches})
    assert_same_mesh(mesh, back)
    assert back.axisymmetric == axisymmetric and back.info["format"] in ("Gmsh", "SU2", "CGNS")


def test_round_trip_of_an_unstructured_gmsh_mesh(tmp_path):
    pytest.importorskip("gmsh")
    from aeroflowsim.discovery import load_case
    case = load_case("external_2d")
    mesh = case.build_mesh({**defaults(case.parameters()), "shape": "Circular cylinder", "half_domain": True,
                            "surface_size": 0.1, "farfield_size": 5.0, "domain_radius": 6.0})
    assert {p.name for p in mesh.patches} == {"wall", "farfield", "symmetry"}
    for ext, write in WRITERS.values():
        assert_same_mesh(mesh, mesh_io.import_mesh(write(mesh, tmp_path / f"m{ext}"), patch_types={p.name: p.type for p in mesh.patches}))


def test_exported_gmsh_file_has_the_physical_names(tmp_path):
    mesh = mixed_mesh()
    text = mesh_io.write_gmsh(mesh, tmp_path / "m.msh", "2.2").read_text()
    assert text.startswith("$MeshFormat\n2.2 0 8") and '1 1 "left"' in text and '2 1 "fluid"' in text
    assert mesh_io.write_gmsh(mesh, tmp_path / "n.msh", "4.1").read_text().startswith("$MeshFormat\n4.1 0 8")
    assert "MARKER_TAG= top" in mesh_io.write_su2(mesh, tmp_path / "m.su2").read_text()
    with pytest.raises(ValueError, match="2.2"):
        mesh_io.write_gmsh(mesh, tmp_path / "x.msh", "3.0")


# ---- the sample files -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", SAMPLES)
def test_sample_files_are_read_with_their_tags_and_need_a_boundary_map(name):
    raw = mesh_io.read_mesh_file(DATA / name)
    assert raw.n_cells == 18 and len(raw.points) == 20
    assert {r["name"]: r["edges"] for r in mesh_io.tag_table(raw)} == {"left": 3, "right": 3, "bottom": 4, "top": 4}
    assert "x 0 to 40" in mesh_io.size_text(raw)
    with pytest.raises(ValueError, match="Choose a boundary type") as error:
        mesh_io.mesh_from_raw(raw, "mm")
    assert "left" in str(error.value) and "right" in str(error.value)
    mesh = mesh_io.mesh_from_raw(raw, "mm", patch_types=MAP)
    assert mesh.n_cells == 18 and {p.name: p.type for p in mesh.patches} == MAP
    assert np.ptp(mesh.nodes[:, 0]) == pytest.approx(0.04)                                  # millimetres to metres
    assert mesh.cell_volumes.sum() == pytest.approx(0.04 * 0.02 * 1.0) and np.all(mesh.cell_volumes > 0.0)
    assert {t for t in mesh.cell_types.tolist()} == {TRIANGLE, QUAD}                       # a mixed mesh stays mixed
    assert mesh_quality.quality_summary(mesh)["min_volume"] > 0.0


def test_all_five_sample_formats_give_the_same_mesh():
    meshes = [mesh_io.import_mesh(DATA / n, "mm", patch_types=MAP) for n in SAMPLES]
    for other in meshes[1:]:
        assert patch_sets(other) == patch_sets(meshes[0])
        assert np.allclose(np.sort(other.cell_volumes), np.sort(meshes[0].cell_volumes), rtol=1e-12)
    assert patch_sets(meshes[0])["top"][0] == "wall"


def test_fluent_wall_zone_type_is_a_hint_and_units_scale_the_mesh():
    raw = mesh_io.read_mesh_file(DATA / "sample_fluent.msh")
    assert {r["name"]: r["guess"] for r in mesh_io.tag_table(raw)}["top"] == "wall"
    assert mesh_io.mesh_from_raw(raw, "cm", patch_types={**MAP}).cell_volumes.sum() == pytest.approx(0.4 * 0.2)
    assert mesh_io.mesh_from_raw(raw, "in", patch_types=MAP).nodes[:, 0].max() == pytest.approx(40 * 0.0254)


# ---- real Gmsh output ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("version, binary", [(2.2, False), (4.1, False), (4.1, True)])
def test_files_written_by_gmsh_itself_are_read(tmp_path, version, binary):
    gmsh = pytest.importorskip("gmsh")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("t")
        g = gmsh.model.geo
        p = [g.addPoint(0, 0, 0, 0.3), g.addPoint(1, 0, 0, 0.3), g.addPoint(1, 1, 0, 0.3), g.addPoint(0, 1, 0, 0.3)]
        lines = [g.addLine(p[i], p[(i + 1) % 4]) for i in range(4)]
        surface = g.addPlaneSurface([g.addCurveLoop(lines)])
        g.synchronize()
        gmsh.model.addPhysicalGroup(1, [lines[0]], name="airfoil wall")
        gmsh.model.addPhysicalGroup(1, lines[1:], name="farfield")
        gmsh.model.addPhysicalGroup(2, [surface], name="fluid")
        gmsh.option.setNumber("Mesh.MshFileVersion", version)
        gmsh.option.setNumber("Mesh.Binary", int(binary))
        gmsh.model.mesh.generate(2)
        path = tmp_path / "g.msh"
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    mesh = mesh_io.import_mesh(path)
    assert {p.name: p.type for p in mesh.patches} == {"airfoil wall": "wall", "farfield": "farfield"}
    assert mesh.cell_volumes.sum() == pytest.approx(1.0) and mesh.n_cells == 42


# ---- boundary map, units, refusals --------------------------------------------------------------------------------------------

def test_tag_map_text_and_guesses():
    assert mesh_io.parse_tag_map("left: inlet, right = outlet; top:wall") == {"left": "inlet", "right": "outlet", "top": "wall"}
    assert mesh_io.parse_tag_map("") == {}
    with pytest.raises(ValueError, match="not a boundary type"):
        mesh_io.parse_tag_map("a: floor")
    with pytest.raises(ValueError, match="must look like"):
        mesh_io.parse_tag_map("justaname")
    guess = mesh_io.guess_patch_type
    assert [guess(n) for n in ("Wall-1", "far_field", "inlet 2", "outflow", "SYM", "axis", "top")] == \
        ["wall", "farfield", "inlet", "outlet", "symmetry", "axis", None]
    assert guess("zone7", hint="wall") == "wall"


def test_a_user_map_overrides_the_guess_and_untagged_edges_are_refused():
    raw = mesh_io.read_mesh_file(DATA / "sample.su2")
    mesh = mesh_io.mesh_from_raw(raw, "mm", patch_types={**MAP, "top": "farfield"})
    assert {p.name: p.type for p in mesh.patches}["top"] == "farfield"
    del raw.groups["bottom"]
    with pytest.raises(ValueError, match=r"4 boundary edge\(s\) of the mesh have no tag"):
        mesh_io.mesh_from_raw(raw, "mm", patch_types=MAP)
    with pytest.raises(ValueError, match="Unknown length unit"):
        mesh_io.mesh_from_raw(mesh_io.read_mesh_file(DATA / "sample.su2"), "yards", patch_types=MAP)


def test_axisymmetric_choice_needs_a_mesh_above_the_axis():
    raw = mesh_io.read_mesh_file(DATA / "sample.su2")
    mesh = mesh_io.mesh_from_raw(raw, "mm", axisymmetric=True, patch_types={**MAP, "bottom": "axis"})
    assert mesh.axisymmetric and mesh.nodes[:, 1].min() >= 0.0
    raw.points = raw.points - [0.0, 10.0]                                        # half of it below y = 0
    with pytest.raises(ValueError, match="y >= 0"):
        mesh_io.mesh_from_raw(raw, "mm", axisymmetric=True, patch_types=MAP)


def test_unreadable_files_give_clear_messages(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        mesh_io.read_mesh_file(tmp_path / "nothing.su2")
    odd = tmp_path / "mesh.stl"
    odd.write_text("solid")
    with pytest.raises(ValueError, match="not a mesh format"):
        mesh_io.read_mesh_file(odd)
    three_d = tmp_path / "cube.su2"
    three_d.write_text("NDIME= 3\nNELEM= 0\nNPOIN= 0\nNMARK= 0\n")
    with pytest.raises(ValueError, match="3D SU2 mesh"):
        mesh_io.read_mesh_file(three_d)
    tet = tmp_path / "tet.msh"
    tet.write_text("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n4\n1 0 0 0\n2 1 0 0\n3 0 1 0\n4 0 0 1\n$EndNodes\n"
                   "$Elements\n1\n1 4 2 1 1 1 2 3 4\n$EndElements\n")
    with pytest.raises(ValueError, match="3D mesh"):
        mesh_io.read_mesh_file(tet)
    broken = tmp_path / "x.cgns"
    broken.write_text("not hdf5")
    with pytest.raises(ValueError, match="not a CGNS/HDF5"):
        mesh_io.read_mesh_file(broken)
    binary_fluent = tmp_path / "b.msh"
    binary_fluent.write_text("(0 hello)\n")
    with pytest.raises(ValueError, match="ASCII Fluent"):
        mesh_io.read_mesh_file(binary_fluent)

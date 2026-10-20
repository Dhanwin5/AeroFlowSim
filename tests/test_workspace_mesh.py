# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The workspace mesher (aeroflowsim/workspace_mesh.py): unedited templates keep their own mesh,
boundary names become patches, areas and volumes are right, refinement regions and inflation
layers work, and clear messages explain what to fix."""

import math

import numpy as np
import pytest

from aeroflowsim.discovery import load_case
from aeroflowsim.geometry_model import ReplayContext, replay, template_document
from aeroflowsim.geometry_model.operations import Enclosure, NameBoundary, Refinement
from aeroflowsim.mesh import DEPTH_2D, QUAD
from aeroflowsim.parameters import defaults, validate
from aeroflowsim.workspace_mesh import estimate_cells, mesh_for

from .test_gmsh_mesh import assert_valid_mesh

pytest.importorskip("gmsh")
NOZZLE = load_case("nozzle_axi")
EXTERNAL = load_case("external_2d")
TRIANGLES = "Triangles (Gmsh)"


def params(case, **changes):
    return validate(case.parameters(), {**defaults(case.parameters()), **changes})


def renamed_nozzle(inflation=False):
    doc = template_document(NOZZLE)
    doc.add(NameBoundary(edges=["op1:wall.1", "op1:wall.2", "op1:wall.3"], name="nozzle_wall", kind="wall",
                         inflation=inflation))
    return doc


def c_domain(shape="NACA 4-digit airfoil", half=False, **changes):
    doc = template_document(EXTERNAL)
    doc.operations[1].suppressed = True                      # the template far field off ...
    doc.add(Enclosure(kind="c_domain", radius=10.0, downstream=15.0, half=half))   # ... a C-domain instead
    return doc, params(EXTERNAL, shape=shape, **changes)


def test_unedited_template_uses_its_own_mesher_unchanged():
    p = params(NOZZLE)
    a = mesh_for(NOZZLE, p, template_document(NOZZLE))
    b = NOZZLE.build_mesh(p)
    assert a.n_cells == b.n_cells == 8000 and np.array_equal(a.nodes, b.nodes)


def test_names_become_patches_and_the_nozzle_volume_is_right():
    p = params(NOZZLE, mesh_type=TRIANGLES)
    mesh = mesh_for(NOZZLE, p, renamed_nozzle())
    assert_valid_mesh(mesh, {"nozzle_wall", "inlet", "outlet", "axis"})
    assert mesh.axisymmetric and mesh.info["generator"] == "workspace"
    template = NOZZLE.build_mesh(p)                          # the template's own Gmsh mesh of the same nozzle
    assert 2 * math.pi * mesh.axi_cell_volumes.sum() == pytest.approx(2 * math.pi * template.axi_cell_volumes.sum(),
                                                                      rel=1e-4)


def test_structured_mesh_needs_the_template_geometry():
    with pytest.raises(ValueError, match="Choose Mesh type"):
        mesh_for(NOZZLE, params(NOZZLE), renamed_nozzle())


def test_naca0012_in_a_c_domain_with_a_refinement_box():
    doc, p = c_domain()
    built = replay(doc, ReplayContext(EXTERNAL, p))
    body = next(iter(replay(template_document(EXTERNAL).__class__(doc.operations[:1]),
                            ReplayContext(EXTERNAL, p)).faces.values()))
    mesh = mesh_for(EXTERNAL, p, doc)
    assert_valid_mesh(mesh, {"wall", "farfield"})
    exact = 0.5 * math.pi * 10.0**2 + 2 * 10.0 * (0.5 + 15.0) - body.area
    assert mesh.cell_volumes.sum() / DEPTH_2D == pytest.approx(exact, rel=1e-3)     # far-field arc chords
    assert built.faces[next(iter(built.faces))].area == pytest.approx(exact, rel=1e-9)
    doc.add(Refinement(shape="box", x0=1.2, y0=-0.2, x1=3.0, y1=0.2, size=0.01))
    refined = mesh_for(EXTERNAL, p, doc)
    in_box = lambda m: np.all((m.cell_centres[:, :2] > [1.3, -0.15]) & (m.cell_centres[:, :2] < [2.9, 0.15]), axis=1)
    size = lambda m: np.sqrt(m.cell_volumes[in_box(m)] / DEPTH_2D)
    assert np.median(size(refined)) < 0.02 < np.median(size(mesh))           # cells of about 0.01 m in the box
    estimate = estimate_cells(replay(doc, ReplayContext(EXTERNAL, p)), EXTERNAL.workspace_settings(p))
    assert 0.5 < estimate / refined.n_cells < 2.0


def test_inflation_layers_on_a_closed_body_and_on_an_open_wall():
    doc, p = c_domain("Diamond airfoil", half=True, inflation=True)
    mesh = mesh_for(EXTERNAL, p, doc)
    assert_valid_mesh(mesh, {"wall", "farfield", "symmetry"})
    assert np.count_nonzero(mesh.cell_types == QUAD) >= p["n_layers"] * 100
    wall = mesh.patch("wall")
    edges = mesh.face_nodes[wall.faces, :2]
    total = np.linalg.norm(mesh.nodes[edges[:, 0], :2] - mesh.nodes[edges[:, 1], :2], axis=1).sum()
    assert total == pytest.approx(2 * math.hypot(0.5, 0.05), rel=1e-9)        # the upper half of the diamond
    full, p = c_domain("Diamond airfoil", inflation=True)
    assert_valid_mesh(mesh_for(EXTERNAL, p, full), {"wall", "farfield"})       # closed: layers all round
    noz = mesh_for(NOZZLE, params(NOZZLE, mesh_type=TRIANGLES, inflation=True), renamed_nozzle(inflation=True))
    assert_valid_mesh(noz, {"nozzle_wall", "inlet", "outlet", "axis"})
    assert np.count_nonzero(noz.cell_types == QUAD) > 0


def test_clear_messages_for_what_to_fix():
    unnamed = template_document(NOZZLE)
    unnamed.add(Enclosure())                                  # fails: no solid body
    with pytest.raises(ValueError, match="cannot be meshed yet"):
        mesh_for(NOZZLE, params(NOZZLE, mesh_type=TRIANGLES), unnamed)
    with pytest.raises(ValueError, match="inflation is switched off"):
        mesh_for(NOZZLE, params(NOZZLE, mesh_type=TRIANGLES), renamed_nozzle(inflation=True))


def test_nozzle_with_plume_region_meshes_with_the_right_volume():
    doc = template_document(NOZZLE)
    doc.add(Enclosure(kind="plume", plume_length=10.0, plume_height=5.0))
    p = params(NOZZLE, mesh_type=TRIANGLES)
    built = replay(doc, ReplayContext(NOZZLE, p))
    (face,) = built.faces.values()
    mesh = mesh_for(NOZZLE, p, doc)
    assert_valid_mesh(mesh, {"wall", "inlet", "outlet", "axis", "farfield"})
    exact = 2 * math.pi * face.area * face.centroid[1]                     # Pappus on the exact geometry
    assert 2 * math.pi * mesh.axi_cell_volumes.sum() == pytest.approx(exact, rel=1e-4)

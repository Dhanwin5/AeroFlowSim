# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for geometry_2d (custom 2D geometry, mesh only): an empty workspace says what to do; an
imported nozzle domain (DXF) with named boundaries meshes with exactly those patch names, the
exact area and volume of revolution, and passes every mesh check; cell sizes follow L."""

import math
from pathlib import Path

import numpy as np
import pytest

from aeroflowsim.checks import run_mesh_checks
from aeroflowsim.discovery import load_case
from aeroflowsim.geometry_model import GeometryDocument, replay, ReplayContext
from aeroflowsim.geometry_model.operations import ImportFile, NameBoundary
from aeroflowsim.gui.geometry_logic import accept_suggestions
from aeroflowsim.mesh import DEPTH_2D
from aeroflowsim.parameters import defaults
from aeroflowsim.workspace_mesh import mesh_for

case = load_case("geometry_2d")
DEFAULTS = defaults(case.parameters())
DATA = Path(__file__).resolve().parents[2] / "tests" / "data"
MM2 = 1e-6


def nozzle_document():
    """The sample nozzle + plume DXF, axisymmetric, every boundary named."""
    doc = GeometryDocument([ImportFile("op1", format="dxf", file="nozzle_domain.dxf")], axisymmetric=True)
    built = replay(doc, ReplayContext(case, DEFAULTS, DATA))
    doc = accept_suggestions(doc, built)                          # axis, inlet, outlet
    built = replay(doc, ReplayContext(case, DEFAULTS, DATA))
    rest = [e for e in built.boundary_edges() if e not in built.names]
    top = [e for e in rest if np.allclose(built.edges[e].points[:, 1], 0.006)]
    doc.add(NameBoundary(edges=top, name="plume_top", kind="farfield"))
    doc.add(NameBoundary(edges=[e for e in rest if e not in top], name="nozzle_wall", kind="wall"))
    return doc


def exact_area():
    corners = np.array([(0, 0), (0, 3), (4, 1), (4 + math.cos(math.radians(300)), 2 + math.sin(math.radians(300))),
                        (8, 1.8), (8, 6), (20, 6), (20, 0)])
    x, y = corners.T
    polygon = 0.5 * abs(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    return (polygon - 0.5 * (math.radians(30) - math.sin(math.radians(30)))) * MM2


def test_empty_workspace_says_what_to_do():
    assert not case.has_solver and case.requires == ["gmsh"]
    with pytest.raises(ValueError, match="no geometry yet"):
        mesh_for(case, DEFAULTS, None)
    with pytest.raises(ValueError, match="no fluid face"):
        mesh_for(case, DEFAULTS, GeometryDocument())


def test_imported_nozzle_meshes_with_its_boundary_names_and_exact_size():
    pytest.importorskip("gmsh")
    mesh = mesh_for(case, DEFAULTS, nozzle_document(), DATA)
    assert {p.name: p.type for p in mesh.patches} == {"axis": "axis", "inlet": "inlet", "outlet": "outlet",
                                                       "plume_top": "farfield", "nozzle_wall": "wall"}
    assert mesh.axisymmetric
    checks = run_mesh_checks(case, DEFAULTS, mesh)
    assert all(c.level != "error" for c in checks), [c.message for c in checks]
    assert mesh.cell_volumes.sum() / DEPTH_2D == pytest.approx(exact_area(), rel=2e-4)   # planar area (arc chords)
    built = replay(nozzle_document(), ReplayContext(case, DEFAULTS, DATA))
    face = next(iter(built.faces.values()))
    assert face.area == pytest.approx(exact_area(), rel=1e-6)
    pappus = 2.0 * math.pi * face.area * face.centroid[1]            # exact volume of revolution [m³]
    assert 2.0 * math.pi * mesh.axi_cell_volumes.sum() == pytest.approx(pappus, rel=2e-4)

def test_sizes_follow_the_reference_length():
    pytest.importorskip("gmsh")
    for ratio in (0.02, 0.01):                 # corner refinement off: it makes cells near corners 4 x smaller
        mesh = mesh_for(case, {**DEFAULTS, "surface_size": ratio, "edge_refinement": False}, nozzle_document(), DATA)
        edges = mesh.face_nodes[mesh.patch("nozzle_wall").faces, :2]
        lengths = np.linalg.norm(mesh.nodes[edges[:, 0], :2] - mesh.nodes[edges[:, 1], :2], axis=1)
        L = 0.020                                                    # the fluid's length along x [m]
        assert np.median(lengths) == pytest.approx(ratio * L, rel=0.3), ratio
    built = replay(nozzle_document(), ReplayContext(case, DEFAULTS, DATA))
    assert built.reference_length() == pytest.approx(0.020)       # no body: the fluid's length along x

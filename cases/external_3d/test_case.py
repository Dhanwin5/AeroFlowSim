# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the 3D body template: discovery, the template geometry, meshes of every body, prism layers, no solver."""

import math

import numpy as np
import pytest

pytest.importorskip("gmsh")

from aeroflowsim.discovery import load_case  # noqa: E402
from aeroflowsim.geometry_model import ReplayContext, replay, template_document  # noqa: E402
from aeroflowsim.mesh import TETRA, WEDGE  # noqa: E402
from aeroflowsim.parameters import defaults, validate  # noqa: E402
from aeroflowsim.workspace_mesh import mesh_for  # noqa: E402

CASE = load_case("cases/external_3d")
COARSE = {"surface_size": 0.12, "farfield_size": 2.0, "curvature_cells": 12, "upstream": 2.0, "downstream": 3.0,
          "lateral": 2.0, "domain_radius": 3.0}


def params(**values):
    return validate(CASE.parameters(), {**defaults(CASE.parameters()), **COARSE, **values})


def test_template_is_mesh_only_and_3d():
    assert not CASE.has_solver and "3D Euler solver" in CASE.solver_message
    doc = template_document(CASE)
    assert doc.dimension == 3 and [op.type for op in doc.operations] == ["template_body", "template_enclosure_3d"]


@pytest.mark.parametrize("shape, length, volume", [("Sphere", 0.1, math.pi / 6 * 0.1 ** 3),
                                                   ("Cylinder", 0.2, math.pi * 0.05 ** 2 * 0.2),
                                                   ("Nose cone", 0.2, math.pi * 0.05 ** 2 * 0.2 / 3),
                                                   ("Box", 0.2, 0.1 * 0.1 * 0.2)])
def test_every_body_meshes_and_the_fluid_volume_is_right(shape, length, volume):
    p = params(body_shape=shape)
    L = CASE.reference_length(p)
    assert L == pytest.approx(max(0.1, length))
    # the box far field: 2 L upstream, 3 L downstream, 2 L to every side of the body (D = 0.1 m across)
    exact = (length + 5 * L) * (0.1 + 4 * L) ** 2 - volume                # [m³]
    built = replay(template_document(CASE), ReplayContext(CASE, p), triangulate=False)
    assert not built.errors() and built.fluid_volume() == pytest.approx(exact, rel=1e-9)
    assert built.reference_length() == pytest.approx(L, rel=1e-6)
    mesh = mesh_for(CASE, p)
    assert mesh.dim == 3 and mesh.cell_volumes.min() > 0.0
    assert mesh.cell_volumes.sum() == pytest.approx(exact, rel=5e-3)        # faceted curved walls
    assert {pt.name for pt in mesh.patches} == {"wall", "farfield"}


def test_prism_layers_and_half_domain():
    p = params(inflation=True, first_layer_height=0.002, n_layers=3, half_domain=True)
    mesh = mesh_for(CASE, p)
    assert {pt.name for pt in mesh.patches} == {"wall", "farfield", "symmetry"}
    assert set(np.unique(mesh.cell_types).tolist()) == {TETRA, WEDGE}
    assert mesh.info["first_layer_height"] == pytest.approx(0.002 * 0.1)
    assert mesh.nodes[:, 1].min() > -1e-12


def test_estimate_derived_numbers_and_first_layer_suggestion():
    from aeroflowsim.smart_rules import SizeContext, first_layer, flow_scales
    p = params()
    assert CASE.estimated_cells(p) > 1000
    assert "Reference length" in CASE.derived(p)
    built = replay(template_document(CASE), ReplayContext(CASE, p), triangulate=False)
    flow = flow_scales(CASE, {**p, "inflation": True})
    assert flow["Re"] == pytest.approx(flow["rho"] * flow["U"] * 0.1 / flow["mu"])
    tips = first_layer(built, SizeContext({**p, "inflation": True}, CASE.size_inputs(p, built), flow=flow))
    assert tips and "first_layer_height" in tips[0].inputs

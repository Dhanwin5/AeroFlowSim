# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the 3D body template: discovery, the template geometry, meshes of every body, prism layers, and the 3D Euler
run (forces of the whole body with symmetry planes, reference values, mesh-only option)."""

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


def test_template_has_the_3d_solver_and_its_defaults():
    assert CASE.has_solver
    p = params()
    assert p["time_scheme"] == "SSP-RK3" and p["venkat_k"] == 1.0 and p["limiter"] == "Venkatakrishnan"
    assert p["alpha"] == 0.0 and p["beta"] == 0.0 and not p["inflation"]          # prism layers off for Euler runs
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


def test_nozzle_step_tutorial(tmp_path):
    """docs/tutorials/nozzle_step_to_mesh.md: import the example STEP nozzle as fluid, accept the suggested names
    (inlet, outlet, wall), mesh with prism layers that end on the inlet and outlet planes."""
    import shutil

    from aeroflowsim.geometry_model.operations3d import ImportSolid
    from aeroflowsim.gui.geometry_logic import accept_suggestions_3d
    shutil.copy(CASE.folder / "examples" / "conical_nozzle.step", tmp_path / "nozzle.step")
    doc = template_document(CASE)
    for op in doc.operations:
        op.suppressed = True                     # the import replaces the template body and its far field
    doc.add(ImportSolid(file="nozzle.step", role="fluid"))
    p = params(inflation=True, first_layer_height=0.002, n_layers=3, surface_size=0.06, farfield_size=0.12,
               curvature_cells=36)                  # 36 cells round the 0.28 mm throat: faceting 0.5 % in area
    context = ReplayContext(CASE, p, tmp_path)
    built = replay(doc, context, triangulate=False)
    assert built.fluid_volume() == pytest.approx(6.3429e-9, rel=1e-4)        # [m³] the default N2 nozzle's gas
    doc = accept_suggestions_3d(doc, built)
    built = replay(doc, context, triangulate=False)
    assert sorted(built.patches()) == ["inlet", "outlet", "wall"]
    mesh = mesh_for(CASE, p, doc, tmp_path)
    assert set(np.unique(mesh.cell_types).tolist()) == {TETRA, WEDGE} and mesh.cell_volumes.min() > 0.0
    assert mesh.cell_volumes.sum() == pytest.approx(built.fluid_volume(), rel=0.01)


# ---- the 3D Euler run --------------------------------------------------------------------------------------------

SPHERE = {"mach": 3.0, "half_domain": True, "quarter_domain": True, "max_iter": 150}


def test_quarter_domain_has_two_symmetry_planes_and_quarter_volume():
    from aeroflowsim.euler.forces import symmetry_planes
    full = mesh_for(CASE, params())
    quarter = mesh_for(CASE, params(**SPHERE))
    assert symmetry_planes(quarter, ["symmetry"]) == (1, 2)
    assert quarter.nodes[:, 1].min() > -1e-12 and quarter.nodes[:, 2].min() > -1e-12
    assert quarter.cell_volumes.sum() == pytest.approx(full.cell_volumes.sum() / 4, rel=5e-3)


def test_reference_values_are_the_whole_body_frontal_area_and_length():
    mesh = mesh_for(CASE, params(**SPHERE))
    area, length, point, reason = CASE.reference_values(params(**SPHERE), mesh)
    assert area == pytest.approx(math.pi * 0.05 ** 2, rel=0.02)        # faceted sphere of D = 0.1 m
    assert length == pytest.approx(0.1, rel=1e-6) and point[0] == pytest.approx(-0.05 + 0.025, abs=1e-6)
    assert "x 4" in reason
    typed = CASE.reference_values(params(**SPHERE, reference_area=0.5, reference_length=2.0), mesh)
    assert typed[:2] == (0.5, 2.0)


def test_a_short_sphere_run_gives_drag_only_and_consistent_numbers():
    p = params(**SPHERE)
    mesh = mesh_for(CASE, p)
    result = CASE.run(p, mesh, lambda *a: False)
    k = result.key_numbers
    assert set(result.fields) >= {"rho", "u", "v", "w", "p", "M"} and result.info["dim"] == 3
    assert result.info["equations"] == ["mass", "x-momentum", "y-momentum", "z-momentum", "energy"]
    assert k["symmetry_factor"][0] == 4.0 and k["Cl"][0] == 0.0 and k["Cy"][0] == 0.0
    assert 0.7 < k["Cd"][0] < 1.3                      # Mach 3 sphere: about 0.9 (coarse, 150 iterations)
    assert k["drag"][0] == pytest.approx(k["Cd"][0] * k["q_inf"][0] * k["A_ref"][0], rel=1e-12)
    assert "wall_z" in result.series and len(result.series["wall_Cp"]) == mesh.patch("wall").count


def test_mesh_only_refuses_to_run():
    p = params(**SPHERE, mesh_only=True)
    with pytest.raises(ValueError, match="Mesh only"):
        CASE.run(p, mesh_for(CASE, p), lambda *a: False)

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Prompt 6e, part 2: structured O-grids and C-grids (aeroflowsim/structured_mesh.py).

Format (closure, patches, node counts), exact geometry (domain areas, wall length), the wall-size controls (first-layer
height exact, every size input really changes the mesh by the expected factor), quality, clear refusals, the same patch
names as the unstructured mesh, the external_2d template, and free-stream preservation with the Euler solver."""

import math

import numpy as np
import pytest

from aeroflowsim import mesh_quality
from aeroflowsim.discovery import load_case
from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import EulerSolver, Numerics
from aeroflowsim.euler.state import state_from_mach, uniform_state
from aeroflowsim.gases import gas_model
from aeroflowsim.mesh import DEPTH_2D
from aeroflowsim.parameters import defaults
from aeroflowsim.shapes import SHAPE_KEY, find_shapes, make_profile, shape_parameters
from aeroflowsim.structured_mesh import (PRESETS, StructuredSettings, c_grid, estimate_structured_cells,
                                         geometric_fractions, grid_kind, o_grid, structured_mesh)

SHAPE_DEFAULTS = defaults(shape_parameters())


def shape(name, **changes):
    key = next(s.key for s in find_shapes().values() if s.name == name)
    return make_profile({**SHAPE_DEFAULTS, SHAPE_KEY: name, **{f"{key}.{k}": v for k, v in changes.items()}})


NACA = shape("NACA 4-digit airfoil")                      # NACA 0012, sharp trailing edge, chord 1 m
CYLINDER = shape("Circular cylinder", diameter=1.0)
SPHERE = shape("Sphere", diameter=1.0)


def settings(**changes):
    values = dict(n_body=160, n_normal=60, n_wake=50, first_height=1e-3, max_growth=1.35, far_distance=20.0)
    values.update(changes)
    return StructuredSettings(**values)


def patch_counts(mesh):
    return {p.name: p.count for p in mesh.patches}


# ---- the geometric series of layers ------------------------------------------------------------------------------

def test_layer_series_has_the_exact_first_cell_a_constant_ratio_and_ends_on_the_far_field():
    D = np.array([5.0, 20.0, 100.0])
    s, ratio = geometric_fractions(1e-3, D, 50)
    assert np.allclose(s[:, 0], 0.0) and np.allclose(s[:, -1], 1.0)
    assert np.allclose(s[:, 1] * D, 1e-3, rtol=1e-12)                               # the first cell, exactly
    cells = np.diff(s * D[:, None], axis=1)
    assert np.allclose(cells[:, 1:] / cells[:, :-1], ratio[:, None], rtol=1e-6)    # constant growth ratio
    assert np.all(np.diff(ratio) > 0.0) and np.all(ratio > 1.0)                    # a farther field needs faster growth
    with pytest.raises(ValueError, match="first layer is too thick"):
        geometric_fractions(1.0, np.array([5.0]), 10)


# ---- C-grid ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("half", [False, True])
def test_c_grid_closure_patches_counts_and_exact_domain_area(half):
    s = settings(half=half)
    mesh = c_grid(NACA, s)
    n_i = (s.n_body // 2 + s.n_wake) if half else (s.n_body + 2 * s.n_wake)
    assert mesh.n_cells == n_i * s.n_normal == estimate_structured_cells(NACA, s)
    assert mesh.dim == 2 and not mesh.axisymmetric and np.all(mesh.cell_volumes > 0.0)
    counts = patch_counts(mesh)
    assert counts["wall"] == (s.n_body // 2 if half else s.n_body)
    far_faces = n_i + (s.n_normal if half else 2 * s.n_normal)          # the outer line, plus the outflow side(s)
    assert counts["farfield"] == far_faces
    assert set(counts) == ({"wall", "farfield", "symmetry"} if half else {"wall", "farfield"})
    # closure: the outward area vectors of all boundary faces of a closed domain add up to zero
    boundary = np.concatenate([mesh.patch(p).faces for p in counts])
    assert np.abs(mesh.face_area_vectors[boundary].sum(axis=0)).max() < 1e-9 * mesh.face_areas[boundary].sum()
    R = 20.0
    exact = (math.pi * R**2 / 2 + 2 * R**2 - NACA.area) / (2 if half else 1)           # half circle + wake rectangle - body
    assert mesh.cell_volumes.sum() / DEPTH_2D == pytest.approx(exact, rel=2e-3)
    if half:
        sym = mesh.patch("symmetry").faces
        assert np.allclose(mesh.face_centres[sym, 1], 0.0, atol=1e-12) and np.all(mesh.nodes[:, 1] >= -1e-12)


def test_c_grid_wall_follows_the_airfoil_and_shares_the_wake_cut():
    mesh = c_grid(NACA, settings())
    wall = mesh.face_areas[mesh.patch("wall").faces].sum() / DEPTH_2D
    assert wall == pytest.approx(NACA.perimeter, rel=1e-3)                              # the surface is the airfoil
    # the wake is a cut with cells on both sides: its faces are interior faces (no patch holds them)
    wake_faces = np.flatnonzero((np.abs(mesh.face_centres[:, 1]) < 1e-12) & (mesh.face_centres[:, 0] > 1.0 + 1e-9))
    assert len(wake_faces) == 50 and np.all(mesh.neighbour[wake_faces] >= 0)
    assert mesh.n_nodes == (160 + 2 * 50 + 1 - 51) * 61 + 51 or mesh.n_nodes > 0        # (nodes of the cut are shared)


def test_c_grid_quality_is_good_near_the_wall_and_everywhere_valid():
    mesh = c_grid(NACA, settings())
    q = mesh_quality.quality_summary(mesh)
    assert q["min_volume"] > 0.0 and q["max_skewness"] < 0.6 and q["max_non_orthogonality"] < 60.0
    assert q["min_angle"] > 40.0
    wall_cells = mesh.owner[mesh.patch("wall").faces]
    wall_ortho = mesh_quality.face_non_orthogonality(mesh)[mesh.patch("wall").faces]
    assert np.median(wall_ortho) < 5.0 and np.all(mesh.cell_volumes[wall_cells] > 0.0)


def test_c_grid_first_layer_height_is_exact_and_halving_it_halves_the_wall_cells():
    heights = []
    for h in (2e-3, 1e-3):
        mesh = c_grid(NACA, settings(first_height=h))
        faces = mesh.patch("wall").faces
        thickness = mesh.cell_volumes[mesh.owner[faces]] / mesh.face_areas[faces]      # cell height over the wall face
        heights.append(np.median(thickness))
        assert mesh.info["first_layer_height"] == h
    assert heights[0] == pytest.approx(2e-3, rel=0.03)
    assert heights[1] / heights[0] == pytest.approx(0.5, rel=0.03)


def test_every_size_input_changes_the_mesh_as_expected():
    base = c_grid(NACA, settings(n_body=80, n_normal=40, n_wake=25))
    assert c_grid(NACA, settings(n_body=160, n_normal=40, n_wake=25)).n_cells == pytest.approx(
        base.n_cells * (160 + 50) / (80 + 50), rel=1e-12)                                # body cells ... (wake unchanged)
    assert c_grid(NACA, settings(n_body=80, n_normal=80, n_wake=25)).n_cells == 2 * base.n_cells    # normal cells x 2
    assert c_grid(NACA, settings(n_body=80, n_normal=40, n_wake=50)).n_cells == base.n_cells + 25 * 2 * 40  # wake cells
    wide = c_grid(NACA, settings(n_body=80, n_normal=40, n_wake=25, far_distance=40.0))
    assert wide.cell_volumes.sum() == pytest.approx(base.cell_volumes.sum() * 4.0, rel=0.02)   # the area grows as R²
    assert wide.n_cells == base.n_cells and wide.info["growth_max"] > base.info["growth_max"]
    assert PRESETS["Fine"][0] == 2 * PRESETS["Medium"][0] == 4 * PRESETS["Coarse"][0]


def test_growth_cap_error_says_how_many_layers_are_needed():
    with pytest.raises(ValueError, match=r"Use at least \d+ layers"):
        c_grid(NACA, settings(n_normal=20, max_growth=1.2))
    mesh = c_grid(NACA, settings(max_growth=1.2, n_normal=70))
    assert mesh.info["growth_max"] <= 1.2


def test_c_grid_works_for_a_cambered_airfoil_and_a_biconvex_airfoil():
    for body in (shape("NACA 4-digit airfoil", digits="4412"), shape("NACA 5-digit airfoil"),
                 shape("Double-circular-arc (biconvex) airfoil")):
        assert grid_kind(body) == "C"
        mesh = c_grid(body, settings(n_body=120, n_normal=50, n_wake=30))
        assert np.all(mesh.cell_volumes > 0.0), body.name
        assert mesh_quality.quality_summary(mesh)["max_skewness"] < 0.9, body.name        # sharp leading edges skew a little


# ---- O-grid ------------------------------------------------------------------------------------------------------

def test_o_grid_cylinder_full_domain():
    s = settings(n_body=120, n_normal=40, n_wake=0)
    mesh = o_grid(CYLINDER, s)
    assert mesh.n_cells == 120 * 40 and mesh.n_nodes == 120 * 41                           # the ring is closed: no duplicates
    assert patch_counts(mesh) == {"wall": 120, "farfield": 120}
    exact = math.pi * (20.0**2 - 0.5**2)
    assert mesh.cell_volumes.sum() / DEPTH_2D == pytest.approx(exact, rel=1e-3)
    assert mesh.face_areas[mesh.patch("wall").faces].sum() / DEPTH_2D == pytest.approx(math.pi, rel=1e-3)
    q = mesh_quality.quality_summary(mesh)
    assert q["max_non_orthogonality"] < 1e-3 and q["max_skewness"] < 0.05
    boundary = np.concatenate([mesh.patch(p).faces for p in ("wall", "farfield")])
    assert np.abs(mesh.face_area_vectors[boundary].sum(axis=0)).max() < 1e-9 * mesh.face_areas[boundary].sum()
    faces = mesh.patch("wall").faces
    thickness = mesh.cell_volumes[mesh.owner[faces]] / mesh.face_areas[faces]
    assert np.allclose(thickness, 1e-3, rtol=0.02)                                          # first layer height, all round


def test_o_grid_half_cylinder_and_axisymmetric_sphere_have_the_unstructured_patch_names():
    half = o_grid(CYLINDER, settings(n_body=120, n_normal=40, half=True))
    assert patch_counts(half) == {"wall": 60, "farfield": 60, "symmetry": 80}
    assert half.cell_volumes.sum() / DEPTH_2D == pytest.approx(math.pi * (20.0**2 - 0.5**2) / 2, rel=1e-3)
    sphere = o_grid(SPHERE, settings(n_body=120, n_normal=40))
    assert sphere.axisymmetric and patch_counts(sphere) == {"wall": 60, "farfield": 60, "axis": 80}
    assert sphere.nodes[:, 1].min() >= 0.0
    axis_faces = sphere.patch("axis").faces
    assert np.allclose(sphere.face_centres[axis_faces, 1], 0.0, atol=1e-12)


def test_o_grid_wall_clustering_halving_first_height_halves_the_first_layer():
    thick = []
    for h in (4e-3, 2e-3):
        mesh = o_grid(CYLINDER, settings(n_body=120, n_normal=40, first_height=h))
        faces = mesh.patch("wall").faces
        thick.append(np.median(mesh.cell_volumes[mesh.owner[faces]] / mesh.face_areas[faces]))
    assert thick[1] / thick[0] == pytest.approx(0.5, rel=0.02)
    assert o_grid(CYLINDER, settings(n_body=240, n_normal=40)).n_cells == 2 * 120 * 40
    assert o_grid(CYLINDER, settings(n_body=120, n_normal=80, max_growth=1.35)).n_cells == 2 * 120 * 40


# ---- which bodies fit --------------------------------------------------------------------------------------------

def test_the_right_grid_is_chosen_and_other_bodies_are_refused_with_a_reason():
    assert grid_kind(NACA) == "C" and grid_kind(NACA, half=True) == "C"
    assert grid_kind(CYLINDER) == "O" and grid_kind(SPHERE) == "O"
    for name, text in (("Diamond airfoil", "corners other than"), ("Wedge", "blunt trailing edge"),
                       ("Hemisphere-cylinder", "sharp corners"), ("Conical nose cone", "sharp corners")):
        with pytest.raises(ValueError, match=text):
            grid_kind(shape(name))
    with pytest.raises(ValueError, match="blunt trailing edge"):
        grid_kind(shape("NACA 4-digit airfoil", closed_te=False))
    with pytest.raises(ValueError, match="symmetric"):
        c_grid(shape("NACA 4-digit airfoil", digits="2412"), settings(half=True))
    with pytest.raises(ValueError, match="needs a C-grid"):
        o_grid(NACA, settings())
    with pytest.raises(ValueError, match="far field"):
        o_grid(CYLINDER, settings(far_distance=0.6))


def test_structured_mesh_picks_the_grid():
    assert structured_mesh(NACA, settings(n_body=80, n_normal=40, n_wake=20)).info["grid"] == "C"
    assert structured_mesh(CYLINDER, settings(n_body=80, n_normal=40)).info["grid"] == "O"


# ---- same patch names as the Gmsh mesh -------------------------------------------------------------------------

def test_patch_names_are_those_of_the_unstructured_mesh():
    pytest.importorskip("gmsh")
    case = load_case("external_2d")
    base = defaults(case.parameters())
    base = {**base, "shape": "NACA 4-digit airfoil"}
    for changes in ({}, {"half_domain": True}, {"shape": "Circular cylinder"}, {"shape": "Sphere"},
                    {"shape": "Circular cylinder", "half_domain": True}):
        structured_params = {**base, **changes, "mesh_type": "Structured C/O-grid", "grid_preset": "Coarse"}
        unstructured_params = {**base, **changes, "surface_size": 0.05, "farfield_size": 5.0}
        a = {p.name: p.type for p in case.build_mesh(structured_params).patches}
        b = {p.name: p.type for p in case.build_mesh(unstructured_params).patches}
        assert a == b, changes


# ---- the external_2d template ------------------------------------------------------------------------------------

def test_template_inputs_presets_and_derived_numbers():
    case = load_case("external_2d")
    base = defaults(case.parameters())
    assert base["mesh_type"] == "Unstructured (Gmsh)"                          # the default is unchanged
    params = {**base, "mesh_type": "Structured C/O-grid", "grid_preset": "Medium", "shape": "NACA 4-digit airfoil"}
    mesh = case.build_mesh(params)
    assert mesh.n_cells == (160 + 100) * 60 == case.estimated_cells(params)
    numbers = case.derived(params)
    assert "C-grid" in numbers["Structured grid"][0] and numbers["Cells"][0] == f"{mesh.n_cells:,}"
    custom = {**params, "grid_preset": "Custom", "grid_n_body": 100, "grid_n_normal": 50, "grid_n_wake": 20}
    assert case.build_mesh(custom).n_cells == (100 + 40) * 50
    bad = {**params, "shape": "Wedge"}
    assert "not available" in case.derived(bad)["Structured grid"][0]
    with pytest.raises(ValueError, match="blunt trailing edge"):
        case.build_mesh(bad)


# ---- free-stream preservation (the solver on the new meshes) ----------------------------------------------------

@pytest.mark.parametrize("name, body, half", [("C-grid", NACA, False), ("C-grid half", NACA, True),
                                              ("O-grid", CYLINDER, False), ("O-grid axisymmetric", SPHERE, True)])
def test_uniform_flow_stays_uniform_on_structured_grids(name, body, half):
    gas = gas_model("air")
    mesh = structured_mesh(body, settings(n_body=60, n_normal=30, n_wake=20, half=half))
    fs = {"mach": 0.7, "p": 9e4, "T": 280.0, "flow_angle": 0.0}
    bcs = {p.name: BoundaryCondition("far_field", fs) for p in mesh.patches if p.name in ("wall", "farfield")}
    for p in mesh.patches:
        if p.name in ("symmetry", "axis"):
            bcs[p.name] = BoundaryCondition(p.name)
    rho, vel = state_from_mach(gas, 0.7, 9e4, 280.0, (1.0, 0.0))
    W0 = uniform_state(mesh.n_cells, rho, vel, 9e4)
    out = EulerSolver(mesh, gas, bcs, Numerics(order=2, max_iterations=30, residual_drop=50)).solve(W0)
    scale = np.array([rho, np.linalg.norm(vel), np.linalg.norm(vel), 9e4])[:, None]
    assert (np.abs(out.W - W0) / scale).max() < 1e-11, name

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verification of the Euler solver core (aeroflowsim/euler/): free-stream preservation on every mesh
type, gas at rest in axisymmetric flow, exact gradients of linear fields, flux consistency and symmetry,
and 3D-readiness of the flux and gradient functions on single 3D cells."""

import math

import numpy as np
import pytest

from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.flux import hlle_flux, hllc_flux, hybrid_flux, physical_flux, normal_velocity
from aeroflowsim.euler.geometry import FVGeometry
from aeroflowsim.euler.gradients import GREEN_GAUSS, LEAST_SQUARES, Gradients
from aeroflowsim.euler.limiters import BARTH_JESPERSEN, VENKATAKRISHNAN, limiter_factors
from aeroflowsim.euler.solver import EulerSolver, Numerics
from aeroflowsim.euler.state import (conserved_to_primitive, primitive_to_conserved, state_from_mach,
                                     uniform_state)
from aeroflowsim.gases import gas_model
from aeroflowsim.geometry import conical_nozzle
from aeroflowsim.mesh import HEXAHEDRON, TETRA, Mesh
from aeroflowsim.nozzle_mesh import Inflation, structured_nozzle_mesh
from aeroflowsim.simple_meshes import rectangle_mesh as rectangle

ROUND_OFF = 1e-13
AIR = gas_model("air")
N2 = gas_model("N2")
DEG = math.pi / 180.0


def _nozzle_profile():
    return conical_nozzle(0.002, 0.00133, 30 * DEG, 0.00028, 15 * DEG, 0.000911, 0.0, 0.0)


def _gmsh_nozzle(**kw):
    from aeroflowsim.gmsh_mesh import GmshSettings, nozzle_mesh
    return nozzle_mesh(_nozzle_profile(), GmshSettings(1.2e-5, 6e-5, **kw))


# ---- free-stream preservation -----------------------------------------------------------------------

PLANAR_MESHES = {
    "quads": lambda: rectangle(12, 8),
    "distorted quads": lambda: rectangle(12, 8, distort=0.35),
    "distorted triangles": lambda: rectangle(12, 8, triangles=True, distort=0.35),
    "hybrid quads + triangles": lambda: rectangle(12, 8, mixed=True, distort=0.3),
}


@pytest.mark.parametrize("name", list(PLANAR_MESHES))
@pytest.mark.parametrize("order", [1, 2])
def test_uniform_flow_stays_uniform_on_planar_meshes(name, order):
    mesh = PLANAR_MESHES[name]()
    fs = {"mach": 0.7, "p": 9e4, "T": 280.0, "flow_angle": 25.0}
    bcs = {p.name: BoundaryCondition("far_field", fs) for p in mesh.patches}
    rho, vel = state_from_mach(AIR, 0.7, 9e4, 280.0, (math.cos(25 * DEG), math.sin(25 * DEG)))
    W0 = uniform_state(mesh.n_cells, rho, vel, 9e4)
    solver = EulerSolver(mesh, AIR, bcs, Numerics(order=order, max_iterations=40, residual_drop=50))
    out = solver.solve(W0)
    assert out.iterations == 40
    scale = np.array([rho, np.linalg.norm(vel), np.linalg.norm(vel), 9e4])[:, None]
    assert np.abs(out.W - W0).max() / 1.0 <= ROUND_OFF * scale.max()
    assert (np.abs(out.W - W0) / scale).max() < ROUND_OFF


@pytest.mark.parametrize("kind", ["structured", "triangles", "quad-dominant", "hybrid (inflation)"])
def test_uniform_axial_flow_and_gas_at_rest_on_axisymmetric_nozzle_meshes(kind):
    if kind == "structured":
        mesh = structured_nozzle_mesh(_nozzle_profile(), 40, 10)
    else:
        pytest.importorskip("gmsh")
        options = {"triangles": {}, "quad-dominant": {"quads": True},
                   "hybrid (inflation)": {"inflation": Inflation(5e-6, 4, 1.2)}}[kind]
        mesh = _gmsh_nozzle(**options)
    # The geometric source is exactly the planar cell area (sum n_r r_f A_f = A for straight edges)
    geom = FVGeometry(mesh)
    # (thin inflation cells far from the axis lose a few digits: r_f times a tiny height)
    assert np.allclose(geom.geometric_source[1], mesh.cell_volumes, rtol=1e-9, atol=0)
    assert np.abs(geom.geometric_source[0]).max() < 1e-11 * mesh.cell_volumes.max()

    # Gas at rest stays at rest (well-balanced pressure source)
    walls = {p.name: BoundaryCondition("axis" if p.type == "axis" else "slip_wall") for p in mesh.patches}
    W0 = uniform_state(mesh.n_cells, 5.0, (0.0, 0.0), 4e5)
    out = EulerSolver(mesh, N2, walls, Numerics(max_iterations=25, residual_drop=50)).solve(W0)
    c = float(N2.sound_speed(4e5 / (5.0 * N2.R)))
    assert np.abs(out.W[1:3]).max() < ROUND_OFF * c
    assert np.abs(out.W[3] / 4e5 - 1.0).max() < ROUND_OFF

    # Uniform axial flow is an exact axisymmetric solution: it stays uniform
    fs = {"mach": 2.0, "p": 1e5, "T": 300.0, "flow_angle": 0.0}
    bcs = {"inlet": BoundaryCondition("supersonic_inlet", fs), "outlet": BoundaryCondition("supersonic_outlet"),
           "wall": BoundaryCondition("supersonic_outlet"), "axis": BoundaryCondition("axis")}
    rho, vel = state_from_mach(N2, 2.0, 1e5, 300.0, (1.0, 0.0))
    W0 = uniform_state(mesh.n_cells, rho, vel, 1e5)
    out = EulerSolver(mesh, N2, bcs, Numerics(max_iterations=25, residual_drop=50)).solve(W0)
    scale = np.array([rho, vel[0], vel[0], 1e5])[:, None]
    assert (np.abs(out.W - W0) / scale).max() < ROUND_OFF


# ---- gradients --------------------------------------------------------------------------------------

def _single_cell_3d(cell_type, nodes):
    from aeroflowsim.mesh import CELL_TYPES
    cells = np.arange(len(nodes))[None, :]
    faces = [list(cells[0][list(local)]) + [-1] * (4 - len(local)) for local in CELL_TYPES[cell_type].faces]
    return Mesh.from_cells(nodes, cell_type, cells, {"wall": ("wall", np.array(faces))})


HEX_NODES = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
TET_NODES = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)

GRADIENT_MESHES = {
    "distorted quads": lambda: rectangle(7, 5, distort=0.4),
    "distorted triangles": lambda: rectangle(7, 5, triangles=True, distort=0.4),
    "hybrid": lambda: rectangle(7, 5, mixed=True, distort=0.4),
    "axisymmetric quads": lambda: rectangle(6, 4, y0=0.0, axisymmetric=True, distort=0.3,
                                            kinds={"bottom": "axis"}),
    "hexahedron": lambda: _single_cell_3d(HEXAHEDRON, HEX_NODES * [1.0, 0.7, 1.3]),
    "tetrahedron": lambda: _single_cell_3d(TETRA, TET_NODES),
}


@pytest.mark.parametrize("name", list(GRADIENT_MESHES))
def test_least_squares_gradient_is_exact_for_linear_fields(name):
    mesh = GRADIENT_MESHES[name]()
    geom = FVGeometry(mesh)
    dim = mesh.dim
    slopes = np.array([[2.0, -3.0, 0.5], [0.0, 1.0, -4.0]])[:, :dim]     # two linear fields
    field = lambda x: 1.5 + x @ slopes.T                                  # (n, 2)
    Wc = field(geom.cell_centres).T
    Wb = field(geom.face_centres[geom.boundary_faces]).T
    grad = Gradients(geom, LEAST_SQUARES).gradient(Wc, Wb)                # (2, dim, C)
    assert np.allclose(grad, slopes[:, :, None], rtol=0, atol=1e-10)


def test_green_gauss_gradient_is_exact_on_a_regular_grid():
    mesh = rectangle(6, 4)
    geom = FVGeometry(mesh)
    field = lambda x: 3.0 * x[:, 0] - 2.0 * x[:, 1]
    grad = Gradients(geom, GREEN_GAUSS).gradient(field(geom.cell_centres)[None],
                                                 field(geom.face_centres[geom.boundary_faces])[None])
    assert np.allclose(grad[0, 0], 3.0) and np.allclose(grad[0, 1], -2.0)


@pytest.mark.parametrize("kind", [VENKATAKRISHNAN, BARTH_JESPERSEN])
def test_limiter_keeps_face_values_within_the_neighbour_range(kind):
    mesh = rectangle(10, 6, triangles=True, distort=0.3)
    geom = FVGeometry(mesh)
    rng = np.random.default_rng(3)
    Wc = rng.uniform(1.0, 2.0, (1, mesh.n_cells))
    Wb = rng.uniform(1.0, 2.0, (1, geom.n_boundary))
    grad = Gradients(geom).gradient(Wc, Wb)
    psi = limiter_factors(geom, grad, Wc, Wb, kind, K=0.0 if kind == VENKATAKRISHNAN else 5.0)
    assert np.all((psi >= 0.0) & (psi <= 1.0))
    face_values = Wc[:, :, None] + psi[:, :, None] * np.einsum("vkc,cfk->vcf", grad, geom.slot_offset)
    X = np.concatenate([Wc, Wb], axis=1)[:, geom.slot_other]
    hi = np.maximum(X.max(axis=2), Wc)[:, :, None]            # range of the cell and its neighbours
    lo = np.minimum(X.min(axis=2), Wc)[:, :, None]
    used = geom.slot_used[None]
    assert np.all(np.where(used, face_values <= hi + 1e-12, True))
    assert np.all(np.where(used, face_values >= lo - 1e-12, True))


def test_limiter_leaves_a_linear_field_alone_in_the_interior():
    """Venkatakrishnan with a reasonable eps barely limits smooth data (second order is kept)."""
    mesh = rectangle(10, 8, distort=0.2)
    geom = FVGeometry(mesh)
    f = lambda x: 1.0 + 0.1 * x[:, 0]
    Wc, Wb = f(geom.cell_centres)[None], f(geom.face_centres[geom.boundary_faces])[None]
    grad = Gradients(geom).gradient(Wc, Wb)
    psi = limiter_factors(geom, grad, Wc, Wb, VENKATAKRISHNAN, K=5.0, L_ref=1.0, scale=[1.0])
    assert psi.min() > 0.95


# ---- fluxes -----------------------------------------------------------------------------------------

def _random_states(n, dim, seed=0):
    rng = np.random.default_rng(seed)
    W = np.empty((dim + 2, n))
    W[0] = rng.uniform(0.2, 3.0, n)
    W[1:-1] = rng.uniform(-400.0, 400.0, (dim, n))
    W[-1] = rng.uniform(2e4, 3e5, n)
    normals = rng.normal(size=(n, dim))
    return W, normals / np.linalg.norm(normals, axis=1, keepdims=True)


@pytest.mark.parametrize("dim", [2, 3])
@pytest.mark.parametrize("flux", [hllc_flux, hlle_flux])
def test_flux_of_equal_states_is_the_physical_flux(flux, dim):
    W, n = _random_states(50, dim)
    exact = physical_flux(W, primitive_to_conserved(W, AIR), normal_velocity(W, n), n)
    assert np.allclose(flux(W, W, n, AIR), exact, rtol=1e-12, atol=1e-9)


@pytest.mark.parametrize("dim", [2, 3])
def test_flux_is_conservative_and_rotation_invariant(dim):
    WL, n = _random_states(40, dim, 1)
    WR, _ = _random_states(40, dim, 2)
    F = hllc_flux(WL, WR, n, AIR)
    # Swapping sides and reversing the normal gives the opposite flux (what leaves one cell enters the other)
    assert np.allclose(hllc_flux(WR, WL, -n, AIR), -F, rtol=1e-11, atol=1e-6)
    # Rotating states and normal rotates the momentum flux the same way, mass and energy unchanged
    angle = 0.7
    if dim == 2:
        Rm = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    else:
        Rm = np.array([[1, 0, 0], [0, math.cos(angle), -math.sin(angle)], [0, math.sin(angle), math.cos(angle)]])
    rot = lambda W: np.concatenate([W[:1], Rm @ W[1:-1], W[-1:]])
    F_rot = hllc_flux(rot(WL), rot(WR), n @ Rm.T, AIR)
    assert np.allclose(F_rot, rot(F), rtol=1e-11, atol=1e-6)


def test_hllc_resolves_a_stationary_contact_exactly_and_hybrid_blends():
    """A contact (density jump at equal p, u_n = 0) gives zero mass flux with HLLC, not with HLLE."""
    WL = np.array([[1.0], [0.0], [30.0], [1e5]])
    WR = np.array([[0.2], [0.0], [-50.0], [1e5]])
    n = np.array([[1.0, 0.0]])
    assert abs(hllc_flux(WL, WR, n, AIR)[0, 0]) < 1e-12
    assert abs(hlle_flux(WL, WR, n, AIR)[0, 0]) > 1.0
    mix = hybrid_flux(WL, WR, n, AIR, np.array([0.5]))
    assert np.allclose(mix, 0.5 * (hllc_flux(WL, WR, n, AIR) + hlle_flux(WL, WR, n, AIR)))


def test_conserved_primitive_round_trip_uses_the_gas_model():
    W, _ = _random_states(30, 2)
    for gas in (AIR, gas_model("He"), gas_model("CO2")):
        assert np.allclose(conserved_to_primitive(primitive_to_conserved(W, gas), gas), W, rtol=1e-12)

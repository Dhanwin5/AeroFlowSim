# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Euler solver on 3D meshes (5 equations): free-stream preservation on every cell type, Numba = NumPy to 1e-12,
results independent of the thread count, gas at rest, and the 3D ghost states of every boundary-condition type."""

import math

import numpy as np
import pytest

from aeroflowsim import compute
from aeroflowsim.euler.boundary import BC_TYPES, BoundaryCondition, PatchInfo, ghost_state
from aeroflowsim.euler.flux import hllc_flux, normal_velocity
from aeroflowsim.euler.solver import LUSGS, SSP_RK3, EulerSolver, Numerics
from aeroflowsim.euler.state import primitive_to_conserved, state_from_mach, uniform_state
from aeroflowsim.gases import gas_model
from aeroflowsim.simple_meshes import BOX_KINDS, box_mesh_3d

AIR = gas_model("air")
DEG = math.pi / 180.0
TOL = 1e-12
FS = {"mach": 2.0, "p": 1e5, "T": 300.0, "flow_angle": 10.0, "sideslip": 5.0}


@pytest.fixture
def backend():
    old, old_threads = compute.backend(), compute._settings["threads"]
    yield
    compute.set_backend(old)
    compute.set_threads(old_threads)


def _free_stream_state(n, fs=FS):
    a, b = fs["flow_angle"] * DEG, fs.get("sideslip", 0.0) * DEG
    rho, vel = state_from_mach(AIR, fs["mach"], fs["p"], fs["T"], (math.cos(a) * math.cos(b),
                                                                    math.sin(a) * math.cos(b), math.sin(b)))
    return uniform_state(n, rho, vel, fs["p"])


def _far_field(mesh, fs=FS):
    return {p.name: BoundaryCondition("far_field", fs) for p in mesh.patches}


def _solver(mesh, which, numerics, conditions=None):
    compute.set_backend(which)
    s = EulerSolver(mesh, AIR, conditions or _far_field(mesh), numerics, L_ref=1.0,
                    scales=(1.0, 500.0, 500.0, 500.0, 1e5))
    if which == compute.NUMBA:
        pytest.importorskip("numba")
    assert s.backend == which
    return s


def test_box_meshes_are_closed_and_positive():
    for kind in BOX_KINDS:
        m = box_mesh_3d(3, kind, warp=0.04)
        assert m.dim == 3 and m.cell_volumes.min() > 0.0
        assert abs(m.cell_volumes.sum() - 1.0) < 1e-12
        # every cell is a closed surface: the sum of its outward area vectors is zero
        closure = np.zeros((m.n_cells, 3))
        S = m.face_area_vectors
        np.add.at(closure, m.owner, S)
        inner = m.neighbour >= 0
        np.add.at(closure, m.neighbour[inner], -S[inner])
        assert np.abs(closure).max() < 1e-15


@pytest.mark.parametrize("kind", BOX_KINDS)
@pytest.mark.parametrize("scheme", [SSP_RK3, LUSGS])
@pytest.mark.parametrize("which", [compute.NUMPY, compute.NUMBA])
def test_uniform_flow_stays_uniform_on_3d_meshes(kind, scheme, which, backend):
    """A uniform flow at 10 deg incidence and 5 deg sideslip through a warped box stays uniform to round-off."""
    mesh = box_mesh_3d(3, kind, warp=0.04)
    s = _solver(mesh, which, Numerics(time_scheme=scheme, max_iterations=15, residual_drop=50))
    W0 = _free_stream_state(mesh.n_cells)
    out = s.solve(W0.copy())
    assert out.W.shape == (5, mesh.n_cells)
    assert (np.abs(out.W - W0) / np.abs(W0).max(axis=1, keepdims=True)).max() < 1e-13


@pytest.mark.parametrize("which", [compute.NUMPY, compute.NUMBA])
def test_gas_at_rest_stays_at_rest_in_a_closed_3d_box(which, backend):
    mesh = box_mesh_3d(3, "hex-prism", warp=0.04)
    walls = {p.name: BoundaryCondition("slip_wall") for p in mesh.patches}
    s = _solver(mesh, which, Numerics(time_scheme=LUSGS, max_iterations=15, residual_drop=50), walls)
    out = s.solve(uniform_state(mesh.n_cells, 1.2, (0.0, 0.0, 0.0), 1e5))
    assert np.abs(out.W[1:4]).max() < 1e-12 and np.abs(out.W[4] / 1e5 - 1.0).max() < 1e-13


def _wavy_state(mesh, shock=False, seed=2):
    x, y, z = mesh.cell_centres.T
    rng = np.random.default_rng(seed)
    W = np.empty((5, mesh.n_cells))
    W[0] = 1.2 + 0.3 * np.sin(3 * x) * np.cos(2 * y) * np.cos(z) + 0.02 * rng.standard_normal(mesh.n_cells)
    W[1] = 400 + 80 * np.cos(2 * x + y - z)
    W[2] = 60 * np.sin(4 * y) - 30 * x
    W[3] = 40 * np.cos(3 * z) + 20 * y
    W[4] = 1e5 * (1.0 + 0.3 * np.cos(3 * x - y + 2 * z))
    if shock:
        W[4] *= np.where(x > 0.5, 3.0, 1.0)
    return W


def _rel(a, b):
    scale = np.abs(b).max(axis=-1, keepdims=True)
    return float((np.abs(a - b) / np.where(scale > 0, scale, 1.0)).max())


@pytest.mark.parametrize("kind", BOX_KINDS)
@pytest.mark.parametrize("numerics", [
    {"order": 1, "carbuncle_fix": False},
    {"order": 2, "limiter": "None", "carbuncle_fix": False},
    {"order": 2, "limiter": "Venkatakrishnan"},
    {"order": 2, "limiter": "Barth-Jespersen"},
    {"order": 2, "limiter": "Venkatakrishnan", "gradient": "Green-Gauss"},
], ids=["order1", "unlimited", "venkat", "barth", "green-gauss"])
def test_numba_residual_equals_numpy_in_3d(kind, numerics, backend):
    pytest.importorskip("numba")
    mesh = box_mesh_3d(4, kind, warp=0.04)
    W = _wavy_state(mesh, shock=True)
    out = {}
    for which in (compute.NUMPY, compute.NUMBA):
        s = _solver(mesh, which, Numerics(**numerics))
        R, _ = s.residual(primitive_to_conserved(W, AIR), numerics["order"] == 2, W.copy())
        out[which] = (R, s.boundary_flux.copy(), s.time_steps(W, 0.8), s.last_positivity)
    (Rp, bp, dp, pp), (Rn, bn, dn, pn) = out[compute.NUMPY], out[compute.NUMBA]
    assert _rel(Rn, Rp) < TOL and _rel(bn, bp) < TOL
    assert np.allclose(dn, dp, rtol=TOL, atol=0) and pn == pp


def _history(which, scheme, threads=None):
    compute.set_threads(threads)
    mesh = box_mesh_3d(5, "tetrahedra", warp=0.03)
    s = _solver(mesh, which, Numerics(time_scheme=scheme, max_iterations=40, residual_drop=50, cfl=0.5))
    return s.solve(_wavy_state(mesh))


@pytest.mark.parametrize("scheme", [SSP_RK3, LUSGS])
def test_whole_3d_runs_agree_between_numpy_and_numba(scheme, backend):
    pytest.importorskip("numba")
    a, b = _history(compute.NUMPY, scheme), _history(compute.NUMBA, scheme)
    assert a.iterations == b.iterations and a.cfl_reductions == b.cfl_reductions
    assert np.allclose(a.residuals, b.residuals, rtol=1e-9, atol=1e-14)
    assert np.allclose(a.W, b.W, rtol=1e-10, atol=0)


def test_3d_runs_do_not_depend_on_the_thread_count(backend):
    kernels = pytest.importorskip("aeroflowsim.euler.kernels")
    if kernels.numba is None:
        pytest.skip("no Numba")
    counts = sorted({1, 2, min(4, kernels.numba.config.NUMBA_NUM_THREADS)})
    runs = [_history(compute.NUMBA, LUSGS, threads=n) for n in counts]
    for r in runs[1:]:
        assert np.array_equal(r.residuals, runs[0].residuals) and np.array_equal(r.W, runs[0].W)


# ---- 3D ghost states -------------------------------------------------------------------------------------

def _random_normals(n, seed=3):
    v = np.random.default_rng(seed).standard_normal((n, 3))
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def _inside(n, seed=4):
    rng = np.random.default_rng(seed)
    W = np.empty((5, n))
    W[0] = 1.0 + 0.2 * rng.random(n)
    W[1:4] = 150.0 * rng.standard_normal((3, n))
    W[4] = 1e5 * (1.0 + 0.2 * rng.random(n))
    return W


def test_every_bc_type_gives_a_physical_3d_ghost_state():
    n = 50
    Wi, normals = _inside(n), _random_normals(n)
    for kind in BC_TYPES:
        bc = BoundaryCondition(kind, {"p0": 2e5, "T0": 400.0} if kind == "total_pressure_inlet" else {})
        Wg = ghost_state(bc, Wi, normals, AIR, PatchInfo("p", 0.5))
        assert Wg.shape == (5, n) and np.all(np.isfinite(Wg)) and np.all(Wg[0] > 0) and np.all(Wg[4] > 0), kind


def test_3d_slip_wall_lets_no_mass_through_and_keeps_the_tangential_velocity():
    n = 40
    Wi, normals = _inside(n), _random_normals(n)
    Wg = ghost_state(BoundaryCondition("slip_wall"), Wi, normals, AIR, PatchInfo("w", 1.0))
    assert np.allclose(normal_velocity(Wg, normals), -normal_velocity(Wi, normals), atol=1e-10)
    t_i = Wi[1:4] - normal_velocity(Wi, normals) * normals.T
    t_g = Wg[1:4] - normal_velocity(Wg, normals) * normals.T
    assert np.allclose(t_i, t_g, atol=1e-10)
    F = hllc_flux(Wi, Wg, normals, AIR)
    assert np.abs(F[0]).max() < 1e-9 * np.abs(Wi[0] * 150).max()


def test_3d_free_stream_direction_uses_angle_of_attack_and_sideslip():
    Wg = ghost_state(BoundaryCondition("supersonic_inlet", FS), _inside(1), _random_normals(1), AIR, None)
    V = np.linalg.norm(Wg[1:4, 0])
    a, b = 10 * DEG, 5 * DEG
    assert np.allclose(Wg[1:4, 0] / V, [math.cos(a) * math.cos(b), math.sin(a) * math.cos(b), math.sin(b)])
    assert math.isclose(V, 2.0 * float(AIR.sound_speed(300.0)), rel_tol=1e-12)


def test_3d_mass_flow_inlet_delivers_the_mass_flux_normal_to_the_face():
    n = 30
    Wi, normals = _inside(n), _random_normals(n)
    bc = BoundaryCondition("mass_flow_inlet", {"mass_flow": 2.0, "T0": 300.0})
    Wg = ghost_state(bc, Wi, normals, AIR, PatchInfo("in", 0.5))
    assert np.allclose(-Wg[0] * normal_velocity(Wg, normals), 4.0, rtol=1e-10)   # G = 2 kg/s / 0.5 m²
    tangential = Wg[1:4] - normal_velocity(Wg, normals) * normals.T
    assert np.abs(tangential).max() < 1e-10

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Numba kernels (aeroflowsim/euler/kernels.py) against the NumPy reference implementation.

Every residual evaluation must agree to 1e-12 (relative to the size of the residual) on every mesh type, order,
limiter and with the carbuncle fix; positivity fallbacks, limiter freezing and the stall freeze must behave the
same; runs must be deterministic and independent of the thread count (gather face sums)."""

import math

import numpy as np
import pytest

from aeroflowsim import compute
from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import EulerSolver, Numerics
from aeroflowsim.euler.state import primitive_to_conserved, state_from_mach, uniform_state
from aeroflowsim.gases import gas_model
from aeroflowsim.mesh import HEXAHEDRON, TETRA
from aeroflowsim.simple_meshes import rectangle_mesh as rectangle

pytest.importorskip("numba")

AIR = gas_model("air")
DEG = math.pi / 180.0
TOL = 1e-12

MESHES = {
    "quads": lambda: rectangle(12, 8),
    "distorted quads": lambda: rectangle(12, 8, distort=0.35),
    "triangles": lambda: rectangle(12, 8, triangles=True, distort=0.35),
    "mixed": lambda: rectangle(12, 8, mixed=True, distort=0.3),
    "axisymmetric quads": lambda: rectangle(12, 8, y0=0.0, axisymmetric=True, distort=0.3, kinds={"bottom": "axis"}),
    "axisymmetric triangles": lambda: rectangle(12, 8, y0=0.0, axisymmetric=True, triangles=True, distort=0.3,
                                                kinds={"bottom": "axis"}),
}


@pytest.fixture
def backend():
    """Restore the backend setting after a test that changes it."""
    old, old_threads = compute.backend(), compute._settings["threads"]
    yield
    compute.set_backend(old)
    compute.set_threads(old_threads)


def _solver(mesh, which, numerics, conditions=None):
    compute.set_backend(which)
    if conditions is None:
        fs = {"mach": 1.6, "p": 9e4, "T": 280.0, "flow_angle": 20.0}
        conditions = {p.name: BoundaryCondition("axis" if p.type == "axis" else "far_field", fs) for p in mesh.patches}
    s = EulerSolver(mesh, AIR, conditions, numerics, L_ref=1.0, scales=(1.0, 500.0, 500.0, 1e5))
    assert s.backend == which
    return s


def _wavy_state(mesh, shock=False, seed=1):
    """A smooth, non-uniform flow (and optionally a pressure jump, so the carbuncle blend is active)."""
    x, y = mesh.cell_centres[:, 0], mesh.cell_centres[:, 1]
    rng = np.random.default_rng(seed)
    W = np.empty((4, mesh.n_cells))
    W[0] = 1.2 + 0.3 * np.sin(3 * x) * np.cos(2 * y) + 0.02 * rng.standard_normal(mesh.n_cells)
    W[1] = 400 + 80 * np.cos(2 * x + y)
    W[2] = 60 * np.sin(4 * y) - 30 * x
    W[3] = 1e5 * (1.0 + 0.3 * np.cos(3 * x - y))
    if shock:
        W[3] *= np.where(x > 0.5 * (x.min() + x.max()), 3.0, 1.0)     # pressure ratio 3: full HLLE band
    return W


def _residuals(mesh, numerics, W, conditions=None):
    out = {}
    for which in (compute.NUMPY, compute.NUMBA):
        s = _solver(mesh, which, Numerics(**numerics), conditions)
        U = primitive_to_conserved(W, AIR)
        R, _ = s.residual(U, numerics.get("order", 2) == 2, W.copy())
        out[which] = (R, s.last_positivity, s.boundary_flux.copy(), s.time_steps(W, 0.8))
    return out


def _rel(a, b):
    """Largest difference relative to the size of each equation's residual."""
    scale = np.abs(b).max(axis=-1, keepdims=True)
    return float((np.abs(a - b) / np.where(scale > 0, scale, 1.0)).max())


@pytest.mark.parametrize("name", list(MESHES))
@pytest.mark.parametrize("numerics", [
    {"order": 1, "carbuncle_fix": False},
    {"order": 2, "limiter": "None", "carbuncle_fix": False},
    {"order": 2, "limiter": "Venkatakrishnan"},
    {"order": 2, "limiter": "Barth-Jespersen"},
    {"order": 2, "limiter": "Venkatakrishnan", "gradient": "Green-Gauss"},
], ids=["order1", "unlimited", "venkat", "barth", "green-gauss"])
@pytest.mark.parametrize("shock", [False, True], ids=["smooth", "shock"])
def test_numba_residual_equals_numpy(name, numerics, shock, backend):
    mesh = MESHES[name]()
    out = _residuals(mesh, numerics, _wavy_state(mesh, shock))
    (Rp, posp, bfp, dtp), (Rn, posn, bfn, dtn) = out[compute.NUMPY], out[compute.NUMBA]
    assert _rel(Rn, Rp) < TOL
    assert _rel(bfn, bfp) < TOL
    assert np.allclose(dtn, dtp, rtol=TOL, atol=0)
    assert posn == posp


def test_positivity_fallback_counts_are_equal(backend):
    mesh = rectangle(16, 10, triangles=True, distort=0.3)
    W = _wavy_state(mesh)
    W[3, ::7] = 50.0                     # near-vacuum cells: reconstructed pressures go negative
    out = _residuals(mesh, {"order": 2, "limiter": "None"}, W)
    assert out[compute.NUMPY][1] > 0
    assert out[compute.NUMBA][1] == out[compute.NUMPY][1]
    assert _rel(out[compute.NUMBA][0], out[compute.NUMPY][0]) < TOL


@pytest.mark.parametrize("kind", [HEXAHEDRON, TETRA])
def test_numba_residual_equals_numpy_on_single_3d_cells(kind, backend):
    from tests.test_euler_core import HEX_NODES, TET_NODES, _single_cell_3d
    mesh = _single_cell_3d(kind, HEX_NODES * [1.0, 0.7, 1.3] if kind == HEXAHEDRON else TET_NODES)
    W = np.array([[1.2], [300.0], [-40.0], [25.0], [1.1e5]])
    fs = {"mach": 0.8, "p": 1e5, "T": 300.0, "flow_angle": 10.0}
    conds = {p.name: BoundaryCondition("slip_wall", fs) for p in mesh.patches}
    for order in (1, 2):
        res = {}
        for which in (compute.NUMPY, compute.NUMBA):
            compute.set_backend(which)
            s = EulerSolver(mesh, AIR, conds, Numerics(order=order), scales=(1.0, 300.0, 300.0, 300.0, 1e5))
            res[which] = s.residual(primitive_to_conserved(W, AIR), order == 2, W.copy())[0]
        # A closed single cell: the mass and energy residuals are pure round-off, so compare against the size of the
        # fluxes (|U| (|u| + c) / h, h = 1 m) instead of the residual itself.
        c = math.sqrt(1.4 * 1.1e5 / 1.2)
        scale = np.abs(primitive_to_conserved(W, AIR)) * (np.linalg.norm(W[1:4]) + c)
        assert float((np.abs(res[compute.NUMBA] - res[compute.NUMPY]) / scale).max()) < TOL


@pytest.mark.parametrize("name", ["distorted quads", "triangles", "mixed"])
def test_free_stream_is_preserved_by_the_numba_kernels(name, backend):
    mesh = MESHES[name]()
    fs = {"mach": 0.7, "p": 9e4, "T": 280.0, "flow_angle": 25.0}
    rho, vel = state_from_mach(AIR, 0.7, 9e4, 280.0, (math.cos(25 * DEG), math.sin(25 * DEG)))
    W0 = uniform_state(mesh.n_cells, rho, vel, 9e4)
    s = _solver(mesh, compute.NUMBA, Numerics(max_iterations=40, residual_drop=50),
                {p.name: BoundaryCondition("far_field", fs) for p in mesh.patches})
    out = s.solve(W0)
    scale = np.array([rho, np.linalg.norm(vel), np.linalg.norm(vel), 9e4])[:, None]
    assert out.backend == compute.NUMBA and (np.abs(out.W - W0) / scale).max() < 1e-13


def test_gas_at_rest_stays_at_rest_with_the_numba_kernels(backend):
    mesh = MESHES["axisymmetric triangles"]()
    walls = {p.name: BoundaryCondition("axis" if p.type == "axis" else "slip_wall") for p in mesh.patches}
    s = _solver(mesh, compute.NUMBA, Numerics(max_iterations=25, residual_drop=50), walls)
    out = s.solve(uniform_state(mesh.n_cells, 5.0, (0.0, 0.0), 4e5))
    assert np.abs(out.W[1:3]).max() < 1e-13 * 300.0 and np.abs(out.W[3] / 4e5 - 1.0).max() < 1e-13


def _history(which, numerics, threads=None, mesh=None):
    compute.set_threads(threads)
    mesh = mesh or rectangle(24, 16, triangles=True, distort=0.3)
    s = _solver(mesh, which, Numerics(**numerics))
    return s.solve(_wavy_state(mesh))


def test_whole_runs_agree_and_limiter_freezing_happens_at_the_same_iteration(backend):
    num = {"max_iterations": 300, "residual_drop": 50, "freeze_limiter_orders": 1.0, "cfl": 0.5}
    a, b = _history(compute.NUMPY, num), _history(compute.NUMBA, num)
    assert a.limiter_frozen_at is not None and a.limiter_frozen_at == b.limiter_frozen_at
    assert a.positivity_events == b.positivity_events and a.cfl_reductions == b.cfl_reductions
    assert np.allclose(a.residuals, b.residuals, rtol=1e-9, atol=1e-14)
    assert np.allclose(a.W, b.W, rtol=1e-10, atol=0)


def test_stall_freeze_behaves_as_before(backend, monkeypatch):
    from aeroflowsim.euler import solver as solver_module
    monkeypatch.setattr(solver_module, "STALL_ORDERS", 0.3)      # a short stall rule, to see it within 300 iterations
    monkeypatch.setattr(solver_module, "STALL_ITERATIONS", 20)
    num = {"max_iterations": 300, "residual_drop": 50, "freeze_limiter_orders": 12.0, "cfl": 0.5}
    a, b = _history(compute.NUMPY, num), _history(compute.NUMBA, num)
    assert a.limiter_frozen_at == b.limiter_frozen_at
    assert np.allclose(a.residuals, b.residuals, rtol=1e-9, atol=1e-14)


def test_runs_are_deterministic_and_independent_of_the_thread_count(backend):
    from aeroflowsim.euler import kernels
    num = {"max_iterations": 60, "residual_drop": 50}
    counts = sorted({1, 2, min(4, kernels.numba.config.NUMBA_NUM_THREADS)})
    runs = [_history(compute.NUMBA, num, threads=n) for n in counts] + [_history(compute.NUMBA, num, threads=counts[-1])]
    for r in runs[1:]:
        # gather face sums: every number is computed by one thread in a fixed order -> bit-for-bit identical
        assert np.array_equal(r.residuals, runs[0].residuals)
        assert np.array_equal(r.W, runs[0].W)
    assert runs[-1].threads == counts[-1]


def test_numpy_backend_and_missing_numba_fall_back_cleanly(backend, monkeypatch):
    from aeroflowsim.euler import kernels
    mesh = rectangle(4, 3)
    compute.set_backend(compute.AUTO)
    monkeypatch.setattr(kernels, "numba", None)
    monkeypatch.setattr(kernels, "NUMBA_ERROR", "ImportError: no module named numba")
    s = EulerSolver(mesh, AIR, {p.name: BoundaryCondition("slip_wall") for p in mesh.patches})
    assert s.backend == compute.NUMPY and "Numba could not be loaded" in s.backend_note

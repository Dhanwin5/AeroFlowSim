# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Turbulence models (aeroflowsim/euler/turbulence.py): free-stream preservation, wall values, positivity, Numba = NumPy,
thread independence, the transport operator's order (MMS, expected 1), and short runs in 2D, axisymmetric and 3D."""

import math

import numpy as np
import pytest

from aeroflowsim import compute, mms_ns
from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import LUSGS, EulerSolver, Numerics
from aeroflowsim.euler.state import uniform_state
from aeroflowsim.euler.turbulence import SAModel, SSTModel, attach_turbulence, sa_chi_from_ratio, sa_fv1
from aeroflowsim.euler.viscous import SA, SST, ViscousSettings
from aeroflowsim.gases import gas_model
from aeroflowsim.simple_meshes import box_mesh_3d, geometric_points, graded_rectangle, rectangle_mesh

AIR = gas_model("air")


@pytest.fixture
def backend():
    old, old_threads = compute.backend(), compute._settings["threads"]
    yield
    compute.set_backend(old)
    compute.set_threads(old_threads)


def _plate(model, nx=24, ny=20, its=300, which=None, axisymmetric=False):
    if which:
        compute.set_backend(which)
    T, M = 300.0, 0.2
    a = float(AIR.sound_speed(T))
    U, mu = M * a, float(AIR.mu(T))
    rho = 5e6 * mu / U
    p = rho * AIR.R * T
    xs = np.concatenate([geometric_points(0.0, -0.33, 6, 2e-3)[::-1][:-1], geometric_points(0.0, 2.0, nx, 2e-3)])
    y0 = 0.5 if axisymmetric else 0.0
    ys = y0 + geometric_points(0.0, 1.0, ny, 1e-5)
    mesh = graded_rectangle(xs, ys, bottom=(("front", "symmetry", 0.0), ("plate", "wall", None)), axisymmetric=axisymmetric)
    fs = {"mach": M, "p": p, "T": T}
    bc = {"left": BoundaryCondition("far_field", fs), "top": BoundaryCondition("far_field", fs),
          "right": BoundaryCondition("pressure_outlet", {"p": p}), "front": BoundaryCondition("symmetry"),
          "plate": BoundaryCondition("no_slip_wall")}
    num = Numerics(time_scheme=LUSGS, cfl=5, cfl_max=1e3, max_iterations=its, residual_drop=12, limiter="None")
    s = EulerSolver(mesh, AIR, bc, num, viscous=ViscousSettings(model))
    attach_turbulence(s)
    return s, s.solve(uniform_state(mesh.n_cells, rho, (U, 0.0), p)), mu


def test_sa_functions():
    assert sa_fv1(0.0) == 0.0 and abs(sa_fv1(1e6) - 1.0) < 1e-9
    chi = sa_chi_from_ratio(0.21)
    assert abs(chi * sa_fv1(chi) - 0.21) < 1e-10


@pytest.mark.parametrize("model", [SA, SST])
def test_free_stream_is_preserved(model):
    """Uniform flow, no walls: SA's nu_tilde stays at its free-stream value (no vorticity, no wall). SST's k and omega
    decay physically along the stream (destruction without production): positive and never above the free stream."""
    mesh = rectangle_mesh(8, 6, distort=0.2)
    fs = {"mach": 0.5, "p": 1e5, "T": 300.0}
    bc = {p.name: BoundaryCondition("far_field", fs) for p in mesh.patches}
    s = EulerSolver(mesh, AIR, bc, Numerics(time_scheme=LUSGS, max_iterations=20, residual_drop=30),
                    viscous=ViscousSettings(model))
    t = attach_turbulence(s)
    rho = 1e5 / (AIR.R * 300.0)
    s.solve(uniform_state(mesh.n_cells, rho, (0.5 * float(AIR.sound_speed(300.0)), 0.0), 1e5))
    if model == SA:
        assert np.allclose(t.Q, t.Q_inf[:, None], rtol=1e-8)
    else:
        assert np.all(t.Q > 0.0) and np.all(t.Q <= t.Q_inf[:, None] * (1.0 + 1e-9))


def test_tmr_free_stream_values():
    mesh = rectangle_mesh(4, 4)
    fs = {"mach": 0.2, "p": 1e5, "T": 300.0}
    bc = {p.name: BoundaryCondition("far_field", fs) for p in mesh.patches}
    s = EulerSolver(mesh, AIR, bc, Numerics(), viscous=ViscousSettings(SST))
    t = attach_turbulence(s)
    a, rho, mu = float(AIR.sound_speed(300.0)), 1e5 / (AIR.R * 300.0), float(AIR.mu(300.0))
    assert np.allclose(t.Q_inf, [9e-9 * a * a, 1e-6 * rho * a * a / mu])
    s2 = EulerSolver(mesh, AIR, bc, Numerics(), viscous=ViscousSettings(SA))
    assert np.isclose(attach_turbulence(s2).Q_inf[0], 3.0 * mu / rho)


@pytest.mark.parametrize("model", [SA, SST])
def test_plate_runs_positive_and_turbulent(model):
    s, r, mu = _plate(model, its=2000)
    assert r.status != "diverged"
    assert np.all(s.turbulence.Q >= 0.0) and np.all(np.isfinite(s.turbulence.Q))
    assert (s.mu_t / mu).max() > 5.0           # a turbulent boundary layer develops


def test_axisymmetric_runs():
    s, r, mu = _plate(SA, axisymmetric=True, its=200)
    assert r.status != "diverged" and np.all(np.isfinite(s.mu_t))


@pytest.mark.parametrize("model", [SA, SST])
def test_numba_equals_numpy(model, backend):
    pytest.importorskip("numba")
    s1, r1, _ = _plate(model, its=40, which=compute.NUMPY)
    s2, r2, _ = _plate(model, its=40, which=compute.NUMBA)
    scale = np.abs(r1.W).max(axis=1, keepdims=True)
    assert np.all(np.abs(r1.W - r2.W) <= 1e-9 * scale)       # 40 coupled iterations: round-off growth allowed
    assert np.allclose(s1.turbulence.Q, s2.turbulence.Q, rtol=1e-8, atol=0.0)


def test_thread_independent(backend):
    pytest.importorskip("numba")
    compute.set_threads(1)
    s1, r1, _ = _plate(SST, its=30, which=compute.NUMBA)
    compute.set_threads(4)
    s4, r4, _ = _plate(SST, its=30, which=compute.NUMBA)
    assert np.array_equal(r1.W, r4.W) and np.array_equal(s1.turbulence.Q, s4.turbulence.Q)


def test_3d_extrusion_runs():
    from aeroflowsim.simple_meshes import extrude_2d
    s2, r2, mu = _plate(SA, nx=12, ny=12, its=60)
    mesh3 = extrude_2d(s2.mesh, depth=0.05)
    bc = {name: bc for name, bc, _l, _i in s2.patches}
    for p in mesh3.patches:
        bc.setdefault(p.name, BoundaryCondition("symmetry"))
    num = Numerics(time_scheme=LUSGS, cfl=5, cfl_max=1e3, max_iterations=60, residual_drop=12, limiter="None")
    s3 = EulerSolver(mesh3, AIR, bc, num, viscous=ViscousSettings(SA))
    attach_turbulence(s3)
    W0 = uniform_state(mesh3.n_cells, r2.W[0, 0], (r2.W[1].max(), 0.0, 0.0), r2.W[-1, 0])
    r3 = s3.solve(W0)
    assert r3.status != "diverged" and np.all(np.isfinite(s3.mu_t))


def test_transport_mms_first_order():
    """The turbulence transport operator converges at order ~1 (first-order upwind convection, as stated)."""
    r = [mms_ns.run_turbulence_level("quads", n) for n in (8, 16)]
    order = math.log(r[0][1] / r[1][1]) / math.log(r[0][0] / r[1][0])
    assert 0.8 < order < 1.3

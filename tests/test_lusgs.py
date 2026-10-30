# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Implicit LU-SGS (aeroflowsim/euler/kernels.py lusgs, solver.py): same converged solution as SSP-RK3, fewer
iterations, deterministic for any thread count, and the user's next actions (stop, continue with the CFL ramp
state, start from scratch, NumPy backend) behave as with the explicit schemes."""

import math

import numpy as np
import pytest

from aeroflowsim import compute
from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import LUSGS, SSP_RK3, Continuation, EulerSolver, Numerics
from aeroflowsim.euler.state import state_from_mach, uniform_state
from aeroflowsim.gases import gas_model
from aeroflowsim.mms import MMSSolver, exact_state, mms_mesh
from aeroflowsim.simple_meshes import rectangle_mesh as rectangle

AIR = gas_model("air")


@pytest.fixture
def restore():
    old, threads = compute.backend(), compute._settings["threads"]
    yield
    compute.set_backend(old)
    compute.set_threads(threads)


def _mms(scheme, kind="triangles", n=16, **kw):
    settings = {"limiter": "None", "carbuncle_fix": False, "time_scheme": scheme, "residual_drop": 10.0,
                "max_iterations": 40000, **kw}
    s = MMSSolver(mms_mesh(kind, n), AIR, Numerics(**settings))
    cc = s.geom.cell_centres
    return s, exact_state(cc[:, 0], cc[:, 1])


@pytest.mark.parametrize("kind", ["quads", "triangles", "mixed"])
def test_lusgs_converges_to_the_explicit_solution_in_fewer_iterations(kind):
    s, W0 = _mms(SSP_RK3, kind)
    ex = s.solve(W0.copy())
    s, W0 = _mms(LUSGS, kind)
    im = s.solve(W0.copy())
    assert ex.status == im.status == "converged"
    assert im.iterations < ex.iterations / 2.5
    rel = np.abs(im.W - ex.W).max(axis=1) / np.abs(ex.W).max(axis=1)
    assert rel.max() < 1e-9                      # both meet the 1e-10 residual drop: the same discrete solution


def test_lusgs_ramps_the_cfl_and_keeps_it_on_continue():
    s, W0 = _mms(LUSGS, max_iterations=60)
    first = s.solve(W0.copy())
    assert first.cfl_final > 10.0                # the ramp grew from 0.8
    cont = Continuation(first.iterations, first.residuals, first.monitors, first.norm, cfl=first.cfl_final)
    s2, _ = _mms(LUSGS, max_iterations=61)
    again = s2.solve(first.W.copy(), continuation=cont)
    assert again.first_iteration == 61 and again.cfl_final >= first.cfl_final    # no restart of the ramp
    s3, _ = _mms(LUSGS, max_iterations=1)
    fresh = s3.solve(first.W.copy())             # Start from scratch: the ramp starts again at the input CFL
    assert fresh.cfl_final == pytest.approx(0.8)


def test_lusgs_stop_keeps_the_flow_of_that_moment():
    s, W0 = _mms(LUSGS)
    out = s.solve(W0.copy(), progress=lambda it, level, info: it >= 15)
    assert out.status == "stopped" and out.iterations == 15


def test_lusgs_is_deterministic_for_any_thread_count(restore):
    pytest.importorskip("numba")
    compute.set_backend(compute.NUMBA)
    runs = []
    for n in (1, 2, 4, 1):
        compute.set_threads(n)
        s, W0 = _mms(LUSGS, max_iterations=80)
        runs.append(s.solve(W0.copy()))
    for r in runs[1:]:
        assert np.array_equal(r.W, runs[0].W) and np.array_equal(r.residuals, runs[0].residuals)


def test_lusgs_numpy_and_numba_backends_agree(restore):
    pytest.importorskip("numba")
    out = {}
    for which in (compute.NUMPY, compute.NUMBA):
        compute.set_backend(which)
        s, W0 = _mms(LUSGS, max_iterations=50)
        out[which] = s.solve(W0.copy())
    assert np.allclose(out[compute.NUMBA].W, out[compute.NUMPY].W, rtol=1e-9, atol=0)


def test_lusgs_free_stream_and_supersonic_start():
    mesh = rectangle(16, 10, triangles=True, distort=0.3)
    fs = {"mach": 2.0, "p": 1e5, "T": 300.0, "flow_angle": 15.0}
    bcs = {p.name: BoundaryCondition("far_field", fs) for p in mesh.patches}
    rho, vel = state_from_mach(AIR, 2.0, 1e5, 300.0, (math.cos(15 * math.pi / 180), math.sin(15 * math.pi / 180)))
    W0 = uniform_state(mesh.n_cells, rho, vel, 1e5)
    out = EulerSolver(mesh, AIR, bcs, Numerics(time_scheme=LUSGS, max_iterations=60, residual_drop=50)).solve(W0)
    scale = np.array([rho, np.linalg.norm(vel), np.linalg.norm(vel), 1e5])[:, None]
    assert (np.abs(out.W - W0) / scale).max() < 1e-12          # a uniform flow stays uniform at CFL 100
    # Start from rest inside a Mach 2 stream (a violent start): it must survive (CFL back-off) and converge
    W_rest = uniform_state(mesh.n_cells, rho, (0.0, 0.0), 1e5)
    out = EulerSolver(mesh, AIR, bcs, Numerics(time_scheme=LUSGS, max_iterations=3000, residual_drop=6,
                                               freeze_limiter_orders=4.0)).solve(W_rest)
    assert out.status == "converged" and (np.abs(out.W - W0) / scale).max() < 1e-3

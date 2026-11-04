# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Robust second order on triangles and tetrahedra: the Green-Gauss gradient with node values (vertex-neighbour
stencil) and the per-cell update limit of the implicit solver (docs/roadmap/robust_second_order.md)."""

import math

import numpy as np
import pytest

from aeroflowsim import compute
from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.geometry import FVGeometry
from aeroflowsim.euler.gradients import GREEN_GAUSS_NODES, Gradients
from aeroflowsim.euler.solver import LUSGS, SSP_RK3, EulerSolver, Numerics
from aeroflowsim.euler.state import primitive_to_conserved, state_from_mach, uniform_state
from aeroflowsim.gases import gas_model
from aeroflowsim.simple_meshes import BOX_KINDS, box_mesh_3d, rectangle_mesh

AIR = gas_model("air")
MESHES = {
    "triangles": lambda: rectangle_mesh(10, 8, triangles=True, distort=0.3),
    "quads": lambda: rectangle_mesh(10, 8, distort=0.3),
    "mixed": lambda: rectangle_mesh(10, 8, mixed=True, distort=0.3),
    "axisymmetric triangles": lambda: rectangle_mesh(10, 8, y0=0.0, axisymmetric=True, triangles=True, distort=0.3,
                                                     kinds={"bottom": "axis"}),
    **{f"3D {k}": (lambda k=k: box_mesh_3d(4, k, warp=0.03)) for k in BOX_KINDS},
}


@pytest.fixture
def backend():
    old, old_threads = compute.backend(), compute._settings["threads"]
    yield
    compute.set_backend(old)
    compute.set_threads(old_threads)


def _bcs(mesh):
    fs = {"mach": 1.6, "p": 9e4, "T": 280.0, "flow_angle": 10.0}
    return {p.name: BoundaryCondition("axis" if p.type == "axis" else "far_field", fs) for p in mesh.patches}


def _wavy(mesh):
    c = mesh.cell_centres
    x, y, z = c[:, 0], c[:, 1], c[:, 2]
    rows = [1.2 + 0.3 * np.sin(3 * x) * np.cos(2 * y), 400 + 80 * np.cos(2 * x + y), 60 * np.sin(4 * y) - 30 * x]
    if mesh.dim == 3:
        rows.append(40 * np.cos(3 * z) + 20 * y)
    rows.append(1e5 * (1.0 + 0.3 * np.cos(3 * x - y + z)) * np.where(x > 0.5, 3.0, 1.0))
    return np.array(rows)


def _solver(mesh, which, **numerics):
    compute.set_backend(which)
    nv = mesh.dim + 2
    s = EulerSolver(mesh, AIR, _bcs(mesh), Numerics(gradient=GREEN_GAUSS_NODES, **numerics), L_ref=1.0,
                    scales=(1.0,) + (500.0,) * (nv - 2) + (1e5,))
    assert s.backend == which
    return s


@pytest.mark.parametrize("name", ["triangles", "3D tetrahedra", "3D hex-prism", "3D pyramids"])
def test_node_gradient_is_exact_for_linear_fields_on_simplices(name):
    mesh = MESHES[name]()
    g = FVGeometry(mesh)
    grad = Gradients(g, GREEN_GAUSS_NODES)
    a = np.array([2.0, -3.0, 1.0])[:mesh.dim]
    f = lambda x: x[:, :mesh.dim] @ a
    out = grad.gradient(f(mesh.cell_centres)[None], f(mesh.face_centres[g.boundary_faces])[None])[0]
    tol = 1e-10
    assert np.abs(out - a[:, None]).max() < tol


@pytest.mark.parametrize("name", list(MESHES))
def test_node_gradient_numba_equals_numpy(name, backend):
    pytest.importorskip("numba")
    mesh = MESHES[name]()
    W = _wavy(mesh)
    out = {}
    for which in (compute.NUMPY, compute.NUMBA):
        s = _solver(mesh, which)
        R, _ = s.residual(primitive_to_conserved(W, AIR), True, W.copy())
        out[which] = R
    scale = np.abs(out[compute.NUMPY]).max(axis=1, keepdims=True)
    assert (np.abs(out[compute.NUMBA] - out[compute.NUMPY]) / scale).max() < 1e-12


@pytest.mark.parametrize("name", ["triangles", "3D tetrahedra", "3D hex-prism"])
@pytest.mark.parametrize("scheme", [SSP_RK3, LUSGS])
def test_free_stream_and_gas_at_rest_with_the_node_gradient(name, scheme, backend):
    mesh = MESHES[name]()
    s = _solver(mesh, compute.NUMPY, time_scheme=scheme, max_iterations=12,
                residual_drop=50, update_limit=0.2)
    a = math.radians(10.0)
    direction = (math.cos(a), math.sin(a)) + ((0.0,) if mesh.dim == 3 else ())
    rho, vel = state_from_mach(AIR, 1.6, 9e4, 280.0, direction)
    W0 = uniform_state(mesh.n_cells, rho, vel, 9e4)
    W = s.solve(W0.copy()).W
    scale = np.abs(W0).max(axis=1, keepdims=True)
    scale[1:-1] = np.abs(W0[1:-1]).max()                         # velocity components: the speed
    assert (np.abs(W - W0) / scale).max() < 1e-13
    walls = {p.name: BoundaryCondition("axis" if p.type == "axis" else "slip_wall") for p in mesh.patches}
    s = EulerSolver(mesh, AIR, walls, Numerics(gradient=GREEN_GAUSS_NODES, time_scheme=scheme, max_iterations=12,
                                              residual_drop=50))
    rest = uniform_state(mesh.n_cells, 1.2, (0.0,) * mesh.dim, 1e5)
    W = s.solve(rest.copy()).W
    assert np.abs(W[1:-1]).max() < 1e-10 and np.abs(W[-1] / 1e5 - 1.0).max() < 1e-12


def test_node_gradient_runs_do_not_depend_on_the_thread_count(backend):
    kernels = pytest.importorskip("aeroflowsim.euler.kernels")
    if kernels.numba is None:
        pytest.skip("no Numba")
    mesh = box_mesh_3d(5, "tetrahedra", warp=0.03)
    runs = []
    for n in sorted({1, 2, min(4, kernels.numba.config.NUMBA_NUM_THREADS)}):
        compute.set_threads(n)
        s = _solver(mesh, compute.NUMBA, time_scheme=LUSGS, max_iterations=30, residual_drop=50, cfl=0.5)
        runs.append(s.solve(_wavy(mesh)))
    for r in runs[1:]:
        assert np.array_equal(r.W, runs[0].W) and np.array_equal(r.residuals, runs[0].residuals)


def test_mms_order_with_the_node_gradient():
    from aeroflowsim import mms
    tets = [mms.run_level_3d("tetrahedra", n, residual_drop=8.0, gradient=GREEN_GAUSS_NODES) for n in (6, 12)]
    assert min(mms.observed_orders(tets)[0]) > 1.6           # least squares on the same boxes: 1.65


# ---- the update limit -----------------------------------------------------------------------------------------

def test_update_limit_changes_nothing_where_no_cell_exceeds_it(backend):
    mesh = MESHES["triangles"]()
    W = _wavy(mesh) * np.array([[1.0], [1.0], [1.0], [1.0 / 3.0]])        # mild: no 20 % changes per iteration
    runs = []
    for limit in (0.0, 0.9):
        s = _solver(mesh, compute.NUMPY, time_scheme=LUSGS, max_iterations=15, residual_drop=50, update_limit=limit,
                    cfl=0.5)
        runs.append(s.solve(W.copy()))
    assert runs[1].limited_updates == 0 and np.array_equal(runs[0].W, runs[1].W)


def test_update_limit_bounds_every_relative_change_and_is_counted(backend):
    mesh = MESHES["triangles"]()
    s = _solver(mesh, compute.NUMPY, time_scheme=LUSGS, update_limit=0.05)
    W = _wavy(mesh)
    U = primitive_to_conserved(W, AIR)
    R, _ = s.residual(U, True, W)
    dU = s._lusgs(U, W, R, s.time_steps(W, 50.0))
    limited = s._limit_update(U, dU, 0.05)
    W_new = s._primitive(U + limited)
    assert s.last_limited > 0
    assert np.all(np.abs(W_new[-1] - W[-1]) / W[-1] <= 0.05 + 1e-9)
    assert np.all(np.abs(limited[0]) / U[0] <= 0.05 + 1e-9)


def test_new_input_at_its_old_value_keeps_old_project_fingerprints(tmp_path):
    from aeroflowsim.project import Project
    project = Project.create("cases/external_2d", tmp_path / "old.afsproj")
    before = project.fingerprint("run")
    assert project.values["update_limit"] == 0.0
    del project.values["update_limit"]                  # an old project's file has no such value ...
    project.save()
    again = Project.open(tmp_path / "old.afsproj")      # ... and gets the default 0 when opened
    assert again.values["update_limit"] == 0.0 and again.fingerprint("run") == before
    again.values["update_limit"] = 0.2                  # switching it on makes the result out of date
    assert again.fingerprint("run") != before

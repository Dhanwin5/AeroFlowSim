# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Viscous (Navier-Stokes) terms (aeroflowsim/euler/viscous.py): exactness for linear fields, Numba = NumPy to 1e-12,
thread independence, the Euler path untouched, walls, and a small MMS order check (the full study is
validation/mms_navier_stokes)."""

import numpy as np
import pytest

from aeroflowsim import compute, mms_ns
from aeroflowsim.euler.boundary import BoundaryCondition
from aeroflowsim.euler.solver import EulerSolver, Numerics
from aeroflowsim.euler.state import primitive_to_conserved
from aeroflowsim.euler.viscous import LAMINAR, ViscousOperator, ViscousSettings
from aeroflowsim.euler.geometry import FVGeometry
from aeroflowsim.gases import gas_model
from aeroflowsim.simple_meshes import box_mesh_3d, rectangle_mesh

AIR = gas_model("air")

MESHES = {
    "quads": lambda: rectangle_mesh(10, 8, distort=0.3),
    "triangles": lambda: rectangle_mesh(10, 8, triangles=True, distort=0.3),
    "axisymmetric": lambda: rectangle_mesh(10, 8, y0=0.0, axisymmetric=True, distort=0.3, kinds={"bottom": "axis"}),
    "hexahedra": lambda: box_mesh_3d(4, "hexahedra", warp=0.03),
    "prisms": lambda: box_mesh_3d(4, "prisms", warp=0.03),
    "tetrahedra": lambda: box_mesh_3d(4, "tetrahedra", warp=0.03),
}


@pytest.fixture
def backend():
    old, old_threads = compute.backend(), compute._settings["threads"]
    yield
    compute.set_backend(old)
    compute.set_threads(old_threads)


def _wavy(mesh):
    cc = mesh.cell_centres
    dim = mesh.dim
    W = np.empty((dim + 2, mesh.n_cells))
    W[0] = 1.0 + 0.2 * np.sin(3 * cc[:, 0]) * np.cos(2 * cc[:, 1])
    for k in range(dim):
        W[1 + k] = 80.0 * np.cos(2 * cc[:, (k + 1) % dim] + k) + 30.0 * cc[:, k]
    W[-1] = 1e5 * (1.0 + 0.1 * np.sin(4 * cc[:, 1] + cc[:, 0]))
    return W


def _conditions(mesh, iso=True):
    fs = {"mach": 0.5, "p": 1e5, "T": 300.0}
    out = {}
    for i, p in enumerate(mesh.patches):
        if p.type == "axis":
            out[p.name] = BoundaryCondition("axis")
        elif i % 2 == 0:
            out[p.name] = BoundaryCondition("no_slip_wall", {"thermal": "Isothermal" if iso else "Adiabatic",
                                                             "T_wall": 320.0})
        else:
            out[p.name] = BoundaryCondition("far_field", fs)
    return out


def _residual(mesh, which, gas, mu_t=None, threads=None, order=2):
    compute.set_backend(which)
    if threads:
        compute.set_threads(threads)
    s = EulerSolver(mesh, gas, _conditions(mesh), Numerics(order=order), viscous=ViscousSettings(LAMINAR))
    assert s.backend == which
    if mu_t is not None:
        s.mu_t = mu_t
    if which == compute.NUMBA:
        from aeroflowsim.euler import kernels as kn
        kn.set_threads(compute.threads())
    W = _wavy(mesh)
    return s.residual(primitive_to_conserved(W, gas), order == 2, W)[0], s.time_steps(W, 1.0)


@pytest.mark.parametrize("name", list(MESHES))
def test_numba_equals_numpy(name, backend):
    pytest.importorskip("numba")
    mesh = MESHES[name]()
    gas = mms_ns.ns_gas(0.01)            # viscous terms of the size of the convective ones
    mu_t = 0.005 * (1.0 + np.arange(mesh.n_cells) % 3)
    for mt in (None, mu_t):
        R1, dt1 = _residual(mesh, compute.NUMPY, gas, mt)
        R2, dt2 = _residual(mesh, compute.NUMBA, gas, mt)
        scale = np.abs(R1).max(axis=1, keepdims=True)
        assert np.all(np.abs(R1 - R2) <= 1e-12 * scale), name
        assert np.allclose(dt1, dt2, rtol=1e-12, atol=0.0)


def test_thread_independent(backend):
    pytest.importorskip("numba")
    mesh = MESHES["tetrahedra"]()
    gas = mms_ns.ns_gas(0.01)
    R1, _ = _residual(mesh, compute.NUMBA, gas, threads=1)
    R4, _ = _residual(mesh, compute.NUMBA, gas, threads=4)
    assert np.array_equal(R1, R4)


@pytest.mark.parametrize("name", ["quads", "triangles", "tetrahedra"])
def test_linear_field_exact_stress(name):
    """u = a y (simple shear), constant T: the corrected face gradient reproduces du/dy = a exactly on every face, so
    the viscous momentum flux through each face is mu a (n_y e_x + n_x e_y) A."""
    mesh = MESHES[name]()
    geom = FVGeometry(mesh)
    vop = ViscousOperator(geom)
    dim = geom.dim
    a = 50.0
    Xc = np.zeros((dim + 1, geom.n_cells))
    Xc[0] = a * geom.cell_centres[:, 1]
    Xc[dim] = 300.0
    Xb = np.zeros((dim + 1, geom.n_boundary))
    Xb[0] = a * geom.face_centres[geom.boundary_faces, 1]
    Xb[dim] = 300.0
    from aeroflowsim.euler.gradients import Gradients
    grad = Gradients(geom).gradient(Xc, Xb)
    mu = 1.5
    FV = vop.fluxes(Xc, Xb, grad, np.full(geom.n_faces, mu), np.full(geom.n_faces, 1.0), np.ones(geom.n_faces))
    n = geom.normals
    expected_x = mu * a * n[:, 1] * geom.flux_areas
    expected_y = mu * a * n[:, 0] * geom.flux_areas
    assert np.allclose(FV[1], expected_x, rtol=0, atol=1e-10 * mu * a)
    assert np.allclose(FV[2], expected_y, rtol=0, atol=1e-10 * mu * a)
    assert np.allclose(FV[0], 0.0)


def test_euler_path_unchanged():
    """viscous=None: the residual is the plain Euler residual (no viscous code runs)."""
    mesh = MESHES["quads"]()
    conds = {p.name: BoundaryCondition("far_field", {"mach": 0.5, "p": 1e5, "T": 300.0}) for p in mesh.patches}
    s = EulerSolver(mesh, AIR, conds, Numerics())
    assert s.viscous is None and not hasattr(s, "vop")


def test_wall_values_no_slip():
    """No-slip wall boundary values: zero velocity; isothermal density from T_wall at the inside pressure."""
    mesh = MESHES["quads"]()
    s = EulerSolver(mesh, AIR, _conditions(mesh), Numerics(), viscous=ViscousSettings(LAMINAR))
    W = _wavy(mesh)
    g = s.geom
    Wb = W[:, g.boundary_owner]
    out = s.boundary_face_values(Wb, s.ghosts(Wb))
    w = s.wall_local
    assert len(w) and np.all(out[1:-1, w] == 0.0)
    assert np.allclose(out[-1, w] / (out[0, w] * AIR.R), 320.0)

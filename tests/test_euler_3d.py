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


# ---- 3D MMS (Part 2) ---------------------------------------------------------------------------------------

def test_3d_mms_source_equals_the_divergence_of_the_exact_flux():
    """source_3d (hand-written derivatives) against central differences of the exact Euler flux."""
    from aeroflowsim import mms
    from aeroflowsim.euler.flux import physical_flux
    rng = np.random.default_rng(5)
    pts = rng.uniform(0.1, 0.9, (3, 20))
    h = 1e-5
    div = np.zeros((5, 20))
    for k in range(3):
        n = np.zeros((20, 3))
        n[:, k] = 1.0
        for sign in (1.0, -1.0):
            q = pts.copy()
            q[k] += sign * h
            W = mms.exact_state_3d(*q)
            U = primitive_to_conserved(W, AIR)
            div += sign * physical_flux(W, U, W[1 + k], n) / (2.0 * h)
    S = mms.source_3d(*pts, AIR)
    assert np.allclose(S, div, rtol=1e-6, atol=1e-6 * np.abs(S).max(axis=1, keepdims=True))


@pytest.mark.parametrize("kind,minimum", [("hexahedra", 1.8), ("prisms", 1.6), ("tetrahedra", 1.55)])
def test_3d_mms_is_second_order_on_small_boxes(kind, minimum):
    """Observed L2 order between 6^3 and 12^3 boxes (coarse; the full study is validation/mms_euler3d)."""
    from aeroflowsim import mms
    runs = [mms.run_level_3d(kind, n, residual_drop=8.0) for n in (6, 12)]
    assert min(mms.observed_orders(runs)[0]) > minimum


# ---- 3D mesh import (Part 2) -----------------------------------------------------------------------------------

TYPES = {"xmin": "inlet", "xmax": "outlet", "ymin": "wall", "ymax": "wall", "zmin": "symmetry", "zmax": "farfield"}


@pytest.mark.parametrize("kind", BOX_KINDS)
@pytest.mark.parametrize("fmt", ["gmsh2", "gmsh4", "su2"])
def test_3d_meshes_round_trip_through_gmsh_and_su2(kind, fmt, tmp_path):
    from aeroflowsim import mesh_io
    mesh = box_mesh_3d(3, kind, warp=0.03, kinds=TYPES)
    path = tmp_path / ("m.su2" if fmt == "su2" else "m.msh")
    if fmt == "su2":
        mesh_io.write_su2_3d(mesh, path)
    else:
        mesh_io.write_gmsh_3d(mesh, path, "2.2" if fmt == "gmsh2" else "4.1")
    raw = mesh_io.read_mesh_file(path)
    assert raw.dim == 3 and raw.n_cells == mesh.n_cells and "z " in mesh_io.size_text(raw)
    back = mesh_io.mesh_from_raw(raw, "mm", patch_types=TYPES)
    assert back.dim == 3 and back.n_cells == mesh.n_cells and back.cell_volumes.min() > 0.0
    assert math.isclose(back.cell_volumes.sum(), 1e-9, rel_tol=1e-12)            # 1 m³ read as mm³
    assert [(p.name, p.type, p.count) for p in back.patches] == [(p.name, p.type, p.count) for p in mesh.patches]


def test_3d_import_turns_inside_out_cells_round_and_requires_every_face_tagged(tmp_path):
    from aeroflowsim import mesh_io
    mesh = box_mesh_3d(2, "tetrahedra", kinds=TYPES)
    path = mesh_io.write_su2_3d(mesh, tmp_path / "m.su2")
    raw = mesh_io.read_mesh_file(path)
    t, conn = raw.cells[0]
    conn[:, [1, 2]] = conn[:, [2, 1]]                                   # every tetrahedron inside out
    assert mesh_io.mesh_from_raw(raw, patch_types=TYPES).cell_volumes.min() > 0.0
    del raw.groups["zmax"]
    with pytest.raises(ValueError, match="no tag"):
        mesh_io.mesh_from_raw(raw, patch_types=TYPES)
    with pytest.raises(ValueError, match="axisymmetric"):
        mesh_io.mesh_from_raw(mesh_io.read_mesh_file(path), axisymmetric=True, patch_types=TYPES)


def test_an_imported_3d_mesh_keeps_a_free_stream_uniform(tmp_path, backend):
    from aeroflowsim import mesh_io
    mesh = box_mesh_3d(3, "pyramids", warp=0.03, kinds={k: "farfield" for k in TYPES})
    back = mesh_io.import_mesh(mesh_io.write_gmsh_3d(mesh, tmp_path / "p.msh", "4.1"), patch_types={k: "farfield" for k in TYPES})
    s = _solver(back, compute.NUMPY, Numerics(time_scheme=LUSGS, max_iterations=10, residual_drop=50))
    W0 = _free_stream_state(back.n_cells)
    assert (np.abs(s.solve(W0.copy()).W - W0) / np.abs(W0).max(axis=1, keepdims=True)).max() < 1e-13


# ---- consistency checks of the addendum (Part 3) -------------------------------------------------------------------

def test_a_closed_body_in_uniform_pressure_feels_no_force(backend):
    """Gas at rest at uniform pressure around a closed body: the integral of p n A over the body is zero to round-off."""
    from aeroflowsim.euler import forces
    mesh = box_mesh_3d(4, "tetrahedra", warp=0.04, kinds={k: "wall" for k in TYPES})    # the box is the "body"
    walls = {p.name: BoundaryCondition("slip_wall") for p in mesh.patches}
    s = _solver(mesh, compute.NUMPY, Numerics(max_iterations=1, residual_drop=50), walls)
    W = uniform_state(mesh.n_cells, 1.2, (0.0, 0.0, 0.0), 1e5)
    s.residual(primitive_to_conserved(W, AIR), True, W)
    s.stage0_boundary_flux = s.boundary_flux
    f = forces.body_forces_3d(s, list(walls), 0.0, 1.0, 0.0, 0.0, 1.0, 1.0)
    assert max(abs(f[k]) for k in ("Fx", "Fy", "Fz", "Mx", "My", "Mz")) < 1e-9 * 1e5


def test_symmetry_mirroring_of_forces_and_moments():
    """A force and moment on the meshed half: the mirror plane y = 0 doubles Fx, Fz, My and cancels Fy, Mx, Mz."""
    from types import SimpleNamespace
    from aeroflowsim.euler import forces
    geom = SimpleNamespace(n_interior=0, flux_areas=np.array([1.0]), face_centres=np.array([[1.0, 2.0, 3.0]]))
    s = SimpleNamespace(geom=geom, patches=[("w", None, np.array([0]), None)], boundary_normals=np.array([[0.0, 0, 1]]),
                        stage0_boundary_flux=np.array([[0.0], [1.0], [2.0], [3.0], [0.0]]))
    one = forces.body_forces_3d(s, ["w"], 0.0, 1.0, 0.0, 0.0, 1.0, 1.0)
    half = forces.body_forces_3d(s, ["w"], 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, planes=(1,))
    assert (half["Fx"], half["Fy"], half["Fz"]) == (2 * one["Fx"], 0.0, 2 * one["Fz"])
    assert (half["Mx"], half["My"], half["Mz"]) == (0.0, 2 * one["My"], 0.0) and half["factor"] == 2.0
    assert one["Cm"] == -one["CMz"]


def test_a_one_layer_extrusion_reproduces_the_2d_residual():
    """The 2D residual of a non-uniform flow and the 3D residual of its one-layer extrusion (symmetry sides) agree to
    round-off, first and second order, with the limiter (Barth-Jespersen: no cell-size term) and without."""
    from aeroflowsim.simple_meshes import extrude_2d, rectangle_mesh
    m2 = rectangle_mesh(10, 8, triangles=True, distort=0.3, mixed=True,
                        kinds={"left": "farfield", "right": "farfield", "bottom": "wall", "top": "farfield"})
    m3 = extrude_2d(m2)
    assert m3.n_cells == m2.n_cells and m3.cell_volumes.min() > 0
    x, y = m2.cell_centres[:, 0], m2.cell_centres[:, 1]
    W2 = np.array([1.2 + 0.3 * np.sin(3 * x) * np.cos(2 * y), 500 + 80 * np.cos(2 * x + y), 60 * np.sin(4 * y) - 30 * x,
                   1e5 * (1 + 0.3 * np.cos(3 * x - y)) * np.where(x > 0.5, 2.5, 1.0)])
    W3 = np.insert(W2, 3, 0.0, axis=0)
    fs = {"mach": 1.6, "p": 9e4, "T": 280.0, "flow_angle": 10.0}
    for limiter in ("Barth-Jespersen", "None"):
        for order in (1, 2):
            out = []
            for m, W in ((m2, W2), (m3, W3)):
                # supersonic inlet / outlet: the far field blends its outflow branches in 3D only (boundary.far_field)
                kinds = {"left": ("supersonic_inlet", fs), "right": ("supersonic_outlet", {}),
                         "top": ("supersonic_outlet", {}), "bottom": ("slip_wall", {})}
                bcs = {p.name: BoundaryCondition(*kinds.get(p.name, ("symmetry", {}))) for p in m.patches}
                compute.set_backend(compute.NUMPY)
                s = EulerSolver(m, AIR, bcs, Numerics(order=order, limiter=limiter), L_ref=1.0,
                                scales=(1.0,) + (500.0,) * m.dim + (1e5,))
                R, _ = s.residual(primitive_to_conserved(W, AIR), order == 2, W)
                out.append(R)
            R2, R3 = out
            assert np.abs(R3[3]).max() < 1e-9 * np.abs(R3).max()             # no z-momentum
            assert _rel(np.delete(R3, 3, axis=0), R2) < 1e-10, (limiter, order)
    compute.set_backend(compute.AUTO)


# ---- 3D internal flow (Part 4) -----------------------------------------------------------------------------------

def _nozzle_meshes(n_theta=4):
    pytest.importorskip("gmsh")
    from aeroflowsim.discovery import load_case
    from aeroflowsim.parameters import defaults, validate
    from aeroflowsim.simple_meshes import revolve_axisymmetric
    from aeroflowsim.workspace_mesh import mesh_for
    case = load_case("cases/nozzle_axi")
    p = validate(case.parameters(), {**defaults(case.parameters()), "mesh_preset": "Coarse"})
    m2 = mesh_for(case, p)
    return case, p, m2, revolve_axisymmetric(m2, 90.0, n_theta)


def test_revolved_nozzle_is_a_closed_quarter_with_symmetry_planes():
    from aeroflowsim.euler.forces import symmetry_planes
    _case, _p, m2, m3 = _nozzle_meshes(n_theta=6)
    assert {p.name for p in m3.patches} == {"inlet", "outlet", "wall", "symmetry"}
    assert symmetry_planes(m3, ["symmetry"]) == (1, 2) and m3.cell_volumes.min() > 0.0
    n = 4 * 6                                        # polygon of 24 sides round the axis instead of a circle
    polygon = n / (2 * math.pi) * math.sin(2 * math.pi / n)
    assert 4 * m3.cell_volumes.sum() == pytest.approx(2 * math.pi * m2.axi_cell_volumes.sum() * polygon, rel=1e-3)


def test_a_short_3d_nozzle_run_reports_whole_nozzle_numbers():
    from aeroflowsim.discovery import load_case
    from aeroflowsim.parameters import defaults, validate
    from aeroflowsim.euler.setup import mesh_wall_profile
    case2, p2, m2, m3 = _nozzle_meshes()
    ext = load_case("cases/external_3d")
    bnd = {"inlet": {"type": "total_pressure_inlet", "p0": p2["p0"], "T0": p2["T0"]},
           "outlet": {"type": "pressure_outlet", "p": p2["p_back"]}}
    p = validate(ext.parameters(), {**defaults(ext.parameters()), "gas": p2["gas"], "boundaries": bnd,
                                    "time_scheme": "Implicit LU-SGS", "venkat_k": 5.0, "first_order_iterations": 0,
                                    "max_iter": 1500})
    assert ext.is_internal(m3)
    r = ext.run(p, m3, lambda *a: False)
    k = r.key_numbers
    assert k["symmetry_factor"][0] == 4.0 and r.info["kind"] == "nozzle"
    n = 16
    polygon = n / (2 * math.pi) * math.sin(2 * math.pi / n)
    r_t = float(mesh_wall_profile(m2, ["wall"]).r.min())                         # the 2D profile's throat radius
    assert k["A_throat"][0] == pytest.approx(math.pi * r_t ** 2, rel=1e-9)
    assert 0.93 < k["discharge_coefficient"][0] / polygon < 0.96        # coarse 2D axisymmetric: 0.946
    assert k["F_vacuum"][0] == pytest.approx(k["F_vacuum_wall"][0], rel=0.02)
    assert k["mdot_inlet"][0] == pytest.approx(k["mdot"][0], rel=0.02)

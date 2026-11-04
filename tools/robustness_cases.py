# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The reproduction set of the robust-second-order stage: cases that do not converge at second order on triangles and
tetrahedra, plus hexahedron / prism controls. Developer tool (not packaged).

    python tools/robustness_cases.py                         every case, default numerics
    python tools/robustness_cases.py sphere3 cone '{"gradient": "Green-Gauss"}'   named cases, numerics overrides (JSON)

Per case one line: status, iterations, final residual, CFL reductions, positivity fallbacks, wall clock, the case's
measured number; then the worst cell of the final state (largest |d rho/dt| / rho): position, type, boundary, skewness,
volume ratio to its neighbours, limiter psi (rho, p), relative pressure gradient |grad p| h / p.
"""

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CAP = {"sphere3": 3000, "sphere6": 3000, "cone": 6000, "ramp_tet": 3000, "ramp_hex": 3000, "ramp_prism": 3000,
       "cylinder2d": 4000}


def _template(case, inputs):
    import aeroflowsim
    out = aeroflowsim.run_case(case, inputs)
    return out.mesh, out.result, out.params


def sphere(mach, numerics):
    from validation.euler3d_sphere import validate as v
    inputs = {**v.SPHERE_3D, "surface_size": 0.02, "farfield_size": 0.12, "mach": mach, **numerics}
    mesh, r, p = _template("cases/external_3d", inputs)
    standoff = float("nan") if r.info["status"] == "diverged" else v.standoff_3d(
        type("O", (), {"mesh": mesh, "result": r, "params": p}), mach)
    return mesh, r, p, f"stand-off/R {standoff:.4f} (Billig {v.billig(mach):.4f})"


def cone(numerics):
    from validation.euler3d_cone import validate as v
    out = type("O", (), {})()
    out.mesh, out.result, out.params = _template("cases/external_3d", {**v.BASE, "surface_size": 0.015,
                                                                       "farfield_size": 0.06, **numerics})
    m = v._measure(out) if out.result.info["status"] != "diverged" else {"beta": float("nan"), "Cp": float("nan")}
    return out.mesh, out.result, out.params, f"beta {m['beta']:.3f} (31.206), Cp {m['Cp']:.5f} (0.10447)"


def cylinder2d(numerics):
    mesh, r, p = _template("cases/external_2d", {"shape": "Circular cylinder", "mach": 3.0, **numerics})
    return mesh, r, p, f"Cd {r.key_numbers['Cd'][0]:.4f}"


def ramp(kind, numerics):
    """30 deg compression ramp at Mach 2 in a box (detached shock): Kuhn tetrahedra, hexahedra or prisms, 16 cells."""
    from types import SimpleNamespace
    from aeroflowsim.euler.boundary import BoundaryCondition
    from aeroflowsim.euler.setup import EQUATIONS_3D
    from aeroflowsim.euler.solver import EulerSolver, LUSGS, Numerics
    from aeroflowsim.euler.state import state_from_mach, uniform_state
    from aeroflowsim.gases import gas_model
    from aeroflowsim.mesh import Mesh
    from aeroflowsim.simple_meshes import box_mesh_3d
    gas = gas_model("air")
    m0 = box_mesh_3d(16, kind, nz=4, hi=(1.0, 1.0, 0.25),
                     kinds={"xmin": "farfield", "xmax": "farfield", "ymin": "wall", "ymax": "farfield",
                            "zmin": "symmetry", "zmax": "symmetry"})
    X = m0.nodes.copy()
    lift = np.maximum(X[:, 0] - 0.3, 0.0) * math.tan(math.radians(30.0))
    X[:, 1] = lift + (1.0 - lift) * X[:, 1]
    mesh = Mesh(X, m0.cell_types, m0.cell_nodes, m0.face_nodes, m0.owner, m0.neighbour, m0.patches, 3)
    fs = {"mach": 2.0, "p": 1e5, "T": 300.0}
    bcs = {p.name: BoundaryCondition("far_field", fs) if p.type == "farfield" else
           BoundaryCondition("slip_wall" if p.type == "wall" else "symmetry") for p in mesh.patches}
    rho, vel = state_from_mach(gas, 2.0, 1e5, 300.0, (1, 0, 0))
    opts = {"time_scheme": LUSGS, "max_iterations": CAP["ramp_tet"], "residual_drop": 8.0,
            "freeze_limiter_orders": 4.0}
    names = {"cfl", "order", "gradient", "limiter", "venkat_k", "first_order_iterations", "time_scheme", "carbuncle_fix",
             "cfl_max", "update_limit"}
    opts.update({k: v for k, v in numerics.items() if k in names})
    s = EulerSolver(mesh, gas, bcs, Numerics(**opts), L_ref=1.0, scales=(rho, 700, 700, 700, 1e5))
    out = s.solve(uniform_state(mesh.n_cells, rho, vel, 1e5))
    r = SimpleNamespace(iterations=out.iterations, residuals=out.residuals.max(axis=1) if len(out.residuals) else [1.0],
                        converged=out.status == "converged", key_numbers={"wall_time": (out.wall_time_s, "s")},
                        info={"status": out.status, "cfl_reductions": out.cfl_reductions,
                              "positivity_events": out.positivity_events, "diverged_at": out.diverged_at,
                              "limited_updates": out.limited_updates,
                              "equations": list(EQUATIONS_3D)},
                        W=out.W, solver=s)
    return mesh, r, {}, ""


def _diagnose(mesh, r, params):
    """Worst cell of the final state: where |d rho / dt| / rho is largest."""
    from aeroflowsim import mesh_quality as mq
    from aeroflowsim.euler.state import primitive_to_conserved
    if hasattr(r, "solver"):
        solver, W = r.solver, r.W
    else:
        from aeroflowsim.post.solution import Solution
        sol = Solution.from_result(mesh, r, params)
        solver, W = sol._solver, sol.W
    if solver is None or not np.all(np.isfinite(W)):
        return "no diagnosis (no boundary conditions or a non-finite state)"
    R, _ = solver.residual(primitive_to_conserved(W, solver.gas), True, W)
    rel = np.abs(R[0]) / W[0]
    c = int(np.argmax(rel))
    share = float(np.sort(rel ** 2)[::-1][:max(1, len(rel) // 100)].sum() / np.sum(rel ** 2))
    skew = mq.skewness(mesh)[c]
    vr = mq.volume_ratio(mesh)[c]
    psi = solver.last_psi[:, c] if getattr(solver, "last_psi", None) is not None else np.full(W.shape[0], np.nan)
    gp = solver.grad.gradient(W, solver.boundary_face_values(W[:, solver.geom.boundary_owner],
                                                              solver.ghosts(W[:, solver.geom.boundary_owner])))[-1, :, c]
    h = solver.geom.cell_size[c]
    on = [p.name for p in mesh.patches if c in set(mesh.owner[p.faces].tolist())]
    return (f"worst cell {c} at {np.round(mesh.cell_centres[c], 4).tolist()} type {int(mesh.cell_types[c])} "
            f"boundary {on or '-'} skew {skew:.2f} vol.ratio {vr:.2f} psi(rho,p) {psi[0]:.2f},{psi[-1]:.2f} "
            f"|grad p| h/p {np.linalg.norm(gp) * h / W[-1, c]:.3f}; top 1 % of cells hold {100 * share:.0f} % "
            "of the residual")


SOLVER_ONLY = {"cfl_max", "backend"}     # Numerics fields that are not template inputs

CASES = {
    "sphere3": lambda n: sphere(3.0, {"max_iter": CAP["sphere3"], **n}),
    "sphere6": lambda n: sphere(6.0, {"max_iter": CAP["sphere6"], **n}),
    "cone": lambda n: cone({"max_iter": CAP["cone"], **n}),
    "ramp_tet": lambda n: ramp("tetrahedra", n),
    "ramp_hex": lambda n: ramp("hexahedra", n),
    "ramp_prism": lambda n: ramp("prisms", n),
    "cylinder2d": lambda n: cylinder2d({"max_iter": CAP["cylinder2d"], **n}),
}


def main(argv):
    numerics = {}
    names = []
    for a in argv:
        if a.startswith("{"):
            numerics = json.loads(a)
        else:
            names.append(a)
    import os
    solver_only = {k: v for k, v in numerics.items() if k in SOLVER_ONLY}
    if solver_only.pop("backend", None) == "numpy":
        from aeroflowsim import compute
        compute.set_backend(compute.NUMPY)
    if solver_only:                        # Numerics fields that are not template inputs: the developer knob
        os.environ["AEROFLOWSIM_NUMERICS"] = json.dumps(solver_only)
        numerics = {k: v for k, v in numerics.items() if k not in SOLVER_ONLY}
        numerics_ramp = solver_only
    else:
        numerics_ramp = {}
    for name in names or list(CASES):
        t = time.perf_counter()
        mesh, r, params, number = CASES[name]({**numerics, **numerics_ramp} if name.startswith("ramp") else numerics)
        info = r.info
        res = r.residuals[-1] if len(r.residuals) else float("nan")
        print(f"{name:11s} {mesh.n_cells:>7,} cells  {info['status']:14s} it {r.iterations:>6,}  res {res:.1e}  "
              f"CFL red {info['cfl_reductions']}  positivity {int(info['positivity_events']):,}  "
              f"limited {int(info.get('limited_updates', 0)):,}  "
              f"{time.perf_counter() - t:6.0f} s  {number}", flush=True)
        print(f"            {_diagnose(mesh, r, params)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])

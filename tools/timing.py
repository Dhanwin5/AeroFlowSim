# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Timing of the 2D Euler solver: milliseconds per iteration on the validation meshes, and where the time goes.

Each case runs a few hundred iterations (not to convergence): the time per iteration does not depend on how far
the run is, so ms/iteration x the iteration count of the validation run estimates the full wall time without
re-running hours of work. Writes a Markdown table (validation/timing.md is assembled from these tables).

    python tools/timing.py --backend numpy --iterations 200 --out timing_numpy.md
    python tools/timing.py --backend numba --threads 1
    python tools/timing.py --threads-table             speed-up versus thread count on three mesh sizes
    python tools/timing.py --profile                   where the time of one residual goes (NumPy and Numba)
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from aeroflowsim import compute  # noqa: E402

# Iterations of the validation runs (validation/report.md, post-processing and alpha release stage), to estimate the full wall time.
STORED_ITERATIONS = {"MMS quads 128": 20367, "MMS triangles 128": 29216, "N2 nozzle Coarse": 8095,
                     "N2 nozzle Medium": 24688, "N2 nozzle triangles 0.04": 30000, "wedge 0.02 L": 1935,
                     "cylinder polar 60 x 80": 6184, "diamond 0.01 c alpha 0": 1358, "NACA 0012 0.01 c M 0.8": 12771}


def _mms(kind, n):
    from aeroflowsim.euler.solver import Numerics
    from aeroflowsim.gases.library import gas_model
    from aeroflowsim.mms import MMSSolver, exact_state, mms_mesh

    mesh = mms_mesh(kind, n)
    solver = MMSSolver(mesh, gas_model("air"), Numerics(limiter="None", carbuncle_fix=False))
    cc = solver.geom.cell_centres
    return solver, exact_state(cc[:, 0], cc[:, 1])


def _engine(case, inputs, mesh=None, boundaries=None):
    """(solver, W0) of a template run, built exactly as aeroflowsim.run_case builds it."""
    import aeroflowsim
    from aeroflowsim.discovery import load_case
    from aeroflowsim.parameters import defaults, validate

    case = load_case(case)
    params = validate(case.parameters(), {**defaults(case.parameters()), **inputs, "max_iter": 1})
    if boundaries:
        params["boundaries"] = boundaries
    captured = {}
    from aeroflowsim.euler import solver as solver_module
    original = solver_module.EulerSolver.solve

    def capture(self, W0, *args, **kwargs):
        captured["solver"], captured["W0"] = self, W0.copy()
        return original(self, W0, *args, **kwargs)

    solver_module.EulerSolver.solve = capture
    try:
        aeroflowsim.run_case(case, params, mesh=mesh)
    finally:
        solver_module.EulerSolver.solve = original
    return captured["solver"], captured["W0"]


def _naca(size):
    from aeroflowsim.discovery import load_case
    from aeroflowsim.geometry_model import template_document
    from aeroflowsim.geometry_model.operations import Enclosure
    from aeroflowsim.parameters import defaults, validate
    from aeroflowsim.workspace_mesh import mesh_for

    case = load_case("cases/external_2d")
    inputs = {"shape": "Custom coordinates file", "mach": 0.8, "alpha": 1.25, "surface_size": size,
              "coordinates_file.file": str(ROOT / "validation/euler2d_naca0012/naca0012_vassberg_jameson.dat"),
              "farfield_size": 2.0, "size_growth": 1.15}
    params = validate(case.parameters(), {**defaults(case.parameters()), **inputs})
    doc = template_document(case)
    doc.operations[1].suppressed = True
    doc.add(Enclosure(kind="c_domain", radius=30.0, downstream=30.0))
    return _engine("cases/external_2d", inputs, mesh=mesh_for(case, params, doc))


def cases():
    """name -> builder of (solver, W0). Same inputs as the validation scripts."""
    from aeroflowsim.simple_meshes import cylinder_front_mesh
    from validation.euler2d_cylinder.validate import FREE_STREAM, POLAR
    from validation.euler2d_diamond.validate import BASE as DIAMOND
    from validation.euler2d_wedge.validate import INPUTS as WEDGE

    noz = "cases/nozzle_axi"
    return {
        "MMS quads 64": lambda: _mms("quads", 64),
        "MMS quads 128": lambda: _mms("quads", 128),
        "MMS triangles 64": lambda: _mms("triangles", 64),
        "MMS triangles 128": lambda: _mms("triangles", 128),
        "N2 nozzle Coarse": lambda: _engine(noz, {"mesh_preset": "Coarse"}),
        "N2 nozzle Medium": lambda: _engine(noz, {"mesh_preset": "Medium"}),
        "N2 nozzle Fine": lambda: _engine(noz, {"mesh_preset": "Fine"}),
        "N2 nozzle triangles 0.04": lambda: _engine(noz, {"mesh_type": "Triangles (Gmsh)", "surface_size": 0.04,
                                                          "max_size": 0.2}),
        "wedge 0.02 L": lambda: _engine("cases/external_2d", WEDGE),
        "cylinder polar 60 x 80": lambda: _engine("cases/external_2d", FREE_STREAM, cylinder_front_mesh(**POLAR),
                                                  {"outlet": {"type": "supersonic_outlet"}}),
        "diamond 0.01 c alpha 0": lambda: _engine("cases/external_2d", {**DIAMOND, "surface_size": 0.01,
                                                                        "farfield_size": 0.05, "alpha": 0.0}),
        "NACA 0012 0.01 c M 0.8": lambda: _naca(0.01),
        "NACA 0012 C-grid Medium": lambda: _engine("cases/external_2d", {"shape": "NACA 4-digit airfoil",
                                                                         "mesh_type": "Structured C/O-grid",
                                                                         "grid_preset": "Medium", "mach": 0.8}),
    }


def ms_per_iteration(solver, W0, iterations, warmup=3):
    """Mean wall time of one solver iteration [ms] (second order, as the validation runs)."""
    from aeroflowsim.euler.solver import Numerics
    num = solver.numerics
    keep = (num.max_iterations, num.residual_drop, num.first_order_iterations, num.freeze_limiter_orders)
    num.residual_drop, num.first_order_iterations, num.freeze_limiter_orders = 99.0, 0, 0.0
    num.max_iterations = warmup
    solver.solve(W0.copy())                        # first call: compiles the kernels (not timed)
    num.max_iterations = iterations
    res = solver.solve(W0.copy())
    num.max_iterations, num.residual_drop, num.first_order_iterations, num.freeze_limiter_orders = keep
    assert isinstance(num, Numerics)
    return 1000.0 * res.wall_time_s / max(res.iterations, 1), res.iterations


def table(names, iterations):
    lines = [f"Backend: {compute.backend()}, threads: {compute.threads()}, {iterations} iterations per case.", "",
             "| Case | Cells | ms / iteration | Iterations (validation run) | Estimated wall time [s] |",
             "|---|---:|---:|---:|---:|"]
    builders = cases()
    for name in names:
        solver, W0 = builders[name]()
        ms, _n = ms_per_iteration(solver, W0, iterations)
        stored = STORED_ITERATIONS.get(name)
        est = f"{ms * stored / 1000.0:.0f}" if stored else "-"
        lines.append(f"| {name} | {solver.geom.n_cells:,} | {ms:.2f} | {stored if stored else '-':,} | {est} |"
                     if stored else f"| {name} | {solver.geom.n_cells:,} | {ms:.2f} | - | - |")
        print(lines[-1], flush=True)
    return lines


def profile(iterations=50):
    """Time of each part of one residual evaluation on the MMS 128 x 128 quads (NumPy reference path)."""
    from aeroflowsim.euler.flux import hybrid_flux
    from aeroflowsim.euler.limiters import limiter_factors
    from aeroflowsim.euler.state import conserved_to_primitive, is_physical, primitive_to_conserved

    solver, W0 = _mms("quads", 128)
    solver.numerics.limiter = "Venkatakrishnan"     # include the limiter, as the flow cases use it
    g, nI = solver.geom, solver.geom.n_interior
    parts = dict.fromkeys(("state conversion", "ghost states", "gradients", "limiter", "reconstruction",
                           "flux", "face sums", "time steps"), 0.0)
    U = primitive_to_conserved(W0, solver.gas)
    for _ in range(iterations):
        t = time.perf_counter()
        W = conserved_to_primitive(U, solver.gas)
        t1 = time.perf_counter(); parts["state conversion"] += t1 - t   # noqa: E702
        Wb_in = W[:, g.boundary_owner]
        ghost_c = solver.ghosts(Wb_in)
        Wb = solver.boundary_face_values(Wb_in, ghost_c)
        t2 = time.perf_counter(); parts["ghost states"] += t2 - t1      # noqa: E702
        grad = solver.grad.gradient(W, Wb)
        t3 = time.perf_counter(); parts["gradients"] += t3 - t2         # noqa: E702
        dW = g.change_to_faces(grad)
        psi = limiter_factors(g, grad, W, Wb, "Venkatakrishnan", 5.0, 1.0, solver.scales, delta=dW)
        t4 = time.perf_counter(); parts["limiter"] += t4 - t3           # noqa: E702
        dW *= psi[:, :, None]
        WL = W[:, g.owner] + dW[:, g.owner, g.owner_slot]
        WR = np.concatenate([W[:, g.neighbour] + dW[:, g.neighbour, g.neighbour_slot], solver.ghosts(WL[:, nI:])], 1)
        _bad = ~(is_physical(WL) & is_physical(WR))
        t5 = time.perf_counter(); parts["reconstruction"] += t5 - t4    # noqa: E702
        F = hybrid_flux(WL, WR, g.normals, solver.gas, None)
        t6 = time.perf_counter(); parts["flux"] += t6 - t5              # noqa: E702
        R = g.sum_over_faces(F * g.flux_areas)
        t7 = time.perf_counter(); parts["face sums"] += t7 - t6         # noqa: E702
        solver.time_steps(W, 0.8)
        parts["time steps"] += time.perf_counter() - t7
        del R
    total = sum(parts.values())
    lines = [f"Profile of one residual evaluation (NumPy reference path, MMS 128 x 128 quads, {g.n_cells:,} cells, "
             f"Venkatakrishnan limiter), mean of {iterations}:", "",
             "| Part | ms | Share |", "|---|---:|---:|"]
    for k, v in parts.items():
        lines.append(f"| {k} | {1000 * v / iterations:.2f} | {100 * v / total:.0f} % |")
    lines.append(f"| total | {1000 * total / iterations:.2f} | 100 % |")
    print("\n".join(lines))
    return lines


def threads_table(iterations=100, counts=(1, 2, 4, 8, 16, 24)):
    names = ("MMS quads 64", "MMS quads 128", "MMS quads 256")
    builders = {"MMS quads 64": lambda: _mms("quads", 64), "MMS quads 128": lambda: _mms("quads", 128),
                "MMS quads 256": lambda: _mms("quads", 256)}
    counts = [c for c in counts if c <= compute.max_threads()]
    head = "| Mesh | Cells | " + " | ".join(f"{c} thr. [ms]" for c in counts) + f" | speed-up at {counts[-1]} |"
    lines = ["Numba backend, ms per iteration (SSP-RK3, three residuals per iteration):", "", head,
             "|---|---:|" + "---:|" * (len(counts) + 1)]
    for name in names:
        solver, W0 = builders[name]()
        times = []
        for c in counts:
            compute.set_threads(c)
            times.append(ms_per_iteration(solver, W0, iterations)[0])
        lines.append(f"| {name} | {solver.geom.n_cells:,} | " + " | ".join(f"{t:.2f}" for t in times)
                     + f" | {times[0] / times[-1]:.1f} x |")
        print(lines[-1], flush=True)
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default=None, choices=compute.BACKENDS)
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--iterations", type=int, default=200)
    ap.add_argument("--cases", default=None, help="comma-separated case names (default: all)")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--threads-table", action="store_true")
    ap.add_argument("--out", default=None, help="write the table to this Markdown file")
    a = ap.parse_args(argv)
    if a.backend:
        compute.set_backend(a.backend)
    if a.threads:
        compute.set_threads(a.threads)
    if a.profile:
        lines = profile()
    elif a.threads_table:
        lines = threads_table(a.iterations)
    else:
        names = a.cases.split(",") if a.cases else list(cases())
        lines = table(names, a.iterations)
    if a.out:
        Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

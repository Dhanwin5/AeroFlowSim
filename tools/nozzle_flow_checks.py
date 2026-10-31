# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Quick flow runs on the new nozzle contours (Shapes, grids and mesh import stage): checks that the contours WORK, not new validation cases.

    python tools/nozzle_flow_checks.py [bell] [moc]        (no argument: both; one result line each)

bell   Rao bell (area ratio 25, 80 % length, throat diameter 20 mm) as a wall-profile CSV in the axisymmetric nozzle_axi template
       (N2, p0 = 5 bar, T0 = 293 K): mass flow against the choked flow of the throat, and the exit Mach number against the
       isentropic Mach number of the area ratio.
moc    Planar minimum-length nozzle (Mach 2.4, gamma 1.4) with a short converging inlet, solved directly with the Euler solver on a
       structured planar mesh (there is no planar nozzle template yet: gap register): mass flow against the choked flow of the
       throat and the Mach number on the exit plane against the design Mach number 2.4 (the contour is designed for it).
"""

import math
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np                                              # noqa: E402

import aeroflowsim                                              # noqa: E402
from aeroflowsim import gasdynamics as gd                       # noqa: E402
from aeroflowsim import nozzle_contours as nc                   # noqa: E402
from aeroflowsim.euler.boundary import BoundaryCondition       # noqa: E402
from aeroflowsim.euler.solver import EulerSolver, Numerics     # noqa: E402
from aeroflowsim.euler.state import mach_number, uniform_state  # noqa: E402
from aeroflowsim.gases import gas_model                         # noqa: E402
from aeroflowsim.geometry import write_profile_csv             # noqa: E402
from aeroflowsim.mesh import QUAD, Mesh                         # noqa: E402


def report(name, ok, text):
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {text}", flush=True)


def bell():
    rt, eps, gamma = 0.01, 25.0, 1.4
    wall = nc.bell_nozzle(rt, eps, 0.8)
    path = Path(tempfile.mkdtemp()) / "bell.csv"
    write_profile_csv(path, wall, np.linspace(wall.x[0], wall.x[-1], 600))
    start = time.time()
    out = aeroflowsim.run_case("cases/nozzle_axi", {"geometry_source": "Custom profile (CSV)", "profile_csv": str(path),
                                                    "gas": "N2", "p0": 5e5, "T0": 293.15, "p_back": 1000.0, "max_iter": 20000})
    k, r = out.result.key_numbers, out.result
    print(f"      {out.mesh.n_cells:,} cells, {r.iterations:,} iterations, converged {r.converged}, {time.time() - start:.0f} s; "
          f"key numbers: {', '.join(k)}", flush=True)
    gas = gas_model("N2")
    mdot_ideal = gd.choked_mass_flow(5e5, 293.15, math.pi * rt**2, 1.4, gas.R)
    mdot = k["mdot"][0]
    M_ideal = gd.mach_from_area_ratio(eps, 1.4, True)
    exit_M = k["M_exit"][0]
    report("Rao bell in nozzle_axi", abs(mdot / mdot_ideal - 1) < 0.02 and abs(exit_M / M_ideal - 1) < 0.05,
           f"mass flow {mdot:.5f} kg/s vs choked {mdot_ideal:.5f} ({mdot / mdot_ideal - 1:+.2%}), exit Mach {exit_M:.3f} vs "
           f"isentropic {M_ideal:.3f}")


def moc():
    gamma, h, M_design = 1.4, 0.005, 2.4
    wall = nc.moc_min_length_nozzle(M_design, gamma, h, 40)
    inlet = np.array([[-6 * h, 3 * h], [0.0, h]])                          # straight converging inlet, 3 h high
    xs = np.r_[np.linspace(inlet[0, 0], 0.0, 25)[:-1], wall.x]
    rs = np.r_[np.interp(np.linspace(inlet[0, 0], 0.0, 25)[:-1], inlet[:, 0], inlet[:, 1]), wall.r]
    nx, ny = len(xs) - 1, 40 if "--debug" not in sys.argv else 20
    s = np.linspace(0.0, 1.0, ny + 1) ** 1.0
    X = np.repeat(xs[:, None], ny + 1, axis=1)
    Y = rs[:, None] * s[None, :]
    nodes = np.column_stack([X.ravel(), Y.ravel()])
    ids = lambda i, j: i * (ny + 1) + j                                     # noqa: E731
    cells = [[ids(i, j), ids(i + 1, j), ids(i + 1, j + 1), ids(i, j + 1)] for i in range(nx) for j in range(ny)]
    boundary = {"inlet": ("inlet", [[ids(0, j), ids(0, j + 1)] for j in range(ny)]),
                "outlet": ("outlet", [[ids(nx, j), ids(nx, j + 1)] for j in range(ny)]),
                "wall": ("wall", [[ids(i, ny), ids(i + 1, ny)] for i in range(nx)]),
                "symmetry": ("symmetry", [[ids(i, 0), ids(i + 1, 0)] for i in range(nx)])}
    mesh = Mesh.from_cells(nodes, QUAD, np.array(cells), {k: (t, np.array(v)) for k, (t, v) in boundary.items()}, dim=2)
    gas = gas_model("air")
    p0, T0 = 5e5, 300.0
    p_exit = p0 / gd.p0_over_p(M_design, gamma)                         # the pressure of the design exit Mach number [Pa]
    bcs = {"inlet": BoundaryCondition("total_pressure_inlet", {"p0": p0, "T0": T0}),
           "outlet": BoundaryCondition("pressure_outlet", {"p": 0.5 * p_exit}), "wall": BoundaryCondition("slip_wall"),
           "symmetry": BoundaryCondition("symmetry")}
    rho0 = p0 / (gas.R * T0)
    # start from the isentropic quasi-1D flow of the area ratio (subsonic before the throat, supersonic after it)
    xc = mesh.cell_centres[:, 0]
    area = np.interp(xc, xs, rs) / h
    M0 = np.array([gd.mach_from_area_ratio(max(a, 1.0), gamma, bool(x > 0.0)) for a, x in zip(area, xc)])
    T = T0 / gd.t0_over_t(M0, gamma)
    p = p0 / gd.p0_over_p(M0, gamma)
    rho = p / (gas.R * T)
    u = M0 * np.sqrt(gamma * gas.R * T)
    W0 = np.vstack([rho, u, np.zeros_like(rho), p])                         # primitive variables (rho, u, v, p)
    start = time.time()
    out = EulerSolver(mesh, gas, bcs, Numerics(order=2, max_iterations=20000 if "--debug" not in sys.argv else 8000, residual_drop=1e5, cfl=0.5)).solve(W0)
    print(f"      {mesh.n_cells:,} cells, {out.iterations:,} iterations, {time.time() - start:.0f} s", flush=True)
    W = out.W
    M = mach_number(W, gas)
    last = [c for c in range(mesh.n_cells) if mesh.cell_centres[c, 0] > xs[-2]]
    exit_M = float(np.mean(M[last]))
    if "--debug" in sys.argv:
        print(f"      exit column: centre-line Mach {M[last][np.argmin(mesh.cell_centres[last, 1])]:.3f}, wall Mach "
              f"{M[last][np.argmax(mesh.cell_centres[last, 1])]:.3f}, mean {exit_M:.3f}", flush=True)
    face = mesh.patch("outlet").faces
    mdot = float(np.sum((W[0] * W[1])[mesh.owner[face]] * mesh.face_area_vectors[face][:, 0]))   # rho u_x x area of the exit faces [kg/s per m]
    if "--debug" in sys.argv:
        inner = np.flatnonzero(mesh.neighbour >= 0)
        sx = mesh.face_area_vectors[inner][:, 0]
        for x_station in xs[::max(1, len(xs) // 10)]:
            on = inner[np.abs(mesh.face_centres[inner, 0] - x_station) < 1e-12]
            rho_u = W[0] * W[1]
            flux = 0.5 * (rho_u[mesh.owner[on]] + rho_u[mesh.neighbour[on]]) * mesh.face_area_vectors[on][:, 0]
            print(f"      x = {x_station * 1e3:7.2f} mm: half-nozzle mass flow {flux.sum():.4f} kg/s/m", flush=True)
        print(f"      residual history end: {out.residuals[-3:] if hasattr(out, 'residuals') else 'n/a'}", flush=True)
    mdot_ideal = gd.choked_mass_flow(p0, T0, h, gamma, gas.R)                     # the half nozzle: throat area h x 1 m
    report("MOC planar nozzle", abs(exit_M / M_design - 1) < 0.05,
           f"exit-plane Mach {exit_M:.3f} vs design {M_design} (back pressure 0.5 x the design exit pressure {p_exit:.0f} Pa: supersonic exit), flow {mdot:.4f} vs choked {mdot_ideal:.4f} kg/s/m (half nozzle)")


if __name__ == "__main__":
    for name in [a for a in sys.argv[1:] if not a.startswith("--")] or ["bell", "moc"]:
        {"bell": bell, "moc": moc}[name]()

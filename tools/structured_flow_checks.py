# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Quick flow runs on the structured grids (Shapes, grids and mesh import stage): checks that the meshes WORK with the solver, not new validation cases.

    python tools/structured_flow_checks.py [naca] [cylinder]      (no argument: both; results are printed as one line each)

naca      NACA 0012 (Vassberg and Jameson geometry, validation/euler2d_naca0012), Mach 0.5, alpha 1.25 deg: the same flow on
          a C-grid and on a Gmsh triangle mesh (wall cells 0.01 c, far field 30 c), Cl and Cd side by side and against the
          reference of the validation case. No tuning: both meshes use the template's default numerics.
cylinder  Mach 6 cylinder (validation/euler2d_cylinder) on an O-grid (half domain, far field 4 D): the bow-shock stand-off
          distance against Billig's correlation and the carbuncle metric (a settled shock gives a tiny number).
"""

import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np                                              # noqa: E402

import aeroflowsim                                              # noqa: E402
from aeroflowsim.discovery import load_case                     # noqa: E402
from aeroflowsim.parameters import defaults                     # noqa: E402

CASE = "cases/external_2d"
NACA_FILE = ROOT / "validation" / "euler2d_naca0012" / "naca0012_vassberg_jameson.dat"
CL_REFERENCE = 0.179969                                         # Vassberg and Jameson, Mach 0.5, alpha 1.25 deg


def report(name, ok, text):
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {text}", flush=True)


def naca():
    base = {"shape": "Custom coordinates file", "coordinates_file.file": str(NACA_FILE), "mach": 0.5, "alpha": 1.25,
            "max_iter": 8000}
    rows = {}
    for name, extra in (("C-grid Medium", {"mesh_type": "Structured C/O-grid", "grid_preset": "Medium",
                                           "grid_first_height": 0.002, "grid_far_distance": 30.0}),
                        ("triangles", {"surface_size": 0.01, "farfield_size": 2.0, "size_growth": 1.15,
                                       "domain_radius": 30.0})):
        start = time.time()
        out = aeroflowsim.run_case(CASE, {**base, **extra})
        k = out.result.key_numbers
        rows[name] = (out.mesh.n_cells, k["Cl"][0], k["Cd"][0], out.result.iterations, out.result.converged)
        print(f"      {name}: {out.mesh.n_cells:,} cells, Cl = {k['Cl'][0]:.4f}, Cd = {k['Cd'][0]:.5f}, "
              f"{out.result.iterations:,} iterations, converged {out.result.converged}, {time.time() - start:.0f} s", flush=True)
    (_, cl_c, cd_c, _, _), (_, cl_t, cd_t, _, _) = rows["C-grid Medium"], rows["triangles"]
    report("NACA 0012 C-grid vs triangles (Mach 0.5, alpha 1.25)", abs(cl_c - cl_t) < 0.02 and abs(cd_c) < 0.002 and abs(cd_t) < 0.002,
           f"Cl {cl_c:.4f} vs {cl_t:.4f} (reference {CL_REFERENCE:.4f}), Cd {cd_c:.5f} vs {cd_t:.5f}")


def cylinder():
    from validation.euler2d_cylinder import validate as cyl
    base = {**cyl.FREE_STREAM, "shape": "Circular cylinder", "half_domain": True, "mesh_type": "Structured C/O-grid",
            "grid_preset": "Medium", "grid_first_height": 0.002, "grid_far_distance": 4.0}
    start = time.time()
    values = {**base, "max_iter": 12000}
    out = aeroflowsim.run_case(CASE, values, extras={"report_definitions": [cyl.SHOCK_BOX]})
    r = out.result
    standoff = cyl._standoff(out)
    carbuncle = cyl.carbuncle_metric(r)
    billig = 0.5 * 0.386 * math.exp(4.67 / cyl.MACH**2)
    print(f"      O-grid: {out.mesh.n_cells:,} cells, {r.iterations:,} iterations, converged {r.converged}, "
          f"residual {r.residuals[-1]:.1e}, {time.time() - start:.0f} s", flush=True)
    report("Mach 6 cylinder O-grid", abs(standoff / billig - 1.0) < 0.1 and carbuncle < 1e-2,
           f"stand-off {standoff:.4f} D (Billig {billig:.4f}), carbuncle metric {carbuncle:.1e}")


if __name__ == "__main__":
    which = sys.argv[1:] or ["naca", "cylinder"]
    for name in which:
        {"naca": naca, "cylinder": cylinder}[name]()

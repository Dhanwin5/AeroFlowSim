# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Full 3D release stage, Part 1: why do bow shocks sit too far out on triangle / tetrahedron meshes?

One hypothesis, one experiment. Each run is one configuration of the 2D cylinder on triangles (external_2d, Mach 3,
the validation case euler2d_cylinder_triangles) or the 3D sphere (external_3d, Mach 3, quarter domain, the validation
case euler3d_sphere), with the stand-off measured exactly as the validation scripts do. Results are appended as one
JSON line per run to the output file, so a long study can be read while it runs.

    python tools/shock_position_study.py 2d   <name> [key=value ...]  [--numerics '{"venkat_k": 20}']
    python tools/shock_position_study.py 3d   <name> [key=value ...]
    python tools/shock_position_study.py axi  <name> [key=value ...]   (sphere, 2D axisymmetric, structured)
    python tools/shock_position_study.py polar <name> n_r=60 n_theta=80 [key=value ...]   (structured quads)

key=value pairs are template inputs (numbers are parsed); --numerics sets Numerics fields on top (the developer knob
AEROFLOWSIM_NUMERICS). Output: validation/results/shock_study.jsonl.
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
OUT = ROOT / "validation" / "results" / "shock_study.jsonl"


def _value(text):
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            pass
    return {"true": True, "false": False}.get(text.lower(), text)


def _standoff_symmetry(out, v):
    """Stand-off / R on the polar grid (front of the cylinder at x = 0, R = 0.5 m): the cells along the symmetry line
    (the grid has a cell row on y = 0+), the last half-way crossing of the pressure, linear interpolation."""
    import numpy as np
    from aeroflowsim.gasdynamics import normal_shock
    mesh = out.mesh
    cells = mesh.owner[mesh.patch("symmetry").faces]
    x = mesh.cell_centres[cells, 0]
    o = np.argsort(x)
    x, p = x[o], out.result.fields["p"].values[cells][o]
    level = 0.5 * (1.0 + normal_shock(v.MACH, 1.4)["p2_p1"]) * out.params["p_inf"]
    i = np.flatnonzero((p[:-1] < level) & (p[1:] >= level))[-1]
    return -float(x[i] + (level - p[i]) * (x[i + 1] - x[i]) / (p[i + 1] - p[i])) / 0.5


def main(argv):
    dim, name, rest = argv[0], argv[1], argv[2:]
    if "--numerics" in rest:
        i = rest.index("--numerics")
        os.environ["AEROFLOWSIM_NUMERICS"] = rest[i + 1]
        rest = rest[:i] + rest[i + 2:]
    extra = {k: _value(v) for k, v in (a.split("=", 1) for a in rest)}
    t0 = time.time()
    if dim == "polar":                       # the same Mach 3 cylinder on the structured polar grid (quads)
        from validation.euler2d_cylinder_triangles import validate as v
        from aeroflowsim.simple_meshes import cylinder_front_mesh
        import aeroflowsim
        n_r, n_theta = int(extra.pop("n_r", 60)), int(extra.pop("n_theta", 80))
        mesh = cylinder_front_mesh(n_r=n_r, n_theta=n_theta)
        inputs = {**v.INPUTS, "boundaries": {"outlet": {"type": "supersonic_outlet"}}, **extra}
        out = aeroflowsim.run_case("cases/external_2d", inputs, mesh=mesh)
        extra.update({"n_r": n_r, "n_theta": n_theta})
        standoff = _standoff_symmetry(out, v)
        ref = v.billig()
    elif dim == "axi":                       # the sphere as a 2D axisymmetric run (structured O-grid), Mach 3
        from validation.euler3d_sphere import validate as v
        import aeroflowsim
        inputs = {"shape": "Sphere", "sphere.diameter": v.D, "mesh_type": "Structured C/O-grid", "mach": 3.0,
                  "first_order_iterations": 200, "max_iter": 20000, **extra}
        out = aeroflowsim.run_case("cases/external_2d", inputs)
        standoff = v.standoff_2d(out, 3.0)
        ref = v.billig(3.0)
    elif dim == "2d":
        from validation.euler2d_cylinder_triangles import validate as v
        import aeroflowsim
        out = aeroflowsim.run_case("cases/external_2d", {**v.INPUTS, **extra})
        standoff = v._standoff(out)
        ref = v.billig()
    else:
        from validation.euler3d_sphere import validate as v
        import aeroflowsim
        out = aeroflowsim.run_case("cases/external_3d", {**v.SPHERE_3D, **v._sizes_3d(), "mach": 3.0, **extra})
        standoff = v.standoff_3d(out, 3.0)
        ref = v.billig(3.0)
    r = out.result
    row = {"dim": dim, "name": name, "inputs": extra, "numerics": os.environ.get("AEROFLOWSIM_NUMERICS", ""),
           "cells": int(out.mesh.n_cells), "iterations": int(r.iterations), "status": r.info["status"],
           "residual": float(r.residuals[-1]), "standoff": float(standoff), "reference": ref,
           "error_percent": 100.0 * (standoff / ref - 1.0), "Cd": float(r.key_numbers["Cd"][0]),
           "seconds": round(time.time() - t0, 1)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row))


if __name__ == "__main__":
    main(sys.argv[1:])

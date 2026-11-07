# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""ONERA M6 wing, Euler, M = 0.8395, 3.06 deg (full 3D release stage). The wing is built here from the NASA NPARC
data (validation/onera_m6/data): ONERA D section (foilmod.txt, closed trailing edge), root chord 0.8059 m, taper 0.562,
leading-edge sweep 30 deg, span b = 1.1963 m, no twist; a loft (OpenCASCADE ThruSections) from root to tip, written as a
STEP file and imported into external_3d (half domain y >= 0: the root on the symmetry plane).

Axes: span along +y (the template's half domain keeps y >= 0), thickness along z. external_3d turns alpha towards +y,
so the incidence is given as the sideslip beta = 3.06 deg (flow towards +z): the same flow; the lift is the side force.
Cp at a section: view3d.wall_cut of the wing at y = eta b, split into upper (z above the chord line) and lower surface,
interpolated at the measured x/c points."""

import math
from pathlib import Path

import numpy as np

import aeroflowsim
from validation.common import is_quick

HERE = Path(__file__).parent
DATA = HERE / "data"
B = 1.1963                                # semi-span [m]
C_ROOT = 0.8059                           # root chord [m]
TAPER = 0.562
SWEEP_LE = 30.0                           # deg
MACH, INCIDENCE = 0.8395, 3.06
SECTIONS = {1: 0.20, 2: 0.44, 3: 0.65, 4: 0.80, 5: 0.90, 6: 0.95}
RUNS = {}


def section_points():
    """Closed ONERA D section (x/c, z/c), from the upper half in foilmod.txt (symmetric profile)."""
    xz = np.loadtxt(DATA / "foilmod.txt")
    upper = xz[np.argsort(xz[:, 0])]
    lower = upper[::-1][1:-1] * np.array([1.0, -1.0])
    return np.vstack([upper, lower])


def chord_at(y):
    return C_ROOT * (1.0 - (1.0 - TAPER) * y / B)


def x_le(y):
    return y * math.tan(math.radians(SWEEP_LE))


def write_step(path):
    """The wing as a STEP solid (gmsh / OpenCASCADE loft of the root and tip sections)."""
    import gmsh
    sec = section_points()
    gmsh.initialize(["-noenv"])
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        occ = gmsh.model.occ
        loops = []
        for y in (0.0, B):
            c = chord_at(y)
            pts = [occ.addPoint(x_le(y) + c * x, y, c * z) for x, z in sec]
            # Two splines (upper LE -> TE, lower TE -> LE) meeting at the sharp trailing edge: one closed spline
            # through the corner overshoots there and gives Gmsh coincident surface points.
            te = len(sec) // 2
            upper = occ.addSpline(pts[:te + 1])
            lower = occ.addSpline(pts[te:] + [pts[0]])
            loops.append(occ.addWire([upper, lower]))
        occ.addThruSections(loops, makeSolid=True, makeRuled=True)
        occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def _sizes():
    return (0.03, 0.4) if is_quick() else (0.012, 0.25)      # wall cell size, largest size [m]


def run():
    from aeroflowsim.geometry_model import GeometryDocument, ReplayContext
    from aeroflowsim.geometry_model.operations3d import Enclosure3D, ImportSolid
    from aeroflowsim.workspace_mesh3d import MeshSettings3D, mesh_3d
    out_dir = (HERE.parent / "results").resolve()
    out_dir.mkdir(exist_ok=True)
    step = write_step((out_dir / "onera_m6.step").resolve())
    surface, largest = _sizes()
    doc = GeometryDocument([ImportSolid("wing", file=str(step), unit="m", role="solid"),
                            Enclosure3D("domain", kind="box", upstream=5.0, downstream=8.0, lateral=5.0, half=True)],
                           dimension=3)
    mesh = mesh_3d(doc, ReplayContext(folder=out_dir), MeshSettings3D(surface_size=surface, max_size=largest,
                                                                       growth=1.2, curvature=36))
    area = 0.5 * (C_ROOT + chord_at(B)) * B                       # half-wing planform area [m^2]
    params = {"mach": MACH, "alpha": 0.0, "beta": INCIDENCE, "half_domain": True, "reference_area": 2.0 * area,
              "reference_length": 0.64607, "max_iter": 3000 if is_quick() else 12000}
    return aeroflowsim.run_case("cases/external_3d", params, mesh=mesh)


def section_cp(out, eta):
    """(x/c, Cp) of the upper and the lower surface of the computed wing at y = eta b."""
    from aeroflowsim.post import view3d
    from aeroflowsim.post.fields import node_values
    from aeroflowsim.post.solution import Solution
    sol = Solution.from_result(out.mesh, out.result, out.params)
    walls = [p.name for p in out.mesh.patches if p.type == "wall"]
    surface = view3d.patch_surface(out.mesh, walls, node_values(sol, "Cp"))
    y = eta * B
    pts, cp = view3d.wall_cut(surface, (0.0, y, 0.0), (0.0, 1.0, 0.0))
    xc = (pts[:, 0] - x_le(y)) / chord_at(y)
    upper = pts[:, 2] >= 0.0
    return {"u": (xc[upper], cp[upper]), "l": (xc[~upper], cp[~upper])}


def measure():
    out = run()
    r = out.result
    rms = {}
    for k, eta in SECTIONS.items():
        comp = section_cp(out, eta)
        diffs = []
        for side in ("u", "l"):
            exp = np.loadtxt(DATA / f"cp{k}{side}.ex")
            x, cp = comp[side]
            o = np.argsort(x)
            diffs.append(np.interp(exp[:, 0], x[o], cp[o]) - exp[:, 1])
        d = np.concatenate(diffs)
        rms[k] = float(np.sqrt(np.mean(d * d)))
    RUNS["Euler"] = {"cells": out.mesh.n_cells, "iterations": r.iterations, "converged": r.converged,
                     "time": r.key_numbers["wall_time"][0], "rms": rms,
                     "CL": r.key_numbers.get("Cy", (float("nan"),))[0], "CD": r.key_numbers["Cd"][0]}
    return {"cp_rms": float(np.mean(list(rms.values())))}


def study():
    m = RUNS["Euler"]
    rows = [[f"{k} (y/b = {SECTIONS[k]:.2f})", f"{v:.4f}"] for k, v in m["rms"].items()]
    return {"title": "Cp RMS difference per section", "columns": ["Section", "RMS(Delta Cp)"], "rows": rows,
            "notes": [f"Euler, {m['cells']:,} cells, {m['iterations']:,} iterations, converged: {m['converged']}, "
                      f"{m['time']:.0f} s; CL (side force) {m['CL']:.4f}, CD {m['CD']:.4f}.",
                      "Spalart-Allmaras not run in this stage (time box): SHORTFALL."]}

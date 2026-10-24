# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mach 6 cylinder with the external_2d template: bow-shock stand-off distance and the carbuncle test.

Three runs through the one engine (aeroflowsim.run_case):
  1. a structured polar grid in front of the cylinder (aeroflowsim.simple_meshes.cylinder_front_mesh), whose
     grid lines follow the bow shock - the setting that provokes the carbuncle - with the carbuncle fix on;
  2. the same grid with the fix OFF (pure HLLC), to show what the fix does;
  3. the template's own Gmsh mesh (quad-dominant, half domain around the whole cylinder), fix on.
The stand-off distance is where the pressure in the cells along the stagnation line (y = 0) crosses half-way between the free
stream and the normal-shock value. The shock-front roughness is the largest jump of the shock radius between
neighbouring grid rays, relative to the radial cell size: a carbuncle or an odd-even wiggle makes it grow.
"""

import math

import numpy as np

import aeroflowsim
from aeroflowsim.gasdynamics import normal_shock
from aeroflowsim.simple_meshes import cylinder_front_mesh

CASE = "cases/external_2d"
MACH, P_INF, T_INF = 6.0, 1000.0, 220.0
FREE_STREAM = {"shape": "Circular cylinder", "mach": MACH, "p_inf": P_INF, "T_inf": T_INF, "alpha": 0.0,
               "cfl": 0.5, "first_order_iterations": 500, "max_iter": 12000}
POLAR = {"n_r": 60, "n_theta": 80}
GMSH = {"half_domain": True, "domain_shape": "Rectangle", "upstream": 1.0, "downstream": 1.0, "height": 3.0,
        "surface_size": 0.02, "farfield_size": 0.1, "cell_type": "Quad-dominant (recombined)"}
RUNS = {}


def _shock_level():
    return 0.5 * (1.0 + normal_shock(MACH, 1.4)["p2_p1"]) * P_INF


def _standoff(out):
    """Distance from the cylinder front (x = 0) to the bow shock on the stagnation line [D]."""
    mesh = out.mesh
    cells = mesh.owner[mesh.patch("symmetry").faces]         # the cells along the stagnation line
    cells = cells[mesh.cell_centres[cells, 0] < 0.0]
    order = np.argsort(mesh.cell_centres[cells, 0])
    x = mesh.cell_centres[cells, 0][order]
    p = out.result.fields["p"].values[cells][order]
    level = _shock_level()
    i = np.flatnonzero((p[:-1] < level) & (p[1:] >= level))[0]
    return -float(x[i] + (level - p[i]) * (x[i + 1] - x[i]) / (p[i + 1] - p[i]))


def _roughness(out):
    """Largest jump of the shock radius between neighbouring rays of the polar grid, / radial cell size."""
    n_r, n_t = POLAR["n_r"], POLAR["n_theta"]
    p = out.result.fields["p"].values.reshape(n_r, n_t)
    centres = out.mesh.cell_centres[:, :2].reshape(n_r, n_t, 2)
    radius = np.linalg.norm(centres - np.array([0.5, 0.0]), axis=2)
    level = 2.0 * P_INF            # the shock has arrived (the oblique part far from the axis is weaker than 21 p_inf)
    shock = []
    for j in range(n_t):
        i = np.flatnonzero((p[:-1, j] >= level) & (p[1:, j] < level))
        k = i[-1]
        shock.append(radius[k, j] + (level - p[k, j]) * (radius[k + 1, j] - radius[k, j]) / (p[k + 1, j] - p[k, j]))
    shock = np.array(shock)
    dr = float(np.median(np.diff(radius[:, 0])))
    second = np.abs(np.diff(shock, 2))                       # a smooth front has small second differences
    return float(second.max() / dr)


def _run(name, inputs, mesh=None, boundaries=None):
    values = {**FREE_STREAM, **inputs}
    if boundaries:
        values["boundaries"] = boundaries
    out = aeroflowsim.run_case(CASE, values, mesh=mesh)
    r = out.result
    RUNS[name] = {"cells": out.mesh.n_cells, "iterations": r.iterations, "converged": r.converged,
                  "residual": r.residuals[-1], "time": r.key_numbers["wall_time"][0], "standoff": _standoff(out),
                  "roughness": _roughness(out) if mesh is not None else None,
                  "positivity": r.info["positivity_events"]}
    return RUNS[name]


def measure():
    polar = cylinder_front_mesh(**POLAR)
    outlet = {"outlet": {"type": "supersonic_outlet"}}       # the line above the centre: supersonic outflow
    fixed = _run("polar grid, carbuncle fix on", {}, polar, outlet)
    _run("polar grid, carbuncle fix OFF", {"carbuncle_fix": False}, polar, outlet)
    gmsh = _run("Gmsh quad-dominant, fix on", GMSH)
    return {"standoff": fixed["standoff"], "standoff_gmsh": gmsh["standoff"]}


def study():
    rows = []
    for name, m in RUNS.items():
        rows.append([name, f"{m['cells']:,}", f"{m['iterations']:,}", "yes" if m["converged"] else "NO",
                     f"{m['residual']:.1e}", f"{m['time']:.0f}", f"{m['standoff']:.4f}",
                     "-" if m["roughness"] is None else f"{m['roughness']:.2f}", f"{m['positivity']:,}"])
    billig = 0.5 * 0.386 * math.exp(4.67 / MACH**2)
    return {"title": "Runs", "columns": ["Run", "Cells", "Iterations", "Converged", "Final residual", "Time [s]",
                                         "Stand-off / D", "Shock roughness", "Positivity events"],
            "rows": rows,
            "notes": [f"Billig correlation: stand-off / D = {billig:.4f}.",
                      "Shock roughness: largest second difference of the shock radius between neighbouring grid rays, "
                      "divided by the radial cell size (below 1: the front never jumps a whole cell between rays; it is "
                      "similar with and without the fix here, so convergence is the clearer sign).",
                      "Without the fix (pure HLLC) the bow shock never settles on the shock-aligned grid: the residual "
                      "stalls high; with the HLLE blend near the shock the run converges.",
                      "Inviscid, calorically perfect air (gamma = 1.4): a numerics test, not real Mach 6 air."],
            "runs": RUNS}

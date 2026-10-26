# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Experimental nozzle: the 45-15 deg conical nozzle of Back, Massier and Gier (JPL TR 32-654, 1964), wall pressure.

The real test geometry (validation/bmg_nozzle/bmg_45_15_profile.csv, built from the dimensions printed in Fig. 4 of
the report: inlet radius 2.5 in, inlet rounding 0.8 in, 45 deg convergence, throat radius 0.8 in with a circular arc
of 0.5 in (r_c/r_th = 0.625), 15 deg divergence to z = 7.285 in) is solved with the nozzle_axi template (CSV wall
profile, structured mesh, 2D axisymmetric Euler), air (gamma = 1.4), p0 = 150 psia, T0 = 1500 R. The computed wall
pressure ratio p/p0 (from the solver's wall fluxes) is interpolated to the measured positions.

Pointwise tolerance band: +-0.03 in p/p0 (absolute), written per point as a percentage of the measured value; the
band covers the digitizing uncertainty (+-0.005) and the spread between runs (the report finds boundary-layer
effects on the wall pressure negligible, and tap-size effects of up to 7 %). At z = 2.46 in, where the runs differ by 0.04, the band is +-0.05.
Only points with p/p0 between 0.09 and 0.97 are compared as percentages (smaller values would turn an absolute band
into huge percentages; they are listed in the study table).
"""

import csv
from pathlib import Path

import numpy as np

import aeroflowsim
from validation.common import is_quick

HERE = Path(__file__).resolve().parent
CASE = "cases/nozzle_axi"
INCH = 0.0254       # [m]
PSI = 6894.757      # [Pa]
RUNS = {}


def data():
    rows = []
    with open(HERE / "bmg_wall_pressure.csv", encoding="utf-8") as fh:
        for row in csv.reader(line for line in fh if not line.startswith("#")):
            if row and row[0] != "z_in":
                rows.append((float(row[0]), float(row[1])))
    return np.array(rows)


def _run():
    if "run" not in RUNS:
        mesh = {"mesh_preset": "Coarse"} if is_quick() else {"mesh_preset": "Medium"}
        out = aeroflowsim.run_case(CASE, {"geometry_source": "Custom profile (CSV)",
                                          "profile_csv": str(HERE / "bmg_45_15_profile.csv"), "gas": "air",
                                          "p0": 150.0 * PSI, "T0": 1500.0 / 1.8, "p_back": 1000.0, "max_iter": 80000,
                                          **mesh})
        r = out.result
        x, pr = np.asarray(r.series["wall_x"]), np.asarray(r.series["wall_p_over_p0"])
        y = np.asarray(r.series["wall_y"])
        order = np.argsort(x)
        keep = order[y[order] > 0.5 * INCH]               # the nozzle wall (not the inlet or the axis)
        RUNS["run"] = {"x": x[keep], "p": pr[keep], "cells": out.mesh.n_cells, "iterations": r.iterations,
                       "converged": r.converged, "time": r.key_numbers["wall_time"][0],
                       "Cd": r.key_numbers["discharge_coefficient"][0]}
    return RUNS["run"]


def computed_at(z_in):
    run = _run()
    return np.interp(np.asarray(z_in) * INCH, run["x"], run["p"])


def point_id(z):
    return f"p_z{z:.3f}".replace(".", "_")


def measure():
    d = data()
    values = computed_at(d[:, 0])
    out = {}
    for (z, _), v in zip(d, values):
        out[point_id(z)] = float(v)
    return out


def study():
    d = data()
    run = _run()
    values = computed_at(d[:, 0])
    rows = [[f"{z:.3f}", f"{p:.4f}", f"{v:.4f}", f"{v - p:+.4f}"] for (z, p), v in zip(d, values)]
    rms = float(np.sqrt(np.mean((values - d[:, 1]) ** 2)))
    return {"title": "Wall pressure along the nozzle", "columns": ["z [in]", "p/p0 measured", "p/p0 AeroFlowSim",
                                                                   "difference"],
            "rows": rows,
            "notes": [f"Mesh: {run['cells']:,} cells, {run['iterations']:,} iterations, converged "
                      f"{'yes' if run['converged'] else 'NO'}, {run['time']:.0f} s; discharge coefficient "
                      f"{run['Cd']:.4f}.",
                      f"RMS difference over all {len(d)} measured points: {rms:.4f} (in p/p0).",
                      "Geometry from the printed dimensions; the profile's exit area ratio is 6.57 (the report rounds it "
                      "to 6.63; the measured points end at z = 6.66 in, before the exit).",
                      "The test gas was heated air (1500 R) with a boundary layer; the solver is inviscid with "
                      "gamma = 1.4 (the report's one-dimensional curve uses 1.40 as well)."]}

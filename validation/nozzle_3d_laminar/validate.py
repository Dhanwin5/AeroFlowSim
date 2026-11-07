# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The CubeSat nozzle, laminar, 3D quarter with prism layers (cases/nozzle_3d) against the axisymmetric laminar run of
the same contour (cases/nozzle_axi with its inflation layers, as validation/viscous_cubesat_nozzle): discharge
coefficient and vacuum Isp as ratios 3D / axisymmetric. Prism layers: first layer 0.005 throat diameters, 8 layers,
growth 1.2 (the throat boundary layer at Re_t = 2.1e4 is about 0.02 D_t thick). The quick set: fewer iterations."""

import aeroflowsim
from validation.common import is_quick

RUNS = {}
LAMINAR = {"flow_model": "Laminar", "max_iter": 3000 if is_quick() else 30000}
LAYERS = {"inflation": True, "first_layer_height": 0.005, "n_layers": 8, "growth_rate": 1.2}


def _numbers(out):
    k, r = out.result.key_numbers, out.result
    return {"cells": out.mesh.n_cells, "iterations": r.iterations, "converged": r.converged,
            "Cd": k["discharge_coefficient"][0], "Isp": k["Isp_vacuum"][0], "time": k["wall_time"][0]}


def measure():
    RUNS["axisymmetric laminar (nozzle_axi)"] = _numbers(aeroflowsim.run_case("cases/nozzle_axi",
                                                                              {**LAMINAR, "inflation": True}))
    RUNS["3D quarter laminar (nozzle_3d)"] = _numbers(aeroflowsim.run_case("cases/nozzle_3d", {**LAMINAR, **LAYERS}))
    a, b = RUNS["axisymmetric laminar (nozzle_axi)"], RUNS["3D quarter laminar (nozzle_3d)"]
    return {"cd_ratio": b["Cd"] / a["Cd"], "isp_ratio": b["Isp"] / a["Isp"]}


def study():
    rows = [[n, f"{m['cells']:,}", f"{m['iterations']:,}", "yes" if m["converged"] else "NO", f"{m['time']:.0f}",
             f"{m['Cd']:.5f}", f"{m['Isp']:.3f}"] for n, m in RUNS.items()]
    return {"title": "Runs", "columns": ["Run", "Cells", "Iterations", "Converged", "Time [s]", "Cd", "Isp vacuum [s]"],
            "rows": rows, "notes": ["Laminar, adiabatic no-slip walls, N2, p0 = 5 bar, p_back = 1 kPa."]}

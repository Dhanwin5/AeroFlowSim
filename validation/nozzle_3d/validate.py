# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The 3D quarter nozzle (cases/nozzle_3d defaults) against the axisymmetric nozzle on the same contour
(cases/nozzle_axi defaults): mass flow, vacuum thrust and Isp as ratios 3D / axisymmetric (reference 1). The quick set
runs a coarser 3D mesh (fewer iterations); the tolerance is the same."""

import aeroflowsim
from validation.common import is_quick

RUNS = {}


def _numbers(out):
    k, r = out.result.key_numbers, out.result
    return {"cells": out.mesh.n_cells, "iterations": r.iterations, "converged": r.converged, "mdot": k["mdot"][0],
            "F": k["F_vacuum"][0], "F_wall": k["F_vacuum_wall"][0], "Isp": k["Isp_vacuum"][0],
            "time": k["wall_time"][0]}


def measure():
    axi = aeroflowsim.run_case("cases/nozzle_axi", {})
    extra = {"surface_size": 0.3, "max_iter": 3000} if is_quick() else {}
    three = aeroflowsim.run_case("cases/nozzle_3d", extra)
    RUNS["axisymmetric (nozzle_axi)"] = _numbers(axi)
    RUNS["3D quarter (nozzle_3d)"] = _numbers(three)
    a, b = RUNS["axisymmetric (nozzle_axi)"], RUNS["3D quarter (nozzle_3d)"]
    return {"mdot_ratio": b["mdot"] / a["mdot"], "thrust_ratio": b["F"] / a["F"], "isp_ratio": b["Isp"] / a["Isp"]}


def study():
    rows = [[name, f"{m['cells']:,}", f"{m['iterations']:,}", "yes" if m["converged"] else "NO", f"{m['time']:.0f}",
             f"{m['mdot']:.6e}", f"{m['F']:.6e}", f"{m['F_wall']:.6e}", f"{m['Isp']:.3f}"] for name, m in RUNS.items()]
    return {"title": "Runs", "columns": ["Run", "Cells", "Iterations", "Converged", "Time [s]", "Mass flow [kg/s]",
                                         "Vacuum thrust, exit [N]", "Vacuum thrust, wall [N]", "Isp vacuum [s]"],
            "rows": rows, "notes": ["Both runs inviscid, N2, the templates' default chamber state and contour."]}

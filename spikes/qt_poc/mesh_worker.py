# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spike only: build a mesh in a separate process, so the window never freezes and Cancel always works.

The parent starts  build(case_name, params, out_path, queue)  in a child process (multiprocessing,
"spawn"). The child re-loads the case from its folder, builds the mesh, saves it to out_path (.npz)
and reports through the queue:  ("stage", text), then ("done", path, n_cells) or ("error", text).
Cancel = the parent terminates the child; nothing is half-written because the file is saved last.
"""

import time
import traceback


def build(case_name, params, out_path, queue):
    try:
        queue.put(("stage", f"Loading case {case_name}"))
        from aeroflowsim.discovery import load_case
        from aeroflowsim.parameters import defaults, validate

        case = load_case(case_name)
        values = validate(case.parameters(), {**defaults(case.parameters()), **params})
        queue.put(("stage", "Meshing (Gmsh or structured generator)"))
        t0 = time.perf_counter()
        mesh = case.build_mesh(values)
        queue.put(("stage", f"Saving mesh ({mesh.n_cells:,} cells, {time.perf_counter() - t0:.1f} s)"))
        mesh.save(out_path)
        queue.put(("done", str(out_path), mesh.n_cells))
    except Exception as error:   # report every failure to the window instead of dying silently
        queue.put(("error", f"{type(error).__name__}: {error}\n{traceback.format_exc()}"))

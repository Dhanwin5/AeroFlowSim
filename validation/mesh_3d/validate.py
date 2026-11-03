# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""3D mesh study without a solver: a sphere (D = 1 m) in a box enclosure, meshed with tetrahedra and 5 prism layers
(aeroflowsim/workspace_mesh3d.py) on three levels, every cell size halved from one level to the next.

Measured on every level, against exact values:
    fluid volume       the sum of the cell volumes = box (16 x 11 x 11 m) - sphere, to 0.1 %
                       (the faceted sphere is a little smaller than the exact one, so this also tests the faceting)
    wall area          the area of the wall patch = 4 pi r² (faceted: slightly less), to 1 %
    first layer        the height of the prisms on the wall (volume / wall face area) = the requested 2 mm
    valid cells        the share of cells with a positive volume = 1, and no error-level mesh check
The study table lists the cell counts against the size (the growth of the mesh), the time and the quality numbers.
The quick set uses cell sizes twice as large.
"""

import math
import time

import numpy as np

from aeroflowsim.checks import run_mesh_checks
from aeroflowsim.geometry_model import GeometryDocument
from aeroflowsim.geometry_model.operations3d import Enclosure3D, Sphere
from aeroflowsim.mesh import TETRA, WEDGE
from aeroflowsim.mesh_quality import quality_summary
from aeroflowsim.nozzle_mesh import Inflation
from aeroflowsim.workspace_mesh3d import MeshSettings3D, mesh_3d
from validation.common import is_quick

LEVELS = {"coarse": 1.0, "medium": 2.0, "fine": 4.0}   # cell sizes divided by this
SURFACE, LARGEST = 0.08, 1.0                           # cell size on the sphere and largest cell size, coarse [m]
FIRST = 0.002                                          # first prism layer height [m]
RUNS = {}


def _runs():
    if RUNS:
        return RUNS
    doc = GeometryDocument([Sphere("op1", radius=0.5),
                            Enclosure3D("op2", kind="box", upstream=5.0, downstream=10.0, lateral=5.0)], dimension=3)
    scale = 2.0 if is_quick() else 1.0
    for level, k in LEVELS.items():
        settings = MeshSettings3D(SURFACE * scale / k, LARGEST * scale / k, 1.25, 0, Inflation(FIRST, 5, 1.2))
        t0 = time.perf_counter()
        mesh = mesh_3d(doc, None, settings)
        seconds = time.perf_counter() - t0
        wall = mesh.patch("wall").faces
        prisms = wall[mesh.cell_types[mesh.owner[wall]] == WEDGE]
        checks = run_mesh_checks(None, {}, mesh)
        RUNS[level] = {"size": settings.surface_size, "cells": mesh.n_cells, "time": seconds,
                       "tets": int(np.sum(mesh.cell_types == TETRA)), "prisms": int(np.sum(mesh.cell_types == WEDGE)),
                       "volume": float(mesh.cell_volumes.sum()), "area": float(mesh.face_areas[wall].sum()),
                       "first": float(np.mean(mesh.cell_volumes[mesh.owner[prisms]] / mesh.face_areas[prisms])),
                       "positive": float(np.mean(mesh.cell_volumes > 0.0)),
                       "no_errors": float(not any(c.level == "error" for c in checks)),
                       "quality": quality_summary(mesh)}
    return RUNS


def measure():
    values = {}
    for level, run in _runs().items():
        values[f"volume_{level}"] = run["volume"]
        values[f"area_{level}"] = run["area"]
        values[f"first_layer_{level}"] = run["first"]
        values[f"positive_{level}"] = run["positive"]
        values[f"no_errors_{level}"] = run["no_errors"]
    return values


def study():
    rows = []
    for level, r in _runs().items():
        q = r["quality"]
        rows.append([level, f"{r['size'] * 1000:.0f}", f"{r['cells']:,}", f"{r['tets']:,}", f"{r['prisms']:,}",
                     f"{r['time']:.1f}", f"{q['max_skewness']:.3f}", f"{q['min_dihedral_angle']:.1f}",
                     f"{q['max_non_orthogonality']:.1f}", f"{q['max_volume_ratio']:.2f}"])
    runs = list(_runs().values())
    growth = [b["cells"] / a["cells"] for a, b in zip(runs, runs[1:])]
    return {"title": "Mesh levels (sphere D = 1 m in a 16 x 11 x 11 m box, 5 prism layers from 2 mm)",
            "columns": ["Level", "Wall cell size [mm]", "Cells", "Tetrahedra", "Prisms", "Time [s]", "Max skewness",
                        "Min dihedral [deg]", "Max non-orth. [deg]", "Max volume ratio"],
            "rows": rows,
            "notes": [f"Halving every cell size multiplied the number of cells by {', '.join(f'{g:.2f}' for g in growth)}: cells "
                      "that fill a fixed volume uniformly grow 8 times, the prism layers 4 times (wall area / size²), so "
                      "the growth rises towards 8 as the volume cells dominate (the coarsest quick level has very few cells).",
                      "Skewness: equivolume for the tetrahedra, equiangle for the prisms."]}


def exact():
    volume = 16.0 * 11.0 * 11.0 - 4.0 / 3.0 * math.pi * 0.5 ** 3      # [m³]
    return {"volume": volume, "area": math.pi, "first_layer": FIRST, "positive": 1.0, "no_errors": 1.0}


if __name__ == "__main__":
    for key, value in measure().items():
        print(f"{key:<22} {value:.10g}")
    for row in study()["rows"]:
        print(row)

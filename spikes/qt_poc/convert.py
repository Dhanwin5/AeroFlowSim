# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Spike only: turn an AeroFlowSim face-based Mesh into PyVista objects for the 3D view.

Our Mesh already stores VTK cell type numbers and VTK node ordering, so the conversion is just
re-packing arrays: VTK wants one flat list  [n, node0, node1, ..., n, node0, ...]  per cell.
"""

import numpy as np
import pyvista as pv

from aeroflowsim import mesh_quality


def mesh_to_grid(mesh) -> pv.UnstructuredGrid:
    """The cells of the mesh as a pv.UnstructuredGrid, with quality fields as cell data."""
    counts = (mesh.cell_nodes >= 0).sum(axis=1)                 # nodes per cell (rest is -1 padding)
    flat = []
    for n, row in zip(counts, mesh.cell_nodes):
        flat.append(n)
        flat.extend(row[:n])
    grid = pv.UnstructuredGrid(np.array(flat, dtype=np.int64), mesh.cell_types.astype(np.uint8), mesh.nodes)
    grid.cell_data["cell_volume"] = mesh.cell_volumes                       # [m³] (2D: per metre depth)
    grid.cell_data["aspect_ratio"] = mesh_quality.aspect_ratio(mesh)        # [-]
    grid.cell_data["non_orthogonality"] = mesh_quality.non_orthogonality(mesh)  # [deg]
    return grid


def patch_lines(mesh) -> pv.PolyData:
    """The boundary faces (edges in 2D) as lines; cell data 'patch' = index into mesh.patches."""
    lines, patch_ids = [], []
    for k, p in enumerate(mesh.patches):
        for f in p.faces:
            nodes = mesh.face_nodes[f]
            nodes = nodes[nodes >= 0]
            lines.append([len(nodes), *nodes])
            patch_ids.append(k)
    poly = pv.PolyData(mesh.nodes, lines=np.concatenate(lines))
    poly.cell_data["patch"] = np.array(patch_ids, dtype=np.int32)
    return poly

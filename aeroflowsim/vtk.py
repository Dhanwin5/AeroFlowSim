# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Write a face-based Mesh (aeroflowsim/mesh.py) with any cell data to a ParaView .vtu file.

.vtu is the VTK XML "UnstructuredGrid" format: a plain-text XML file with the node coordinates
(Points), the cells (Cells: connectivity, offsets, types) and one value (or vector) per cell
(CellData). ParaView, VisIt and many other tools open it directly. AeroFlowSim's Mesh already
uses VTK cell type numbers and node ordering, so the cells are written as they are.

The writer accepts ANY cell fields, so the same code exports mesh quality now and flow results
(pressure, Mach number, velocity vectors ...) from Prompt 7 on:

    write_vtu("mesh.vtu", mesh, {"p": pressure, "U": velocity})   # (C,) or (C, 3) arrays

No extra Python package is needed.
"""

import io
from pathlib import Path

import numpy as np

from aeroflowsim import __version__
from aeroflowsim import mesh_quality


def mesh_cell_data(mesh) -> dict:
    """The standard mesh-quality fields of a mesh, one value per cell, for ParaView.

    patch_marker: 0 for cells away from the boundary; k+1 for cells that touch patch k
    (mesh.patches[k]). A corner cell touching two patches shows the later patch.
    """
    marker = np.zeros(mesh.n_cells, dtype=np.int32)
    for k, p in enumerate(mesh.patches):
        marker[mesh.owner[p.faces]] = k + 1
    data = {
        "cell_volume": mesh.cell_volumes,                          # [m³] (2D: per metre depth)
        "aspect_ratio": mesh_quality.aspect_ratio(mesh),           # [-]
        "non_orthogonality": mesh_quality.non_orthogonality(mesh), # [deg]
        "volume_ratio": mesh_quality.volume_ratio(mesh),           # [-]
        "cell_size": mesh_quality.cell_size(mesh),                 # [m]
        "min_angle": mesh_quality.min_angle(mesh),                 # [deg]
        "skewness": mesh_quality.equiangle_skewness(mesh),         # [-]
        "patch_marker": marker,
    }
    if mesh.axisymmetric:
        data["axi_cell_volume"] = mesh.axi_cell_volumes            # [m⁴ per radian]
    return data


def solution_cell_data(result) -> dict:
    """The solution fields of a 2D/3D Result for ParaView: every field, plus the velocity as a vector."""
    data = {key: f.values for key, f in result.fields.items()}
    if "u" in data and "v" in data:
        u, v = data["u"], data["v"]
        w = data.get("w", np.zeros_like(u))
        data["velocity"] = np.column_stack([u, v, w])            # [m/s]
    return data


def _data_array(out, name, values, n_components=1):
    """One <DataArray> in ASCII: integers stay integers, everything else is Float64."""
    values = np.asarray(values)
    if np.issubdtype(values.dtype, np.integer):
        kind, fmt = ("UInt8", "%d") if values.dtype == np.uint8 else ("Int64", "%d")
    else:
        kind, fmt = "Float64", "%.12g"
    out.write(f'        <DataArray type="{kind}" Name="{name}" NumberOfComponents="{n_components}" '
              'format="ascii">\n')
    np.savetxt(out, values.reshape(-1, n_components), fmt=fmt, delimiter=" ")
    out.write("        </DataArray>\n")


def vtu_text(mesh, cell_data=None, point_data=None) -> str:
    """The .vtu file content as text. cell_data: {name: (C,) or (C, 3) array}; point_data: {name: (N,) or (N, 3)}
    (node values, e.g. the smooth node averages of aeroflowsim/post/fields.py)."""
    cell_data = dict(cell_data or {})
    point_data = dict(point_data or {})
    for name, values in point_data.items():
        values = np.asarray(values)
        if values.shape[0] != mesh.n_nodes or values.ndim > 2 or " " in name or '"' in name:
            raise ValueError(f"Point data '{name}' must have one value (or vector) per node ({mesh.n_nodes}) and a "
                             "name without spaces or quotes.")
    for name, values in cell_data.items():
        values = np.asarray(values)
        if values.shape[0] != mesh.n_cells or values.ndim > 2:
            raise ValueError(f"Cell data '{name}' must have one value (or vector) per cell "
                             f"({mesh.n_cells}), got shape {values.shape}.")
        if " " in name or '"' in name:
            raise ValueError(f"Cell data name '{name}' must not contain spaces or quotes.")
    used = mesh.cell_nodes >= 0
    connectivity = mesh.cell_nodes[used]                      # row by row, padding removed
    offsets = np.cumsum(used.sum(axis=1))                     # where each cell's node list ends

    out = io.StringIO()
    out.write('<?xml version="1.0"?>\n')
    out.write(f"<!-- Written by AeroFlowSim {__version__}. Patches (patch_marker = number): "
              + ", ".join(f"{k + 1} = {p.name} ({p.type})" for k, p in enumerate(mesh.patches))
              + " -->\n")
    out.write('<VTKFile type="UnstructuredGrid" version="1.0" byte_order="LittleEndian" '
              'header_type="UInt64">\n  <UnstructuredGrid>\n')
    out.write(f'    <Piece NumberOfPoints="{mesh.n_nodes}" NumberOfCells="{mesh.n_cells}">\n')
    out.write("      <Points>\n")
    _data_array(out, "Points", mesh.nodes, 3)
    out.write("      </Points>\n      <Cells>\n")
    _data_array(out, "connectivity", connectivity)
    _data_array(out, "offsets", offsets)
    _data_array(out, "types", mesh.cell_types.astype(np.uint8))
    out.write("      </Cells>\n")
    if point_data:
        out.write("      <PointData>\n")
        for name, values in point_data.items():
            values = np.asarray(values)
            _data_array(out, name, values, 1 if values.ndim == 1 else values.shape[1])
        out.write("      </PointData>\n")
    if cell_data:
        out.write("      <CellData>\n")
        for name, values in cell_data.items():
            values = np.asarray(values)
            _data_array(out, name, values, 1 if values.ndim == 1 else values.shape[1])
        out.write("      </CellData>\n")
    out.write("    </Piece>\n  </UnstructuredGrid>\n</VTKFile>\n")
    return out.getvalue()


def write_vtu(path, mesh, cell_data=None, point_data=None) -> Path:
    """Write the mesh and its cell (and node) data to a .vtu file; returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(vtu_text(mesh, cell_data, point_data), encoding="utf-8", newline="\n")
    return path


MESH_FOLDER = "mesh"   # cases/<case>/mesh/ holds the generated mesh files (git-ignored)


def save_mesh_files(mesh, case_folder) -> tuple[Path, Path]:
    """Save a mesh into cases/<case>/mesh/: mesh.npz (to reload it exactly) and mesh.vtu (ParaView).

    Returns (npz path, vtu path).
    """
    folder = Path(case_folder) / MESH_FOLDER
    npz = mesh.save(folder / "mesh.npz")
    vtu = write_vtu(folder / "mesh.vtu", mesh, mesh_cell_data(mesh))
    return npz, vtu

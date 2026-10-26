# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export of results: fields (CSV, VTU, Tecplot ASCII), surface data and report definitions (CSV).

Everything is written in SI units with the unit in each column name, e.g. "p [Pa]" (the GUI may convert to the
user's display units, as its other exports do, and then says so in the header).

Tecplot ASCII (.dat), one zone per file: FEQUADRILATERAL for meshes of quads (a triangle is written as a quad
with a repeated last node, the usual Tecplot convention), node coordinates as nodal data and every field
cell-centred (VARLOCATION=([3-n]=CELLCENTERED)), so the exported numbers are the solver's own cell values. The
format is described in the Tecplot 360 Data Format Guide (ASCII "FE data, BLOCK packing").
"""

import csv
import io
from pathlib import Path

import numpy as np

from aeroflowsim import __version__
from aeroflowsim.post.fields import field_info, field_values, node_values

DEFAULT_FIELDS = ("rho", "u", "v", "p", "T", "M", "p0", "T0", "s")


def _column(sol, name, scale=None):
    info = field_info(sol, name)
    unit = info.unit if info.unit else "-"
    return f"{name} [{unit}]"


def fields_csv(sol, path, fields=DEFAULT_FIELDS, location="cell", convert=None) -> Path:
    """CSV with one row per cell centre (location "cell") or per node ("node"): x, y and the fields.

    convert: optional function (values, unit) -> (values, unit) to write display units (GUI exports)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if location == "node":
        xy = sol.mesh.nodes[:, :2]
        columns = [node_values(sol, f) for f in fields]
    else:
        xy = sol.geom.cell_centres[:, :2]
        columns = [field_values(sol, f) for f in fields]
    units = [field_info(sol, f).unit or "-" for f in fields]
    length_unit = "m"
    x, y = xy[:, 0], xy[:, 1]
    if convert is not None:
        (x, length_unit), (y, _) = convert(x, "m"), convert(y, "m")
        converted = [convert(c, u) for c, u in zip(columns, units)]
        columns, units = [c for c, _ in converted], [u for _, u in converted]
    header = [f"x [{length_unit}]", f"{'r' if sol.axisymmetric else 'y'} [{length_unit}]"]
    header += [f"{f} [{u}]" for f, u in zip(fields, units)]
    data = np.column_stack([x, y] + list(columns))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# AeroFlowSim {__version__}: {'node' if location == 'node' else 'cell-centre'} values of "
                 f"{sol.name}\n")
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in data:
            writer.writerow([f"{v:.10g}" for v in row])
    return path


def fields_vtu(sol, path, fields=DEFAULT_FIELDS, node_data=True) -> Path:
    """ParaView .vtu with every field as cell data, the velocity vector, and (node_data) the node values."""
    from aeroflowsim.vtk import write_vtu
    cell = {f: field_values(sol, f) for f in fields}
    u, v = field_values(sol, "u"), field_values(sol, "v")
    cell["velocity"] = np.column_stack([u, v, np.zeros_like(u)])
    point = None
    if node_data:
        point = {f"{f}_node": node_values(sol, f) for f in fields}
        point["velocity_node"] = np.column_stack([point["u_node"], point["v_node"], np.zeros(sol.mesh.n_nodes)])
    return write_vtu(path, sol.mesh, cell, point)


def tecplot_text(sol, fields=DEFAULT_FIELDS, title="AeroFlowSim result") -> str:
    """Tecplot ASCII text: one FEQUADRILATERAL zone, node coordinates, cell-centred fields (BLOCK packing)."""
    mesh = sol.mesh
    names = ["X", "Y"] + [_column(sol, f) for f in fields]
    cn = mesh.cell_nodes[:, :4].copy()
    tri = cn[:, 3] < 0
    cn[tri, 3] = cn[tri, 2]                               # triangle -> degenerate quad
    if np.any(mesh.cell_nodes[:, 4:] >= 0):
        raise ValueError("Tecplot export supports triangles and quadrilaterals only.")
    out = io.StringIO()
    out.write(f'TITLE = "{title} (AeroFlowSim {__version__})"\n')
    out.write("VARIABLES = " + ", ".join(f'"{n}"' for n in names) + "\n")
    n_vars = len(names)
    loc = f"[3-{n_vars}]=CELLCENTERED" if n_vars > 3 else "[3]=CELLCENTERED"
    out.write(f'ZONE T="{sol.name}", NODES={mesh.n_nodes}, ELEMENTS={mesh.n_cells}, DATAPACKING=BLOCK, '
              f"ZONETYPE=FEQUADRILATERAL, VARLOCATION=({loc})\n")

    def block(values):
        values = np.asarray(values, dtype=float)
        for i in range(0, len(values), 5):
            out.write(" ".join(f"{v:.10g}" for v in values[i:i + 5]) + "\n")

    block(mesh.nodes[:, 0])
    block(mesh.nodes[:, 1])
    for f in fields:
        block(field_values(sol, f))
    for row in cn + 1:                                    # Tecplot numbers nodes from 1
        out.write(" ".join(str(int(k)) for k in row) + "\n")
    return out.getvalue()


def fields_tecplot(sol, path, fields=DEFAULT_FIELDS) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tecplot_text(sol, fields), encoding="utf-8", newline="\n")
    return path


def read_tecplot_header(path) -> dict:
    """Variables, node and element counts of a Tecplot ASCII file written by fields_tecplot (used by the tests)."""
    text = Path(path).read_text(encoding="utf-8").splitlines()
    variables = [v.strip().strip('"') for v in text[1].split("=", 1)[1].split(",")]
    zone = text[2]
    nodes = int(zone.split("NODES=")[1].split(",")[0])
    elements = int(zone.split("ELEMENTS=")[1].split(",")[0])
    return {"variables": variables, "nodes": nodes, "elements": elements, "lines": text}


def table_csv(path, header, rows, comment="") -> Path:
    """A plain table as CSV (surface data, XY data, report definitions, flux balance)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        if comment:
            fh.write(f"# {comment}\n")
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow([f"{v:.10g}" if isinstance(v, (float, np.floating)) else v for v in row])
    return path


def surface_csv(sol, surface, path, fields=DEFAULT_FIELDS) -> Path:
    """Data along a surface (segment ends; exact per cell): arc length, x, y and the fields."""
    from aeroflowsim.post.xy import surface_samples
    columns = {}
    s = None
    for f in fields:
        s, x, y, values = surface_samples(sol, surface, f)
        columns[f] = values
    header = ["s [m]", "x [m]", f"{'r' if sol.axisymmetric else 'y'} [m]"] + [_column(sol, f) for f in fields]
    rows = np.column_stack([s, x, y] + [columns[f] for f in fields]) if s is not None else []
    return table_csv(path, header, rows, f"AeroFlowSim {__version__}: surface '{surface.name}' of {sol.name}")


def definitions_csv(values, path, definitions=()) -> Path:
    """Report definitions table: name, description, value, unit."""
    describe = {d.name: d.describe() for d in definitions}
    rows = [(name, describe.get(name, ""), value, unit) for name, (value, unit) in values.items()]
    return table_csv(path, ["name", "definition", "value", "unit"], rows, f"AeroFlowSim {__version__}: report definitions")

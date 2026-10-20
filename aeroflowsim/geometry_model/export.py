# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export the workspace geometry for other programs: STEP (metres), DXF (millimetres) and CSV (mm).

    export_step(document, context, path)   exact CAD geometry (OpenCASCADE, in metres), e.g. for a CAD program
    export_dxf(built, path)                lines and circle arcs exactly, other curves as splines
                                           through their points; one DXF layer per boundary name
    export_csv(built, path)                every edge's points: boundary, type, edge id, x_mm, y_mm
    export_geometry(...)                   picks the format from the file name's ending
"""

import csv
from pathlib import Path

import numpy as np

from aeroflowsim.geometry_model.document import run_operations
from aeroflowsim.geometry_model.kernel import Kernel, gmsh_session

MM = 1e-3          # one millimetre [m]
FORMATS = {".step": "step", ".stp": "step", ".dxf": "dxf", ".csv": "csv"}


def export_step(document, context, path):
    """Replay the history and write the exact geometry as STEP, in metres.

    OpenCASCADE labels the numbers it writes as millimetres. Scaling the model by 1000 first would
    turn exact lines and circles into B-spline approximations, so instead the numbers stay in
    metres and the file's unit label is changed to metres (an exact, standard STEP unit).
    """
    with gmsh_session() as gmsh:
        kernel = Kernel(gmsh)
        run_operations(kernel, document, context)
        if kernel.failed_operation:
            raise ValueError("The geometry has a failed step; fix it before exporting.")
        everything = gmsh.model.getEntities(2) + [(1, t) for t in kernel.free_curves()]
        if not everything:
            raise ValueError("There is no geometry to export.")
        gmsh.write(str(path))
    text = Path(path).read_text(encoding="latin-1")
    if ".MILLI.,.METRE." not in text:
        raise ValueError("Unexpected STEP unit from OpenCASCADE; the file was not written in a known unit.")
    Path(path).write_text(text.replace(".MILLI.,.METRE.", "$,.METRE."), encoding="latin-1")


def _circle(points):
    """(centre, radius) of the circle through three of the points (start, middle and end; for a full
    circle, whose start and end are the same point: one third and two thirds of the way round)."""
    n = len(points)
    if np.allclose(points[0], points[-1]):
        a, b, c = points[0], points[n // 3], points[2 * n // 3]
    else:
        a, b, c = points[0], points[n // 2], points[-1]
    d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-300:
        raise ValueError("not a circle")
    sq = [p @ p for p in (a, b, c)]
    ux = (sq[0] * (b[1] - c[1]) + sq[1] * (c[1] - a[1]) + sq[2] * (a[1] - b[1])) / d
    uy = (sq[0] * (c[0] - b[0]) + sq[1] * (a[0] - c[0]) + sq[2] * (b[0] - a[0])) / d
    centre = np.array([ux, uy])
    return centre, float(np.linalg.norm(a - centre))


def export_dxf(built, path):
    """Write the edges as DXF entities in millimetres; the layer is the boundary name (or GEOMETRY)."""
    import ezdxf
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4                                      # millimetres
    msp = doc.modelspace()
    for edge in built.edges.values():
        b = built.names.get(edge.id)
        layer = b.name if b is not None else "GEOMETRY"
        if layer not in doc.layers:
            doc.layers.add(layer)
        pts = edge.points / MM
        attribs = {"layer": layer}
        if edge.kind == "line":
            msp.add_line(tuple(pts[0]), tuple(pts[-1]), dxfattribs=attribs)
            continue
        if edge.kind == "arc":
            centre, radius = _circle(pts)
            closed = np.allclose(pts[0], pts[-1])
            if closed:
                msp.add_circle(tuple(centre), radius, dxfattribs=attribs)
                continue
            a0, am, a1 = (np.degrees(np.arctan2(p[1] - centre[1], p[0] - centre[0])) % 360.0
                          for p in (pts[0], pts[len(pts) // 2], pts[-1]))
            ccw = (am - a0) % 360.0 < (a1 - a0) % 360.0              # does the arc run counter-clockwise?
            start, end = (a0, a1) if ccw else (a1, a0)
            msp.add_arc(tuple(centre), radius, start, end, dxfattribs=attribs)
            continue
        msp.add_spline([tuple(p) + (0.0,) for p in pts], dxfattribs=attribs)
    doc.saveas(str(path))


def export_csv(built, path):
    """Write every edge's points (mm): boundary name, type, edge id, x_mm, y_mm."""
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["boundary", "type", "edge", "x_mm", "y_mm"])
        for edge in built.edges.values():
            b = built.names.get(edge.id)
            for x, y in edge.points / MM:
                writer.writerow([b.name if b else "", b.type if b else "", edge.id, f"{x:.9g}", f"{y:.9g}"])


def export_geometry(document, context, built, path):
    """Export in the format given by the file name's ending (.step / .stp, .dxf, .csv)."""
    fmt = FORMATS.get(Path(path).suffix.lower())
    if fmt is None:
        raise ValueError("Choose a file ending in .step, .dxf or .csv.")
    if fmt == "step":
        export_step(document, context, path)
    elif fmt == "dxf":
        export_dxf(built, path)
    else:
        export_csv(built, path)

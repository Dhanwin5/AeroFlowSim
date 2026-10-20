# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reading geometry files into the workspace: coordinates (CSV, Selig/Lednicer .dat), DXF, STEP and IGES.

Every reader turns its file into the same few kinds of curve, in metres ("curve specs"):
    ("line", p, q)                              straight line from p to q
    ("arc", centre, radius, a0, a1)             circle arc, counter-clockwise from angle a0 to a1 [rad]
    ("circle", centre, radius)                  full circle
    ("spline", points)                          smooth curve through the points
    ("bspline", poles, degree, knots, mults, weights)   exact B-spline / NURBS (DXF splines)
    ("chain", points, corners, closed)          an outline of points: lines/splines split at corners
make_curves() builds them in the CAD kernel; healing.py then glues them and makes the faces.
STEP and IGES are read directly by OpenCASCADE (exact CAD curves, units from the file).

Units: the numbers in a file are multiplied by UNITS[unit] to get metres. DXF files say their
unit in the header ($INSUNITS), STEP and IGES files too; "file" means: use what the file says.
"""

import math
import re
from pathlib import Path

import numpy as np

UNITS = {"m": 1.0, "mm": 1e-3, "inch": 0.0254}          # metres per file unit
DXF_UNITS = {1: "inch", 4: "mm", 6: "m"}                  # $INSUNITS codes we accept (0 = unitless)
COORDINATE_SUFFIXES = (".csv", ".dat", ".txt")
CAD_SUFFIXES = {".dxf": "dxf", ".step": "step", ".stp": "step", ".iges": "iges", ".igs": "iges"}
ELLIPSE_POINTS = 65


def file_format(path) -> str:
    """'coordinates', 'wall_profile' (x_mm,r_mm nozzle wall CSV), 'dxf', 'step' or 'iges'."""
    suffix = Path(path).suffix.lower()
    if suffix in CAD_SUFFIXES:
        return CAD_SUFFIXES[suffix]
    if suffix in COORDINATE_SUFFIXES:
        try:
            first = Path(path).read_text(encoding="utf-8-sig", errors="replace").lstrip().splitlines()[0]
        except (OSError, IndexError):
            return "coordinates"
        header = first.replace(" ", "").lower()
        return "wall_profile" if header.startswith("x_mm,r_mm") else "coordinates"
    raise ValueError(f"'{Path(path).name}': unknown file type. Use CSV or .dat (coordinates), DXF, STEP or IGES.")


# ---- coordinates --------------------------------------------------------------------------------------

def read_coordinate_points(path) -> np.ndarray:
    """The (x, y) points of a CSV / Selig / Lednicer file, in file units."""
    from aeroflowsim.shapes.coordinates_file import read_coordinates
    points, _ = read_coordinates(Path(path).resolve())
    return points


def read_wall_profile_points(path) -> np.ndarray:
    """The wall points (x, r) of an x_mm,r_mm nozzle profile CSV, in millimetres (checked)."""
    from aeroflowsim.geometry import read_profile_csv
    profile = read_profile_csv(Path(path).resolve())         # checks the format; WallProfile in metres
    return np.column_stack([profile.x, profile.r]) * 1e3


# ---- DXF (ezdxf) ----------------------------------------------------------------------------------------

def dxf_unit(path) -> str | None:
    """The unit the DXF file states ($INSUNITS), or None if it gives none we know."""
    import ezdxf
    try:
        doc = ezdxf.readfile(str(path))
    except (OSError, ezdxf.DXFError) as error:
        raise ValueError(f"Could not read the DXF file {Path(path).name}: {error}") from None
    return DXF_UNITS.get(int(doc.header.get("$INSUNITS", 0)))


def read_dxf(path, scale):
    """Curve specs (metres, after multiplying by scale) of the 2D entities in a DXF file's model space.

    LINE, ARC, CIRCLE, LWPOLYLINE / POLYLINE (straight and bulged segments), SPLINE (exact NURBS)
    and ELLIPSE (as a smooth curve through points); blocks (INSERT) are exploded. Returns
    (specs, notes) - notes list entities that were skipped.
    """
    import ezdxf
    from ezdxf.math import bulge_to_arc
    try:
        doc = ezdxf.readfile(str(path))
    except (OSError, ezdxf.DXFError) as error:
        raise ValueError(f"Could not read the DXF file {Path(path).name}: {error}") from None
    s = float(scale)
    specs, skipped = [], {}

    def xy(v):
        return np.array([float(v[0]), float(v[1])]) * s

    def polyline(points, bulges, closed):
        n = len(points)
        for k in range(n if closed else n - 1):
            p, q, b = points[k], points[(k + 1) % n], bulges[k]
            if np.allclose(p, q):
                continue
            if abs(b) < 1e-12:
                specs.append(("line", xy(p), xy(q)))
            else:
                centre, a0, a1, r = bulge_to_arc(p[:2], q[:2], b)
                if b < 0:                      # clockwise bulge: the same arc, counter-clockwise from q to p
                    a0, a1 = a1, a0
                specs.append(("arc", xy(centre), r * s, a0, a1))

    def add(entity):
        kind = entity.dxftype()
        if kind == "LINE":
            specs.append(("line", xy(entity.dxf.start), xy(entity.dxf.end)))
        elif kind == "ARC":
            specs.append(("arc", xy(entity.dxf.center), entity.dxf.radius * s,
                          math.radians(entity.dxf.start_angle), math.radians(entity.dxf.end_angle)))
        elif kind == "CIRCLE":
            specs.append(("circle", xy(entity.dxf.center), entity.dxf.radius * s))
        elif kind == "LWPOLYLINE":
            rows = list(entity.get_points("xyb"))
            polyline([(r[0], r[1]) for r in rows], [r[2] for r in rows], entity.closed)
        elif kind == "POLYLINE" and not entity.is_3d_polyline:
            verts = list(entity.vertices)
            polyline([(v.dxf.location[0], v.dxf.location[1]) for v in verts],
                     [v.dxf.bulge for v in verts], entity.is_closed)
        elif kind == "SPLINE":
            poles = np.array([[p[0], p[1]] for p in entity.control_points], dtype=float)
            if len(poles) >= 2:
                knots = np.asarray(entity.knots, dtype=float)
                values, mults = np.unique(np.round(knots, 12), return_counts=True)
                weights = list(entity.weights) or [1.0] * len(poles)
                specs.append(("bspline", poles * s, int(entity.dxf.degree), values.tolist(), mults.tolist(),
                              [float(w) for w in weights]))
            elif len(entity.fit_points) >= 2:
                specs.append(("spline", np.array([[p[0], p[1]] for p in entity.fit_points]) * s))
        elif kind == "ELLIPSE":
            pts = np.array([[v[0], v[1]] for v in entity.flattening(0.0, segments=ELLIPSE_POINTS)])
            specs.append(("spline", pts * s))
        elif kind == "INSERT":
            for sub in entity.virtual_entities():
                add(sub)
        else:
            skipped[kind] = skipped.get(kind, 0) + 1

    for entity in doc.modelspace():
        add(entity)
    notes = [f"Skipped {n} {kind} entit{'y' if n == 1 else 'ies'} (not a 2D curve)." for kind, n in
             sorted(skipped.items()) if kind not in ("TEXT", "MTEXT", "DIMENSION", "HATCH", "POINT")]
    if not specs:
        raise ValueError(f"{Path(path).name} has no lines, arcs, circles, polylines or splines in its model space.")
    return specs, notes


# ---- STEP / IGES units ------------------------------------------------------------------------------

def cad_file_unit(path) -> str | None:
    """The length unit a STEP or IGES file states ('mm', 'm', 'inch'), or None."""
    try:
        text = Path(path).read_text(encoding="latin-1", errors="replace")[:200_000]
    except OSError:
        return None
    if Path(path).suffix.lower() in (".igs", ".iges"):
        # IGES global section (lines marked G in column 73): parameter 15 is the unit name, e.g. 2HMM.
        globals_ = "".join(line[:72] for line in text.splitlines() if len(line) >= 73 and line[72] == "G")
        match = re.search(r"\d+H(MM|M|IN|INCH|FT|CM)\b", globals_.upper())
        return {"MM": "mm", "M": "m", "IN": "inch", "INCH": "inch"}.get(match.group(1)) if match else None
    upper = text.upper()
    if re.search(r"SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.", upper):
        return "mm"
    if re.search(r"SI_UNIT\s*\(\s*\$\s*,\s*\.METRE\.", upper):
        return "m"
    if "'INCH'" in upper:
        return "inch"
    return None


# ---- building curves in the kernel ---------------------------------------------------------------

def make_curves(kernel, specs, tolerance) -> list:
    """Create OCC curves for the specs; drops curves shorter than the tolerance [m] (reported)."""
    occ = kernel.occ
    P = kernel.point
    tags, dropped = [], 0
    for spec in specs:
        kind = spec[0]
        if kind == "line":
            p, q = spec[1], spec[2]
            if np.linalg.norm(q - p) <= tolerance:
                dropped += 1
                continue
            tags.append(occ.addLine(P(*p), P(*q)))
        elif kind == "arc":
            centre, r, a0, a1 = spec[1], spec[2], spec[3], spec[4]
            while a1 <= a0:
                a1 += 2.0 * math.pi
            if r * (a1 - a0) <= tolerance:
                dropped += 1
                continue
            tags.append(occ.addCircle(centre[0], centre[1], 0.0, r, angle1=a0, angle2=a1))
        elif kind == "circle":
            tags.append(occ.addCircle(spec[1][0], spec[1][1], 0.0, spec[2]))
        elif kind == "spline":
            pts = _distinct(spec[1], tolerance)
            if len(pts) < 2:
                dropped += 1
                continue
            ids = [P(*p) for p in pts]
            tags.append(occ.addSpline(ids) if len(pts) > 2 else occ.addLine(*ids))
        elif kind == "bspline":
            poles, degree, knots, mults, weights = spec[1:]
            ids = [P(*p) for p in poles]
            tags.append(occ.addBSpline(ids, degree=degree, weights=weights, knots=knots, multiplicities=mults))
        elif kind == "chain":
            points, corners, closed = spec[1], spec[2], spec[3]
            chain = kernel.add_chain(points, corners, closed, "tmp", "tmp")
            tags.extend(chain.curves)
        else:
            raise ValueError(f"unknown curve kind '{kind}'")
    if dropped:
        kernel.message(f"Removed {dropped} zero-length edge(s).", "info")
    kernel.sync()
    return tags


def _distinct(points, tolerance):
    pts = np.asarray(points, dtype=float)
    keep = np.r_[True, np.linalg.norm(np.diff(pts, axis=0), axis=1) > tolerance]
    return pts[keep]


def import_cad(kernel, path, unit, section_plane):
    """Read a STEP / IGES file with OpenCASCADE, in metres; returns (dim, [tags]) of the highest dimension.

    A 3D solid is cut by the chosen plane ("xy", "xz" or "yz") and the section is imported; any 2D
    geometry outside the x-y plane is turned into it.
    """
    gmsh, occ = kernel.gmsh, kernel.occ
    # OpenCASCADE reads the file in millimetres (converted from the unit the file states); Gmsh's
    # import scaling turns that into metres EXACTLY (lines stay lines, circles stay circles; a
    # later "dilate" would turn curves into B-spline approximations).
    stated = cad_file_unit(path)
    factor = UNITS["mm"]                                  # millimetres -> metres
    if unit != "file":
        factor *= UNITS[unit] / UNITS[stated or "mm"]     # the numbers are in `unit`, not in the stated one
        if unit != (stated or "mm"):
            kernel.message(f"The file's numbers are taken as {unit} (the file says {stated or 'nothing'}).", "info")
    elif stated is None:
        kernel.message("The file does not state its unit; millimetres assumed. Choose the unit if that is wrong.",
                       "warning")
    gmsh.option.setNumber("Geometry.OCCScaling", factor)
    try:
        entities = occ.importShapes(str(path), highestDimOnly=True)
    except Exception as error:
        raise ValueError(f"OpenCASCADE could not read {Path(path).name}: {error}") from None
    finally:
        gmsh.option.setNumber("Geometry.OCCScaling", 1.0)
    kernel.sync()
    if not entities:
        raise ValueError(f"{Path(path).name} contains no geometry.")
    dim = max(d for d, _ in entities)
    if dim == 0:
        raise ValueError(f"{Path(path).name} contains only points; curves, faces or solids are needed.")
    if dim == 3:
        entities = _section(kernel, entities, section_plane)
        dim = 2
    else:
        entities = _into_xy_plane(kernel, entities)
    kernel.sync()
    return dim, [t for d, t in entities if d == dim]


ROTATE_TO_XY = {"xy": None, "xz": ((1.0, 0.0, 0.0), -0.5 * math.pi), "yz": ((0.0, 1.0, 0.0), 0.5 * math.pi)}


def _section(kernel, volumes, plane):
    """Cut solids with a plane (through the origin) and turn the section into the x-y plane."""
    gmsh, occ = kernel.gmsh, kernel.occ
    if plane not in ROTATE_TO_XY:
        raise ValueError(f"unknown section plane '{plane}'")
    x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(-1, -1)
    big = 4.0 * max(x1 - x0, y1 - y0, z1 - z0, 1e-9) + 4.0 * max(map(abs, (x0, y0, z0, x1, y1, z1)))
    rect = occ.addRectangle(-big, -big, 0.0, 2.0 * big, 2.0 * big)
    if plane != "xy":                     # rotate the cutting rectangle from x-y into the chosen plane
        axis, angle = ROTATE_TO_XY[plane]
        occ.rotate([(2, rect)], 0.0, 0.0, 0.0, *axis, -angle)
    out, _ = occ.intersect([(d, t) for d, t in volumes if d == 3], [(2, rect)], removeObject=True, removeTool=True)
    kernel.sync()
    faces = [(d, t) for d, t in out if d == 2]
    if not faces:
        raise ValueError(f"The {plane} plane (through the origin) does not cut the solid; move the solid or choose "
                         "another plane.")
    if plane != "xy":
        axis, angle = ROTATE_TO_XY[plane]
        occ.rotate(faces, 0.0, 0.0, 0.0, *axis, angle)
    kernel.message(f"Cut the solid with the {plane} plane; imported the {len(faces)} section face(s).", "info")
    return faces


def _into_xy_plane(kernel, entities):
    """2D geometry lying in the x-z or y-z plane is turned into the x-y plane."""
    gmsh = kernel.gmsh
    kernel.sync()
    x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(-1, -1)
    size = max(x1 - x0, y1 - y0, z1 - z0, 1e-300)
    flat = 1e-6 * size + 2e-7                              # Gmsh pads boxes by 1e-7
    if z1 - z0 <= flat:
        if abs(z0) > flat:
            kernel.occ.translate(entities, 0.0, 0.0, -0.5 * (z0 + z1))
        return entities
    for plane, extent in (("xz", y1 - y0), ("yz", x1 - x0)):
        if extent <= flat:
            axis, angle = ROTATE_TO_XY[plane]
            kernel.occ.rotate(entities, 0.0, 0.0, 0.0, *axis, angle)
            kernel.message(f"The geometry lay in the {plane} plane; turned it into the x-y plane.", "info")
            return entities
    raise ValueError("The 2D geometry is not flat in any coordinate plane; only planar 2D geometry can be imported "
                     "(or a solid, which is cut by a plane).")

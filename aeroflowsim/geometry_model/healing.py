# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Healing of imported geometry: from loose curves to clean closed faces, telling the user what was fixed.

Geometry from other programs is rarely perfect: lines that should meet leave a tiny gap,
points are repeated, an edge has zero length, a curve is drawn twice, outlines run clockwise.
A mesher needs closed, non-crossing loops. The steps below are what serious pre-processors do
(e.g. the "repair" tools of ANSYS SpaceClaim or Salome's "shape healing"):

  1. clean_outline():   for point lists (CSV / .dat): remove repeated points, close an open outline
                        (or report it), make it counter-clockwise, count self-crossings.
  2. glue():            for curves: OpenCASCADE "fragment" with a tolerance. Curve ends closer than
                        the tolerance become ONE point (the gap is closed), identical curves become
                        one, and curves that cross are split where they cross.
  3. build_faces():     find the closed loops of curves (every point joins exactly two curves),
                        put loops inside loops as holes, and make plane faces. Open chains and
                        branching points (three or more curves meet: a crossing) are reported.
Every fix becomes a line in the Messages panel.
"""

import numpy as np

from aeroflowsim.geometry_model.built import FLUID, SOLID
from aeroflowsim.geometry_model.picking import point_in_polygon
from aeroflowsim.shapes.profile import count_self_intersections, signed_area

DEFAULT_TOLERANCE = 1e-5     # gaps smaller than this x geometry size are closed [-]
AXIS_FRACTION = 1e-3         # "on the axis": |y| below this x size [-]


def clean_outline(points, tolerance=DEFAULT_TOLERANCE, closed=None):
    """Clean a list of outline points. Returns (points, closed, messages).

    closed=None: a closed body outline (three or more points); an open one is closed with a straight segment.
    """
    pts = np.asarray(points, dtype=float)
    messages = []
    if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) < 2:
        raise ValueError("an outline needs at least two (x, y) points")
    size = float(np.ptp(pts, axis=0).max())
    if size <= 0.0:
        raise ValueError("all points of the outline are the same")
    tol = tolerance * size
    step = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    keep = np.r_[True, step > tol]
    if not keep.all():
        messages.append(("info", f"Removed {np.count_nonzero(~keep)} repeated point(s)."))
        pts = pts[keep]
    gap = float(np.linalg.norm(pts[-1] - pts[0]))
    if closed is None:                  # a body outline is closed; an open one gets a straight closing segment
        closed = len(pts) >= 3
    if closed:
        if gap <= tol:
            pts = pts[:-1]              # the last point repeats the first
        else:
            messages.append(("info", f"The outline was open: closed it with a straight segment of {gap:.3g} "
                                     "(file units) from the last to the first point."))
    if closed and len(pts) < 3:
        raise ValueError("a closed outline needs at least three different points")
    if closed and signed_area(pts) < 0.0:
        pts = np.r_[pts[:1], pts[:0:-1]]
        messages.append(("info", "Turned the outline round so that it runs counter-clockwise."))
    if closed:
        crossings = count_self_intersections(pts)
        if crossings:
            messages.append(("error", f"The outline crosses itself ({crossings} crossing(s)); check the order of "
                                      "the points."))
    return pts, bool(closed), messages


def glue(kernel, curves, tolerance):
    """Fragment curves with a tolerance [m] (see the module docstring); returns the new curve tags."""
    if not curves:
        return []
    gmsh = kernel.gmsh
    old = gmsh.option.getNumber("Geometry.ToleranceBoolean")
    points_before = _end_points(kernel, curves)
    gmsh.option.setNumber("Geometry.ToleranceBoolean", float(tolerance))
    try:
        out, _ = kernel.occ.fragment([(1, c) for c in curves], [])
    finally:
        gmsh.option.setNumber("Geometry.ToleranceBoolean", old)
    kernel.sync()
    new = sorted({t for d, t in out if d == 1})
    joined = points_before - _end_points(kernel, new)
    if joined > 0:
        kernel.message(f"Joined {joined} curve end(s) closer than {tolerance:.3g} m.", "info")
    if len(new) < len(curves):
        kernel.message(f"Removed {len(curves) - len(new)} duplicate curve(s).", "info")
    elif len(new) > len(curves):
        kernel.message(f"Split curves where they cross or touch: {len(curves)} curves became {len(new)}.", "info")
    return new


def _end_points(kernel, curves) -> int:
    ends = set()
    for c in curves:
        ends.update(t for _, t in kernel.gmsh.model.getBoundary([(1, c)], combined=False, oriented=False))
    return len(ends)


def build_faces(kernel, curves, op_id, role="auto"):
    """Make plane faces from the closed loops among `curves`; returns the new face tags.

    role "fluid" / "solid", or "auto": fluid if the face has an edge along y = 0 (a half domain of
    a nozzle or an axisymmetric body), otherwise solid (a body to put in a free stream).
    """
    model = kernel.gmsh.model
    ends = {c: [t for _, t in model.getBoundary([(1, c)], combined=False, oriented=False)] for c in curves}
    degree = {}
    for c, pts in ends.items():
        for p in set(pts):                       # a closed curve (circle) starts and ends at one point: counts 2
            degree[p] = degree.get(p, 0) + (2 if len(set(pts)) == 1 else 1)
    branch = [p for p, n in degree.items() if n > 2]
    for p in branch:
        x, y = model.getValue(0, p, [])[:2]
        kernel.message(f"{degree[p]} curves meet at ({x:.6g}, {y:.6g}) m: the curves cross or branch there, so no "
                       "face is made from them. Delete or trim the extra curves.", "error")
    loops, used = [], set()
    for start in curves:                        # walk round each loop
        if start in used or any(degree[p] != 2 for p in ends[start]):
            continue
        loop, current, point = [start], start, ends[start][-1]
        used.add(start)
        while point != ends[start][0]:
            nxt = next((c for c in curves if c not in used and point in ends[c]
                        and all(degree[p] == 2 for p in ends[c])), None)
            if nxt is None:
                break
            loop.append(nxt)
            used.add(nxt)
            point = ends[nxt][1] if ends[nxt][0] == point else ends[nxt][0]
            current = nxt
        if point == ends[start][0]:
            loops.append(loop)
    open_curves = [c for c in curves if c not in used]
    if open_curves:
        kernel.message(f"{len(open_curves)} curve(s) do not form a closed loop (open outline); they are kept as "
                       "free curves. Close the gap with a sketch line or a larger healing tolerance.", "warning")
    if not loops:
        return []
    polygons = [np.vstack([kernel.sample(c, 65) for c in loop]) for loop in loops]
    areas = [abs(signed_area(p)) for p in polygons]
    inside = [[j for j in range(len(loops)) if j != i and areas[j] > areas[i]
               and point_in_polygon(polygons[i][0], polygons[j])] for i in range(len(loops))]
    depth = [len(x) for x in inside]
    faces = []
    n_faces = sum(d % 2 == 0 for d in depth)
    for i, loop in enumerate(loops):
        if depth[i] % 2:                         # a hole of the loop just outside it
            continue
        holes = [j for j in range(len(loops)) if depth[j] == depth[i] + 1 and i in inside[j]]
        tags = [kernel.occ.addCurveLoop(loop)] + [kernel.occ.addCurveLoop(loops[j]) for j in holes]
        surface = kernel.occ.addPlaneSurface(tags)
        name = f"{op_id}:face{len(faces) + 1}" if n_faces > 1 else f"{op_id}:face"
        _set_role(kernel, surface, loop, name, role, len(faces) + 1)
        faces.append(surface)
    return faces


def _set_role(kernel, surface, curves, face_id, role, number):
    """Register a new face with its role; "auto": fluid if it has an edge along y = 0 (see build_faces)."""
    face_role = role
    if role == "auto":
        size = kernel.model_size()
        on_axis = any(np.all(np.abs(kernel.sample(c, 9)[:, 1]) <= AXIS_FRACTION * size) and
                      kernel.occ.getMass(1, c) > 1e-2 * size for c in curves)
        face_role = FLUID if on_axis else SOLID
        kernel.message(f"Face {number}: imported as {face_role} ("
                       + ("it has an edge on y = 0, like a half nozzle domain" if on_axis else
                          "a closed body to put in a flow") + "); change it with Fluid / solid if needed.", "info")
    kernel.name_face(surface, face_id, face_role)


def name_faces(kernel, surfaces, op_id, role="auto"):
    """Register faces read from a CAD file (STEP / IGES) with ids and roles."""
    for n, surface in enumerate(sorted(surfaces), start=1):
        curves = [abs(t) for _, t in kernel.gmsh.model.getBoundary([(2, surface)], oriented=False)]
        _set_role(kernel, surface, curves, f"{op_id}:face{n}" if len(surfaces) > 1 else f"{op_id}:face", role, n)

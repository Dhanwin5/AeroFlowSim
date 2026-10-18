# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unstructured 2D meshes made with Gmsh (optional install), returned as a face-based Mesh.

Gmsh (https://gmsh.info, C. Geuzaine and J.-F. Remacle, 2009) is a free, widely used mesh
generator with a Python interface. It is OPTIONAL: install it with  pip install -e ".[mesh]".
Without it AeroFlowSim still works (structured meshes only), and this module says how to install it.

What this module does, in plain words:
  1. Describe the geometry to Gmsh: points, curves (straight lines, smooth splines through the
     outline points between sharp corners, exact circle arcs), and the region to be meshed.
     Every boundary curve is put in a "physical group" named after its patch: wall, farfield,
     symmetry, axis, inlet, outlet.
  2. Tell Gmsh how big the cells should be ("size fields", see SIZE FIELD below) and whether to
     combine triangles into quadrilaterals (quad-dominant mesh, "recombination").
  3. Let Gmsh mesh it, then copy its nodes, cells and boundary edges into a Mesh
     (aeroflowsim/mesh.py): physical groups become patches with the same names. See _gmsh_arrays().

INFLATION LAYERS (quad layers along the walls) are grown by AeroFlowSim itself
(aeroflowsim/inflation_layers.py), not by Gmsh's BoundaryLayer field: in tests that field failed
("edge not recovered") for about half of the nozzle cell sizes. So with inflation Gmsh runs twice:
first it only places the nodes along the wall, then the layers are grown from those nodes, and
finally Gmsh meshes the rest of the domain, whose inner boundary is the top of the layers.

SIZE FIELD: the wanted cell size h at a point grows linearly with its distance d from the body
(or nozzle wall) and is capped at the largest size:
        h(d) = min(h_max, h_surface + (growth - 1) d)
A cell of size h then has neighbours of about growth x h further out - which is what "growth
rate" means. With edge refinement, corners, leading and trailing edges and the nozzle throat get
the same rule starting from h_surface / EDGE_REFINEMENT. In Gmsh this is a Distance field (d) fed
into a Threshold field (the linear ramp), combined with a Min field.

Gmsh keeps global state, so only one mesh is made at a time (a lock), and it is started with
interruptible=False because the GUI runs it outside Python's main thread.
"""

import math
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from aeroflowsim.inflation_layers import grow_layers
from aeroflowsim.mesh import QUAD, TRIANGLE, Mesh
from aeroflowsim.nozzle_mesh import Inflation
from aeroflowsim.parameters import install_hint, module_available
from aeroflowsim.shapes.profile import turning_corners

EDGE_REFINEMENT = 4.0          # corners / edges / throat get cells this many times smaller [-]
MIN_FARFIELD_FACES = 100       # a far-field circle is split into at least this many faces [-]
NOZZLE_CORNER_ANGLE = 5.0      # a nozzle wall that turns more than this at a point has a corner [deg]
SPACING_JUMP = 4.0             # split a spline where neighbouring point spacings differ more than this [-]
MAX_CELLS = 2_000_000          # refuse to start Gmsh above this estimate (the GUI would freeze) [-]
TRIANGLE_AREA = math.sqrt(3.0) / 4.0   # area of an equilateral triangle of side 1 [-]
GMSH_TRIANGLE, GMSH_QUAD, GMSH_LINE = 2, 3, 1   # Gmsh element type numbers (first order)

_LOCK = threading.Lock()


def gmsh_available() -> bool:
    """True if the optional Gmsh package is installed."""
    return module_available("gmsh")


def _import_gmsh():
    """Import gmsh, or raise ValueError saying how to install it."""
    try:
        import gmsh
    except ImportError:
        raise ValueError(f"Gmsh is not installed, so triangle meshes are not available. Install it with: "
                         f"{install_hint('gmsh')}") from None
    return gmsh


@dataclass
class GmshSettings:
    """How Gmsh should mesh (all lengths in metres)."""

    surface_size: float               # cell size on the body / nozzle wall [m]
    max_size: float                   # largest cell size (the far-field size for external flow) [m]
    growth: float = 1.2               # size growth per cell away from the wall [-] (> 1)
    edge_refinement: bool = True      # smaller cells at corners, leading/trailing edges and the throat
    quads: bool = False               # True: quad-dominant (triangles recombined into quads)
    inflation: Inflation | None = None   # quad layers along the walls, or None
    msh_path: Path | None = None      # also save Gmsh's own .msh file here (None = do not save)

    def check(self):
        if not (self.surface_size > 0.0 and self.max_size >= self.surface_size):
            raise ValueError("The cell sizes must be positive, and the largest (far-field) size at least the "
                             "surface size.")
        if self.growth <= 1.0:
            raise ValueError("The growth rate must be larger than 1.")

    def size_at(self, distance, start=None):
        """The wanted cell size [m] at `distance` [m] from the wall (the SIZE FIELD rule)."""
        h0 = self.surface_size if start is None else start
        return np.minimum(self.max_size, h0 + (self.growth - 1.0) * np.asarray(distance))

    @property
    def corner_size(self) -> float:
        """Cell size at refined points [m]."""
        return self.surface_size / EDGE_REFINEMENT if self.edge_refinement else self.surface_size


@dataclass
class Domain:
    """The far-field boundary around a body (all lengths in metres)."""

    shape: str = "Circle"             # "Circle" or "Rectangle"
    radius: float = 20.0              # circle radius, from the body centre [m]
    upstream: float = 10.0            # rectangle: distance from the body's front to the inflow side [m]
    downstream: float = 20.0          # rectangle: distance from the body's back to the outflow side [m]
    height: float = 10.0              # rectangle: distance from y = 0 to the top (and bottom) side [m]
    half: bool = False                # True: only y >= 0 (symmetry plane or axis at y = 0)


# =============================================================================================
# Public mesh functions
# =============================================================================================

def external_mesh(profile, domain: Domain, settings: GmshSettings) -> Mesh:
    """Mesh of the flow around a body (a ShapeProfile) inside a far-field boundary.

    Patches: wall (the body), farfield, and symmetry (planar) or axis (axisymmetric) on y = 0 for
    a half domain. Axisymmetric bodies always use the half domain (the axis is at y = 0).
    """
    settings.check()
    half = domain.half or profile.axisymmetric
    if profile.self_intersections():
        raise ValueError("The body outline crosses itself, so it cannot be meshed. Check the coordinates.")
    x0, y0, x1, y1 = profile.bbox
    xc = 0.5 * (x0 + x1)                                          # body centre on the x axis [m]
    if domain.shape == "Circle":
        far = (np.hypot(profile.points[:, 0] - xc, profile.points[:, 1]).max())
        if domain.radius <= 1.5 * far:
            raise ValueError(f"The far-field circle (radius {domain.radius:g} m) must be well outside the body "
                             f"(more than {1.5 * far:.3g} m).")
    elif domain.upstream <= 0 or domain.downstream <= 0 or domain.height <= 1.5 * max(abs(y0), abs(y1)):
        raise ValueError("The far-field rectangle must lie well outside the body on every side.")
    estimate = estimate_external_cells(profile, domain, settings)
    if estimate > MAX_CELLS:
        raise ValueError(f"This mesh would have about {estimate:,.0f} cells (limit {MAX_CELLS:,}). Use a larger "
                         "surface cell size or growth rate.")
    symmetry_patch = ("axis" if profile.axisymmetric else "symmetry") if half else None
    if half:
        chain, corners, refine = profile.upper_half()             # right end on y = 0 ... left end on y = 0
    else:
        chain, corners, refine = profile.points, profile.corners, profile.refine
    refine_xy = chain[refine]

    def build(gmsh, top=None):
        """Body (or, with inflation, the top of the layers), far-field boundary and the fluid surface."""
        geo = gmsh.model.geo
        if top is None:
            body = _add_chain(geo, chain, corners | refine, closed=not half)
        else:
            body = _add_polyline(geo, top, closed=not half)
        left, right = body.point_tags[-1], body.point_tags[0]       # half domain: the body's ends on y = 0
        patches = {"wall": ("wall", list(body.curves))}
        if domain.shape == "Circle":
            R = domain.radius
            centre = geo.addPoint(xc, 0.0, 0.0)
            angles = [0.0, 0.5 * math.pi, math.pi] + ([] if half else [1.5 * math.pi])
            ring = [geo.addPoint(xc + R * math.cos(a), R * math.sin(a), 0.0) for a in angles]
            ends = list(zip(ring, ring[1:] + ([] if half else ring[:1])))
            arcs = [geo.addCircleArc(a, centre, b) for a, b in ends]
            n_faces = 4 * math.ceil(max(MIN_FARFIELD_FACES, 2.0 * math.pi * R / settings.max_size) / 4)
            for arc in arcs:                                         # keep the circle round
                geo.mesh.setTransfiniteCurve(arc, n_faces // 4 + 1)
            outer, far_curves = ring, arcs
            far_size = 2.0 * math.pi * R / n_faces                   # face length on the circle [m]
        else:
            X0, X1, H = x0 - domain.upstream, x1 + domain.downstream, domain.height
            corners_xy = [(X1, 0.0), (X1, H), (X0, H), (X0, 0.0)] if half else [(X1, -H), (X1, H), (X0, H), (X0, -H)]
            outer = [geo.addPoint(x, y, 0.0) for x, y in corners_xy]
            pairs = list(zip(outer, outer[1:] + ([] if half else outer[:1])))
            far_curves = [geo.addLine(a, b) for a, b in pairs]
            far_size = settings.max_size
        patches["farfield"] = ("farfield", far_curves)
        if half:
            sym_right = geo.addLine(right, outer[0])                 # body back -> far field (on y = 0)
            sym_left = geo.addLine(outer[-1], left)                  # far field -> body front
            patches[symmetry_patch] = (symmetry_patch, [sym_right, sym_left])
            loop = geo.addCurveLoop([sym_right] + far_curves + [sym_left] + [-c for c in reversed(body.curves)])
            surface = geo.addPlaneSurface([loop])
        else:
            outer_loop = geo.addCurveLoop(far_curves)
            body_loop = geo.addCurveLoop(body.curves)
            surface = geo.addPlaneSurface([outer_loop, body_loop])
        far_length = 2.0 * math.pi * domain.radius if domain.shape == "Circle" else 4.0 * (X1 - X0 + H)
        return dict(surface=surface, patches=patches, wall_curves=body.curves, wall_length=body.length,
                    refine_xy=refine_xy, far_curves=far_curves, far_size=far_size, far_length=far_length)

    info = {
        "generator": "gmsh_external", "shape": profile.name, "axisymmetric": bool(profile.axisymmetric),
        "reference_length": float(profile.reference_length), "reference_area": float(profile.reference_area),
        "body_bbox": [float(x0), float(y0), float(x1), float(y1)], "domain": domain.shape,
        "half_domain": bool(half),
    }
    # With inflation the layers end on the symmetry line / axis: at the body's back (chain start)
    # they run along +x, at its front (chain end) along -x.
    ends = ((symmetry_patch, (1.0, 0.0)), (symmetry_patch, (-1.0, 0.0))) if half else None
    return _run_gmsh(build, settings, profile.axisymmetric, info, closed=not half, ends=ends)


def nozzle_mesh(wall, settings: GmshSettings) -> Mesh:
    """Unstructured mesh of the upper half of an axisymmetric nozzle, axis (r = 0) to wall.

    wall: a WallProfile (aeroflowsim/geometry.py). Patches inlet, outlet, wall and axis - the same as
    the structured mesh (aeroflowsim/nozzle_mesh.py), so a solver treats both the same way.
    """
    settings.check()
    if wall.interpolation == "pchip":     # a smooth CSV profile: follow the same smooth curve densely
        x = np.linspace(wall.x[0], wall.x[-1], 801)
        x = np.unique(np.r_[x, wall.x_throat])
    else:
        x = wall.x
    points = np.column_stack([x, wall.radius_at(x)])                  # inlet -> exit [m]
    corners = np.zeros(len(points), dtype=bool)
    corners[1:-1] = turning_corners(points, NOZZLE_CORNER_ANGLE)[1:-1]
    corners[[0, -1]] = True
    for _, x_mark, _ in wall.marks:     # e.g. rounded-throat tangent points: a straight cone meets an arc
        corners[int(np.argmin(np.abs(points[:, 0] - x_mark)))] = True
    throat = int(np.argmin(np.abs(points[:, 0] - wall.x_throat)))
    refine = corners.copy()
    refine[throat] = True
    refine[[0, -1]] = False          # the inlet / exit corners need no extra refinement
    refine_xy = points[refine]
    estimate = estimate_nozzle_cells(wall, settings)
    if estimate > MAX_CELLS:
        raise ValueError(f"This mesh would have about {estimate:,.0f} cells (limit {MAX_CELLS:,}). Use a larger "
                         "surface cell size or growth rate.")

    def build(gmsh, top=None):
        """Wall (or, with inflation, the top of the layers), inlet, outlet, axis and the fluid surface."""
        geo = gmsh.model.geo
        if top is None:
            body = _add_chain(geo, points, corners | refine, closed=False)
        else:
            body = _add_polyline(geo, top, closed=False)
        inlet_wall, exit_wall = body.point_tags[0], body.point_tags[-1]
        x_in, x_out = points[0, 0], points[-1, 0]
        axis_in, axis_out = geo.addPoint(x_in, 0.0, 0.0), geo.addPoint(x_out, 0.0, 0.0)
        axis = geo.addLine(axis_in, axis_out)
        outlet = geo.addLine(axis_out, exit_wall)
        inlet = geo.addLine(inlet_wall, axis_in)
        loop = geo.addCurveLoop([axis, outlet] + [-c for c in reversed(body.curves)] + [inlet])
        surface = geo.addPlaneSurface([loop])
        patches = {"inlet": ("inlet", [inlet]), "outlet": ("outlet", [outlet]),
                   "wall": ("wall", list(body.curves)), "axis": ("axis", [axis])}
        return dict(surface=surface, patches=patches, wall_curves=body.curves, wall_length=body.length,
                    refine_xy=refine_xy)

    info = {"generator": "gmsh_nozzle", "x_throat": float(wall.x_throat), "r_throat": float(wall.r_throat),
            "reference_length": float(2.0 * wall.r_throat),
            "reference_area": float(math.pi * wall.r_throat**2)}
    # With inflation the layers end on the inlet and the outlet, going straight down (towards the axis).
    ends = (("inlet", (0.0, -1.0)), ("outlet", (0.0, -1.0)))
    return _run_gmsh(build, settings, True, info, closed=False, ends=ends)


# =============================================================================================
# Cell-count estimates (no Gmsh needed; for the GUI's "big mesh" warning)
# =============================================================================================

def _cell_area_factor(settings) -> float:
    """Area of one cell / h²: equilateral triangles, or quads made of two triangles."""
    return 2.0 * TRIANGLE_AREA if settings.quads else TRIANGLE_AREA


def _band_cells(settings, perimeter_at, area_limit, start=None, n=4000):
    """Cells in the region around a curve: integral of (band length x dd) / (cell area) over distance d.

    perimeter_at(d): length of the line at distance d from the wall [m]; stops when area_limit is used up.
    """
    d_end = 50.0 * settings.max_size / (settings.growth - 1.0) + 1e3 * settings.max_size
    d = np.concatenate([[0.0], np.geomspace(settings.surface_size * 1e-3, d_end, n)])
    mid, width = 0.5 * (d[1:] + d[:-1]), np.diff(d)
    band = perimeter_at(mid) * width                                       # band areas [m²]
    keep = np.cumsum(band) <= area_limit
    h = settings.size_at(mid, start)
    return float(np.sum(band[keep] / (_cell_area_factor(settings) * h[keep] ** 2)))


def _refinement_cells(settings, n_points, opening=math.pi):
    """Extra cells around n_points refined points (each a sector of the given opening angle)."""
    if not settings.edge_refinement or n_points == 0:
        return 0.0
    extra = 0.0
    d = np.geomspace(settings.corner_size * 1e-3, settings.max_size / (settings.growth - 1.0), 2000)
    mid, width = 0.5 * (d[1:] + d[:-1]), np.diff(d)
    fine, normal = settings.size_at(mid, settings.corner_size), settings.size_at(mid)
    extra = np.sum(opening * mid * width * (1.0 / fine**2 - 1.0 / normal**2)) / _cell_area_factor(settings)
    return float(n_points * extra)


def _inflation_cells(settings, wall_length):
    """Quad cells in the inflation layers (layers x wall length / surface size)."""
    if settings.inflation is None:
        return 0.0
    return settings.inflation.n_layers * wall_length / settings.surface_size


def estimate_external_cells(profile, domain: Domain, settings: GmshSettings) -> int:
    """Rough number of cells (usually within about 30 %) of external_mesh(), without running Gmsh."""
    half = domain.half or profile.axisymmetric
    share = 0.5 if half else 1.0
    if domain.shape == "Circle":
        area = math.pi * domain.radius**2
    else:
        x0, _, x1, _ = profile.bbox
        area = (x1 - x0 + domain.upstream + domain.downstream) * 2.0 * domain.height
    area = share * (area - profile.area)
    perimeter = share * profile.perimeter
    cells = _band_cells(settings, lambda d: perimeter + share * 2.0 * math.pi * d, area)
    n_refine = int(np.count_nonzero(profile.refine))
    if half:
        n_refine = int(np.count_nonzero(profile.upper_half()[2]))
    cells += _refinement_cells(settings, n_refine)
    cells += _inflation_cells(settings, perimeter)
    return int(round(cells))


def estimate_nozzle_cells(wall, settings: GmshSettings) -> int:
    """Rough number of cells of nozzle_mesh(): integral of dx dr / cell area, distance = r_wall - r."""
    x = np.linspace(wall.x[0], wall.x[-1], 2001)
    xm, dx = 0.5 * (x[1:] + x[:-1]), np.diff(x)
    cells = 0.0
    for xi, w in zip(xm, dx):
        r_w = float(wall.radius_at(xi))
        d = np.linspace(0.0, r_w, 200)
        dm = 0.5 * (d[1:] + d[:-1])
        cells += w * np.sum(np.diff(d) / (_cell_area_factor(settings) * settings.size_at(dm) ** 2))
    corners = turning_corners(np.column_stack([wall.x, wall.r]), NOZZLE_CORNER_ANGLE)[1:-1]
    cells += _refinement_cells(settings, int(np.count_nonzero(corners)) + 1, opening=0.5 * math.pi)
    wall_length = float(np.sum(np.hypot(np.diff(wall.x), np.diff(wall.r))))
    cells += _inflation_cells(settings, wall_length)
    return int(round(cells))


# =============================================================================================
# Geometry helpers
# =============================================================================================

@dataclass
class _Chain:
    """Gmsh curves made from a chain of outline points."""

    curves: list        # curve tags, in chain order
    point_tags: list    # Gmsh point tags of the split points (where curves meet), in chain order
    point_index: list   # outline point number of each of those points
    length: float       # total length of the outline [m]


def _add_chain(geo, points, split, closed):
    """Add an outline (open chain or closed loop) to Gmsh as curves split at the `split` points.

    Between two split points: a straight line if there are only two points, otherwise a smooth
    spline through all the points (Gmsh "Spline": an interpolating Catmull-Rom curve). So sharp
    corners stay sharp (they are split points) and smooth parts stay smooth.
    """
    n = len(points)
    split = np.array(split, dtype=bool)
    # A Catmull-Rom spline wiggles where the point spacing changes suddenly (e.g. a long straight
    # segment next to a finely sampled arc), so split there too.
    step = np.linalg.norm(np.diff(np.vstack([points[-1:], points, points[:1]]), axis=0), axis=1)
    before, after = step[:-1], step[1:]
    split |= np.maximum(before, after) > SPACING_JUMP * np.minimum(before, after)
    if not closed:
        split[[0, -1]] = True
    cuts = list(np.flatnonzero(split))
    if closed:                                     # a closed loop needs at least 3 curves
        while len(cuts) < 3:
            gaps = np.diff(cuts + [cuts[0] + n]) if cuts else [n]
            k = int(np.argmax(gaps))
            start = cuts[k] if cuts else 0
            cuts.append((start + gaps[k] // 2) % n)
            cuts = sorted(set(cuts))
    tags = {i: geo.addPoint(points[i, 0], points[i, 1], 0.0) for i in cuts}
    curves = []
    pieces = list(zip(cuts, cuts[1:] + ([cuts[0] + n] if closed else [])))
    for a, b in pieces:
        idx = [i % n for i in range(a, b + 1)]
        if len(idx) == 2:
            curves.append(geo.addLine(tags[idx[0]], tags[idx[1]]))
        else:
            inner = [geo.addPoint(points[i, 0], points[i, 1], 0.0) for i in idx[1:-1]]
            curves.append(geo.addSpline([tags[idx[0]]] + inner + [tags[idx[-1]]]))
    segments = np.diff(np.vstack([points, points[:1]]) if closed else points, axis=0)
    return _Chain(curves, [tags[i] for i in cuts], cuts, float(np.linalg.norm(segments, axis=1).sum()))


def _add_polyline(geo, points, closed):
    """Add a polyline (the top of the inflation layers) whose every point must become a mesh node.

    Each segment is a straight line meshed with exactly one edge (a "transfinite" line with 2
    nodes), so the layer cells below and Gmsh's cells above share the same nodes.
    """
    tags = [geo.addPoint(x, y, 0.0) for x, y in points]
    ends = list(zip(tags, tags[1:] + (tags[:1] if closed else [])))
    curves = [geo.addLine(a, b) for a, b in ends]
    for curve in curves:
        geo.mesh.setTransfiniteCurve(curve, 2)
    segments = np.diff(np.vstack([points, points[:1]]) if closed else points, axis=0)
    return _Chain(curves, tags, list(range(len(points))), float(np.linalg.norm(segments, axis=1).sum()))


# =============================================================================================
# Running Gmsh and converting its mesh
# =============================================================================================

def _size_fields(gmsh, settings, parts):
    """Background size field: h(d) = min(h_max, h_s + (growth - 1) d) from the walls and refined points.

    A far-field circle has at least MIN_FARFIELD_FACES faces, which can be smaller than h_max; then
    the cells also grow from that face size away from the circle (no sudden size jump there).
    """
    field = gmsh.model.mesh.field
    ramp = lambda h0: (settings.max_size - h0) / (settings.growth - 1.0)   # distance where h reaches h_max [m]
    far_size = parts.get("far_size", settings.max_size)
    refine_points = []
    if settings.edge_refinement:   # free points (not on any curve), only used to measure distances
        refine_points = [gmsh.model.geo.addPoint(x, y, 0.0) for x, y in parts["refine_xy"]]
        gmsh.model.geo.synchronize()
    fields = []
    for tags, h0, kind in ((parts["wall_curves"], settings.surface_size, "CurvesList"),
                           (refine_points, settings.corner_size, "PointsList"),
                           (parts.get("far_curves", []) if far_size < settings.max_size else [], far_size,
                            "CurvesList")):
        if not tags:
            continue
        distance = field.add("Distance")
        field.setNumbers(distance, kind, tags)
        if kind == "CurvesList":    # sample the curves finely enough to measure distances accurately
            length = parts["wall_length"] if tags is parts["wall_curves"] else parts["far_length"]
            per_curve = 4.0 * length / h0 / len(tags)
            field.setNumber(distance, "Sampling", int(min(20000, max(4, per_curve))))
        threshold = field.add("Threshold")
        field.setNumber(threshold, "InField", distance)
        field.setNumber(threshold, "SizeMin", h0)
        field.setNumber(threshold, "SizeMax", settings.max_size)
        field.setNumber(threshold, "DistMin", 0.0)
        field.setNumber(threshold, "DistMax", max(ramp(h0), 1e-300))
        fields.append(threshold)
    smallest = field.add("Min")
    field.setNumbers(smallest, "FieldsList", fields)
    field.setAsBackgroundMesh(smallest)


def _set_options(gmsh, settings):
    """Gmsh meshing options: sizes only from the size field; triangles or recombined quads."""
    for option, value in (("General.Terminal", 0), ("Mesh.MeshSizeExtendFromBoundary", 0),
                          ("Mesh.MeshSizeFromPoints", 0), ("Mesh.MeshSizeFromCurvature", 0),
                          ("Mesh.ElementOrder", 1),
                          ("Mesh.Algorithm", 8 if settings.quads else 6),   # Frontal-Delaunay (for quads)
                          ("Mesh.RecombineAll", 1 if settings.quads else 0),
                          ("Mesh.RecombinationAlgorithm", 1)):               # Blossom
        gmsh.option.setNumber(option, value)


def _start_model(gmsh, build, settings, top=None):
    """New Gmsh model: geometry from build(gmsh, top), size field and options."""
    gmsh.model.add("aeroflowsim")
    parts = build(gmsh, top)
    gmsh.model.geo.synchronize()
    _size_fields(gmsh, settings, parts)
    _set_options(gmsh, settings)
    return parts


def _wall_nodes(gmsh, curves, closed):
    """Coordinates (m, 2) of the mesh nodes Gmsh put along the wall curves, in wall order."""
    points = []
    for curve in curves:
        start, end = [tag for _, tag in gmsh.model.getBoundary([(1, curve)], oriented=True, combined=False)]
        _, coords, params = gmsh.model.mesh.getNodes(1, curve, includeBoundary=False, returnParametricCoord=True)
        inner = np.asarray(coords, dtype=float).reshape(-1, 3)[np.argsort(params), :2]
        points.append(np.asarray(gmsh.model.getValue(0, abs(start), []))[None, :2])
        points.append(inner)
    if not closed:
        points.append(np.asarray(gmsh.model.getValue(0, abs(end), []))[None, :2])
    return np.vstack(points)


def _run_gmsh(build, settings, axisymmetric, info, closed, ends=None) -> Mesh:
    """Mesh the geometry made by build(gmsh, top) with Gmsh and return it as a Mesh.

    Without inflation: one Gmsh run. With inflation, two:
      1. Gmsh places the nodes along the wall (1D mesh only);
      2. the layers are grown from those nodes (aeroflowsim/inflation_layers.py), and Gmsh meshes the
         rest of the domain, whose inner boundary is now the top of the layers.
    ends: for open walls, ((patch, direction), (patch, direction)) at the start and end of the wall:
          the boundary each end lies on, and the direction along it into the flow.
    """
    gmsh = _import_gmsh()
    layers = None
    with _LOCK:
        try:
            if settings.inflation is not None:
                gmsh.initialize(interruptible=False)
                try:
                    parts = _start_model(gmsh, build, settings)
                    gmsh.model.mesh.generate(1)
                    wall = _wall_nodes(gmsh, parts["wall_curves"], closed)
                finally:
                    gmsh.finalize()
                inflation = settings.inflation
                layers = grow_layers(wall, closed, inflation.first_height, inflation.n_layers, inflation.growth,
                                     None if closed else ends[0][1], None if closed else ends[1][1])
            gmsh.initialize(interruptible=False)
            try:
                parts = _start_model(gmsh, build, settings, None if layers is None else layers.nodes[layers.top])
                patch_types = {name: t for name, (t, _) in parts["patches"].items()}
                for name, (_, curves) in parts["patches"].items():
                    if layers is not None and name == "wall":
                        continue            # with layers, these curves are inside the mesh (top of the layers)
                    gmsh.model.addPhysicalGroup(1, curves, name=name)
                gmsh.model.addPhysicalGroup(2, [parts["surface"]], name="fluid")
                gmsh.model.mesh.generate(2)
                if settings.msh_path is not None and layers is None:
                    path = Path(settings.msh_path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    gmsh.write(str(path))
                nodes, types, cells, boundary, point_nodes = _gmsh_arrays(gmsh, patch_types)
                top_nodes = point_nodes(parts["wall_curves"]) if layers is not None else None
            finally:
                gmsh.finalize()
        except ValueError:
            raise
        except Exception as error:
            raise ValueError(f"Gmsh could not make this mesh: {error}. Try other cell sizes or switch edge "
                             "refinement off.") from None
    if layers is not None:
        nodes, types, cells, boundary = _join_layers(nodes, types, cells, boundary, layers, top_nodes, ends)
    nodes, types, cells, boundary = _drop_unused_nodes(nodes, types, cells, boundary)
    if axisymmetric:
        nodes[:, 1] = np.maximum(nodes[:, 1], 0.0)                     # round-off just below the axis
    mesh = Mesh.from_cells(nodes, types, cells, boundary, dim=2, axisymmetric=axisymmetric, info=info)
    mesh.info.update(gmsh_settings(settings))
    if settings.msh_path is not None and layers is not None:
        mesh.info["msh_note"] = "The .msh file is not written for meshes with inflation layers (use the .vtu)."
    return mesh


def gmsh_settings(settings) -> dict:
    """The mesh settings as plain numbers, stored in Mesh.info."""
    info = {"surface_size": settings.surface_size, "max_size": settings.max_size, "growth": settings.growth,
            "edge_refinement": settings.edge_refinement, "quad_dominant": settings.quads,
            "inflation": settings.inflation is not None}
    if settings.inflation is not None:
        layers = settings.inflation
        info.update(first_layer_height=layers.first_height, n_layers=layers.n_layers,
                    growth_rate=layers.growth, inflation_thickness=layers.thickness)
    return info


def _gmsh_arrays(gmsh, patch_types):
    """Copy the 2D mesh Gmsh has just made into plain arrays.

    Returns (nodes (N, 2), cell types, cells (C, 4), boundary {patch: (type, edges (n, 2))},
    point_nodes) - point_nodes(curves) gives the node numbers at the points of a polyline.

    1. Nodes: Gmsh numbers them with "tags" 1, 2, 3 ... (with possible gaps); here they become
       rows 0, 1, 2 ... in the order Gmsh lists them.
    2. Cells: Gmsh element type 2 (3-node triangle) becomes VTK TRIANGLE, type 3 (4-node quad)
       becomes VTK QUAD. Both programs list the corners of a first-order cell in order round the
       cell; a Mesh needs them counter-clockwise (positive area), so clockwise cells are reversed.
    3. Boundary: every physical group of curves (farfield, symmetry, inlet, ...) holds 2-node line
       elements; their node pairs are the boundary faces of the patch with the group's name.
    """
    tags, coords, _ = gmsh.model.mesh.getNodes()
    tags = np.asarray(tags, dtype=np.int64)
    xy = np.asarray(coords, dtype=float).reshape(-1, 3)[:, :2].copy()
    lookup = np.full(int(tags.max()) + 1, -1, dtype=np.int64)        # Gmsh tag -> row of xy
    lookup[tags] = np.arange(len(tags))

    cells, types = [], []
    element_types, _, element_nodes = gmsh.model.mesh.getElements(2)
    for kind, node_tags in zip(element_types, element_nodes):
        node_tags = np.asarray(node_tags, dtype=np.int64)
        if kind == GMSH_TRIANGLE:
            tri = lookup[node_tags.reshape(-1, 3)]
            cells.append(np.column_stack([tri, np.full(len(tri), -1)]))
            types.append(np.full(len(tri), TRIANGLE))
        elif kind == GMSH_QUAD:
            cells.append(lookup[node_tags.reshape(-1, 4)])
            types.append(np.full(len(cells[-1]), QUAD))
        else:
            raise ValueError(f"Gmsh made an element of type {kind}; only triangles and quads are supported in 2D.")
    if not cells:
        raise ValueError("Gmsh made no cells. Check the geometry and the cell sizes.")
    cells, types = _counter_clockwise(xy, np.vstack(cells), np.concatenate(types))

    boundary = {}
    for dim, group in gmsh.model.getPhysicalGroups(1):
        name = gmsh.model.getPhysicalName(dim, group)
        faces = []
        for entity in gmsh.model.getEntitiesForPhysicalGroup(dim, group):
            kinds, _, nodes = gmsh.model.mesh.getElements(1, entity)
            for kind, node_tags in zip(kinds, nodes):
                if kind == GMSH_LINE:
                    faces.append(lookup[np.asarray(node_tags, dtype=np.int64).reshape(-1, 2)])
        boundary[name] = (patch_types[name], np.vstack(faces))

    def point_nodes(curves):
        """Node rows at the start point of every curve (and the end of the last one, if it is open)."""
        rows = []
        for k, curve in enumerate(curves):
            ends = [tag for _, tag in gmsh.model.getBoundary([(1, curve)], oriented=True, combined=False)]
            for point in ([ends[0]] if k < len(curves) - 1 else ends):
                node_tags, _, _ = gmsh.model.mesh.getNodes(0, abs(point))
                rows.append(int(lookup[int(node_tags[0])]))
        if rows[-1] == rows[0]:      # a closed polyline: the last end point is the first point again
            rows.pop()
        return np.array(rows, dtype=np.int64)

    return xy, types, cells, boundary, point_nodes


def _counter_clockwise(xy, cells, types):
    """Reverse the node order of cells whose shoelace area is negative (clockwise)."""
    n_corner = np.where(types == TRIANGLE, 3, 4)
    area = np.zeros(len(cells))
    for k in range(4):
        use = k < n_corner
        a = cells[use, k]
        b = np.where(k + 1 < n_corner[use], cells[use, (k + 1) % 4], cells[use, 0])
        area[use] += xy[a, 0] * xy[b, 1] - xy[b, 0] * xy[a, 1]
    flip = area < 0.0
    tri, quad = flip & (types == TRIANGLE), flip & (types == QUAD)
    cells[tri, :3] = cells[tri][:, [0, 2, 1]]
    cells[quad] = cells[quad][:, [0, 3, 2, 1]]
    return cells, types


def _join_layers(nodes, types, cells, boundary, layers, top_nodes, ends):
    """Add the inflation-layer cells to Gmsh's cells; the top layer nodes are Gmsh's polyline nodes."""
    if len(top_nodes) != len(layers.top):
        raise ValueError("The top of the inflation layers does not match Gmsh's nodes.")
    index = np.full(len(layers.nodes), -1, dtype=np.int64)          # layer node -> row in the joined arrays
    index[layers.top] = top_nodes
    new = np.flatnonzero(index < 0)
    index[new] = len(nodes) + np.arange(len(new))
    nodes = np.vstack([nodes, layers.nodes[new]])
    cells = np.vstack([cells, np.where(layers.cells >= 0, index[np.maximum(layers.cells, 0)], -1)])
    types = np.concatenate([types, layers.cell_types])
    boundary = dict(boundary)
    boundary["wall"] = ("wall", index[layers.wall_faces])
    if ends is not None:
        for (patch, _), faces in zip(ends, (layers.start_faces, layers.end_faces)):
            patch_type, existing = boundary[patch]
            boundary[patch] = (patch_type, np.vstack([existing, index[faces]]))
    return nodes, types, cells, boundary


def _drop_unused_nodes(nodes, types, cells, boundary):
    """Remove nodes no cell uses (e.g. the free refinement points) and renumber the rest 0, 1, 2 ..."""
    used = np.unique(cells[cells >= 0])
    renumber = np.full(len(nodes), -1, dtype=np.int64)
    renumber[used] = np.arange(len(used))
    cells = np.where(cells >= 0, renumber[np.maximum(cells, 0)], -1)
    boundary = {name: (t, renumber[f]) for name, (t, f) in boundary.items()}
    return nodes[used], types, cells, boundary

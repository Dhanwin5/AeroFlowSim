# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Meshing a geometry from the workspace (aeroflowsim/geometry_model/): named boundaries -> mesh patches.

mesh_for(case, params, document, folder) is what the GUI, the command line and the helper process
call. It decides:
  - no workspace edits (no document, or only the template's own geometry): the template's own
    build_mesh(params), EXACTLY as before the workspace existed (so validated meshes are unchanged);
  - edited geometry: workspace_mesh() below, with the template's Gmsh settings
    (case.workspace_settings(params)).

workspace_mesh(), in plain words:
  1. Replay the history in OpenCASCADE (the same replay the Geometry step shows), and refuse with
     a clear message if a step failed or a boundary edge has no name.
  2. Every boundary name becomes a Gmsh "physical group" of its edges, so the mesh patches carry
     exactly the names (and types) given in the workspace; Prompt 7 reads the boundary conditions
     from them. The fluid faces are meshed; solid faces are not.
  3. Cell sizes (Gmsh "size fields", all combined with Min):
        walls          h(d) = min(h_max, h_wall + (growth - 1) d)  (distance d from the walls)
        sharp corners  the same rule from h_wall / EDGE_REFINEMENT (when edge refinement is on)
        refinement box / circle   at most the region's size inside, growing outside it
        wake line      at most its size within half its width of the line, growing beyond
  4. Inflation layers on the walls marked for them (see INFLATION below), then Gmsh meshes the rest.

INFLATION: the same "grow the layers first" method as aeroflowsim/gmsh_mesh.py, for any geometry:
  a) Gmsh places nodes along the edges only (1D mesh); the nodes of each chain of inflation walls
     are read in order (oriented so that the fluid is on the right-hand side);
  b) the layers are grown from them (aeroflowsim/inflation_layers.py);
  c) the region the layers cover is CUT out of the fluid face (an OCC boolean), so the remaining
     face is bounded by the top of the layers; neighbouring straight boundaries (axis, inlet,
     symmetry ...) are trimmed by the cut and keep their names;
  d) Gmsh meshes the remaining face with exactly one mesh edge per top-of-layer segment, so its
     nodes are the layer-top nodes, and the layer cells are added to its cells.
"""

import math

import numpy as np

from aeroflowsim.geometry_model import FLUID, ReplayContext, template_document
from aeroflowsim.geometry_model.boundaries import boundary_problems
from aeroflowsim.geometry_model.kernel import Kernel, gmsh_session
from aeroflowsim.geometry_model.document import run_operations
from aeroflowsim.geometry_model.picking import point_in_polygon
from aeroflowsim.gmsh_mesh import (
    EDGE_REFINEMENT, GMSH_LINE, MAX_CELLS, NOZZLE_CORNER_ANGLE, TRIANGLE_AREA, _counter_clockwise, _drop_unused_nodes,
    _set_options, gmsh_settings)
from aeroflowsim.inflation_layers import grow_layers
from aeroflowsim.mesh import QUAD, TRIANGLE, Mesh
from aeroflowsim.shapes.profile import count_self_intersections

LAYERS = "layers"           # operation id used for the edges made by the inflation cut
WAKE_SAMPLES = 200          # points along a wake line for its distance field [-]


def is_unedited(case, document) -> bool:
    """True if the document is just the template's own geometry (then the template mesher is used)."""
    if document is None:
        return True
    template = template_document(case)
    return document.is_template_only() and document.to_dict()["operations"] == template.to_dict()["operations"]


def mesh_for(case, params, document=None, folder=None):
    """The mesh of a template for these inputs and (optional) workspace geometry; see the module text."""
    if is_unedited(case, document):
        return case.build_mesh(params)
    if not hasattr(case, "workspace_settings"):
        raise ValueError(f"The template '{case.title}' cannot mesh a workspace geometry.")
    if "grid_preset" in params and str(params.get("mesh_type", "")).startswith("Structured"):
        raise ValueError("A structured C/O-grid follows the template's own shape, so it cannot mesh geometry edited in the "
                         "workspace. Set the mesh type to Unstructured (Gmsh), or remove the workspace edits.")
    return workspace_mesh(document, ReplayContext(case, params, folder),
                          lambda built: case.workspace_settings(params, built))


def estimate_cells(built, settings) -> int:
    """Rough number of cells (no Gmsh run): the fluid area in bands of growing cell size from the walls."""
    from aeroflowsim.gmsh_mesh import _band_cells, _inflation_cells
    area = sum(f.area for f in built.faces_with_role(FLUID))
    walls = [e for e in built.boundary_edges() if e in built.names and built.names[e].type == "wall"]
    perimeter = sum(built.edges[e].length for e in walls) or 0.25 * math.sqrt(max(area, 1e-300))
    cells = _band_cells(settings, lambda d: perimeter + 2.0 * math.pi * d, area)
    for region in built.regions:
        p = region.params
        region_area = {"box": lambda: (p["x1"] - p["x0"]) * (p["y1"] - p["y0"]),
                       "circle": lambda: math.pi * p["radius"] ** 2,
                       "wake": lambda: math.hypot(p["x1"] - p["x0"], p["y1"] - p["y0"]) * p["width"]}[region.shape]()
        cells += region_area / (TRIANGLE_AREA * min(region.size, settings.max_size) ** 2)
    cells += _inflation_cells(settings, perimeter)
    return int(round(cells))


# =============================================================================================
# The mesher
# =============================================================================================

def workspace_mesh(document, context, settings) -> Mesh:
    """Mesh of the fluid faces of a workspace geometry; patches = the boundary names (see the module text).

    settings: GmshSettings, or a function built -> GmshSettings (sizes that depend on the geometry).
    """
    with gmsh_session() as gmsh:
        kernel = Kernel(gmsh)
        run_operations(kernel, document, context)
        built = kernel.extract(triangulate=False)
        _check(built)
        if callable(settings):
            settings = settings(built)
        settings.check()
        estimate = estimate_cells(built, settings)
        if estimate > MAX_CELLS:
            raise ValueError(f"This mesh would have about {estimate:,.0f} cells (limit {MAX_CELLS:,}). Use larger cell "
                             "sizes.")
        _drop_solids(kernel)
        named = built                                # the names before the inflation cut changes the edges
        chains = _inflation_chains(built, kernel, settings)
        layers = []
        if chains:
            _size_fields(gmsh, kernel, built, settings, [])
            _set_options(gmsh, settings)
            gmsh.model.mesh.generate(1)
            for chain in chains:
                wall, segment_edges = _chain_nodes(gmsh, chain)
                chain.orient_fluid_right(wall, built)
                if chain.reversed:
                    wall, segment_edges = wall[::-1], segment_edges[::-1]
                inflation = settings.inflation
                grown = grow_layers(wall, chain.closed, inflation.first_height, inflation.n_layers, inflation.growth,
                                    chain.start_direction, chain.end_direction)
                layers.append((chain, grown, segment_edges))
            gmsh.model.mesh.clear()
            for chain, grown, _ in layers:
                _cut_layer_region(kernel, chain, grown, settings.inflation.thickness)
            built = kernel.extract(triangulate=False)
        top_curves = [t for t, m in kernel.edge_meta.items() if m.id.startswith(f"{LAYERS}:top")
                      and t in kernel.curve_tags()]
        sides = [m.id for t, m in kernel.edge_meta.items() if m.id.startswith(f"{LAYERS}:side")
                 and t in kernel.curve_tags()]
        if sides:
            raise ValueError("The inflation layers do not fit the geometry (their side meets the fluid boundary); "
                             "use fewer or thinner layers.")
        patch_types = {}
        tag_of = {m.id: t for t, m in kernel.edge_meta.items()}
        for name, (kind, edge_ids) in built.patches().items():
            tags = [tag_of[e] for e in edge_ids if e in tag_of and tag_of[e] not in top_curves]
            if tags:
                gmsh.model.addPhysicalGroup(1, tags, name=name)
                patch_types[name] = kind
        gmsh.model.addPhysicalGroup(2, kernel.faces_with_role(FLUID), name="fluid")
        for tag in top_curves:
            gmsh.model.mesh.setTransfiniteCurve(tag, 2)
        _round_far_field(gmsh, kernel, built, settings)
        _size_fields(gmsh, kernel, built, settings, top_curves)
        _set_options(gmsh, settings)
        try:
            gmsh.model.mesh.generate(2)
        except Exception as error:
            raise ValueError(f"Gmsh could not mesh this geometry: {error}. Try other cell sizes, or check the "
                             "geometry for very small features.") from None
        nodes, types, cells, boundary = _arrays(gmsh, patch_types)
    for chain, grown, segment_edges in layers:
        nodes, types, cells, boundary = _add_layers(nodes, types, cells, boundary, chain, grown, segment_edges, named)
    nodes, types, cells, boundary = _drop_unused_nodes(nodes, types, cells, boundary)
    if built.axisymmetric:
        nodes[:, 1] = np.maximum(nodes[:, 1], 0.0)                 # round-off just below the axis
    info = {"generator": "workspace", "axisymmetric": bool(built.axisymmetric),
            "operations": len(document.operations), "reference_length": float(built.reference_length()),
            **gmsh_settings(settings)}
    return Mesh.from_cells(nodes, types, cells, boundary, dim=2, axisymmetric=built.axisymmetric, info=info)


def _check(built):
    problems = built.errors() + [text for level, text in boundary_problems(built) if level == "error"]
    if not built.faces_with_role(FLUID):
        problems.append("There is no fluid face to mesh.")
    if problems:
        raise ValueError("The geometry cannot be meshed yet: " + " ".join(dict.fromkeys(problems)))


def _drop_solids(kernel):
    """Remove solid faces and curves that bound no fluid face (they are not meshed)."""
    model = kernel.gmsh.model
    solids = [t for t in kernel.face_tags() if kernel.face_meta[t].role != FLUID]
    if solids:
        kernel.occ.remove([(2, t) for t in solids])
        kernel.sync()
    loose = [(1, t) for t in kernel.curve_tags() if len(model.getAdjacencies(1, t)[0]) == 0]
    if loose:
        kernel.occ.remove(loose, recursive=True)
    kernel.remove_free_points()
    for t in solids:
        kernel.face_meta.pop(t, None)


# ---- size fields ------------------------------------------------------------------------------

def _round_far_field(gmsh, kernel, built, settings):
    """Far-field circle arcs get faces of at most 2 pi R / MIN_FARFIELD_FACES (as in gmsh_mesh.py), so a
    far-field circle stays round even when the largest cell size is big."""
    from aeroflowsim.gmsh_mesh import MIN_FARFIELD_FACES
    tag_of = {m.id: t for t, m in kernel.edge_meta.items()}
    live = set(kernel.curve_tags())
    for edge_id in built.boundary_edges():
        edge, b = built.edges[edge_id], built.names.get(edge_id)
        if b is None or b.type != "farfield" or edge.kind not in ("arc", "ellipse") or tag_of.get(edge_id) not in live:
            continue
        p = edge.points
        radius = _circumradius(p[0], p[len(p) // 2], p[-1])
        face = min(settings.max_size, 2.0 * math.pi * radius / MIN_FARFIELD_FACES)
        gmsh.model.mesh.setTransfiniteCurve(tag_of[edge_id], max(2, math.ceil(edge.length / face) + 1))


def _circumradius(a, b, c) -> float:
    """Radius of the circle through three points [m]."""
    ab, bc, ca = np.linalg.norm(b - a), np.linalg.norm(c - b), np.linalg.norm(a - c)
    area2 = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
    return ab * bc * ca / max(2.0 * area2, 1e-300)


def _size_fields(gmsh, kernel, built, settings, top_curves):
    """Background size field (see the module text); top_curves: tops of inflation layers (wall-like)."""
    field = gmsh.model.mesh.field
    tag_of = {m.id: t for t, m in kernel.edge_meta.items()}
    live = set(kernel.curve_tags())
    walls = [tag_of[e] for e in built.boundary_edges() if e in built.names and built.names[e].type == "wall"
             and e in tag_of and tag_of[e] in live]
    sources = sorted(set(walls) | set(top_curves))
    if not sources:                       # no walls: size the cells from every named boundary but the far field
        sources = [tag_of[e] for e in built.boundary_edges() if e in tag_of and e in built.names
                   and built.names[e].type != "farfield" and tag_of[e] in live]
    ramp = lambda h0: max((settings.max_size - h0) / (settings.growth - 1.0), 1e-300)
    fields = []

    def threshold(distance, h0, d0=0.0):
        t = field.add("Threshold")
        field.setNumber(t, "InField", distance)
        field.setNumber(t, "SizeMin", h0)
        field.setNumber(t, "SizeMax", settings.max_size)
        field.setNumber(t, "DistMin", d0)
        field.setNumber(t, "DistMax", d0 + ramp(h0))
        fields.append(t)

    if sources:
        length = sum(kernel.occ.getMass(1, c) for c in sources)
        d = field.add("Distance")
        field.setNumbers(d, "CurvesList", sources)
        field.setNumber(d, "Sampling", int(min(20000, max(4, 4.0 * length / settings.surface_size / len(sources)))))
        threshold(d, settings.surface_size)
    if settings.edge_refinement:
        corners = [v.xy for v in built.vertices.values() if v.corner and any(
            built.names.get(e) is not None and built.names[e].type == "wall" for e in v.edges)
            and _turn(built, v) > NOZZLE_CORNER_ANGLE]
        if corners:
            points = [kernel.occ.addPoint(x, y, 0.0) for x, y in corners]   # free points: distances only
            kernel.sync()
            d = field.add("Distance")
            field.setNumbers(d, "PointsList", points)
            threshold(d, settings.surface_size / EDGE_REFINEMENT)
    for region in built.regions:
        p, h = region.params, min(region.size, settings.max_size)
        if region.shape == "box":
            box = field.add("Box")
            for key, value in (("VIn", h), ("VOut", settings.max_size), ("XMin", p["x0"]), ("XMax", p["x1"]),
                               ("YMin", p["y0"]), ("YMax", p["y1"]), ("ZMin", -1.0), ("ZMax", 1.0),
                               ("Thickness", ramp(h))):
                field.setNumber(box, key, value)
            fields.append(box)
        elif region.shape == "circle":
            ball = field.add("Ball")
            for key, value in (("VIn", h), ("VOut", settings.max_size), ("XCenter", p["xc"]), ("YCenter", p["yc"]),
                               ("ZCenter", 0.0), ("Radius", p["radius"]), ("Thickness", ramp(h))):
                field.setNumber(ball, key, value)
            fields.append(ball)
        else:
            t = np.linspace(0.0, 1.0, WAKE_SAMPLES)
            points = [kernel.occ.addPoint(p["x0"] + s * (p["x1"] - p["x0"]), p["y0"] + s * (p["y1"] - p["y0"]), 0.0)
                      for s in t]
            kernel.sync()
            d = field.add("Distance")
            field.setNumbers(d, "PointsList", points)
            threshold(d, h, 0.5 * p["width"])
    if not fields:
        constant = field.add("MathEval")
        field.setString(constant, "F", repr(settings.max_size))
        fields.append(constant)
    smallest = field.add("Min")
    field.setNumbers(smallest, "FieldsList", fields)
    field.setAsBackgroundMesh(smallest)


def _turn(built, vertex):
    from aeroflowsim.geometry_model.kernel import turning_angle
    return turning_angle(built, vertex) if len(vertex.edges) == 2 else 180.0


# ---- inflation layers ------------------------------------------------------------------------------

class _Chain:
    """Consecutive edges of one fluid loop that get inflation layers."""

    def __init__(self, edges, tags, closed, face_tag, start=None, end=None):
        self.edges, self.tags, self.closed, self.face_tag = edges, tags, closed, face_tag
        self.start_neighbour, self.end_neighbour = start, end     # (edge id, tag) of the boundaries at the ends
        self.start_direction = self.end_direction = None
        self.reversed = False

    def orient_fluid_right(self, wall, built):
        """Decide the walking direction so that the fluid is on the right (as grow_layers needs)."""
        k = len(wall) // 2
        a, b = wall[k - 1] if k > 0 else wall[0], wall[k] if k > 0 else wall[1]
        t = (b - a) / max(np.linalg.norm(b - a), 1e-300)
        probe = 0.5 * (a + b) + np.array([t[1], -t[0]]) * 1e-6 * built.size
        face = next(f for f in built.faces.values() if f.id == self.face_id)
        inside = point_in_polygon(probe, built.loop_points(face.loops[0])) and not any(
            point_in_polygon(probe, built.loop_points(loop)) for loop in face.loops[1:])
        self.reversed = not inside
        if self.reversed:
            self.start_neighbour, self.end_neighbour = self.end_neighbour, self.start_neighbour
        if not self.closed:
            start, end = (wall[-1], wall[0]) if self.reversed else (wall[0], wall[-1])
            self.start_direction = _along(built, self.start_neighbour[0], start)
            self.end_direction = _along(built, self.end_neighbour[0], end)


def _along(built, edge_id, point):
    """Unit vector along a straight edge, from its end at `point` towards its other end."""
    edge = built.edges[edge_id]
    if edge.kind != "line":
        raise ValueError(f"Inflation layers must end on a straight boundary; '{edge_id}' "
                         f"({built.names.get(edge_id).name if edge_id in built.names else 'unnamed'}) is curved.")
    p = edge.points
    far = p[-1] if np.linalg.norm(p[0] - point) < np.linalg.norm(p[-1] - point) else p[0]
    d = far - point
    return d / max(np.linalg.norm(d), 1e-300)


def _wants_layers(boundary, settings) -> bool:
    if boundary is None or boundary.type != "wall":
        return False
    if boundary.origin == "default":
        return settings.inflation is not None          # the template's own walls follow its inflation input
    return boundary.inflation


def _inflation_chains(built, kernel, settings):
    """The chains of consecutive inflation walls in each fluid loop."""
    tag_of = {m.id: t for t, m in kernel.edge_meta.items()}
    face_tag = {m.id: t for t, m in kernel.face_meta.items()}
    chains = []
    for face in built.faces_with_role(FLUID):
        for loop in face.loops:
            flags = [_wants_layers(built.names.get(e), settings) for e in loop]
            if not any(flags):
                continue
            if settings.inflation is None:
                raise ValueError("Some walls are marked for inflation layers, but inflation is switched off in the "
                                 "mesh inputs (they give the layer sizes). Switch it on, or unmark the walls.")
            n = len(loop)
            if all(flags):
                chain = _Chain(list(loop), [tag_of[e] for e in loop], True, face_tag[face.id])
                chain.face_id = face.id
                chains.append(chain)
                continue
            start = next(k for k in range(n) if flags[k] and not flags[k - 1])
            k = start
            for _ in range(n):                         # walk once round the loop from a chain start
                if flags[k % n] and not flags[(k - 1) % n]:
                    run = []
                    j = k
                    while flags[j % n]:
                        run.append(loop[j % n])
                        j += 1
                    before, after = loop[(k - 1) % n], loop[j % n]
                    chain = _Chain(run, [tag_of[e] for e in run], False, face_tag[face.id],
                                   (before, tag_of[before]), (after, tag_of[after]))
                    chain.face_id = face.id
                    chains.append(chain)
                k += 1
    return chains


def _chain_nodes(gmsh, chain):
    """Mesh nodes along a chain of curves (in loop order) and, per segment, the edge id it lies on."""
    pts, owners = [], []
    model = gmsh.model
    previous_end = None
    for edge_id, curve in zip(chain.edges, chain.tags):
        start, end = [t for _, t in model.getBoundary([(1, curve)], oriented=False, combined=False)]
        _, coords, params = model.mesh.getNodes(1, curve, includeBoundary=False, returnParametricCoord=True)
        inner = np.asarray(coords, dtype=float).reshape(-1, 3)[np.argsort(params), :2]
        a = np.asarray(model.getValue(0, start, []))[:2]
        b = np.asarray(model.getValue(0, end, []))[:2]
        line = np.vstack([a, inner, b])
        if previous_end is not None and np.linalg.norm(line[-1] - previous_end) < np.linalg.norm(line[0] - previous_end):
            line = line[::-1]
        elif previous_end is None and len(chain.tags) > 1:
            nxt = [np.asarray(model.getValue(0, t, []))[:2] for _, t in
                   model.getBoundary([(1, chain.tags[1])], oriented=False, combined=False)]
            if min(np.linalg.norm(line[0] - q) for q in nxt) < min(np.linalg.norm(line[-1] - q) for q in nxt):
                line = line[::-1]
        pts.append(line if not pts else line[1:])
        owners += [edge_id] * (len(line) - 1)
        previous_end = line[-1]
    wall = np.vstack(pts)
    if chain.closed:
        wall = wall[:-1]                                   # the last point is the first one again
    return wall, owners


def _cut_layer_region(kernel, chain, layers, thickness):
    """Cut the region covered by the layers out of the fluid face (see INFLATION in the module text)."""
    top = layers.nodes[layers.top]
    if chain.closed:
        polygon = top
    else:
        wall_ids = _wall_node_ids(layers)
        wall = layers.nodes[wall_ids]
        out = []
        for k in range(len(wall)):                      # the wall pushed out of the fluid, so no slivers stay
            if k == 0:
                d = -np.asarray(chain.start_direction)
            elif k == len(wall) - 1:
                d = -np.asarray(chain.end_direction)
            else:
                t = wall[k + 1] - wall[k - 1]
                t = t / max(np.linalg.norm(t), 1e-300)
                d = -np.array([t[1], -t[0]])            # opposite to the flow side (the right)
            out.append(wall[k] + d * thickness)
        polygon = np.vstack([top, np.array(out)[::-1]])
        if count_self_intersections(polygon):
            polygon = np.vstack([top, wall[::-1]])      # tight curvature: no push-out (tiny slivers possible)
    points = [kernel.point(x, y) for x, y in polygon]
    lines = [kernel.line(points[k], points[(k + 1) % len(points)]) for k in range(len(points))]
    n_top = len(top) if chain.closed else len(top) - 1          # segments of the top of the layers
    for k, line in enumerate(lines):                             # named, so the cut's edges inherit these names
        kernel.name_edge(line, f"{LAYERS}:top{k}" if k < n_top else f"{LAYERS}:side{k}")
    region = kernel.occ.addPlaneSurface([kernel.occ.addCurveLoop(lines)])
    kernel.sync()
    fluid = [t for t in kernel.faces_with_role(FLUID)]
    kernel.boolean("subtract", fluid, [region], LAYERS, role=FLUID)
    kernel.remove_free_points()


def _wall_node_ids(layers):
    """Wall node numbers in order (the first node of each wall face, plus the last end)."""
    faces = layers.wall_faces
    return np.r_[faces[:, 0], faces[-1, 1]]


def _arrays(gmsh, patch_types):
    """Nodes, cells and boundary faces of the 2D mesh Gmsh made (as in gmsh_mesh._gmsh_arrays)."""
    tags, coords, _ = gmsh.model.mesh.getNodes()
    tags = np.asarray(tags, dtype=np.int64)
    xy = np.asarray(coords, dtype=float).reshape(-1, 3)[:, :2].copy()
    lookup = np.full(int(tags.max()) + 1, -1, dtype=np.int64)
    lookup[tags] = np.arange(len(tags))
    cells, types = [], []
    kinds, _, element_nodes = gmsh.model.mesh.getElements(2)
    for kind, node_tags in zip(kinds, element_nodes):
        node_tags = np.asarray(node_tags, dtype=np.int64)
        if kind == 2:
            tri = lookup[node_tags.reshape(-1, 3)]
            cells.append(np.column_stack([tri, np.full(len(tri), -1)]))
            types.append(np.full(len(tri), TRIANGLE))
        elif kind == 3:
            cells.append(lookup[node_tags.reshape(-1, 4)])
            types.append(np.full(len(cells[-1]), QUAD))
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
        if faces:
            boundary[name] = (patch_types[name], np.vstack(faces))
    return xy, types, cells, boundary


def _add_layers(nodes, types, cells, boundary, chain, layers, segment_edges, built):
    """Add one chain's layer cells; its wall faces go to the walls' patches, its end faces to the neighbours'."""
    top = layers.nodes[layers.top]
    size = built.size
    index = np.full(len(layers.nodes), -1, dtype=np.int64)
    for k, p in zip(layers.top, top):                  # layer-top nodes are Gmsh's nodes at the same place
        d = np.linalg.norm(nodes - p, axis=1)
        j = int(d.argmin())
        if d[j] > 1e-9 * size:
            raise ValueError("The top of the inflation layers does not match Gmsh's nodes; try another first-layer "
                             "height or fewer layers.")
        index[k] = j
    new = np.flatnonzero(index < 0)
    index[new] = len(nodes) + np.arange(len(new))
    nodes = np.vstack([nodes, layers.nodes[new]])
    cells = np.vstack([cells, np.where(layers.cells >= 0, index[np.maximum(layers.cells, 0)], -1)])
    types = np.concatenate([types, layers.cell_types])
    boundary = dict(boundary)
    if len(segment_edges) != len(layers.wall_faces):
        raise ValueError("Internal error: the inflation-layer wall faces do not match the wall segments.")
    for edge_id, face in zip(segment_edges, layers.wall_faces):
        b = built.names[edge_id] if edge_id in built.names else None
        name, kind = (b.name, b.type) if b else ("wall", "wall")
        t, existing = boundary.get(name, (kind, np.zeros((0, 2), dtype=np.int64)))
        boundary[name] = (t, np.vstack([existing, index[face][None, :]]))
    if not chain.closed:
        for neighbour, faces in ((chain.start_neighbour, layers.start_faces), (chain.end_neighbour, layers.end_faces)):
            b = built.names.get(neighbour[0])
            name, kind = (b.name, b.type) if b else ("wall", "wall")
            t, existing = boundary.get(name, (kind, np.zeros((0, 2), dtype=np.int64)))
            boundary[name] = (t, np.vstack([existing, index[faces]]))
    return nodes, types, cells, boundary

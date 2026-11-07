# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""3D meshes of a 3D workspace geometry: Gmsh tetrahedra + prism inflation layers; patches = the face names.

mesh_3d(document, context, settings) is called by workspace_mesh.mesh_for() for a 3D document (the
GUI's helper process, the command line and scripts all go through mesh_for). In plain words:

  1. Replay the history in OpenCASCADE (kernel3d.py, the same replay the Geometry step shows) and
     refuse with a clear message if a step failed, there is no fluid body, or a boundary face of the
     fluid has no name. Solid bodies are removed (only the fluid is meshed).
  2. Cell sizes (Gmsh "size fields", combined with Min), as in 2D:
        walls          h(d) = min(h_max, h_wall + (growth - 1) d)    (d = distance from the wall faces)
        curvature      Gmsh's curvature rule: CURVATURE elements per full circle on curved faces
        box / sphere   at most the region's size inside, growing at the same rate outside it
        cylinder       a row of spheres along the axis (a capsule), each as above
  3. Gmsh meshes the surfaces (triangles, Frontal-Delaunay).
  4. Inflation (prism layers) on the wall faces marked for it (aeroflowsim/prism_layers.py):
        a) the wall triangles are oriented into the fluid and the layers are grown from them;
        b) the wall faces' triangles in Gmsh are REPLACED by the top triangles of the layers, so the
           tetrahedra will start at the top of the layers;
        c) a flat boundary next to the wall (symmetry plane, inlet, outlet) is meshed again in its plane
           with its edge at the top of the layers (the layers' side quads fill the strip in between).
  5. Gmsh fills the volume with tetrahedra (Delaunay, the reproducible serial algorithm) and the
     prisms and tetrahedra become one face-based Mesh (aeroflowsim/mesh.py): VTK cell types 10
     (tetrahedron) and 13 (wedge), patches = the boundary names of the workspace.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from aeroflowsim.geometry_model.built3d import FLUID
from aeroflowsim.geometry_model.document import run_operations
from aeroflowsim.geometry_model.kernel import gmsh_session
from aeroflowsim.geometry_model.kernel3d import Kernel3D
from aeroflowsim.mesh import TETRA, WEDGE, Mesh
from aeroflowsim.nozzle_mesh import Inflation
from aeroflowsim.prism_layers import boundary_edges, grow_prisms, triangle_normals

MAX_CELLS_3D = 3_000_000       # refuse to start Gmsh above this estimate [-]
TET_VOLUME = 1.0 / (6.0 * math.sqrt(2.0))   # volume of a regular tetrahedron with edges 1 [-]
TRIANGLE_AREA = math.sqrt(3.0) / 4.0        # area of an equilateral triangle with sides 1 [-]
PLANAR_TOLERANCE = 1e-6        # a boundary is flat if its triangle normals differ by less than this [-]
GMSH_TRIANGLE, GMSH_TETRA = 2, 4             # Gmsh element type numbers (first order)
CAPSULE_SPACING = 0.5          # spheres of a cylinder refinement region, this many radii apart [-]
MIN_SIZE_FRACTION = 0.1        # no cell smaller than this x the smallest requested size (curvature at a sharp tip,
                               # e.g. a cone's apex, would otherwise ask for cells of size 0) [-]


@dataclass
class MeshSettings3D:
    """How a 3D workspace geometry is meshed (all lengths in metres)."""

    surface_size: float               # cell size on the walls [m]
    max_size: float                   # largest cell size (far field) [m]
    growth: float = 1.2               # size growth per cell away from the walls [-] (> 1)
    curvature: int = 0                # curved faces: at least this many cells per full circle (0 = off) [-]
    inflation: Inflation | None = None   # prism layers on the walls, or None
    msh_path: Path | None = None      # (unused in 3D; kept so the settings look like GmshSettings)

    def check(self):
        if not (self.surface_size > 0.0 and self.max_size >= self.surface_size):
            raise ValueError("The cell sizes must be positive, and the largest (far-field) size at least the "
                             "surface size.")
        if self.growth <= 1.0:
            raise ValueError("The growth rate must be larger than 1.")
        if self.curvature < 0:
            raise ValueError("The cells per circle on curved faces cannot be negative.")

    def size_at(self, distance):
        """The wanted cell size [m] at `distance` [m] from the walls (the size field rule)."""
        return np.minimum(self.max_size, self.surface_size + (self.growth - 1.0) * np.asarray(distance))


def settings_info(settings) -> dict:
    """The settings as plain numbers for Mesh.info (shown in the GUI and stored with the mesh)."""
    info = {"surface_size": settings.surface_size, "max_size": settings.max_size, "growth": settings.growth,
            "curvature": settings.curvature, "inflation": settings.inflation is not None}
    if settings.inflation is not None:
        info.update(first_layer_height=settings.inflation.first_height, n_layers=settings.inflation.n_layers,
                    layer_growth=settings.inflation.growth, inflation_thickness=settings.inflation.thickness)
    return info


def wants_layers(boundary, settings) -> bool:
    """True if prism layers grow from a face with this name (as in 2D: walls; a template's own walls follow
    its inflation input, a user's name its own inflation tick)."""
    if boundary is None or boundary.type != "wall" or settings.inflation is None:
        return False
    return True if boundary.origin == "default" else bool(boundary.inflation)


def check_3d(built):
    """Refuse a geometry that cannot be meshed yet, with every reason at once."""
    problems = list(built.errors())
    if not built.bodies_with_role(FLUID):
        problems.append("There is no fluid body to mesh (put an enclosure around the solid bodies, or mark a body "
                        "as fluid).")
    unnamed = [f for f in built.boundary_faces() if f not in built.names]
    if unnamed:
        problems.append(f"{len(unnamed)} boundary face(s) of the fluid have no name: {', '.join(unnamed[:6])}"
                        f"{' ...' if len(unnamed) > 6 else ''}. Name them in the Boundaries tab.")
    if problems:
        raise ValueError("The geometry cannot be meshed yet: " + " ".join(dict.fromkeys(problems)))


def estimate_cells_3d(built, settings) -> int:
    """Rough number of cells (no Gmsh run): the fluid volume in shells of growing cell size around the walls,
    plus the refinement regions and the prism layers."""
    volume = built.fluid_volume()
    walls = [f for f in built.boundary_faces() if f in built.names and built.names[f].type == "wall"]
    area = sum(built.faces[f].area for f in walls) or volume ** (2.0 / 3.0)
    radius = math.sqrt(area / (4.0 * math.pi))      # the walls as a sphere of the same area [m]
    cells, filled, d = 0.0, 0.0, 0.0
    step = settings.surface_size
    while filled < volume and d < 1e3 * built.size:
        shell = min(4.0 * math.pi * (radius + d) ** 2 * step, volume - filled)
        cells += shell / (TET_VOLUME * float(settings.size_at(d)) ** 3)
        filled += shell
        d += step
        step = max(step, float(settings.size_at(d)))
    for region in built.regions:
        p = region.params
        region_volume = {"box": lambda: (p["x1"] - p["x0"]) * (p["y1"] - p["y0"]) * (p["z1"] - p["z0"]),
                         "sphere": lambda: 4.0 / 3.0 * math.pi * p["radius"] ** 3,
                         "cylinder": lambda: math.pi * p["radius"] ** 2 * math.dist(
                             (p["x0"], p["y0"], p["z0"]), (p["x1"], p["y1"], p["z1"]))}[region.shape]()
        cells += min(region_volume, volume) / (TET_VOLUME * min(region.size, settings.max_size) ** 3)
    if settings.inflation is not None:
        cells += 2.0 * settings.inflation.n_layers * area / (TRIANGLE_AREA * settings.surface_size ** 2)
    return int(round(cells))


# =============================================================================================
# The mesher
# =============================================================================================

def mesh_3d(document, context, settings) -> Mesh:
    """Tetrahedra + prism layers of the fluid bodies of a 3D workspace geometry (see the module text).

    settings: MeshSettings3D, or a function built -> MeshSettings3D (sizes that depend on the geometry).
    """
    with gmsh_session() as gmsh:
        kernel = Kernel3D(gmsh)
        run_operations(kernel, document, context)
        built = kernel.extract(triangulate=False)
        check_3d(built)
        if callable(settings):
            settings = settings(built)
        settings.check()
        estimate = estimate_cells_3d(built, settings)
        if estimate > MAX_CELLS_3D:
            raise ValueError(f"This mesh would have about {estimate:,.0f} cells (limit {MAX_CELLS_3D:,}). Use larger "
                             "cell sizes.")
        fluid = kernel.bodies_with_role(FLUID)
        _drop_solids(kernel, fluid)
        surfaces = {}                                   # {surface tag: (face id, Boundary)} of the fluid's boundary
        boundary_ids = set(built.boundary_faces())
        for tag in kernel.face_tags():
            face_id = kernel.face_meta[tag].id if tag in kernel.face_meta else None
            if face_id in boundary_ids:
                surfaces[tag] = (face_id, built.names[face_id])
        walls = [t for t, (_, b) in surfaces.items() if b.type == "wall"]
        layer_walls = [t for t, (_, b) in surfaces.items() if wants_layers(b, settings)]
        _size_fields(gmsh, kernel, built, settings, walls)
        _options(gmsh, settings, min([settings.surface_size] + [r.size for r in built.regions]))
        try:
            gmsh.model.mesh.generate(2)
        except Exception as error:
            raise ValueError(f"Gmsh could not mesh the surfaces: {error}. Try other cell sizes, or check the geometry "
                             "for very small features.") from None
        layers = _inflate(gmsh, kernel, fluid, surfaces, layer_walls, settings) if layer_walls else None
        try:
            gmsh.model.mesh.generate(3)
        except Exception as error:
            raise ValueError(f"Gmsh could not fill the volume with tetrahedra: {error}. Try other cell sizes"
                             f"{' or thinner inflation layers' if layers else ''}.") from None
        nodes, types, cells, boundary = _arrays(gmsh, fluid, surfaces, layers)
        zone_of_volume = {v: (kernel.body_meta[v].zone if v in kernel.body_meta else "") for v in fluid}
        zoned = any(zone_of_volume.values())           # only a Fluid zones operation makes zones
        zone_of_volume = {v: z or "fluid" for v, z in zone_of_volume.items()}
        tet_counts = [len(gmsh.model.mesh.getElementsByType(GMSH_TETRA, v)[1]) // 4 for v in fluid]
        excluded = list(getattr(kernel, "zone_excluded", []))
    info = {"generator": "workspace 3D (Gmsh tetrahedra" + (" + prism layers)" if layers else ")"),
            "operations": len(document.operations), "reference_length": float(built.reference_length()),
            "fluid_volume_exact": float(built.fluid_volume()), **settings_info(settings)}
    mesh = Mesh.from_cells(nodes, types, cells, boundary, dim=3, info=info)
    if not zoned or len(set(zone_of_volume.values())) < 2:
        return mesh                                     # one zone: exactly the mesh as before
    return exclude(with_zones(mesh, [zone_of_volume[v] for v in fluid], tet_counts), excluded)


def exclude(mesh, excluded) -> Mesh:
    """The mesh without its excluded ("solid / excluded") zones (mesh.remove_zones, one wall patch per zone)."""
    from aeroflowsim.mesh import remove_zones
    for zone in [z for z in excluded if z in mesh.cell_zones]:
        mesh = remove_zones(mesh, zone)
    return mesh


def with_zones(mesh, volume_zones, tet_counts) -> Mesh:
    """The mesh with its cell zones: the tetrahedra come first, volume after volume (tet_counts), so each block gets
    the zone of its volume; every other cell (the prism layers, which follow) gets the zone of the cell it touches
    through its faces (a prism stack grows from a wall into one zone), found by passing zones across interior faces
    until every cell has one."""
    zone = np.full(mesh.n_cells, -1, dtype=np.int64)
    names = list(dict.fromkeys(volume_zones))
    start = 0
    for name, n in zip(volume_zones, tet_counts):
        zone[start:start + n] = names.index(name)
        start += n
    nI = mesh.n_interior_faces
    own, nb = mesh.owner[:nI], mesh.neighbour[:nI]
    while np.any(zone < 0):
        before = int(np.count_nonzero(zone < 0))
        take = (zone[own] < 0) & (zone[nb] >= 0)
        zone[own[take]] = zone[nb[take]]
        take = (zone[nb] < 0) & (zone[own] >= 0)
        zone[nb[take]] = zone[own[take]]
        if int(np.count_nonzero(zone < 0)) == before:
            zone[zone < 0] = 0                           # cells cut off from every volume (cannot happen): zone 1
    cells = {n: np.flatnonzero(zone == k) for k, n in enumerate(names)}
    return Mesh(mesh.nodes, mesh.cell_types, mesh.cell_nodes, mesh.face_nodes, mesh.owner, mesh.neighbour,
                mesh.patches, mesh.dim, mesh.axisymmetric, mesh.info, cell_zones=cells)


def _drop_solids(kernel, fluid):
    """Remove the solid bodies (only the fluid is meshed); faces they share with the fluid stay."""
    model = kernel.gmsh.model
    fluid_faces = {f for v in fluid for f in kernel.faces_of(v)}
    for tag in [t for t in kernel.volume_tags() if t not in fluid]:
        shared = set(kernel.faces_of(tag)) & fluid_faces
        kernel.occ.remove([(3, tag)], recursive=not shared)
        kernel.body_meta.pop(tag, None)
    kernel.sync()
    loose = [(2, t) for t in kernel.face_tags() if len(model.getAdjacencies(2, t)[0]) == 0]
    if loose:
        kernel.occ.remove(loose, recursive=True)
        kernel.sync()


def _options(gmsh, settings, smallest):
    """Gmsh options: sizes from the size fields and the curvature rule, never below MIN_SIZE_FRACTION x smallest [m]."""
    for option, value in (("General.Terminal", 0), ("Mesh.MeshSizeExtendFromBoundary", 0),
                          ("Mesh.MeshSizeFromPoints", 0), ("Mesh.MeshSizeFromCurvature", int(settings.curvature)),
                          ("Mesh.MeshSizeMax", settings.max_size), ("Mesh.MeshSizeMin", MIN_SIZE_FRACTION * smallest),
                          ("Mesh.ElementOrder", 1), ("Mesh.Algorithm", 6), ("Mesh.Algorithm3D", 1),
                          ("Mesh.RecombineAll", 0), ("Mesh.Optimize", 1), ("General.NumThreads", 1),
                          ("Mesh.Renumber", 0)):         # keep node numbers (the layer nodes refer to them)
        gmsh.option.setNumber(option, value)


def _size_fields(gmsh, kernel, built, settings, walls):
    """The size fields of the module text, combined with Min."""
    field = gmsh.model.mesh.field
    ramp = (settings.max_size - settings.surface_size) / (settings.growth - 1.0)   # distance to reach h_max [m]
    fields = []
    if walls:
        d = field.add("Distance")
        field.setNumbers(d, "SurfacesList", walls)
        field.setNumber(d, "Sampling", 40)
        t = field.add("Threshold")
        field.setNumber(t, "InField", d)
        for key, value in (("SizeMin", settings.surface_size), ("SizeMax", settings.max_size), ("DistMin", 0.0),
                           ("DistMax", ramp)):
            field.setNumber(t, key, value)
        fields.append(t)
    for region in built.regions:
        p = region.params
        size = min(region.size, settings.max_size)
        thickness = (settings.max_size - size) / (settings.growth - 1.0)
        if region.shape == "box":
            f = field.add("Box")
            for key in ("x0", "y0", "z0", "x1", "y1", "z1"):             # x0 -> XMin, x1 -> XMax ...
                field.setNumber(f, key[0].upper() + ("Min" if key[1] == "0" else "Max"), p[key])
            for key, value in (("VIn", size), ("VOut", settings.max_size), ("Thickness", thickness)):
                field.setNumber(f, key, value)
            fields.append(f)
            continue
        if region.shape == "sphere":
            centres = [(p["xc"], p["yc"], p["zc"])]
        else:                                      # a cylinder: a row of spheres along the axis (a capsule)
            a, b = np.array([p["x0"], p["y0"], p["z0"]]), np.array([p["x1"], p["y1"], p["z1"]])
            n = max(1, int(math.ceil(np.linalg.norm(b - a) / (CAPSULE_SPACING * p["radius"]))))
            centres = [tuple(a + (b - a) * k / n) for k in range(n + 1)]
        for c in centres:
            f = field.add("Ball")
            for key, value in (("XCenter", c[0]), ("YCenter", c[1]), ("ZCenter", c[2]), ("Radius", p["radius"]),
                               ("VIn", size), ("VOut", settings.max_size), ("Thickness", thickness)):
                field.setNumber(f, key, value)
            fields.append(f)
    for edge_ids, size, op_id in getattr(kernel, "edge_sizes", []):   # local sizes along picked edges
        try:
            curves = kernel.curve_tags(edge_ids)
        except ValueError:
            continue                                    # edges removed by the solid / fluid clean-up
        d = field.add("Distance")
        field.setNumbers(d, "CurvesList", curves)
        field.setNumber(d, "Sampling", 60)
        t = field.add("Threshold")
        field.setNumber(t, "InField", d)
        h = min(size, settings.max_size)
        for key, value in (("SizeMin", h), ("SizeMax", settings.max_size), ("DistMin", 0.0),
                           ("DistMax", (settings.max_size - h) / (settings.growth - 1.0))):
            field.setNumber(t, key, value)
        fields.append(t)
    for zone, size in getattr(kernel, "zone_sizes", {}).items():     # a constant size inside a cell zone
        volumes = [v for v in kernel.volume_tags() if v in kernel.body_meta and kernel.body_meta[v].zone == zone]
        if volumes:
            f = field.add("Constant")
            field.setNumber(f, "VIn", min(size, settings.max_size))
            field.setNumber(f, "VOut", settings.max_size)
            field.setNumbers(f, "VolumesList", volumes)
            fields.append(f)
    if not fields:
        f = field.add("MathEval")
        field.setString(f, "F", f"{settings.max_size!r}")
        fields.append(f)
    m = field.add("Min")
    field.setNumbers(m, "FieldsList", fields)
    field.setAsBackgroundMesh(m)


# =============================================================================================
# Inflation (step 4 of the module text)
# =============================================================================================

@dataclass
class _Layers:
    nodes: dict                # {node tag: (3,) [m]} of every node the cells use that Gmsh no longer has
    prisms: np.ndarray         # (P, 6) node tags
    wall_faces: dict           # {surface tag: (T, 3) node tags} the wall triangles (the wall patches' faces)
    side_faces: dict           # {surface tag: (Q, 4) node tags} the layers' side quads on a neighbouring boundary


def _surface_triangles(gmsh, tag) -> np.ndarray:
    _, nodes = gmsh.model.mesh.getElementsByType(GMSH_TRIANGLE, tag)
    return np.asarray(nodes, dtype=np.int64).reshape(-1, 3)


def _inflate(gmsh, kernel, fluid, surfaces, layer_walls, settings) -> _Layers:
    """Grow the prism layers and give Gmsh the top of the layers as the walls' surface mesh (see the module text)."""
    model = gmsh.model
    tags, coords, _ = model.mesh.getNodes()
    tags = np.asarray(tags, dtype=np.int64)
    xyz = np.asarray(coords, dtype=float).reshape(-1, 3)
    row = np.full(int(tags.max()) + 1, -1, dtype=np.int64)
    row[tags] = np.arange(len(tags))
    triangles = {t: _surface_triangles(gmsh, t) for t in surfaces}

    # a) the wall triangles, every surface turned so its normals point into the fluid
    wall_faces = {}
    for t in layer_walls:
        tri = triangles[t]
        if not _points_into_fluid(model, fluid, xyz[row[tri]], settings):
            tri = tri[:, [0, 2, 1]]
        wall_faces[t] = tri
    wall = np.vstack(list(wall_faces.values()))
    # the edge of the wall: where it meets other boundaries, the columns stay in their (flat) planes
    edge_nodes = np.unique(boundary_edges(row[wall])) if len(wall) else np.zeros(0, dtype=np.int64)
    neighbours = {}                                   # {surface tag: unit normal} of the flat neighbouring boundaries
    planes = {}
    on_surface = {}
    for t, tri in triangles.items():
        if t in wall_faces:
            continue
        for n in np.unique(row[tri]).tolist():
            on_surface.setdefault(n, []).append(t)
    for n in edge_nodes.tolist():
        for t in on_surface.get(n, []):
            if t not in neighbours:
                neighbours[t] = _plane_normal(xyz, row[triangles[t]], surfaces[t])
            planes.setdefault(n, []).append(neighbours[t])
    inflation = settings.inflation
    grown = grow_prisms(xyz, row[wall], inflation.first_height, inflation.n_layers, inflation.growth, planes)

    # node tags for the new nodes: the inner layers first, the top layer last (Gmsh numbers its own new nodes
    # after the largest tag it knows, which is then a top node, so tags never collide)
    first = int(tags.max()) + 1
    n_new = len(grown.nodes)
    tag_of_row = np.concatenate([tags, np.zeros(n_new, dtype=np.int64)])
    top_rows = np.unique(grown.columns[:, -1])
    inner_rows = np.setdiff1d(np.arange(len(xyz), len(xyz) + n_new), top_rows)
    tag_of_row[inner_rows] = first + np.arange(len(inner_rows))
    tag_of_row[top_rows] = first + len(inner_rows) + np.arange(len(top_rows))
    all_xyz = np.vstack([xyz, grown.nodes])

    # b) the walls' surface mesh becomes the top of the layers
    keep = {int(tg): all_xyz[r] for r, tg in enumerate(tag_of_row)}  # every node (Gmsh forgets the cleared ones)
    model.mesh.clear([(2, t) for t in wall_faces])
    added = set()
    top_tris = tag_of_row[grown.top]
    start = 0
    for t, tri in wall_faces.items():
        part = top_tris[start:start + len(tri)]
        start += len(tri)
        fresh = [int(n) for n in np.unique(part) if int(n) not in added]
        added.update(fresh)
        model.mesh.addNodes(2, t, fresh, np.vstack([keep[n] for n in fresh]).ravel().tolist() if fresh else [])
        model.mesh.addElementsByType(t, GMSH_TRIANGLE, [], part.ravel().tolist())

    # c) every flat neighbouring boundary is meshed again with its edge at the top of the layers
    top_of = {int(r): int(c) for r, c in zip(grown.wall_nodes, grown.columns[:, -1])}   # wall row -> top row
    side_faces = {t: [] for t in neighbours}
    for (a, b), quads in grown.side_quads.items():
        owner = [t for t in neighbours if t in on_surface.get(a, []) and t in on_surface.get(b, [])]
        if not owner:
            raise ValueError("The edge of an inflation wall does not lie on a neighbouring boundary.")
        side_faces[owner[0]].append(tag_of_row[quads])
    next_tag = int(max(tag_of_row.max(), model.mesh.getMaxNodeTag())) + 1
    for t, normal in neighbours.items():
        rows = row[triangles[t]]
        new_tris, new_nodes, next_tag = _remesh_plane(gmsh, all_xyz, rows, top_of, normal, next_tag, tag_of_row)
        model.mesh.clear([(2, t)])
        fresh = [n for n in new_nodes if n not in added]
        if fresh:
            model.mesh.addNodes(2, t, fresh, np.vstack([new_nodes[n] for n in fresh]).ravel().tolist())
        added.update(fresh)
        # (its edge nodes are on its curves, which Gmsh keeps, or top nodes, which were added above)
        model.mesh.addElementsByType(t, GMSH_TRIANGLE, [], new_tris.ravel().tolist())
        keep.update(new_nodes)
    prisms = tag_of_row[grown.prisms]
    return _Layers(keep, prisms, {t: tag_of_row[row[tri]] for t, tri in wall_faces.items()},
                   {t: np.vstack(q) for t, q in side_faces.items() if q})


def _points_into_fluid(model, fluid, tri_xyz, settings) -> bool:
    """True if the triangles' normals (right-hand rule) point into the fluid (tested on the largest triangle)."""
    a, b, c = tri_xyz[:, 0], tri_xyz[:, 1], tri_xyz[:, 2]
    cross = np.cross(b - a, c - a)
    k = int(np.argmax(np.linalg.norm(cross, axis=1)))
    n = cross[k] / np.linalg.norm(cross[k])
    centre = (a[k] + b[k] + c[k]) / 3.0
    step = 0.25 * float(np.linalg.norm(b[k] - a[k]))
    inside = lambda p: any(model.isInside(3, v, list(p)) for v in fluid)
    return bool(inside(centre + step * n) or not inside(centre - step * n))


def _plane_normal(xyz, tri_rows, surface) -> np.ndarray:
    """The unit normal of a boundary next to an inflation wall; ValueError if the boundary is not flat."""
    normals = triangle_normals(xyz, tri_rows)
    mean = normals[0]
    deviation = np.linalg.norm(np.cross(normals, mean), axis=1).max(initial=0.0)
    if deviation > PLANAR_TOLERANCE:
        face_id, boundary = surface
        raise ValueError(f"Inflation layers can end only on a flat boundary; the boundary '{boundary.name}' "
                         f"(face {face_id}) next to the inflation wall is curved. Name that face a wall with inflation "
                         "too, or switch the inflation off for the wall it touches.")
    return mean


def _remesh_plane(gmsh, xyz, rows, top_of, normal, next_tag, tag_of_row):
    """Triangles (node tags) of a flat boundary meshed again in its plane, its wall-edge nodes moved to the top of the
    layers. Returns (triangles (T, 3), {new node tag: xyz}, next free tag)."""
    loops = _loops(boundary_edges(rows))
    loops = [[top_of.get(n, n) for n in loop] for loop in loops]
    origin = xyz[loops[0][0]]
    e1 = xyz[loops[0][1]] - origin
    e1 = e1 - np.dot(e1, normal) * normal
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(normal, e1)
    uv = lambda r: ((xyz[r] - origin) @ e1, (xyz[r] - origin) @ e2)
    current = gmsh.model.getCurrent()
    gmsh.model.add("aeroflowsim_plane")
    try:
        geo = gmsh.model.geo
        point_of, curve_loops, lengths = {}, [], {}
        for loop in loops:
            pts = np.array([uv(r) for r in loop])
            seg = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
            for k, r in enumerate(loop):
                lengths[r] = 0.5 * (seg[k] + seg[k - 1])
        for loop in loops:
            for r in loop:
                if r not in point_of:
                    u, v = uv(r)
                    point_of[r] = geo.addPoint(u, v, 0.0, lengths[r])
            lines = [geo.addLine(point_of[a], point_of[b]) for a, b in zip(loop, loop[1:] + loop[:1])]
            curve_loops.append((geo.addCurveLoop(lines), lines, _area(np.array([uv(r) for r in loop]))))
        curve_loops.sort(key=lambda item: -abs(item[2]))           # the outer loop first, then the holes
        geo.addPlaneSurface([c for c, _, _ in curve_loops])
        geo.synchronize()
        for _, lines, _ in curve_loops:
            for line in lines:
                gmsh.model.mesh.setTransfiniteCurve(line, 2)        # exactly the given boundary nodes
        for option, value in (("Mesh.MeshSizeFromPoints", 1), ("Mesh.MeshSizeExtendFromBoundary", 1)):
            gmsh.option.setNumber(option, value)
        gmsh.model.mesh.generate(2)
        tags, coords, _ = gmsh.model.mesh.getNodes()
        tags = np.asarray(tags, dtype=np.int64)
        local = np.asarray(coords, dtype=float).reshape(-1, 3)
        node_of_point = {}
        for r, p in point_of.items():
            node_tags, _, _ = gmsh.model.mesh.getNodes(0, p)
            node_of_point[int(node_tags[0])] = int(tag_of_row[r])
        mapping, new_nodes = {}, {}
        for t, (u, v, _) in zip(tags.tolist(), local):
            if t in node_of_point:
                mapping[t] = node_of_point[t]
            else:
                mapping[t] = next_tag
                new_nodes[next_tag] = origin + u * e1 + v * e2
                next_tag += 1
        _, element_nodes = gmsh.model.mesh.getElementsByType(GMSH_TRIANGLE)
        tris = np.array([mapping[t] for t in np.asarray(element_nodes, dtype=np.int64).tolist()],
                        dtype=np.int64).reshape(-1, 3)
    finally:
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.model.remove()
        gmsh.model.setCurrent(current)
    return tris, new_nodes, next_tag


def _loops(edges) -> list:
    """Closed loops of node numbers from directed boundary edges (each node starts one edge)."""
    nxt = {int(a): int(b) for a, b in edges}
    loops, seen = [], set()
    for start in nxt:
        if start in seen:
            continue
        loop, n = [], start
        while n not in seen:
            seen.add(n)
            loop.append(n)
            n = nxt[n]
        loops.append(loop)
    return loops


def _area(pts) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


# =============================================================================================
# Reading the mesh
# =============================================================================================

def _arrays(gmsh, fluid, surfaces, layers):
    """Nodes, cell types, cells and patches {name: (type, faces)} of the finished mesh."""
    model = gmsh.model
    tags, coords, _ = model.mesh.getNodes()
    tags = np.asarray(tags, dtype=np.int64)
    known = dict(layers.nodes) if layers else {}
    known.update(zip(tags.tolist(), np.asarray(coords, dtype=float).reshape(-1, 3)))
    tets = [np.asarray(model.mesh.getElementsByType(GMSH_TETRA, v)[1], dtype=np.int64).reshape(-1, 4) for v in fluid]
    cells = [np.vstack(tets)] if tets else []
    types = [np.full(len(cells[0]), TETRA)] if cells else []
    if layers is not None:
        cells.append(layers.prisms)
        types.append(np.full(len(layers.prisms), WEDGE))
    if not cells or not sum(len(c) for c in cells):
        raise ValueError("Gmsh made no cells. Check the geometry and the cell sizes.")
    faces = {}
    for t, (_, b) in surfaces.items():
        if layers is not None and t in layers.wall_faces:
            tri = layers.wall_faces[t]
        else:
            tri = _surface_triangles(gmsh, t)
        rows = [np.column_stack([tri, np.full(len(tri), -1)])]
        if layers is not None and t in layers.side_faces:
            rows.append(layers.side_faces[t].reshape(-1, 4))
        name = b.name
        if name in faces:
            faces[name] = (faces[name][0], faces[name][1] + rows)
        else:
            faces[name] = (b.type, rows)
    # number the nodes the cells use 0, 1, 2 ...
    used = np.unique(np.concatenate([c[c >= 0] for c in cells]))
    nodes = np.vstack([known[int(t)] for t in used])
    index = np.full(int(used.max()) + 2, -1, dtype=np.int64)          # index[-1] stays -1 (padding)
    index[used] = np.arange(len(used))

    def lookup(a):
        return index[np.where(a >= 0, a, -1)]
    width = max(c.shape[1] for c in cells)
    cell_nodes = np.vstack([np.pad(lookup(c), ((0, 0), (0, width - c.shape[1])), constant_values=-1) for c in cells])
    boundary = {name: (kind, lookup(np.vstack(rows))) for name, (kind, rows) in faces.items()}
    return nodes, np.concatenate(types), cell_nodes, boundary

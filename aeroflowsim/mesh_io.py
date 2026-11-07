# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh import and export: Gmsh .msh (v2 and v4), SU2 .su2, CGNS (unstructured, 2D) and Fluent .msh (ASCII, import).

IMPORT in three steps, so a GUI or script can look at the file before it builds anything:

    raw = read_mesh_file(path)              the file as it is: points, cells and named groups of boundary edges (RawMesh)
    tag_table(raw)                          one row per boundary tag: name, edge count, guessed AeroFlowSim boundary type
    mesh = mesh_from_raw(raw, unit, axisymmetric, patch_types)    the face-based Mesh (aeroflowsim/mesh.py), quality
                                            checks run afterwards as for every mesh (aeroflowsim/checks.py)

2D meshes (triangles, quadrilaterals; tagged boundary edges) and, from Gmsh and SU2 files, 3D meshes (tetrahedra, pyramids,
prisms, hexahedra; tagged boundary triangles and quadrilaterals) are read; RawMesh.dim says which. Every boundary edge (2D) or
face (3D) must carry a tag; tagged edges or faces inside the mesh (internal zones) are ignored. CGNS and Fluent: 2D only.

EXPORT: write_gmsh (version 2.2 or 4.1, ASCII), write_su2, write_cgns (HDF5, boundary edges as BAR_2 sections named by
patch, plus a ZoneBC) take a Mesh; the patch names become the physical groups / markers / section names, so importing the
file again gives the same nodes, cells and patches (tested for every format).

Which library does what: Gmsh files are read with meshio (MIT licence: both versions, ASCII and binary, physical names);
meshio 5 cannot write tagged 2D meshes correctly (Gmsh v4 needs entity data, its SU2 writer fails, its CGNS writer produces
files it cannot read), so the writers, the SU2 / Fluent readers and the CGNS reader and writer (h5py) are written here.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from aeroflowsim.mesh import HEXAHEDRON, PATCH_TYPES, PYRAMID, QUAD, TETRA, TRIANGLE, WEDGE, Mesh

LENGTH_UNITS = {"m": 1.0, "mm": 1e-3, "cm": 1e-2, "in": 0.0254, "ft": 0.3048}      # file unit -> metres
FORMATS = {".msh": "Gmsh or Fluent .msh", ".su2": "SU2", ".cgns": "CGNS"}
NAME_HINTS = (("wall", "wall"), ("body", "wall"), ("airfoil", "wall"), ("surface", "wall"), ("nozzle", "wall"),
              ("symm", "symmetry"), ("sym", "symmetry"), ("axis", "axis"), ("inlet", "inlet"), ("inflow", "inlet"),
              ("outlet", "outlet"), ("outflow", "outlet"), ("exit", "outlet"), ("farfield", "farfield"),
              ("far_field", "farfield"), ("far-field", "farfield"), ("far", "farfield"), ("freestream", "farfield"),
              ("free_stream", "farfield"), ("infinity", "farfield"))
CGNS_BC = {"wall": "BCWall", "farfield": "BCFarfield", "inlet": "BCInflow", "outlet": "BCOutflow",
           "symmetry": "BCSymmetryPlane", "axis": "BCSymmetryPlane"}


@dataclass
class RawMesh:
    """A mesh file as it is: nothing converted yet (lengths in the file's unit, node numbers from 0)."""

    points: np.ndarray                                  # (N, 2) coordinates in the file's unit
    cells: list                                         # [(vtk cell type, (n, 3 or 4) node numbers)]
    groups: dict = field(default_factory=dict)          # {tag name: (m, 2) boundary edges (node numbers)}
    format: str = ""                                    # "Gmsh", "SU2", "CGNS", "Fluent"
    source: str = ""                                    # file name
    hints: dict = field(default_factory=dict)           # {tag name: boundary type read from the file, if it says}
    dim: int = 2                                        # 2, or 3: points (N, 3), groups (m, 4) faces (triangles: -1)
    zones: dict = field(default_factory=dict)           # {cell zone name: cell numbers in the order of `cells`}; only
                                                        # when the file has two or more cell zones (full 3D release)

    @property
    def n_cells(self) -> int:
        return sum(len(c) for _, c in self.cells)


def guess_patch_type(name, hint=None):
    """The AeroFlowSim boundary type a tag name suggests ("wall", "farfield", ...), or None if it says nothing."""
    if hint in PATCH_TYPES:
        return hint
    low = name.lower()
    for text, kind in NAME_HINTS:
        if text in low:
            return kind
    return None


# ---- reading ------------------------------------------------------------------------------------------------------

def read_mesh_file(path) -> RawMesh:
    """Read a mesh file by its extension (and, for .msh, its first characters). ValueError saying what is wrong."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Mesh file not found: {path}")
    ext = path.suffix.lower()
    if ext == ".su2":
        raw = read_su2(path)
    elif ext == ".cgns":
        raw = read_cgns(path)
    elif ext == ".msh":
        with open(path, "rb") as file:
            start = file.read(16).lstrip()
        raw = read_gmsh(path) if start.startswith(b"$") else read_fluent(path)
    else:
        raise ValueError(f"'{path.suffix}' is not a mesh format AeroFlowSim reads. Use {', '.join(FORMATS)} "
                         "(Gmsh .msh v2 / v4, SU2, CGNS, Fluent ASCII .msh).")
    raw.source = path.name
    return raw


def _flat_2d(points, source):
    """(N, 2) from (N, 2 or 3) points; ValueError if the mesh is really 3D."""
    points = np.asarray(points, dtype=float)
    if points.shape[1] == 3:
        size = max(float(np.ptp(points[:, :2])), 1e-300)
        if float(np.ptp(points[:, 2])) > 1e-9 * size:
            raise ValueError(f"{source} is a 3D mesh (the z coordinates differ). AeroFlowSim reads only 2D meshes now.")
        points = points[:, :2]
    return np.ascontiguousarray(points)


def read_gmsh(path) -> RawMesh:
    """Gmsh .msh version 2 or 4 (ASCII or binary) through meshio; physical names become the tags."""
    try:
        import meshio
    except ImportError:
        raise ValueError("Reading Gmsh files needs the meshio package: pip install meshio") from None
    try:
        m = meshio.read(str(path), file_format="gmsh")
    except Exception as error:
        raise ValueError(f"{Path(path).name} is not a Gmsh .msh file AeroFlowSim can read: {error}") from None
    if any(b.type in GMSH_VOLUME for b in m.cells):
        return _read_gmsh_3d(m, Path(path).name)
    names = {int(v[0]): k for k, v in m.field_data.items() if int(v[1]) == 1}
    zone_names = {int(v[0]): k for k, v in m.field_data.items() if int(v[1]) == 2}
    physical = m.cell_data.get("gmsh:physical")
    cells, groups, zone_tags = [], {}, []
    for k, block in enumerate(m.cells):
        if block.type in ("triangle", "quad"):
            cells.append((TRIANGLE if block.type == "triangle" else QUAD, np.asarray(block.data, dtype=np.int64)))
            zone_tags.append(physical[k] if physical is not None else np.zeros(len(block.data), dtype=int))
        elif block.type == "line":
            tags = physical[k] if physical is not None else np.zeros(len(block.data), dtype=int)
            for tag in np.unique(tags):
                name = names.get(int(tag), f"tag_{int(tag)}" if int(tag) else "untagged")
                groups.setdefault(name, []).append(np.asarray(block.data, dtype=np.int64)[tags == tag])
        elif block.type in ("vertex", "line3", "triangle6", "quad8", "quad9"):
            continue
        else:
            raise ValueError(f"{Path(path).name} contains {block.type} cells, which AeroFlowSim does not read (linear "
                             "triangles and quadrilaterals in 2D; tetrahedra, pyramids, prisms, hexahedra in 3D).")
    if not cells:
        raise ValueError(f"{Path(path).name} has no 2D cells (triangles or quadrilaterals).")
    return RawMesh(_flat_2d(m.points, Path(path).name), cells, {k: np.vstack(v) for k, v in groups.items()}, "Gmsh",
                   zones=_zones_of_tags(zone_tags, zone_names))


def _zones_of_tags(tags, names) -> dict:
    """{zone name: cell numbers} from the physical tag of every cell block ({} when all cells share one tag)."""
    if not tags:
        return {}
    tags = np.concatenate([np.asarray(t, dtype=np.int64) for t in tags])
    unique = np.unique(tags)
    if len(unique) < 2:
        return {}
    return {names.get(int(t), f"zone_{int(t)}"): np.flatnonzero(tags == t) for t in unique}


GMSH_VOLUME = {"tetra": TETRA, "pyramid": PYRAMID, "wedge": WEDGE, "hexahedron": HEXAHEDRON}   # meshio names


def _read_gmsh_3d(m, name) -> RawMesh:
    """The 3D part of read_gmsh: volume cells, and the tagged surface triangles / quadrilaterals as boundary faces.

    meshio returns the cells in VTK node order for these four types (it converts Gmsh's prism order; tested by a round
    trip through write_gmsh_3d), and mesh_from_raw still turns any inside-out cell round."""
    names = {int(v[0]): k for k, v in m.field_data.items() if int(v[1]) == 2}
    zone_names = {int(v[0]): k for k, v in m.field_data.items() if int(v[1]) == 3}
    physical = m.cell_data.get("gmsh:physical")
    cells, groups, zone_tags = [], {}, []
    for k, block in enumerate(m.cells):
        data = np.asarray(block.data, dtype=np.int64)
        if block.type in GMSH_VOLUME:
            cells.append((GMSH_VOLUME[block.type], data))
            zone_tags.append(physical[k] if physical is not None else np.zeros(len(data), dtype=int))
        elif block.type in ("triangle", "quad"):
            tags = physical[k] if physical is not None else np.zeros(len(data), dtype=int)
            faces = np.full((len(data), 4), -1, dtype=np.int64)
            faces[:, :data.shape[1]] = data
            for tag in np.unique(tags):
                tag_name = names.get(int(tag), f"tag_{int(tag)}" if int(tag) else "untagged")
                groups.setdefault(tag_name, []).append(faces[tags == tag])
        elif block.type in ("vertex", "line", "line3"):
            continue
        else:
            raise ValueError(f"{name} contains {block.type} cells (high-order or unknown). AeroFlowSim reads linear "
                             "tetrahedra, pyramids, prisms and hexahedra.")
    return RawMesh(np.asarray(m.points, dtype=float)[:, :3], cells, {k: np.vstack(v) for k, v in groups.items()},
                   "Gmsh", dim=3, zones=_zones_of_tags(zone_tags, zone_names))


def _clean_lines(path):
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("%")[0].strip()
        if line:
            yield line


def read_su2(path) -> RawMesh:
    """SU2 native .su2 (NDIME, NELEM, NPOIN, NMARK / MARKER_TAG / MARKER_ELEMS), 2D or 3D (SU2 uses VTK numbers and
    node orders, so the cells need no reordering). A multi-zone file (NZONE = n, one IZONE block each with its own
    points) becomes one mesh with n cell zones "zone_1", ...: points that coincide between zones (the conformal
    interface, tolerance 1e-9 of the mesh size) are merged, so the interface markers become interior faces."""
    lines = list(_clean_lines(path))
    name = Path(path).name
    starts = [k for k, line in enumerate(lines) if line.split("=", 1)[0].strip().upper() == "IZONE"]
    if not starts:
        return _read_su2_block(lines, name)
    blocks = [_read_su2_block(lines[a:b], name) for a, b in zip(starts, starts[1:] + [len(lines)])]
    text = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    named = [t.split(":", 1)[1].strip() for t in text if t.strip().lower().startswith("% zone:")]
    names = named if len(named) == len(blocks) and len(set(named)) == len(named) else         [f"zone_{k}" for k in range(1, len(blocks) + 1)]
    return _merge_zones(blocks, names, "SU2")


def _merge_zones(blocks, names, fmt) -> RawMesh:
    """One RawMesh with cell zones from several RawMeshes that touch at conformal interfaces (coincident points)."""
    dim = blocks[0].dim
    points = np.vstack([b.points for b in blocks])
    size = float(np.ptp(points, axis=0).max()) or 1.0
    keys = np.round(points / (1e-9 * size)).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.ravel()
    merged = points[first]
    cells, groups, zones, offset, count = [], {}, {}, 0, 0
    for block, zone in zip(blocks, names):
        renumber = inverse[offset:offset + len(block.points)]
        ids = []
        for kind, conn in block.cells:
            cells.append((kind, renumber[conn]))
            ids.append(np.arange(count, count + len(conn)))
            count += len(conn)
        zones[zone] = np.concatenate(ids)
        for tag, faces in block.groups.items():
            faces = np.where(faces >= 0, renumber[np.maximum(faces, 0)], -1)
            groups[tag] = np.vstack([groups[tag], faces]) if tag in groups else faces
        offset += len(block.points)
    return RawMesh(merged, cells, groups, fmt, dim=dim, zones=zones if len(zones) > 1 else {})


def _read_su2_block(lines, name) -> RawMesh:
    """One zone of an SU2 file (or the whole of a one-zone file)."""
    i, ndime, cells, points, groups = 0, 2, {}, None, {}

    def value(line):
        return line.split("=", 1)[1].split()

    while i < len(lines):
        line = lines[i]
        key = line.split("=", 1)[0].strip().upper()
        if key == "NDIME":
            ndime = int(value(line)[0])
            if ndime not in (2, 3):
                raise ValueError(f"{name}: NDIME = {ndime}; a mesh is 2D or 3D.")
        elif key == "NELEM":
            n = int(value(line)[0])
            allowed = SU2_CELLS[ndime]
            for row in lines[i + 1:i + 1 + n]:
                v = [int(x) for x in row.split()]
                if v[0] not in allowed:
                    kinds = ("triangles (5) and quadrilaterals (9)" if ndime == 2
                             else "tetrahedra (10), hexahedra (12), prisms (13) and pyramids (14)")
                    raise ValueError(f"{name} has an element of VTK type {v[0]}; in a {ndime}D mesh only {kinds} are read.")
                cells.setdefault(v[0], []).append(v[1:1 + SU2_NODES[v[0]]])
            i += n
        elif key == "NPOIN":
            n = int(value(line)[0])
            points = np.array([[float(x) for x in row.split()[:ndime]] for row in lines[i + 1:i + 1 + n]])
            i += n
        elif key == "MARKER_TAG":
            tag = value(line)[0]
            count = int(value(lines[i + 1])[0])
            rows = []
            boundary_types = (3,) if ndime == 2 else (5, 9)
            for row in lines[i + 2:i + 2 + count]:
                v = [int(x) for x in row.split()]
                if v[0] not in boundary_types:
                    raise ValueError(f"{name}: marker '{tag}' has an element of VTK type {v[0]}, not a boundary "
                                     f"{'line' if ndime == 2 else 'triangle or quadrilateral'}.")
                nodes = v[1:1 + SU2_NODES[v[0]]]
                rows.append(nodes if ndime == 2 else nodes + [-1] * (4 - len(nodes)))
            groups[tag] = np.array(rows, dtype=np.int64).reshape(-1, 2 if ndime == 2 else 4)
            i += 1 + count
        i += 1
    if points is None or not cells:
        raise ValueError(f"{name} is not a complete SU2 mesh (no points or no elements).")
    return RawMesh(points, [(t, np.array(c, dtype=np.int64)) for t, c in cells.items()], groups, "SU2", dim=ndime)


CELL_NODES = {TRIANGLE: 3, QUAD: 4, TETRA: 4, HEXAHEDRON: 8, WEDGE: 6, PYRAMID: 5}
SU2_CELLS = {2: (TRIANGLE, QUAD), 3: (TETRA, HEXAHEDRON, WEDGE, PYRAMID)}     # VTK numbers SU2 uses
SU2_NODES = {TRIANGLE: 3, QUAD: 4, TETRA: 4, HEXAHEDRON: 8, WEDGE: 6, PYRAMID: 5, 3: 2}


def read_fluent(path) -> RawMesh:
    """Fluent .msh, ASCII, 2D: nodes (10), cells (12), faces (13) with their zones, zone names (45).

    The cells' nodes are found from their faces. Zone type 3 is a wall, 2 is interior; every other boundary zone is a tag whose
    type the user chooses (the file's numbers are not trusted to mean the same in every writer)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    name = Path(path).name
    sections = re.findall(r"\((\d+)\s*\(([^()]*)\)\s*(?:\(([^()]*)\))?", text, flags=re.S)
    nodes, faces, zones, names, cell_zone_types, cell_ranges = [], [], {}, {}, {}, []
    n_dim = 2
    for code, head, body in sections:
        code = int(code)
        h = head.split()
        if code == 2:
            n_dim = int(h[0])
        elif code == 10 and body and int(h[0], 16) != 0:
            nodes.append((int(h[1], 16), np.array(body.split(), dtype=float).reshape(-1, int(h[4]) if len(h) > 4 else 2)))
        elif code == 13 and body and int(h[0], 16) != 0:
            zone, first, last, bctype, ftype = (int(x, 16) for x in h[:5])
            data = body.split()
            width = (4 if ftype == 2 else int(ftype) + 2) if ftype else None
            if ftype == 0:                              # mixed faces: every face starts with its node count
                rows, k = [], 0
                while k < len(data):
                    n = int(data[k], 16)
                    rows.append([int(x, 16) for x in data[k + 1:k + 1 + n + 2]])
                    k += n + 3
            else:
                rows = np.array([int(x, 16) for x in data], dtype=np.int64).reshape(-1, width).tolist()
            faces.append((zone, bctype, rows))
        elif code == 12 and int(h[0], 16) != 0:      # a cell zone: (12 (zone first last type element-type))
            cell_ranges.append((int(h[0], 16), int(h[1], 16), int(h[2], 16)))
        elif code == 45 and h:
            names[int(h[0])] = h[2] if len(h) > 2 else f"zone_{h[0]}"
    if n_dim != 2:
        raise ValueError(f"{name} is a {n_dim}D Fluent mesh. AeroFlowSim reads only 2D meshes now.")
    if not nodes or not faces:
        raise ValueError(f"{name} is not an ASCII Fluent mesh with nodes and faces (binary files are not read).")
    nodes.sort(key=lambda t: t[0])
    points = np.vstack([p for _, p in nodes])
    cell_faces, groups, hints = {}, {}, {}
    for zone, bctype, rows in faces:
        for row in rows:
            n0, n1, c0, c1 = row[0] - 1, row[1] - 1, row[2], row[3]
            for c in (c0, c1):
                if c > 0:
                    cell_faces.setdefault(c, []).append((n0, n1))
            if c0 == 0 or c1 == 0:
                if bctype == 2:
                    continue
                tag = names.get(zone, f"zone_{zone}")
                groups.setdefault(tag, []).append((n0, n1))
                if bctype == 3:
                    hints[tag] = "wall"
    cells, cell_ids = {TRIANGLE: [], QUAD: []}, {TRIANGLE: [], QUAD: []}
    for c in sorted(cell_faces):
        poly = _chain(cell_faces[c], name)
        if len(poly) not in (3, 4):
            raise ValueError(f"{name}: cell {c} has {len(poly)} corners; only triangles and quadrilaterals are read.")
        cells[TRIANGLE if len(poly) == 3 else QUAD].append(poly)
        cell_ids[TRIANGLE if len(poly) == 3 else QUAD].append(c)
    order = [t for t in (TRIANGLE, QUAD) if cells[t]]
    zone_of = {}                                       # Fluent cell id -> cell zone name (sections 12 and 45)
    for zone, first, last in cell_ranges:
        for c in range(first, last + 1):
            zone_of[c] = names.get(zone, f"zone_{zone}")
    ids = [c for t in order for c in cell_ids[t]]
    zones = {}
    if len(set(zone_of.values())) > 1:
        labels = np.array([zone_of.get(c, "fluid") for c in ids])
        zones = {z: np.flatnonzero(labels == z) for z in dict.fromkeys(labels.tolist())}
    return RawMesh(points, [(t, np.array(cells[t], dtype=np.int64)) for t in order],
                   {k: np.array(v, dtype=np.int64) for k, v in groups.items()}, "Fluent", hints=hints, zones=zones)


def _chain(edges, name):
    """The corner nodes of a cell from its edges (each edge as a node pair), in order round the cell."""
    nxt = {}
    for a, b in edges:
        nxt.setdefault(a, []).append(b)
        nxt.setdefault(b, []).append(a)
    start = edges[0][0]
    poly, previous, node = [start], None, start
    while True:
        options = [n for n in nxt[node] if n != previous]
        step = options[0] if options else nxt[node][0]
        if step == start:
            break
        poly.append(step)
        previous, node = node, step
        if len(poly) > len(edges) + 1:
            raise ValueError(f"{name}: a cell's faces do not form a closed loop.")
    return poly


# ---- CGNS (HDF5) --------------------------------------------------------------------------------------------------

CGNS_BAR, CGNS_TRI, CGNS_QUAD, CGNS_MIXED = 3, 5, 7, 20


def _text(node, key):
    value = node.attrs.get(key)
    return value.decode() if isinstance(value, (bytes, np.bytes_)) else ("" if value is None else str(value))


def _data(node):
    return np.asarray(node[" data"][()]) if " data" in node else None


def _children(node, label):
    return [(k, v) for k, v in node.items() if hasattr(v, "attrs") and _text(v, "label") == label]


def read_cgns(path) -> RawMesh:
    """CGNS/HDF5, unstructured, 2D or 3D, one zone or several. Per zone: coordinates; cell sections (2D: TRI_3, QUAD_4;
    3D: TETRA_4, PYRA_5, PENTA_6, HEXA_8; or MIXED); boundary sections (2D: BAR_2; 3D: TRI_3, QUAD_4) named by the
    ZoneBC that points to them, else by the section name. Several zones (each with its own points, the usual CGNS
    multi-zone layout) become one mesh with one cell zone per CGNS zone (named like it); their coincident interface
    points are merged (full 3D release stage)."""
    import h5py
    name = Path(path).name
    try:
        file = h5py.File(path, "r")
    except OSError:
        raise ValueError(f"{name} is not a CGNS/HDF5 file (CGNS files in the old ADF format are not read).") from None
    with file:
        bases = _children(file, "CGNSBase_t")
        zones = [(k, z, int(_data(b)[0])) for _, b in bases for k, z in _children(b, "Zone_t")]
        if not zones:
            raise ValueError(f"{name} has no zone.")
        dims = {d for _, _, d in zones}
        if len(dims) > 1 or dims - {2, 3}:
            raise ValueError(f"{name}: the zones must all be 2D or all 3D (cell dimension {sorted(dims)}).")
        blocks = [_read_cgns_zone(z, d, name) for _, z, d in zones]
    if len(blocks) == 1:
        return blocks[0]
    return _merge_zones(blocks, [k for k, _, _ in zones], "CGNS")


CGNS_VOLUME = {10: (TETRA, 4), 12: (PYRAMID, 5), 14: (WEDGE, 6), 17: (HEXAHEDRON, 8)}   # CGNS type -> (VTK, nodes)
CGNS_NODES = {3: 2, 5: 3, 7: 4, 10: 4, 12: 5, 14: 6, 17: 8}


def _read_cgns_zone(zone, dim, name) -> RawMesh:
    """One unstructured CGNS zone as a RawMesh (2D or 3D)."""
    ztype = next((v for k, v in _children(zone, "ZoneType_t")), None)
    if ztype is None or bytes(_data(ztype)).decode() != "Unstructured":
        raise ValueError(f"{name} is a structured CGNS zone: only unstructured zones are read.")
    coords = next(v for k, v in _children(zone, "GridCoordinates_t"))
    axes = ["CoordinateX", "CoordinateY"] + (["CoordinateZ"] if dim == 3 else [])
    points = np.column_stack([np.asarray(_data(coords[a]), dtype=float) for a in axes])
    cells = {}
    faces = []                                               # (section name, first element id, (n, 2 or 4) nodes)
    boundary_kinds = {CGNS_BAR} if dim == 2 else {CGNS_TRI, CGNS_QUAD}
    width = 2 if dim == 2 else 4

    def add(kind, nodes, collected):
        if kind in boundary_kinds:
            row = np.full(width, -1, dtype=np.int64)
            row[:len(nodes)] = nodes
            collected.append(row)
        elif dim == 2 and kind in (CGNS_TRI, CGNS_QUAD):
            cells.setdefault(TRIANGLE if kind == CGNS_TRI else QUAD, []).append(nodes)
        elif dim == 3 and kind in CGNS_VOLUME:
            vtk = CGNS_VOLUME[kind][0]
            cells.setdefault(vtk, []).append(nodes[FROM_VTK[vtk]] if vtk in FROM_VTK else nodes)
        else:
            raise ValueError(f"{name}: element type {kind} is not read in a {dim}D mesh (linear elements only).")

    for section_name, section in _children(zone, "Elements_t"):
        kind = int(_data(section)[0])
        first, _last = (int(v) for v in _data(section["ElementRange"]))
        conn = np.asarray(_data(section["ElementConnectivity"]), dtype=np.int64).ravel()
        collected = []
        if kind == CGNS_MIXED:
            k = 0
            while k < len(conn):
                t = int(conn[k])
                if t not in CGNS_NODES:
                    raise ValueError(f"{name}: section '{section_name}' holds element type {t} (linear elements only).")
                add(t, conn[k + 1:k + 1 + CGNS_NODES[t]] - 1, collected)
                k += CGNS_NODES[t] + 1
        else:
            if kind not in CGNS_NODES:
                raise ValueError(f"{name}: section '{section_name}' holds element type {kind} (linear elements only).")
            for row in conn.reshape(-1, CGNS_NODES[kind]) - 1:
                add(kind, row, collected)
        if collected:
            faces.append((section_name, first, np.array(collected)))
    by_bc = []
    for bc_zone in _children(zone, "ZoneBC_t"):
        for bc_name, bc in _children(bc_zone[1], "BC_t"):
            if "PointRange" in bc:
                lo, hi = np.asarray(_data(bc["PointRange"])).ravel()[:2]
                ids = np.arange(int(lo), int(hi) + 1)
            elif "PointList" in bc:
                ids = np.asarray(_data(bc["PointList"]), dtype=np.int64).ravel()
            else:
                continue
            by_bc.append((bc_name, ids))
    face_of = {}
    for _section, first, rows in faces:
        for k, row in enumerate(rows):
            face_of[first + k] = row
    groups, used = {}, set()
    for bc_name, ids in by_bc:
        found = [face_of[i] for i in ids if i in face_of]
        if found:
            groups[bc_name] = np.vstack([groups[bc_name], found]) if bc_name in groups else np.array(found)
            used.update(int(i) for i in ids)
    for section_name, first, rows in faces:                  # sections no BC points to: the section is the tag
        rest = [r for k, r in enumerate(rows) if first + k not in used]
        if rest:
            groups[section_name] = np.array(rest, dtype=np.int64)
    order = (TRIANGLE, QUAD) if dim == 2 else (TETRA, PYRAMID, WEDGE, HEXAHEDRON)   # the writers' section order
    out = [(t, np.vstack(cells[t])) for t in order if cells.get(t)]
    if not out:
        raise ValueError(f"{name} has no {dim}D cells.")
    return RawMesh(points, out, groups, "CGNS", dim=dim)


def _node(parent, name, label, kind, data=None):
    """One CGNS/HDF5 node: a group with name, label and data-type attributes and the data in a dataset ' data'."""
    group = parent.create_group(name)
    group.attrs.create("name", np.bytes_(name))
    group.attrs.create("label", np.bytes_(label))
    group.attrs.create("type", np.bytes_(kind))
    group.attrs.create("flags", np.array([1], dtype=np.int32))
    if data is not None:
        dtype = {"I4": np.int32, "R8": np.float64, "R4": np.float32, "C1": np.int8, "I8": np.int64}[kind]
        group.create_dataset(" data", data=np.asarray(data, dtype=dtype))
    return group


INTERFACE_SUFFIX = "_interface"     # boundary of one zone's part where it touches other zones (multi-zone CGNS)


def _cgns_parts(mesh):
    """[(CGNS zone name, Mesh)]: the mesh itself as "Zone", or one part per cell zone; a part's faces shared with other
    zones form the patch "<zone>_interface" (BC type BCTypeNull; reading the file merges them back into interior
    faces). Zone names are the cell zone names."""
    if not mesh.cell_zones:
        return [("Zone", mesh)]
    from aeroflowsim.mesh import remove_zones
    return [(z, remove_zones(mesh, [o for o in mesh.zone_names if o != z], patch_name=z + INTERFACE_SUFFIX))
            for z in mesh.zone_names]


def _cgns_bc(patch):
    if patch.name.endswith(INTERFACE_SUFFIX):
        return "BCTypeNull"
    return CGNS_BC.get(patch.type, "BCTypeNull")


def write_cgns(mesh: Mesh, path) -> Path:
    """CGNS/HDF5: base (2, 2), one unstructured zone, coordinates, cell sections, one BAR_2 section and BC per patch.
    A 3D mesh: see write_cgns_3d."""
    import h5py
    if mesh.dim == 3:
        return write_cgns_3d(mesh, path)
    _check_2d(mesh)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        f.create_dataset(" format", data=np.frombuffer(b"IEEE_LITTLE_64\0", dtype=np.int8))
        f.create_dataset(" hdf5version", data=np.frombuffer(b"HDF5 Version 1.14.0\0", dtype=np.int8))
        _node(f, "CGNSLibraryVersion", "CGNSLibraryVersion_t", "R4", [4.0])
        base = _node(f, "Base", "CGNSBase_t", "I4", [2, 2])
        for zone_name, part in _cgns_parts(mesh):
            _write_cgns_zone(base, zone_name, part)
    return path


def _write_cgns_zone(base, zone_name, mesh):
    """One 2D unstructured zone (coordinates, cell sections, one BAR_2 section and BC per patch)."""
    cells = _cell_lists(mesh)
    zone = _node(base, zone_name, "Zone_t", "I4", [[mesh.n_nodes, mesh.n_cells, 0]])
    _node(zone, "ZoneType", "ZoneType_t", "C1", np.frombuffer(b"Unstructured", dtype=np.int8))
    grid = _node(zone, "GridCoordinates", "GridCoordinates_t", "MT")
    _node(grid, "CoordinateX", "DataArray_t", "R8", mesh.nodes[:, 0])
    _node(grid, "CoordinateY", "DataArray_t", "R8", mesh.nodes[:, 1])
    element = 1
    for section, (kind, conn) in zip(("Cells_tri", "Cells_quad"), cells):
        sec = _node(zone, section, "Elements_t", "I4", [{TRIANGLE: CGNS_TRI, QUAD: CGNS_QUAD}[kind], 0])
        conn = conn if len(conn) else conn
        _node(sec, "ElementRange", "IndexRange_t", "I4", [element, element + len(conn) - 1])
        _node(sec, "ElementConnectivity", "DataArray_t", "I4", (conn + 1).ravel())
        element += len(conn)
    zbc = _node(zone, "ZoneBC", "ZoneBC_t", "MT")
    for patch in mesh.patches:
        edges = mesh.face_nodes[patch.faces, :2]
        sec = _node(zone, patch.name, "Elements_t", "I4", [CGNS_BAR, 0])
        _node(sec, "ElementRange", "IndexRange_t", "I4", [element, element + len(edges) - 1])
        _node(sec, "ElementConnectivity", "DataArray_t", "I4", (edges + 1).ravel())
        bc = _node(zbc, patch.name, "BC_t", "C1", np.frombuffer(_cgns_bc(patch).encode(), dtype=np.int8))
        _node(bc, "PointRange", "IndexRange_t", "I4", [[element], [element + len(edges) - 1]])
        _node(bc, "GridLocation", "GridLocation_t", "C1", np.frombuffer(b"EdgeCenter", dtype=np.int8))
        element += len(edges)


# ---- writing Gmsh and SU2 ----------------------------------------------------------------------------------------------

def _check_2d(mesh):
    if mesh.dim != 2:
        raise ValueError("Only 2D meshes can be exported now.")


def _cell_lists(mesh):
    """[(type, (n, k) node numbers)] of the triangles and of the quads, in cell order within each type."""
    out = []
    for code, width in ((TRIANGLE, 3), (QUAD, 4)):
        out.append((code, mesh.cell_nodes[mesh.cell_types == code][:, :width]))
    return out


def write_gmsh(mesh: Mesh, path, version="2.2") -> Path:
    """Gmsh .msh, ASCII, version "2.2" or "4.1": cells, plus one physical group of edges per patch (named like the patch).
    A 3D mesh: see write_gmsh_3d."""
    if version not in ("2.2", "4.1"):
        raise ValueError("Gmsh version must be '2.2' or '4.1'.")
    if mesh.dim == 3:
        return write_gmsh_3d(mesh, path, version)
    _check_2d(mesh)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nodes = mesh.nodes.tolist()                       # python floats: repr() gives all digits, no 'np.float64(...)'
    patches = list(mesh.patches)
    cells = [(code, conn) for code, conn in _cell_lists(mesh) if len(conn)]
    gmsh_type = {TRIANGLE: 2, QUAD: 3}
    zone_tag = mesh.cell_zone_index() + 1                      # physical surface of every cell (1 = "fluid")
    zone_of = {code: zone_tag[mesh.cell_types == code] for code, _ in cells}
    zones = mesh.zone_names
    out = ["$MeshFormat", f"{version} 0 8", "$EndMeshFormat", "$PhysicalNames", str(len(patches) + len(zones))]
    out += [f'1 {k} "{p.name}"' for k, p in enumerate(patches, start=1)]
    out += [f'2 {k} "{z}"' for k, z in enumerate(zones, start=1)] + ["$EndPhysicalNames"]
    if version == "2.2":
        out += ["$Nodes", str(len(nodes))] + [f"{i + 1} {x!r} {y!r} 0" for i, (x, y, _) in enumerate(nodes)] + ["$EndNodes"]
        n_elements = sum(len(c) for _, c in cells) + sum(p.count for p in patches)
        out += ["$Elements", str(n_elements)]
        element = 1
        for k, p in enumerate(patches, start=1):
            for a, b in mesh.face_nodes[p.faces, :2]:
                out.append(f"{element} 1 2 {k} {k} {a + 1} {b + 1}")
                element += 1
        for code, conn in cells:
            for row, z in zip(conn, zone_of[code]):
                out.append(f"{element} {gmsh_type[code]} 2 {z} {z} " + " ".join(str(int(n) + 1) for n in row))
                element += 1
        out.append("$EndElements")
    else:
        arr = mesh.nodes
        lo, hi = arr[:, :2].min(axis=0).tolist(), arr[:, :2].max(axis=0).tolist()
        out += ["$Entities", f"0 {len(patches)} {len(zones)} 0"]
        for k, p in enumerate(patches, start=1):
            e = mesh.face_nodes[p.faces, :2].ravel()
            a, b = arr[e, :2].min(axis=0).tolist(), arr[e, :2].max(axis=0).tolist()
            out.append(f"{k} {a[0]!r} {a[1]!r} 0 {b[0]!r} {b[1]!r} 0 1 {k} 0")
        for z in range(1, len(zones) + 1):
            out.append(f"{z} {lo[0]!r} {lo[1]!r} 0 {hi[0]!r} {hi[1]!r} 0 1 {z} {len(patches)} "
                       + " ".join(str(k) for k in range(1, len(patches) + 1)))
        out += ["$EndEntities", "$Nodes", f"1 {len(nodes)} 1 {len(nodes)}", f"2 1 0 {len(nodes)}"]
        out += [str(i + 1) for i in range(len(nodes))] + [f"{x!r} {y!r} 0" for x, y, _ in nodes] + ["$EndNodes"]
        cell_blocks = [(z, code, conn[zone_of[code] == z]) for code, conn in cells for z in range(1, len(zones) + 1)
                       if np.any(zone_of[code] == z)]
        blocks = len(patches) + len(cell_blocks)
        n_elements = sum(len(c) for _, c in cells) + sum(p.count for p in patches)
        out += ["$Elements", f"{blocks} {n_elements} 1 {n_elements}"]
        element = 1
        for k, p in enumerate(patches, start=1):
            out.append(f"1 {k} 1 {p.count}")
            for a, b in mesh.face_nodes[p.faces, :2]:
                out.append(f"{element} {a + 1} {b + 1}")
                element += 1
        for z, code, conn in cell_blocks:
            out.append(f"2 {z} {gmsh_type[code]} {len(conn)}")
            for row in conn:
                out.append(f"{element} " + " ".join(str(int(n) + 1) for n in row))
                element += 1
        out.append("$EndElements")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def write_su2(mesh: Mesh, path) -> Path:
    """SU2 .su2: the cells, the points and one MARKER_TAG per patch (named like the patch). 3D: see write_su2_3d.
    A multi-zone mesh: see write_su2_zones."""
    if mesh.cell_zones:
        return write_su2_zones(mesh, path)
    if mesh.dim == 3:
        return write_su2_3d(mesh, path)
    _check_2d(mesh)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cells = [(code, conn) for code, conn in _cell_lists(mesh) if len(conn)]
    out = ["NDIME= 2", f"NELEM= {sum(len(c) for _, c in cells)}"]
    index = 0
    for code, conn in cells:
        for row in conn:
            out.append(f"{code} " + " ".join(str(int(n)) for n in row) + f" {index}")
            index += 1
    out.append(f"NPOIN= {mesh.n_nodes}")
    out += [f"{x!r} {y!r} {i}" for i, (x, y, _) in enumerate(mesh.nodes.tolist())]
    out.append(f"NMARK= {len(mesh.patches)}")
    for p in mesh.patches:
        out += [f"MARKER_TAG= {p.name}", f"MARKER_ELEMS= {p.count}"]
        out += [f"3 {a} {b}" for a, b in mesh.face_nodes[p.faces, :2]]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


# ---- writing 3D meshes -----------------------------------------------------------------------------------------------
# Node orders: SU2 uses VTK's cell numbers and node orders. Gmsh and CGNS number a prism with its bottom triangle turning
# towards the top (VTK: away from it), so VTK wedge (0 1 2 3 4 5) is Gmsh / CGNS (0 2 1 3 5 4); tetrahedra, hexahedra and
# pyramids are numbered the same in all three.

GMSH_3D = {TETRA: 4, HEXAHEDRON: 5, WEDGE: 6, PYRAMID: 7}      # Gmsh element type numbers
CGNS_3D = {TETRA: 10, PYRAMID: 12, WEDGE: 14, HEXAHEDRON: 17}  # CGNS ElementType_t numbers
CGNS_TRI_3, CGNS_QUAD_4 = 5, 7
FROM_VTK = {WEDGE: [0, 2, 1, 3, 5, 4]}                          # VTK node order -> Gmsh / CGNS node order
N_NODES = {TETRA: 4, PYRAMID: 5, WEDGE: 6, HEXAHEDRON: 8}


def _cell_lists_3d(mesh, order=None):
    """[(VTK type, (n, k) node numbers)] for every 3D cell type present; order = FROM_VTK for Gmsh / CGNS."""
    out = []
    for code in (TETRA, PYRAMID, WEDGE, HEXAHEDRON):
        conn = mesh.cell_nodes[mesh.cell_types == code][:, :N_NODES[code]]
        if len(conn):
            out.append((code, conn[:, order[code]] if order and code in order else conn))
    return out


def _patch_faces(mesh, patch):
    """(triangles (n, 3), quads (m, 4)): the node numbers of the faces of a patch."""
    f = mesh.face_nodes[patch.faces]
    tri = f[:, 3] < 0
    return f[tri, :3], f[~tri, :4]


def write_gmsh_3d(mesh: Mesh, path, version="2.2") -> Path:
    """Gmsh .msh of a 3D mesh, ASCII 2.2 or 4.1: one physical surface per patch (triangles, quads), the volume "fluid"."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nodes = mesh.nodes.tolist()
    patches = list(mesh.patches)
    cells = _cell_lists_3d(mesh, FROM_VTK)
    faces = [_patch_faces(mesh, p) for p in patches]
    zone_tag = mesh.cell_zone_index() + 1                      # physical volume of every cell (1 = "fluid")
    zone_of = {code: zone_tag[mesh.cell_types == code] for code, _ in cells}
    zones = mesh.zone_names
    out = ["$MeshFormat", f"{version} 0 8", "$EndMeshFormat", "$PhysicalNames", str(len(patches) + len(zones))]
    out += [f'2 {k} "{p.name}"' for k, p in enumerate(patches, start=1)]
    out += [f'3 {k} "{z}"' for k, z in enumerate(zones, start=1)] + ["$EndPhysicalNames"]
    n_elements = sum(len(c) for _, c in cells) + sum(p.count for p in patches)
    element = 1
    if version == "2.2":
        out += ["$Nodes", str(len(nodes))] + [f"{i + 1} {x!r} {y!r} {z!r}" for i, (x, y, z) in enumerate(nodes)]
        out += ["$EndNodes", "$Elements", str(n_elements)]
        for k, (tri, quad) in enumerate(faces, start=1):
            for kind, conn in ((2, tri), (3, quad)):
                for row in conn:
                    out.append(f"{element} {kind} 2 {k} {k} " + " ".join(str(int(n) + 1) for n in row))
                    element += 1
        for code, conn in cells:
            for row, z in zip(conn, zone_of[code]):
                out.append(f"{element} {GMSH_3D[code]} 2 {z} {z} " + " ".join(str(int(n) + 1) for n in row))
                element += 1
        out.append("$EndElements")
    else:
        arr = mesh.nodes

        def box(points):
            return " ".join(repr(v) for v in [*points.min(axis=0).tolist(), *points.max(axis=0).tolist()])
        out += ["$Entities", f"0 0 {len(patches)} {len(zones)}"]
        for k, p in enumerate(patches, start=1):
            used = mesh.face_nodes[p.faces]
            out.append(f"{k} {box(arr[used[used >= 0]])} 1 {k} 0")
        for z in range(1, len(zones) + 1):
            out.append(f"{z} {box(arr)} 1 {z} {len(patches)} " + " ".join(str(k) for k in range(1, len(patches) + 1)))
        out += ["$EndEntities", "$Nodes", f"1 {len(nodes)} 1 {len(nodes)}", f"3 1 0 {len(nodes)}"]
        out += [str(i + 1) for i in range(len(nodes))] + [f"{x!r} {y!r} {z!r}" for x, y, z in nodes] + ["$EndNodes"]
        blocks = [(2, k, kind, conn) for k, (tri, quad) in enumerate(faces, start=1)
                  for kind, conn in ((2, tri), (3, quad)) if len(conn)]
        blocks += [(3, z, GMSH_3D[code], conn[zone_of[code] == z]) for code, conn in cells
                   for z in range(1, len(zones) + 1) if np.any(zone_of[code] == z)]
        out += ["$Elements", f"{len(blocks)} {n_elements} 1 {n_elements}"]
        for dim, entity, kind, conn in blocks:
            out.append(f"{dim} {entity} {kind} {len(conn)}")
            for row in conn:
                out.append(f"{element} " + " ".join(str(int(n) + 1) for n in row))
                element += 1
        out.append("$EndElements")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def write_su2_zones(mesh: Mesh, path) -> Path:
    """SU2 multi-zone file: NZONE = n and one IZONE block per cell zone, each with its own points (SU2 numbers the
    points per zone), its cells, its part of every patch and one marker per interface ("<zone>_to_<other>", the
    faces it shares with the other zone, which SU2 joins with MARKER_ZONE_INTERFACE). Zone names are not part of the
    format: they are written as comments ("% zone: name")."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    index = mesh.cell_zone_index()
    nI = mesh.n_interior_faces
    face_kind = {2: 3, 3: 5, 4: 9}                               # nodes per face -> VTK line / triangle / quad
    out = [f"NZONE= {len(mesh.zone_names)}"]
    for k, zone in enumerate(mesh.zone_names):
        cells = np.flatnonzero(index == k)
        used = np.unique(mesh.cell_nodes[cells][mesh.cell_nodes[cells] >= 0])
        local = np.full(mesh.n_nodes, -1, dtype=np.int64)
        local[used] = np.arange(len(used))
        out += [f"% zone: {zone}", f"IZONE= {k + 1}", f"NDIME= {mesh.dim}", f"NELEM= {len(cells)}"]
        for j, c in enumerate(cells):
            n = CELL_NODES[int(mesh.cell_types[c])]
            out.append(f"{int(mesh.cell_types[c])} " + " ".join(str(int(local[v])) for v in mesh.cell_nodes[c, :n])
                       + f" {j}")
        out.append(f"NPOIN= {len(used)}")
        out += [" ".join(repr(float(x)) for x in mesh.nodes[v, :mesh.dim]) + f" {j}" for j, v in enumerate(used)]
        markers = []
        for p in mesh.patches:
            faces = p.faces[index[mesh.owner[p.faces]] == k]
            if len(faces):
                markers.append((p.name, faces))
        for j, other in enumerate(mesh.zone_names):
            if j == k:
                continue
            zo, zn = index[mesh.owner[:nI]], index[mesh.neighbour[:nI]]
            faces = np.flatnonzero(((zo == k) & (zn == j)) | ((zo == j) & (zn == k)))
            if len(faces):
                markers.append((f"{zone}_to_{other}", faces))
        out.append(f"NMARK= {len(markers)}")
        for tag, faces in markers:
            out += [f"MARKER_TAG= {tag}", f"MARKER_ELEMS= {len(faces)}"]
            for f in mesh.face_nodes[faces]:
                f = f[f >= 0]
                out.append(f"{face_kind[len(f)]} " + " ".join(str(int(local[v])) for v in f))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def write_su2_3d(mesh: Mesh, path) -> Path:
    """SU2 .su2 of a 3D mesh (VTK cell numbers and node orders; marker faces: triangles 5, quads 9)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cells = _cell_lists_3d(mesh)
    out = ["NDIME= 3", f"NELEM= {sum(len(c) for _, c in cells)}"]
    index = 0
    for code, conn in cells:
        for row in conn:
            out.append(f"{code} " + " ".join(str(int(n)) for n in row) + f" {index}")
            index += 1
    out.append(f"NPOIN= {mesh.n_nodes}")
    out += [f"{x!r} {y!r} {z!r} {i}" for i, (x, y, z) in enumerate(mesh.nodes.tolist())]
    out.append(f"NMARK= {len(mesh.patches)}")
    for p in mesh.patches:
        tri, quad = _patch_faces(mesh, p)
        out += [f"MARKER_TAG= {p.name}", f"MARKER_ELEMS= {p.count}"]
        out += ["5 " + " ".join(str(int(n)) for n in row) for row in tri]
        out += ["9 " + " ".join(str(int(n)) for n in row) for row in quad]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def write_cgns_3d(mesh: Mesh, path) -> Path:
    """CGNS/HDF5 of a 3D mesh: base (3, 3), one unstructured zone, one section per cell type; per patch a TRI_3 and a
    QUAD_4 section (consecutive element numbers) and a BC over their range (GridLocation FaceCenter)."""
    import h5py
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        f.create_dataset(" format", data=np.frombuffer(b"IEEE_LITTLE_64\0", dtype=np.int8))
        f.create_dataset(" hdf5version", data=np.frombuffer(b"HDF5 Version 1.14.0\0", dtype=np.int8))
        _node(f, "CGNSLibraryVersion", "CGNSLibraryVersion_t", "R4", [4.0])
        base = _node(f, "Base", "CGNSBase_t", "I4", [3, 3])
        for zone_name, part in _cgns_parts(mesh):
            _write_cgns_3d_zone(base, zone_name, part)
    return path


def _write_cgns_3d_zone(base, zone_name, mesh):
    """One 3D unstructured zone (coordinates, cell sections, per patch TRI_3 / QUAD_4 sections and a BC)."""
    zone = _node(base, zone_name, "Zone_t", "I4", [[mesh.n_nodes, mesh.n_cells, 0]])
    _node(zone, "ZoneType", "ZoneType_t", "C1", np.frombuffer(b"Unstructured", dtype=np.int8))
    grid = _node(zone, "GridCoordinates", "GridCoordinates_t", "MT")
    for k, axis in enumerate("XYZ"):
        _node(grid, f"Coordinate{axis}", "DataArray_t", "R8", mesh.nodes[:, k])
    element = 1
    names = {TETRA: "Cells_tetra", PYRAMID: "Cells_pyramid", WEDGE: "Cells_prism", HEXAHEDRON: "Cells_hexa"}
    for code, conn in _cell_lists_3d(mesh, FROM_VTK):
        sec = _node(zone, names[code], "Elements_t", "I4", [CGNS_3D[code], 0])
        _node(sec, "ElementRange", "IndexRange_t", "I4", [element, element + len(conn) - 1])
        _node(sec, "ElementConnectivity", "DataArray_t", "I4", (conn + 1).ravel())
        element += len(conn)
    zbc = _node(zone, "ZoneBC", "ZoneBC_t", "MT")
    for patch in mesh.patches:
        first = element
        for suffix, kind, conn in zip(("", "_quads"), (CGNS_TRI_3, CGNS_QUAD_4), _patch_faces(mesh, patch)):
            if len(conn):
                sec = _node(zone, patch.name + suffix, "Elements_t", "I4", [kind, 0])
                _node(sec, "ElementRange", "IndexRange_t", "I4", [element, element + len(conn) - 1])
                _node(sec, "ElementConnectivity", "DataArray_t", "I4", (conn + 1).ravel())
                element += len(conn)
        bc = _node(zbc, patch.name, "BC_t", "C1",
                   np.frombuffer(_cgns_bc(patch).encode(), dtype=np.int8))
        _node(bc, "PointRange", "IndexRange_t", "I4", [[first], [element - 1]])
        _node(bc, "GridLocation", "GridLocation_t", "C1", np.frombuffer(b"FaceCenter", dtype=np.int8))


def write_mesh(mesh: Mesh, path, gmsh_version="2.2") -> Path:
    """Write a mesh in the format of the file name's ending: .msh (Gmsh), .su2, .cgns or .vtu (ParaView)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".vtu":
        from aeroflowsim.vtk import mesh_cell_data, write_vtu
        return write_vtu(path, mesh, mesh_cell_data(mesh))
    writers = {".msh": lambda m, p: write_gmsh(m, p, gmsh_version), ".su2": write_su2, ".cgns": write_cgns}
    if suffix not in writers:
        raise ValueError(f"'{suffix}' is not a mesh format AeroFlowSim writes. Use .msh, .su2, .cgns or .vtu.")
    return writers[suffix](mesh, path)


EXPORTERS = {"Gmsh 2.2 (.msh)": (".msh", lambda m, p: write_gmsh(m, p, "2.2")),
             "Gmsh 4.1 (.msh)": (".msh", lambda m, p: write_gmsh(m, p, "4.1")),
             "SU2 (.su2)": (".su2", write_su2), "CGNS (.cgns)": (".cgns", write_cgns)}


# ---- from a RawMesh to a Mesh ----------------------------------------------------------------------------------------

def tag_table(raw: RawMesh) -> list:
    """One row per boundary tag for the import table: {name, edges, guess} (guess: a boundary type, or None)."""
    return [{"name": name, "edges": int(len(edges)), "guess": guess_patch_type(name, raw.hints.get(name))}
            for name, edges in raw.groups.items()]


def size_text(raw: RawMesh) -> str:
    """Extent of the mesh in the file's unit, to help choosing the unit: 'x -1 to 3, y 0 to 2'."""
    lo, hi = raw.points.min(axis=0), raw.points.max(axis=0)
    text = f"x {lo[0]:.6g} to {hi[0]:.6g}, y {lo[1]:.6g} to {hi[1]:.6g}"
    return text + (f", z {lo[2]:.6g} to {hi[2]:.6g}" if raw.points.shape[1] == 3 else "")


def parse_tag_map(text) -> dict:
    """{tag: boundary type} from text like 'airfoil: wall, outer: farfield' (also '=' and ';'). Empty text: {}."""
    mapping = {}
    for item in re.split(r"[;,\n]", text or ""):
        if not item.strip():
            continue
        if ":" not in item and "=" not in item:
            raise ValueError(f"Boundary map entry '{item.strip()}' must look like  tag: type.")
        tag, kind = re.split(r"[:=]", item, maxsplit=1)
        kind = kind.strip().lower()
        if kind not in PATCH_TYPES:
            raise ValueError(f"Boundary map: '{kind}' is not a boundary type ({', '.join(PATCH_TYPES)}).")
        mapping[tag.strip()] = kind
    return mapping


def mesh_from_raw(raw: RawMesh, unit="m", axisymmetric=False, patch_types=None) -> Mesh:
    """The face-based Mesh of a RawMesh.

    unit           the file's length unit ("m", "mm", "cm", "in", "ft"); coordinates are converted to metres
    axisymmetric   True: the mesh is axisymmetric about y = 0 (all y must be >= 0)
    patch_types    {tag: boundary type}; tags missing here get their guessed type (guess_patch_type); ValueError if none
    """
    if unit not in LENGTH_UNITS:
        raise ValueError(f"Unknown length unit '{unit}'. Use one of {', '.join(LENGTH_UNITS)}.")
    patch_types = dict(patch_types or {})
    if raw.dim == 3:
        if axisymmetric:
            raise ValueError("A 3D mesh cannot be axisymmetric: choose 'Planar' (the 3D mesh is used as it is).")
        return _mesh_from_raw_3d(raw, unit, patch_types)
    nodes = raw.points * LENGTH_UNITS[unit]
    width = 4
    cell_types = np.concatenate([np.full(len(c), t) for t, c in raw.cells])
    cells = np.full((len(cell_types), width), -1, dtype=np.int64)
    k = 0
    for t, c in raw.cells:
        cells[k:k + len(c), :c.shape[1]] = c
        k += len(c)
    if cells.max() >= len(nodes) or cells.min() < -1:
        raise ValueError("A cell refers to a node that does not exist: the file is damaged.")
    # counter-clockwise cells (a Mesh needs positive areas)
    area = np.zeros(len(cells))
    for j in range(4):
        use = (j < np.where(cell_types == TRIANGLE, 3, 4))
        a = cells[use, j]
        nxt = np.where(j + 1 < np.where(cell_types == TRIANGLE, 3, 4)[use], (j + 1) % 4, 0)
        b = cells[use, nxt]
        area[use] += nodes[a, 0] * nodes[b, 1] - nodes[b, 0] * nodes[a, 1]
    if np.any(area == 0.0):
        raise ValueError(f"{int(np.count_nonzero(area == 0.0))} cell(s) have zero area.")
    flip = area < 0.0
    tri, quad = flip & (cell_types == TRIANGLE), flip & (cell_types == QUAD)
    cells[tri, :3] = cells[tri][:, [0, 2, 1]]
    cells[quad] = cells[quad][:, [0, 3, 2, 1]]
    # boundary edges: the cell edges that occur once
    edge_rows = []
    for t in (TRIANGLE, QUAD):
        sel = cells[cell_types == t]
        n = 3 if t == TRIANGLE else 4
        for j in range(n):
            edge_rows.append(np.column_stack([sel[:, j], sel[:, (j + 1) % n]]) if len(sel) else np.empty((0, 2), dtype=np.int64))
    edges = np.vstack(edge_rows)
    keys = np.sort(edges, axis=1)
    unique, counts = np.unique(keys, axis=0, return_counts=True)
    if counts.max() > 2:
        raise ValueError("Three or more cells share one edge: the mesh is not a valid 2D mesh.")
    boundary_keys = {tuple(r) for r in unique[counts == 1]}
    tagged, missing = {}, set(boundary_keys)
    for name, group in raw.groups.items():
        rows = [tuple(sorted(map(int, e))) for e in group]
        on_boundary = np.array([r in boundary_keys for r in rows], dtype=bool)
        if on_boundary.any():
            tagged[name] = np.array(group)[on_boundary]
            missing -= {r for r, ok in zip(rows, on_boundary) if ok}
    if missing:
        raise ValueError(f"{len(missing)} boundary edge(s) of the mesh have no tag (named boundary). Tag every boundary of the "
                         f"mesh in the mesher. Tags found: {', '.join(raw.groups) or 'none'}.")
    types, unknown = {}, []
    for name in tagged:
        kind = patch_types.get(name) or guess_patch_type(name, raw.hints.get(name))
        if kind is None:
            unknown.append(name)
        elif kind not in PATCH_TYPES:
            raise ValueError(f"Tag '{name}': '{kind}' is not a boundary type ({', '.join(PATCH_TYPES)}).")
        else:
            types[name] = kind
    if unknown:
        raise ValueError(f"Choose a boundary type ({', '.join(PATCH_TYPES)}) for the tag(s): {', '.join(unknown)}.")
    used = np.unique(cells[cells >= 0])                                       # drop points no cell uses
    renumber = np.full(len(nodes), -1, dtype=np.int64)
    renumber[used] = np.arange(len(used))
    cells = np.where(cells >= 0, renumber[np.maximum(cells, 0)], -1)
    boundary = {name: (types[name], renumber[g]) for name, g in tagged.items()}
    nodes = nodes[used]
    if axisymmetric and nodes[:, 1].min() < -1e-9 * max(float(np.ptp(nodes[:, 1])), 1e-300):
        raise ValueError("An axisymmetric mesh must have all y >= 0 (y is the radius, the axis is y = 0). Choose 'Planar', "
                         "or move the mesh.")
    if axisymmetric:
        nodes[:, 1] = np.maximum(nodes[:, 1], 0.0)
    info = {"generator": "imported", "source": raw.source, "format": raw.format, "file_unit": unit,
            "axisymmetric": bool(axisymmetric)}
    return Mesh.from_cells(nodes, cell_types, cells, boundary, dim=2, axisymmetric=axisymmetric, info=info,
                           cell_zones=raw.zones or None)


def _mesh_from_raw_3d(raw: RawMesh, unit, patch_types) -> Mesh:
    """The 3D part of mesh_from_raw: orientation check, boundary faces matched to the tags, unused points dropped."""
    from aeroflowsim.mesh import MAX_CELL_NODES, _find_faces
    from aeroflowsim.simple_meshes import _orient_cells
    nodes = np.asarray(raw.points, dtype=float)[:, :3] * LENGTH_UNITS[unit]
    cell_types = np.concatenate([np.full(len(c), t, dtype=np.int32) for t, c in raw.cells])
    cells = np.full((len(cell_types), MAX_CELL_NODES), -1, dtype=np.int64)
    k = 0
    for t, c in raw.cells:
        cells[k:k + len(c), :c.shape[1]] = c
        k += len(c)
    if cells.max() >= len(nodes) or cells.min() < -1:
        raise ValueError("A cell refers to a node that does not exist: the file is damaged.")
    _orient_cells(nodes, cell_types, cells)          # inside-out cells (mirrored node order) are turned round
    face_nodes, _owner, neighbour = _find_faces(cell_types, cells)

    def key(row):
        return tuple(sorted(int(v) for v in row if v >= 0))
    boundary_keys = {key(row) for row in face_nodes[neighbour < 0]}
    tagged, missing = {}, set(boundary_keys)
    for name, group in raw.groups.items():
        rows = [key(r) for r in group]
        on_boundary = np.array([r in boundary_keys for r in rows], dtype=bool)
        if on_boundary.any():
            tagged[name] = np.asarray(group)[on_boundary]
            missing -= {r for r, ok in zip(rows, on_boundary) if ok}
    if missing:
        raise ValueError(f"{len(missing)} boundary face(s) of the mesh have no tag (named boundary). Tag every boundary "
                         f"surface in the mesher. Tags found: {', '.join(raw.groups) or 'none'}.")
    types, unknown = {}, []
    for name in tagged:
        kind = patch_types.get(name) or guess_patch_type(name, raw.hints.get(name))
        if kind is None:
            unknown.append(name)
        elif kind not in PATCH_TYPES:
            raise ValueError(f"Tag '{name}': '{kind}' is not a boundary type ({', '.join(PATCH_TYPES)}).")
        else:
            types[name] = kind
    if unknown:
        raise ValueError(f"Choose a boundary type ({', '.join(PATCH_TYPES)}) for the tag(s): {', '.join(unknown)}.")
    used = np.unique(cells[cells >= 0])
    renumber = np.full(len(nodes), -1, dtype=np.int64)
    renumber[used] = np.arange(len(used))
    cells = np.where(cells >= 0, renumber[np.maximum(cells, 0)], -1)
    boundary = {name: (types[name], np.where(g >= 0, renumber[np.maximum(g, 0)], -1)) for name, g in tagged.items()}
    info = {"generator": "imported", "source": raw.source, "format": raw.format, "file_unit": unit, "axisymmetric": False}
    return Mesh.from_cells(nodes[used], cell_types, cells, boundary, dim=3, info=info, cell_zones=raw.zones or None)


def import_mesh(path, unit="m", axisymmetric=False, patch_types=None) -> Mesh:
    """read_mesh_file + mesh_from_raw in one call."""
    return mesh_from_raw(read_mesh_file(path), unit, axisymmetric, patch_types)

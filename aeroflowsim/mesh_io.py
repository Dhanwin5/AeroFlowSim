# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh import and export: Gmsh .msh (v2 and v4), SU2 .su2, CGNS (unstructured, 2D) and Fluent .msh (ASCII, import).

IMPORT in three steps, so a GUI or script can look at the file before it builds anything:

    raw = read_mesh_file(path)              the file as it is: points, cells and named groups of boundary edges (RawMesh)
    tag_table(raw)                          one row per boundary tag: name, edge count, guessed AeroFlowSim boundary type
    mesh = mesh_from_raw(raw, unit, axisymmetric, patch_types)    the face-based Mesh (aeroflowsim/mesh.py), quality
                                            checks run afterwards as for every mesh (aeroflowsim/checks.py)

Only 2D meshes of triangles and quadrilaterals are read (the solver is 2D / axisymmetric now); 3D files give a message that
says so. Every boundary edge of the mesh must carry a tag; tagged edges inside the mesh (internal zones) are ignored.

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

from aeroflowsim.mesh import PATCH_TYPES, QUAD, TRIANGLE, Mesh

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
    names = {int(v[0]): k for k, v in m.field_data.items() if int(v[1]) == 1}
    physical = m.cell_data.get("gmsh:physical")
    cells, groups = [], {}
    for k, block in enumerate(m.cells):
        if block.type in ("triangle", "quad"):
            cells.append((TRIANGLE if block.type == "triangle" else QUAD, np.asarray(block.data, dtype=np.int64)))
        elif block.type == "line":
            tags = physical[k] if physical is not None else np.zeros(len(block.data), dtype=int)
            for tag in np.unique(tags):
                name = names.get(int(tag), f"tag_{int(tag)}" if int(tag) else "untagged")
                groups.setdefault(name, []).append(np.asarray(block.data, dtype=np.int64)[tags == tag])
        elif block.type in ("vertex", "line3", "triangle6", "quad8", "quad9"):
            continue
        else:
            raise ValueError(f"{Path(path).name} contains {block.type} cells: it is a 3D mesh. AeroFlowSim reads only 2D "
                             "meshes (triangles and quadrilaterals) now.")
    if not cells:
        raise ValueError(f"{Path(path).name} has no 2D cells (triangles or quadrilaterals).")
    return RawMesh(_flat_2d(m.points, Path(path).name), cells, {k: np.vstack(v) for k, v in groups.items()}, "Gmsh")


def _clean_lines(path):
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("%")[0].strip()
        if line:
            yield line


def read_su2(path) -> RawMesh:
    """SU2 native .su2 (NDIME, NELEM, NPOIN, NMARK / MARKER_TAG / MARKER_ELEMS)."""
    lines = list(_clean_lines(path))
    name = Path(path).name
    i, ndime, cells, points, groups = 0, 2, {TRIANGLE: [], QUAD: []}, None, {}

    def value(line):
        return line.split("=", 1)[1].split()

    while i < len(lines):
        line = lines[i]
        key = line.split("=", 1)[0].strip().upper()
        if key == "NDIME":
            ndime = int(value(line)[0])
            if ndime != 2:
                raise ValueError(f"{name} is a {ndime}D SU2 mesh. AeroFlowSim reads only 2D meshes now.")
        elif key == "NELEM":
            n = int(value(line)[0])
            for row in lines[i + 1:i + 1 + n]:
                v = [int(x) for x in row.split()]
                if v[0] == 5:
                    cells[TRIANGLE].append(v[1:4])
                elif v[0] == 9:
                    cells[QUAD].append(v[1:5])
                else:
                    raise ValueError(f"{name} has an element of VTK type {v[0]}; only triangles (5) and quadrilaterals "
                                     "(9) are read.")
            i += n
        elif key == "NPOIN":
            n = int(value(line)[0])
            points = np.array([[float(x) for x in row.split()[:ndime]] for row in lines[i + 1:i + 1 + n]])
            i += n
        elif key == "MARKER_TAG":
            tag = value(line)[0]
            count = int(value(lines[i + 1])[0])
            edges = []
            for row in lines[i + 2:i + 2 + count]:
                v = [int(x) for x in row.split()]
                if v[0] != 3:
                    raise ValueError(f"{name}: marker '{tag}' has an element that is not a line (VTK type {v[0]}).")
                edges.append(v[1:3])
            groups[tag] = np.array(edges, dtype=np.int64).reshape(-1, 2)
            i += 1 + count
        i += 1
    if points is None or not (cells[TRIANGLE] or cells[QUAD]):
        raise ValueError(f"{name} is not a complete SU2 mesh (no points or no elements).")
    return RawMesh(points, [(t, np.array(c, dtype=np.int64)) for t, c in cells.items() if c], groups, "SU2")


def read_fluent(path) -> RawMesh:
    """Fluent .msh, ASCII, 2D: nodes (10), cells (12), faces (13) with their zones, zone names (45).

    The cells' nodes are found from their faces. Zone type 3 is a wall, 2 is interior; every other boundary zone is a tag whose
    type the user chooses (the file's numbers are not trusted to mean the same in every writer)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    name = Path(path).name
    sections = re.findall(r"\((\d+)\s*\(([^()]*)\)\s*(?:\(([^()]*)\))?", text, flags=re.S)
    nodes, faces, zones, names, cell_zone_types = [], [], {}, {}, {}
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
    cells = {TRIANGLE: [], QUAD: []}
    for c in sorted(cell_faces):
        poly = _chain(cell_faces[c], name)
        if len(poly) not in (3, 4):
            raise ValueError(f"{name}: cell {c} has {len(poly)} corners; only triangles and quadrilaterals are read.")
        cells[TRIANGLE if len(poly) == 3 else QUAD].append(poly)
    return RawMesh(points, [(t, np.array(c, dtype=np.int64)) for t, c in cells.items() if c],
                   {k: np.array(v, dtype=np.int64) for k, v in groups.items()}, "Fluent", hints=hints)


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
    """CGNS/HDF5, one unstructured 2D zone: coordinates, TRI_3 / QUAD_4 / MIXED sections, BAR_2 sections or ZoneBC groups."""
    import h5py
    name = Path(path).name
    try:
        file = h5py.File(path, "r")
    except OSError:
        raise ValueError(f"{name} is not a CGNS/HDF5 file (CGNS files in the old ADF format are not read).") from None
    with file:
        zones = [(k, z) for _, b in _children(file, "CGNSBase_t") for k, z in _children(b, "Zone_t")]
        if not zones:
            raise ValueError(f"{name} has no zone.")
        if len(zones) > 1:
            raise ValueError(f"{name} has {len(zones)} zones; AeroFlowSim reads one zone.")
        base = _children(file, "CGNSBase_t")[0][1]
        if int(_data(base)[0]) != 2:
            raise ValueError(f"{name} is a {int(_data(base)[0])}D CGNS mesh. AeroFlowSim reads only 2D meshes now.")
        zone = zones[0][1]
        if _text(next(v for k, v in _children(zone, "ZoneType_t")), "type") != "C1" or \
                bytes(_data(next(v for k, v in _children(zone, "ZoneType_t")))).decode() != "Unstructured":
            raise ValueError(f"{name} is a structured CGNS zone: only unstructured zones are read.")
        coords = next(v for k, v in _children(zone, "GridCoordinates_t"))
        x, y = np.asarray(_data(coords["CoordinateX"]), dtype=float), np.asarray(_data(coords["CoordinateY"]), dtype=float)
        points = np.column_stack([x, y])
        cells, bars = {TRIANGLE: [], QUAD: []}, []                    # bars: (name, first id, edges)
        for section_name, section in _children(zone, "Elements_t"):
            kind = int(_data(section)[0])
            first, last = (int(v) for v in _data(section["ElementRange"]))
            conn = np.asarray(_data(section["ElementConnectivity"]), dtype=np.int64).ravel()
            if kind == CGNS_TRI:
                cells[TRIANGLE].append(conn.reshape(-1, 3) - 1)
            elif kind == CGNS_QUAD:
                cells[QUAD].append(conn.reshape(-1, 4) - 1)
            elif kind == CGNS_BAR:
                bars.append((section_name, first, conn.reshape(-1, 2) - 1))
            elif kind == CGNS_MIXED:
                k, ids, edges = 0, [], []
                while k < len(conn):
                    t = int(conn[k])
                    n = {CGNS_BAR: 2, CGNS_TRI: 3, CGNS_QUAD: 4}.get(t)
                    if n is None:
                        raise ValueError(f"{name}: section '{section_name}' holds element type {t}: only 2D linear elements are read.")
                    nodes = conn[k + 1:k + 1 + n] - 1
                    (edges if t == CGNS_BAR else cells[TRIANGLE if t == CGNS_TRI else QUAD]).append(nodes)
                    k += n + 1
                if edges:
                    bars.append((section_name, first, np.array(edges)))
            else:
                raise ValueError(f"{name}: section '{section_name}' holds element type {kind}: only linear triangles, "
                                 "quadrilaterals and lines are read.")
        groups = {}
        by_bc = []
        for bc_zone in _children(zone, "ZoneBC_t"):
            for bc_name, bc in _children(bc_zone[1], "BC_t"):
                if "PointRange" in bc:
                    a, b = np.asarray(_data(bc["PointRange"])).ravel()[:2]
                    ids = np.arange(int(a), int(b) + 1)
                elif "PointList" in bc:
                    ids = np.asarray(_data(bc["PointList"]), dtype=np.int64).ravel()
                else:
                    continue
                by_bc.append((bc_name, ids))
        edge_of = {}
        for section_name, first, edges in bars:
            for k, e in enumerate(edges):
                edge_of[first + k] = e
        used = set()
        for bc_name, ids in by_bc:
            found = [edge_of[i] for i in ids if i in edge_of]
            if found:
                groups[bc_name] = np.array(found, dtype=np.int64)
                used.update(int(i) for i in ids)
        for section_name, first, edges in bars:                      # sections that no BC points to: the section is the tag
            rest = [e for k, e in enumerate(edges) if first + k not in used]
            if rest:
                groups[section_name] = np.array(rest, dtype=np.int64)
    out = [(t, np.vstack(c)) for t, c in cells.items() if c]
    if not out:
        raise ValueError(f"{name} has no 2D cells (TRI_3 or QUAD_4 sections).")
    return RawMesh(points, out, groups, "CGNS")


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


def write_cgns(mesh: Mesh, path) -> Path:
    """CGNS/HDF5: base (2, 2), one unstructured zone, coordinates, cell sections, one BAR_2 section and BC per patch."""
    import h5py
    _check_2d(mesh)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cells = _cell_lists(mesh)
    with h5py.File(path, "w") as f:
        f.create_dataset(" format", data=np.frombuffer(b"IEEE_LITTLE_64\0", dtype=np.int8))
        f.create_dataset(" hdf5version", data=np.frombuffer(b"HDF5 Version 1.14.0\0", dtype=np.int8))
        _node(f, "CGNSLibraryVersion", "CGNSLibraryVersion_t", "R4", [4.0])
        base = _node(f, "Base", "CGNSBase_t", "I4", [2, 2])
        zone = _node(base, "Zone", "Zone_t", "I4", [[mesh.n_nodes, mesh.n_cells, 0]])
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
            bc = _node(zbc, patch.name, "BC_t", "C1", np.frombuffer(CGNS_BC.get(patch.type, "BCTypeNull").encode(), dtype=np.int8))
            _node(bc, "PointRange", "IndexRange_t", "I4", [[element], [element + len(edges) - 1]])
            _node(bc, "GridLocation", "GridLocation_t", "C1", np.frombuffer(b"EdgeCenter", dtype=np.int8))
            element += len(edges)
    return path


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
    """Gmsh .msh, ASCII, version "2.2" or "4.1": cells, plus one physical group of edges per patch (named like the patch)."""
    _check_2d(mesh)
    if version not in ("2.2", "4.1"):
        raise ValueError("Gmsh version must be '2.2' or '4.1'.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nodes = mesh.nodes.tolist()                       # python floats: repr() gives all digits, no 'np.float64(...)'
    patches = list(mesh.patches)
    cells = [(code, conn) for code, conn in _cell_lists(mesh) if len(conn)]
    gmsh_type = {TRIANGLE: 2, QUAD: 3}
    out = ["$MeshFormat", f"{version} 0 8", "$EndMeshFormat", "$PhysicalNames", str(len(patches) + 1)]
    out += [f'1 {k} "{p.name}"' for k, p in enumerate(patches, start=1)] + ['2 1 "fluid"', "$EndPhysicalNames"]
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
            for row in conn:
                out.append(f"{element} {gmsh_type[code]} 2 1 1 " + " ".join(str(int(n) + 1) for n in row))
                element += 1
        out.append("$EndElements")
    else:
        arr = mesh.nodes
        lo, hi = arr[:, :2].min(axis=0).tolist(), arr[:, :2].max(axis=0).tolist()
        out += ["$Entities", f"0 {len(patches)} 1 0"]
        for k, p in enumerate(patches, start=1):
            e = mesh.face_nodes[p.faces, :2].ravel()
            a, b = arr[e, :2].min(axis=0).tolist(), arr[e, :2].max(axis=0).tolist()
            out.append(f"{k} {a[0]!r} {a[1]!r} 0 {b[0]!r} {b[1]!r} 0 1 {k} 0")
        out.append(f"1 {lo[0]!r} {lo[1]!r} 0 {hi[0]!r} {hi[1]!r} 0 1 1 {len(patches)} " + " ".join(str(k) for k in range(1, len(patches) + 1)))
        out += ["$EndEntities", "$Nodes", f"1 {len(nodes)} 1 {len(nodes)}", f"2 1 0 {len(nodes)}"]
        out += [str(i + 1) for i in range(len(nodes))] + [f"{x!r} {y!r} 0" for x, y, _ in nodes] + ["$EndNodes"]
        blocks = len(patches) + len(cells)
        n_elements = sum(len(c) for _, c in cells) + sum(p.count for p in patches)
        out += ["$Elements", f"{blocks} {n_elements} 1 {n_elements}"]
        element = 1
        for k, p in enumerate(patches, start=1):
            out.append(f"1 {k} 1 {p.count}")
            for a, b in mesh.face_nodes[p.faces, :2]:
                out.append(f"{element} {a + 1} {b + 1}")
                element += 1
        for code, conn in cells:
            out.append(f"2 1 {gmsh_type[code]} {len(conn)}")
            for row in conn:
                out.append(f"{element} " + " ".join(str(int(n) + 1) for n in row))
                element += 1
        out.append("$EndElements")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def write_su2(mesh: Mesh, path) -> Path:
    """SU2 .su2: the cells, the points and one MARKER_TAG per patch (named like the patch)."""
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
    return f"x {lo[0]:.6g} to {hi[0]:.6g}, y {lo[1]:.6g} to {hi[1]:.6g}"


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
    return Mesh.from_cells(nodes, cell_types, cells, boundary, dim=2, axisymmetric=axisymmetric, info=info)


def import_mesh(path, unit="m", axisymmetric=False, patch_types=None) -> Mesh:
    """read_mesh_file + mesh_from_raw in one call."""
    return mesh_from_raw(read_mesh_file(path), unit, axisymmetric, patch_types)

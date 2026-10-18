# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh containers.

Mesh1D: a list of node positions along x (used by the 1D cases).
Mesh2D: a structured grid of node arrays (used only by the 2D contour plot; superseded by Mesh).
Mesh:   THE face-based finite-volume mesh (2D, axisymmetric and 3D). Every mesh generator
        produces one and every 2D/3D solver will use one. See the Mesh class below.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Mesh1D:
    """A 1D mesh: node positions along the axis."""

    x: np.ndarray  # node positions [m], increasing

    @property
    def n_nodes(self) -> int:
        """Number of nodes."""
        return len(self.x)

    @property
    def n_cells(self) -> int:
        """Number of cells (intervals between neighbouring nodes)."""
        return len(self.x) - 1

    @property
    def dx(self) -> np.ndarray:
        """Spacing between neighbouring nodes [m] (length n_nodes - 1)."""
        return np.diff(self.x)

    @property
    def xc(self) -> np.ndarray:
        """Cell centres [m] (length n_nodes - 1), halfway between neighbouring nodes.

        Finite-volume cases store one value per cell; the nodes are then the cell faces.
        """
        return 0.5 * (self.x[:-1] + self.x[1:])

    def positions(self, n_values: int) -> np.ndarray:
        """x positions [m] for a field with n_values entries: nodes or cell centres.

        Lets plots and CSV files handle node-based fields (e.g. the heat demo) and
        cell-based fields (finite-volume cases) with the same code.
        """
        if n_values == self.n_nodes:
            return self.x
        if n_values == self.n_cells:
            return self.xc
        raise ValueError(f"A field with {n_values} values does not fit this mesh "
                         f"({self.n_nodes} nodes, {self.n_cells} cells).")


@dataclass
class Mesh2D:
    """A structured 2D mesh: node coordinates stored as 2D arrays of shape (ni, nj).

    Node (i, j) sits at (x[i, j], y[i, j]). Grid lines run along i (fixed j) and along j (fixed i).
    For an axisymmetric nozzle, x is the axial position and y the radius.
    """

    x: np.ndarray  # node x coordinates [m], shape (ni, nj)
    y: np.ndarray  # node y coordinates [m], shape (ni, nj)

    @property
    def n_nodes(self) -> int:
        """Number of nodes."""
        return self.x.size

    @property
    def n_cells(self) -> int:
        """Number of quadrilateral cells."""
        ni, nj = self.x.shape
        return (ni - 1) * (nj - 1)


# =============================================================================================
# Face-based finite-volume mesh (OpenFOAM-style), for 2D, axisymmetric and 3D solvers
# =============================================================================================
#
# In plain words:
#   node       a corner point, stored as (x, y, z) [m]. 2D meshes lie in the plane z = 0.
#   cell       a small volume (control volume) made of nodes: triangle or quad in 2D;
#              tetrahedron, hexahedron, prism (wedge) or pyramid in 3D.
#   face       the boundary between two cells (in 2D an edge, swept 1 m in z; in 3D a polygon).
#              Each face is stored ONCE. Its "owner" is the lower-numbered cell next to it, its
#              "neighbour" the other cell (-1 on the outer boundary). The face normal points
#              from the owner into the neighbour (and out of the domain on the boundary).
#   patch      a named group of boundary faces with a type (inlet, outlet, wall, axis, ...),
#              so a solver knows which boundary condition to apply where.
#
# A finite-volume solver then loops over FACES: it computes one flux per face, adds it to the
# owner and subtracts it from the neighbour. The same loop works in 2D and 3D.
#
# Cell types use the VTK numbers and VTK node ordering, so ParaView files need no conversion.

TRIANGLE, QUAD = 5, 9                              # 2D cells
TETRA, HEXAHEDRON, WEDGE, PYRAMID = 10, 12, 13, 14  # 3D cells (WEDGE = triangular prism)

PATCH_TYPES = ("inlet", "outlet", "wall", "axis", "farfield", "symmetry")

MAX_CELL_NODES = 8   # a hexahedron has the most nodes; shorter node lists are padded with -1
MAX_FACE_NODES = 4   # a quad face has the most nodes; edges (2) and triangles (3) are padded with -1
DEPTH_2D = 1.0       # 2D meshes are 1 m deep in z: face area = edge length x 1 m [m]
Z_UNIT = np.array([0.0, 0.0, 1.0])
MESH_FORMAT_VERSION = 1   # stored in mesh.npz, so old files can be recognised later


@dataclass(frozen=True)
class CellType:
    """One kind of cell: how many nodes it has and which nodes form each of its faces.

    faces lists the local node numbers of every face, ordered so that the right-hand rule
    gives a normal pointing OUT of the cell (for a cell whose nodes follow the VTK ordering;
    2D cells: nodes counter-clockwise seen from +z).
    """

    name: str
    dim: int        # 2 or 3
    n_nodes: int
    faces: tuple


CELL_TYPES = {
    TRIANGLE: CellType("triangle", 2, 3, ((0, 1), (1, 2), (2, 0))),
    QUAD: CellType("quad", 2, 4, ((0, 1), (1, 2), (2, 3), (3, 0))),
    TETRA: CellType("tetrahedron", 3, 4, ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))),
    HEXAHEDRON: CellType("hexahedron", 3, 8, ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                                              (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))),
    WEDGE: CellType("prism", 3, 6, ((0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0))),
    PYRAMID: CellType("pyramid", 3, 5, ((0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4))),
}


@dataclass
class Patch:
    """A named group of boundary faces. Its faces are numbered start, start+1, ..., start+count-1."""

    name: str    # e.g. "wall"
    type: str    # one of PATCH_TYPES
    start: int   # first face number
    count: int   # number of faces

    @property
    def faces(self) -> np.ndarray:
        """Face numbers of this patch."""
        return np.arange(self.start, self.start + self.count)


class Mesh:
    """A face-based finite-volume mesh. All data are NumPy arrays (fast, and easy to save).

    Stored (the "topology"):
        nodes         (N, 3) node coordinates [m]
        cell_types    (C,)   VTK cell type number of every cell (QUAD, TRIANGLE, HEXAHEDRON, ...)
        cell_nodes    (C, 8) node numbers of every cell, padded with -1
        face_nodes    (F, 4) node numbers of every face, padded with -1, ordered so the normal
                             points from owner to neighbour
        owner         (F,)   cell on the normal's tail side of each face
        neighbour     (F,)   cell on the other side; -1 for boundary faces
        patches       list of Patch. Faces are ordered: all interior faces first, then the
                      boundary faces patch by patch (as in OpenFOAM).
        dim           2 or 3
        axisymmetric  True: 2D mesh in the (x, r) plane, axis along x, r = y >= 0
        info          dict of extra facts from the generator (e.g. inflation settings)

    Computed once from the topology (the "geometry"):
        face_centres (F, 3) [m], face_normals (F, 3) unit vectors, face_areas (F,) [m²]
        cell_centres (C, 3) centroids [m], cell_volumes (C,) [m³]
        face_deltas  (F, 3) owner centre -> neighbour centre (boundary: -> face centre) [m]
        axi_face_areas   (F,) face area x r of the face centre [m³ per radian]   (axisymmetric only)
        axi_cell_volumes (C,) cell volume x r of the cell centroid [m⁴ per radian] (axisymmetric only)
    In 2D the mesh is 1 m deep: a face area is the edge length x 1 m, a cell volume the cell area x 1 m.
    The axisymmetric values are exact for straight-edged cells (theorem of Pappus): revolving a
    cell by one radian about the axis sweeps the volume  area x r_centroid.

    Build a mesh with Mesh.from_cells(...); a generator only supplies nodes, cells and boundary tags.
    """

    def __init__(self, nodes, cell_types, cell_nodes, face_nodes, owner, neighbour, patches,
                 dim, axisymmetric=False, info=None):
        self.nodes = np.asarray(nodes, dtype=float)
        self.cell_types = np.asarray(cell_types, dtype=np.int32)
        self.cell_nodes = np.asarray(cell_nodes, dtype=np.int64)
        self.face_nodes = np.asarray(face_nodes, dtype=np.int64)
        self.owner = np.asarray(owner, dtype=np.int64)
        self.neighbour = np.asarray(neighbour, dtype=np.int64)
        self.patches = list(patches)
        self.dim = int(dim)
        self.axisymmetric = bool(axisymmetric)
        self.info = dict(info or {})
        self._check_topology()
        self._compute_geometry()

    # ---- building a mesh from cells ---------------------------------------------------------

    @classmethod
    def from_cells(cls, nodes, cell_types, cell_nodes, boundary, dim=None, axisymmetric=False, info=None):
        """Build a Mesh from nodes, cells and boundary tags; the faces are found automatically.

        nodes       (N, 2) or (N, 3) coordinates [m] (2D input gets z = 0)
        cell_types  (C,) VTK cell type of each cell (or one number for all cells)
        cell_nodes  (C, k) node numbers of each cell in VTK order (pad with -1 for mixed types)
        boundary    {patch name: (patch type, face node array (n, 2..4))}: the boundary faces of
                    each patch, given by their nodes in any order. Every boundary face must be
                    in exactly one patch.
        dim         2 or 3; None = taken from the cell types
        """
        nodes = np.asarray(nodes, dtype=float)
        if nodes.ndim != 2 or nodes.shape[1] not in (2, 3):
            raise ValueError("nodes must have shape (N, 2) or (N, 3).")
        if nodes.shape[1] == 2:
            nodes = np.column_stack([nodes, np.zeros(len(nodes))])
        cell_nodes = np.atleast_2d(np.asarray(cell_nodes, dtype=np.int64))
        if cell_nodes.ndim != 2 or cell_nodes.shape[1] > MAX_CELL_NODES:
            raise ValueError(f"cell_nodes must have shape (C, k) with k <= {MAX_CELL_NODES}.")
        padded = np.full((len(cell_nodes), MAX_CELL_NODES), -1, dtype=np.int64)
        padded[:, :cell_nodes.shape[1]] = cell_nodes
        cell_types = np.broadcast_to(np.asarray(cell_types, dtype=np.int32), (len(padded),)).copy()
        unknown = sorted(set(np.unique(cell_types).tolist()) - set(CELL_TYPES))
        if unknown:
            raise ValueError(f"Unknown cell type(s) {unknown}; known: {sorted(CELL_TYPES)}.")
        if dim is None:
            dims = {CELL_TYPES[t].dim for t in np.unique(cell_types).tolist()}
            dim = dims.pop() if len(dims) == 1 else 0   # 0: mixed 2D/3D cells, rejected below

        face_nodes, owner, neighbour = _find_faces(cell_types, padded)
        face_nodes, owner, neighbour, patches = _sort_faces_into_patches(face_nodes, owner, neighbour, boundary)
        return cls(nodes, cell_types, padded, face_nodes, owner, neighbour, patches, dim, axisymmetric, info)

    def _check_topology(self):
        """Raise ValueError if the arrays do not describe a consistent mesh."""
        if self.dim not in (2, 3):
            raise ValueError("A mesh must be 2D or 3D, with all cells of that dimension.")
        if self.nodes.ndim != 2 or self.nodes.shape[1] != 3:
            raise ValueError("nodes must have shape (N, 3).")
        for code in np.unique(self.cell_types).tolist():
            if code not in CELL_TYPES:
                raise ValueError(f"Unknown cell type {code}.")
            ct = CELL_TYPES[code]
            if ct.dim != self.dim:
                raise ValueError(f"A {self.dim}D mesh cannot contain {ct.name} cells.")
            rows = self.cell_nodes[self.cell_types == code]
            if np.any(rows[:, :ct.n_nodes] < 0) or np.any(rows[:, ct.n_nodes:] >= 0):
                raise ValueError(f"Every {ct.name} cell needs exactly {ct.n_nodes} node numbers.")
        if self.cell_nodes.max(initial=-1) >= self.n_nodes:
            raise ValueError("A cell refers to a node number that does not exist.")
        if self.axisymmetric and (self.dim != 2 or self.nodes[:, 1].min(initial=0.0) < 0.0):
            raise ValueError("An axisymmetric mesh must be 2D with r = y >= 0 everywhere.")
        if np.any(self.neighbour[:self.n_interior_faces] < 0):
            raise ValueError("Interior faces (with a neighbour) must come before the boundary faces.")
        boundary_faces = sum(p.count for p in self.patches)
        if self.n_interior_faces + boundary_faces != self.n_faces:
            raise ValueError("Every boundary face must belong to exactly one patch.")
        for p in self.patches:
            if p.type not in PATCH_TYPES:
                raise ValueError(f"Patch '{p.name}': type '{p.type}' is not one of {', '.join(PATCH_TYPES)}.")

    # ---- sizes and helpers -------------------------------------------------------------------

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def n_cells(self) -> int:
        return len(self.cell_types)

    @property
    def n_faces(self) -> int:
        return len(self.owner)

    @property
    def n_interior_faces(self) -> int:
        """Interior faces come first, so faces 0 .. n_interior_faces-1 have a neighbour."""
        return int(np.count_nonzero(self.neighbour >= 0))

    @property
    def face_area_vectors(self) -> np.ndarray:
        """Unit normal x area of every face (F, 3) [m²]."""
        return self.face_normals * self.face_areas[:, None]

    def patch(self, name) -> Patch:
        """The patch with this name (KeyError if there is none)."""
        for p in self.patches:
            if p.name == name:
                return p
        raise KeyError(f"No patch '{name}'. Patches: {', '.join(p.name for p in self.patches)}")

    def face_patch_index(self) -> np.ndarray:
        """(F,) index into self.patches of every face; -1 for interior faces."""
        index = np.full(self.n_faces, -1, dtype=np.int64)
        for k, p in enumerate(self.patches):
            index[p.start:p.start + p.count] = k
        return index

    def memory_bytes(self) -> int:
        """Approximate memory used by the mesh arrays [bytes]."""
        return sum(v.nbytes for v in vars(self).values() if isinstance(v, np.ndarray))

    # ---- geometry ----------------------------------------------------------------------------

    def _compute_geometry(self):
        """Face centres, normals and areas; cell centroids and volumes; axisymmetric metrics."""
        self.face_centres, area_vectors = _face_geometry(self.nodes, self.face_nodes)
        self.face_areas = np.linalg.norm(area_vectors, axis=1)                       # [m²]
        safe = np.where(self.face_areas > 0.0, self.face_areas, 1.0)
        self.face_normals = area_vectors / safe[:, None]
        self.cell_volumes, self.cell_centres = _cell_geometry(self, area_vectors)    # [m³], [m]

        interior = self.neighbour >= 0
        self.face_deltas = self.face_centres - self.cell_centres[self.owner]         # [m]
        self.face_deltas[interior] = (self.cell_centres[self.neighbour[interior]]
                                      - self.cell_centres[self.owner[interior]])
        if self.axisymmetric:
            self.axi_face_areas = self.face_areas * self.face_centres[:, 1]          # [m³/rad]
            self.axi_cell_volumes = self.cell_volumes * self.cell_centres[:, 1]      # [m⁴/rad]
        else:
            self.axi_face_areas = self.axi_cell_volumes = None

    # ---- save / load -------------------------------------------------------------------------

    def save(self, path) -> Path:
        """Save the mesh to a .npz file (the geometry is recomputed when loading)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path, format_version=MESH_FORMAT_VERSION, nodes=self.nodes, cell_types=self.cell_types,
            cell_nodes=self.cell_nodes, face_nodes=self.face_nodes, owner=self.owner, neighbour=self.neighbour,
            patch_names=np.array([p.name for p in self.patches], dtype=str),
            patch_types=np.array([p.type for p in self.patches], dtype=str),
            patch_starts=np.array([p.start for p in self.patches], dtype=np.int64),
            patch_counts=np.array([p.count for p in self.patches], dtype=np.int64),
            dim=self.dim, axisymmetric=self.axisymmetric, info=json.dumps(self.info))
        return path

    @classmethod
    def load(cls, path) -> "Mesh":
        """Read a mesh saved with Mesh.save()."""
        with np.load(Path(path), allow_pickle=False) as data:
            if int(data["format_version"]) > MESH_FORMAT_VERSION:
                raise ValueError(f"{path} was written by a newer AeroFlowSim (mesh format "
                                 f"{int(data['format_version'])}); please update AeroFlowSim.")
            patches = [Patch(str(n), str(t), int(s), int(c)) for n, t, s, c in
                       zip(data["patch_names"], data["patch_types"], data["patch_starts"], data["patch_counts"])]
            return cls(data["nodes"], data["cell_types"], data["cell_nodes"], data["face_nodes"],
                       data["owner"], data["neighbour"], patches, int(data["dim"]),
                       bool(data["axisymmetric"]), json.loads(str(data["info"])))

    def __repr__(self):
        kind = "axisymmetric" if self.axisymmetric else f"{self.dim}D"
        return f"Mesh({kind}, {self.n_cells} cells, {self.n_faces} faces, {self.n_nodes} nodes)"


def _find_faces(cell_types, cell_nodes):
    """Find every face once from the cells' local faces.

    Every cell lists its faces (CellType.faces). A face shared by two cells appears twice, with
    the same nodes (in the opposite order). Sorting each face's node numbers gives a "key" that
    is the same for both copies; np.unique then finds the pairs. The first copy (from the
    lower-numbered cell) becomes the face, with that cell as owner, so the normal points out of
    the owner. Returns face_nodes (F, 4), owner (F,), neighbour (F,) (-1 = boundary).
    """
    rows, cells = [], []
    for code in np.unique(cell_types).tolist():
        ids = np.flatnonzero(cell_types == code)
        for local in CELL_TYPES[code].faces:
            face = np.full((len(ids), MAX_FACE_NODES), -1, dtype=np.int64)
            face[:, :len(local)] = cell_nodes[ids][:, list(local)]
            rows.append(face)
            cells.append(ids)
    faces, cells = np.concatenate(rows), np.concatenate(cells)
    order = np.argsort(cells, kind="stable")   # by cell number: the first copy is the owner's
    faces, cells = faces[order], cells[order]

    keys = np.sort(faces, axis=1)
    _, first, inverse, counts = np.unique(keys, axis=0, return_index=True, return_inverse=True,
                                          return_counts=True)
    inverse = inverse.reshape(-1)
    if np.any(counts > 2):
        raise ValueError("A face is shared by more than two cells: the cells overlap or are duplicated.")
    face_nodes, owner = faces[first], cells[first]
    neighbour = np.full(len(first), -1, dtype=np.int64)
    second = np.flatnonzero(np.arange(len(faces)) != first[inverse])   # the second copies
    neighbour[inverse[second]] = cells[second]
    return face_nodes, owner, neighbour


def _face_key(nodes_of_face):
    """Order-independent key of a face: its node numbers sorted, padded to MAX_FACE_NODES."""
    key = np.full(MAX_FACE_NODES, -1, dtype=np.int64)
    key[:len(nodes_of_face)] = nodes_of_face
    return tuple(np.sort(key).tolist())


def _sort_faces_into_patches(face_nodes, owner, neighbour, boundary):
    """Order the faces (interior first, then patch by patch) and make the Patch list."""
    interior = np.flatnonzero(neighbour >= 0)
    interior = interior[np.lexsort((neighbour[interior], owner[interior]))]   # by owner, then neighbour
    boundary_faces = np.flatnonzero(neighbour < 0)
    lookup = {_face_key(f[f >= 0]): i for i, f in zip(boundary_faces.tolist(), face_nodes[boundary_faces])}

    order, patches, used = [interior], [], set()
    start = len(interior)
    for name, (patch_type, tagged) in boundary.items():
        tagged = np.atleast_2d(np.asarray(tagged, dtype=np.int64))
        ids = []
        for f in tagged:
            key = _face_key(f[f >= 0])
            if key not in lookup:
                raise ValueError(f"Patch '{name}': the face with nodes {f[f >= 0].tolist()} is not a "
                                 "boundary face of the mesh.")
            if lookup[key] in used:
                raise ValueError(f"Patch '{name}': the face with nodes {f[f >= 0].tolist()} is already "
                                 "in a patch (each boundary face belongs to exactly one patch).")
            used.add(lookup[key])
            ids.append(lookup[key])
        order.append(np.array(ids, dtype=np.int64))
        patches.append(Patch(name, patch_type, start, len(ids)))
        start += len(ids)
    missing = len(boundary_faces) - len(used)
    if missing:
        raise ValueError(f"{missing} boundary face(s) are in no patch. Every boundary face needs a patch "
                         "(inlet, outlet, wall, axis, ...).")
    order = np.concatenate(order)
    return face_nodes[order], owner[order], neighbour[order], patches


def _face_geometry(nodes, face_nodes):
    """Centre (F, 3) [m] and area vector (F, 3) [m²] of every face.

    Edge faces (2 nodes, 2D meshes): the edge a->b swept DEPTH_2D in z; area vector = (b - a) x z.
    Polygon faces (3 or 4 nodes, 3D meshes): split into triangles around the mean point; the area
    vector is the sum of the triangles' area vectors, the centre their area-weighted centroid.
    """
    n_face = len(face_nodes)
    centres, area_vectors = np.zeros((n_face, 3)), np.zeros((n_face, 3))
    counts = np.count_nonzero(face_nodes >= 0, axis=1)
    for k in np.unique(counts).tolist():
        sel = counts == k
        points = nodes[face_nodes[sel, :k]]               # (m, k, 3)
        if k == 2:
            a, b = points[:, 0], points[:, 1]
            centres[sel] = 0.5 * (a + b)
            area_vectors[sel] = np.cross(b - a, Z_UNIT) * DEPTH_2D
            continue
        mean = points.mean(axis=1)
        total, moment, weight = np.zeros_like(mean), np.zeros_like(mean), np.zeros(len(mean))
        for i in range(k):
            p, q = points[:, i], points[:, (i + 1) % k]
            triangle = 0.5 * np.cross(p - mean, q - mean)    # area vector of one triangle [m²]
            size = np.linalg.norm(triangle, axis=1)
            total += triangle
            moment += size[:, None] * (p + q + mean) / 3.0
            weight += size
        area_vectors[sel] = total
        centres[sel] = moment / np.where(weight > 0.0, weight, 1.0)[:, None]
    return centres, area_vectors


def _cell_geometry(mesh, area_vectors):
    """Signed volume (C,) [m³] and centroid (C, 3) [m] of every cell, from its faces.

    Each cell is split into one pyramid per face (in 2D: one triangle per edge), with its tip at
    the mean of the cell's nodes. A pyramid has volume  (1/dim) x area x height  and its centroid
    lies dim/(dim+1) of the way from the tip to the face centre - the same formula in 2D and 3D.
    The height is measured along the cell's OUTWARD normal, so a cell whose nodes are in the wrong
    order (an inverted, "inside-out" cell) gets a negative volume, which the mesh checks report.
    """
    dim = mesh.dim
    used = mesh.cell_nodes >= 0
    tips = (np.where(used[..., None], mesh.nodes[np.maximum(mesh.cell_nodes, 0)], 0.0).sum(axis=1)
            / used.sum(axis=1)[:, None])                   # mean of the nodes of each cell [m]
    volume = np.zeros(mesh.n_cells)
    moment = np.zeros((mesh.n_cells, 3))
    interior = mesh.neighbour >= 0
    for cells, faces, sign in ((mesh.owner, slice(None), 1.0),
                               (mesh.neighbour[interior], interior, -1.0)):   # neighbour: normal points in
        to_face = mesh.face_centres[faces] - tips[cells]
        pyramid = sign * np.einsum("ij,ij->i", area_vectors[faces], to_face) / dim   # [m³]
        centroid = tips[cells] + dim / (dim + 1.0) * to_face
        volume += np.bincount(cells, pyramid, minlength=mesh.n_cells)
        for axis in range(3):
            moment[:, axis] += np.bincount(cells, pyramid * centroid[:, axis], minlength=mesh.n_cells)
    safe = np.where(volume != 0.0, volume, 1.0)
    centres = np.where(volume[:, None] != 0.0, moment / safe[:, None], tips)
    return volume, centres

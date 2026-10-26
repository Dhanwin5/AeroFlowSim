# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Named surfaces: where results are plotted, integrated and monitored.

A Surface is a GEOMETRIC definition (stored in the project, key `surfaces`), re-evaluated on whatever mesh the
project has now, so it survives re-meshing:

    boundary   one or more named boundaries (patches) of the mesh
    line       a straight line between two points
    rake       a line with N evenly spaced seed points (streamline seeds; integrates like a line)
    point      a probe point
    iso        an iso-line: where a field has a given value (from the node values, marching triangles)
    x_line     the line x = c across the whole domain     y_line   the line y = c across the domain

evaluate_surface() turns a Surface into SurfaceData on a Solution: a list of straight SEGMENTS, each inside one
cell (lines and iso-lines) or on one boundary face (boundaries), with its unit normal. Plots sample the segments'
ends; integrals use 2-point Gauss points on each segment (integrals.py).

Normals: a boundary's normal points OUT of the domain (as the solver's); a line's normal is its direction turned
90 deg clockwise, so a line drawn upwards (+y) has its normal along +x (flow left to right counts positive);
an iso-line's normal is along the field gradient.
"""

import dataclasses
from dataclasses import dataclass

import numpy as np

from aeroflowsim.post.sampling import cut_line, locate

TYPES = ("boundary", "line", "rake", "point", "iso", "x_line", "y_line")
TYPE_LABELS = {"boundary": "Boundary", "line": "Line", "rake": "Rake", "point": "Point (probe)",
               "iso": "Iso-line", "x_line": "Line x = constant", "y_line": "Line y = constant"}


@dataclass
class Surface:
    """A named surface definition (see the module docstring). Coordinates in metres (SI)."""

    name: str
    type: str
    patches: list = dataclasses.field(default_factory=list)      # boundary
    start: tuple = (0.0, 0.0)                        # line, rake: first point [m]; point: the point
    end: tuple = (0.0, 0.0)                          # line, rake: second point [m]
    n_points: int = 10                               # rake: number of seed points
    field: str = ""                                  # iso: field name
    value: float = 0.0                               # iso: field value [SI]; x_line / y_line: c [m]
    visible: bool = True                             # shown in the Results view

    def __post_init__(self):
        if self.type not in TYPES:
            raise ValueError(f"'{self.type}' is not a surface type; use one of {', '.join(TYPES)}.")
        self.start = tuple(float(v) for v in self.start)
        self.end = tuple(float(v) for v in self.end)
        self.patches = [str(p) for p in self.patches]

    # convenient constructors
    @classmethod
    def boundary(cls, *patches, name=None):
        return cls(name or "+".join(patches), "boundary", patches=list(patches))

    @classmethod
    def line(cls, start, end, name="line"):
        return cls(name, "line", start=tuple(start), end=tuple(end))

    @classmethod
    def rake(cls, start, end, n_points=10, name="rake"):
        return cls(name, "rake", start=tuple(start), end=tuple(end), n_points=int(n_points))

    @classmethod
    def point(cls, xy, name="point"):
        return cls(name, "point", start=tuple(xy))

    @classmethod
    def iso(cls, field_name, value, name=None):
        return cls(name or f"{field_name} = {value:g}", "iso", field=field_name, value=float(value))

    @classmethod
    def x_line(cls, c, name=None):
        return cls(name or f"x = {c:g} m", "x_line", value=float(c))

    @classmethod
    def y_line(cls, c, name=None):
        return cls(name or f"y = {c:g} m", "y_line", value=float(c))

    def to_dict(self) -> dict:
        d = {"name": self.name, "type": self.type, "visible": self.visible}
        if self.type == "boundary":
            d["patches"] = list(self.patches)
        if self.type in ("line", "rake", "point"):
            d["start"] = [float(v) for v in self.start]
        if self.type in ("line", "rake"):
            d["end"] = [float(v) for v in self.end]
        if self.type == "rake":
            d["n_points"] = int(self.n_points)
        if self.type == "iso":
            d["field"] = self.field
        if self.type in ("iso", "x_line", "y_line"):
            d["value"] = float(self.value)
        return d

    @classmethod
    def from_dict(cls, d) -> "Surface":
        d = dict(d)
        known = {"name", "type", "patches", "start", "end", "n_points", "field", "value", "visible"}
        return cls(**{k: (tuple(v) if k in ("start", "end") else v) for k, v in d.items() if k in known})

    def describe(self, length_unit="m", scale=1.0) -> str:
        """One line in plain words (coordinates in the given display unit: value x scale)."""
        f = lambda v: f"{v * scale:.4g}"
        if self.type == "boundary":
            return "Boundary: " + ", ".join(self.patches)
        if self.type == "point":
            return f"Point ({f(self.start[0])}, {f(self.start[1])}) {length_unit}"
        if self.type in ("line", "rake"):
            text = (f"{TYPE_LABELS[self.type]} ({f(self.start[0])}, {f(self.start[1])}) to "
                    f"({f(self.end[0])}, {f(self.end[1])}) {length_unit}")
            return text + (f", {self.n_points} seeds" if self.type == "rake" else "")
        if self.type == "iso":
            return f"Iso-line {self.field} = {self.value:g} (SI)"
        return f"{'x' if self.type == 'x_line' else 'y'} = {f(self.value)} {length_unit}"

    def problem(self, sol) -> str:
        """'' if the surface can be evaluated on this solution's mesh, else why not (plain words)."""
        if self.type == "boundary":
            names = {p.name for p in sol.mesh.patches}
            missing = [p for p in self.patches if p not in names]
            if not self.patches:
                return "Choose at least one boundary."
            if missing:
                return (f"The mesh has no boundary called {', '.join(missing)} (it has: "
                        f"{', '.join(sorted(names))}).")
        if self.type in ("line", "rake") and np.allclose(self.start, self.end):
            return "The two points of the line are the same."
        if self.type == "rake" and self.n_points < 1:
            return "A rake needs at least one seed point."
        if self.type == "iso":
            from aeroflowsim.post.fields import FieldError, field_info
            try:
                field_info(sol, self.field)
            except FieldError as exc:
                return str(exc)
        return ""


@dataclass
class SurfaceData:
    """A surface evaluated on a mesh: straight segments, each in one cell or on one boundary face."""

    surface: Surface
    a: np.ndarray            # (n, 2) segment starts [m]
    b: np.ndarray            # (n, 2) segment ends [m]
    cells: np.ndarray        # (n,) cell of each segment (boundary: the owner cell)
    normals: np.ndarray      # (n, 2) unit normals
    faces: np.ndarray        # (n,) boundary-local face index, or -1 for segments inside the domain
    seeds: np.ndarray = None  # (k, 2) seed / probe points (rake, point)

    @property
    def n(self) -> int:
        return len(self.cells)

    @property
    def lengths(self) -> np.ndarray:
        return np.linalg.norm(self.b - self.a, axis=1)

    @property
    def on_boundary(self) -> bool:
        return self.n > 0 and bool(np.all(self.faces >= 0))

    def arc_length(self) -> tuple:
        """(s at segment starts, s at segment ends) [m], measured along the ordered segments."""
        L = self.lengths
        s1 = np.cumsum(L)
        return s1 - L, s1


def _domain_box(sol):
    nodes = sol.mesh.nodes[:, :2]
    lo, hi = nodes.min(axis=0), nodes.max(axis=0)
    pad = 1e-9 * max(float(np.max(hi - lo)), 1e-12)
    return lo - pad, hi + pad


def _line_data(sol, surface, start, end, seeds=None):
    pieces = cut_line(sol, start, end)
    a, b = pieces.points(pieces.t0), pieces.points(pieces.t1)
    n = np.repeat(pieces.normal[None, :], len(a), axis=0)
    return SurfaceData(surface, a, b, pieces.cells, n, np.full(len(a), -1), seeds)


def _boundary_data(sol, surface):
    g, mesh = sol.geom, sol.mesh
    parts = []
    for name in surface.patches:
        local = sol.patch_faces(name)
        faces = g.boundary_faces[local]
        fn = mesh.face_nodes[faces, :2]
        a, b = mesh.nodes[fn[:, 0], :2], mesh.nodes[fn[:, 1], :2]
        parts.append((a, b, g.boundary_owner[local], g.normals[faces, :2], local))
    if not parts:
        return SurfaceData(surface, np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0, int), np.zeros((0, 2)),
                           np.zeros(0, int))
    a, b, c, n, f = (np.concatenate(x) for x in zip(*parts))
    order = _chain_order(a, b)
    return SurfaceData(surface, a[order], b[order], c[order], n[order], f[order])


def _chain_order(a, b):
    """Order boundary segments by position along the boundary (mostly x, then y) so plots and arc lengths run
    smoothly: sort by the segment centre's x (ties by y). Good for walls of nozzles and bodies seen from the side."""
    mid = 0.5 * (a + b)
    return np.lexsort((mid[:, 1], mid[:, 0]))


def _iso_data(sol, surface):
    """Marching triangles on the node values: each cell is split into triangles (fan from its first corner); in
    each triangle where the field crosses the value, one segment joins the two crossing points."""
    from aeroflowsim.post.fields import node_values
    nv = node_values(sol, surface.field)
    mesh = sol.mesh
    cn = mesh.cell_nodes
    counts = (cn >= 0).sum(axis=1)
    A, B, C = [], [], []
    for k in range(1, cn.shape[1] - 1):
        use = counts > k + 1
        cells = np.flatnonzero(use)
        tri = np.column_stack([cn[cells, 0], cn[cells, k], cn[cells, k + 1]])
        A.append(cells), B.append(tri)
    if not A:
        return SurfaceData(surface, np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0, int), np.zeros((0, 2)),
                           np.zeros(0, int))
    cells, tri = np.concatenate(A), np.concatenate(B)
    f = nv[tri] - surface.value                          # (T, 3)
    xy = mesh.nodes[tri, :2]                             # (T, 3, 2)
    pts, owners = [], []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        cross = (f[:, i] * f[:, j] < 0.0) | ((f[:, i] == 0.0) & (f[:, j] != 0.0))
        t = np.where(cross, f[:, i] / np.where(cross, f[:, i] - f[:, j], 1.0), np.nan)
        pts.append(xy[:, i] + t[:, None] * (xy[:, j] - xy[:, i]))
    P = np.stack(pts, axis=1)                            # (T, 3, 2) with NaN where no crossing
    has = ~np.isnan(P[:, :, 0])
    two = has.sum(axis=1) == 2
    P, has, cells = P[two], has[two], cells[two]
    first = np.argmax(has, axis=1)
    second = 2 - np.argmax(has[:, ::-1], axis=1)
    a = P[np.arange(len(P)), first]
    b = P[np.arange(len(P)), second]
    keep = np.linalg.norm(b - a, axis=1) > 0.0
    a, b, cells = a[keep], b[keep], cells[keep]
    from aeroflowsim.post.sampling import field_gradient
    g = field_gradient(sol, surface.field)[:, cells].T
    gn = np.linalg.norm(g, axis=1)
    normals = np.where(gn[:, None] > 0.0, g / np.where(gn > 0.0, gn, 1.0)[:, None], 0.0)
    return SurfaceData(surface, a, b, cells, normals, np.full(len(a), -1))


def evaluate_surface(sol, surface) -> SurfaceData:
    """The surface on this solution's mesh (raises ValueError in plain words if it cannot be made)."""
    problem = surface.problem(sol)
    if problem:
        raise ValueError(f"Surface '{surface.name}': {problem}")
    cache = sol._cache.setdefault("surfaces", {})
    key = repr(sorted(surface.to_dict().items()))
    if key in cache:
        return cache[key]
    if surface.type == "boundary":
        data = _boundary_data(sol, surface)
    elif surface.type in ("line", "rake"):
        seeds = None
        if surface.type == "rake":
            t = np.linspace(0.0, 1.0, surface.n_points) if surface.n_points > 1 else np.array([0.5])
            seeds = np.asarray(surface.start)[None, :] + t[:, None] * (np.subtract(surface.end, surface.start))[None, :]
        data = _line_data(sol, surface, surface.start, surface.end, seeds)
    elif surface.type in ("x_line", "y_line"):
        lo, hi = _domain_box(sol)
        c = surface.value
        start, end = ((c, lo[1]), (c, hi[1])) if surface.type == "x_line" else ((lo[0], c), (hi[0], c))
        data = _line_data(sol, surface, start, end)
    elif surface.type == "point":
        p = np.asarray(surface.start, dtype=float)[None, :]
        cell = locate(sol, p)
        data = SurfaceData(surface, p.copy(), p.copy(), cell, np.zeros((1, 2)), np.full(1, -1), p.copy())
    else:
        data = _iso_data(sol, surface)
    cache[key] = data
    return data


def default_surfaces(sol) -> list:
    """One boundary surface per patch of the mesh (always available, not stored)."""
    return [Surface.boundary(p.name) for p in sol.mesh.patches]


def surfaces_from(dicts) -> list:
    """Surfaces from their stored dicts; broken entries are skipped (an old project never fails to open)."""
    out = []
    for d in dicts or []:
        try:
            out.append(Surface.from_dict(d))
        except (TypeError, ValueError):
            continue
    return out

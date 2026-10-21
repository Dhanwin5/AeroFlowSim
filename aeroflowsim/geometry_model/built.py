# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The result of replaying a geometry document: plain Python data (no Gmsh, no Qt).

After the history has been replayed in the CAD kernel (kernel.py), everything the GUI, the
picking code, the checks and the tests need is copied into these objects:

    Vertex   a point where edges meet (id, x y [m])
    Edge     one curve: a stable id, its kind (line, arc, spline ...), points along it for drawing
             and picking, its length, which faces use it, and the boundary name it gets
    Face     a closed region: its role ("fluid" = to be meshed, "solid" = a body that is cut out),
             its loops of edges (outer first, then holes), area and centroid (exact, from the kernel)
    Region   a refinement region (box, circle, wake line) with a target cell size
    BuiltGeometry  all of the above + the planar/axisymmetric flag and messages for the user

Edge ids are STABLE: they say where an edge came from (see kernel.py, "lineage"), e.g.
"op1:wall.2" (the 2nd wall curve made by operation op1) or "op1:body.3#2" (the 2nd piece of it
after a boolean). Named boundaries refer to these ids, so they survive later edits.

Coordinates are metres. The data is 2D (x, y) now; Phase 3 adds a z column and 3D faces.
"""

from dataclasses import dataclass, field

import numpy as np

FLUID, SOLID = "fluid", "solid"     # face roles


@dataclass
class Vertex:
    id: str
    xy: np.ndarray                  # (2,) [m]
    edges: list = field(default_factory=list)   # ids of the edges that end here
    corner: bool = True             # a real corner (the outline turns here, or not exactly two edges meet);
                                    # False where two curves join smoothly (shown and picked only if True)


@dataclass
class Edge:
    id: str                         # stable id, e.g. "op1:wall.2"
    kind: str                       # "line", "arc", "circle", "ellipse", "spline" or "curve"
    points: np.ndarray              # (n, 2) points from start to end [m] (2 for a line)
    length: float                   # [m]
    sources: tuple = ()             # lineage ids this edge comes from (for matching boundary names)
    default_name: str = ""          # name given by the operation that made it, e.g. "farfield"
    default_type: str = ""          # its boundary type, e.g. "farfield"
    faces: list = field(default_factory=list)   # ids of the faces that use this edge
    start: str = ""                 # vertex ids
    end: str = ""

    @property
    def midpoint(self) -> np.ndarray:
        """The point halfway along the edge [m]."""
        return point_at_fraction(self.points, 0.5)

    def matches(self, pattern: str) -> bool:
        """True if a boundary name given to `pattern` applies to this edge.

        A pattern is an edge id. It applies to that edge, to its pieces after a boolean
        ("<id>#1", "<id>#2" ...) and to edges merged from it, so names survive later edits.
        """
        if self.id == pattern or self.id.startswith(pattern + "#"):
            return True
        return any(s == pattern or s.startswith(pattern + "#") for s in self.sources)


@dataclass
class Face:
    id: str
    role: str                       # FLUID or SOLID
    loops: list                     # [[edge id, ...], ...]: outer loop first, then the holes
    area: float                     # [m²] (exact, from the CAD kernel)
    centroid: np.ndarray            # (2,) [m]
    triangles: np.ndarray = None    # (m, 3, 2) a coarse triangulation, for drawing the face filled


@dataclass
class Boundary:
    """The name a boundary edge gets in the mesh (a mesh patch) and its type."""

    name: str                       # e.g. "nozzle_wall" (patch name)
    type: str                       # e.g. "wall" (see boundaries.py BOUNDARY_TYPES)
    inflation: bool = False         # grow inflation layers from this edge (walls)
    origin: str = "default"         # "default" (given by the operation that made the edge) or "user"


@dataclass
class Region:
    """A refinement region: the mesh is at most `size` [m] inside it."""

    id: str                         # operation id
    shape: str                      # "box", "circle" or "wake"
    params: dict                    # box: x0 y0 x1 y1; circle: xc yc radius; wake: x0 y0 x1 y1 width [m]
    size: float                     # target cell size [m]


@dataclass
class BuiltGeometry:
    axisymmetric: bool = False
    vertices: dict = field(default_factory=dict)     # {id: Vertex}
    edges: dict = field(default_factory=dict)        # {id: Edge}
    faces: dict = field(default_factory=dict)        # {id: Face}
    names: dict = field(default_factory=dict)        # {edge id: Boundary} for named edges
    regions: list = field(default_factory=list)      # [Region]
    construction: list = field(default_factory=list) # sketch construction lines [(n, 2) points], drawn only
    sketch_status: dict = field(default_factory=dict) # {sketch op id: constraint status text}
    dimensions: list = field(default_factory=list)    # driving dimensions to show (operations.dimension_marks)
    messages: list = field(default_factory=list)     # [(level, text)] level: "info", "warning", "error"
    failed_operation: str = ""                       # id of the operation that failed (replay stopped there)

    # ---- simple facts --------------------------------------------------------------------------

    @property
    def empty(self) -> bool:
        return not self.edges

    def bbox(self):
        """(x_min, y_min, x_max, y_max) of all edges [m], or None if there are none."""
        if not self.edges:
            return None
        pts = np.vstack([e.points for e in self.edges.values()])
        (x0, y0), (x1, y1) = pts.min(axis=0), pts.max(axis=0)
        return float(x0), float(y0), float(x1), float(y1)

    @property
    def size(self) -> float:
        """Size of the geometry (bounding-box diagonal) [m]; 1 if empty."""
        box = self.bbox()
        return 1.0 if box is None else max(float(np.hypot(box[2] - box[0], box[3] - box[1])), 1e-300)

    def reference_length(self) -> float:
        """A length for sizing cells and domains [m]: the length along x of the bodies (the holes in the
        fluid, or the solid faces), or of the whole fluid region when there are none (e.g. a nozzle)."""
        loops = [loop for f in self.faces_with_role(FLUID) for loop in f.loops[1:]]
        loops += [f.loops[0] for f in self.faces_with_role(SOLID) if f.loops]
        if not loops:
            loops = [f.loops[0] for f in self.faces_with_role(FLUID) if f.loops]
        if not loops:
            box = self.bbox()
            return 1.0 if box is None else max(box[2] - box[0], 1e-300)
        x = np.concatenate([self.loop_points(loop)[:, 0] for loop in loops])
        return max(float(np.ptp(x)), 1e-300)

    def faces_with_role(self, role):
        return [f for f in self.faces.values() if f.role == role]

    def boundary_edges(self) -> list:
        """Ids of the edges on the boundary of the fluid region: used by exactly one fluid face.

        These become mesh patches, so every one of them needs a name. Edges between two fluid
        faces are inside the fluid; edges of solid faces only, or free curves, are not meshed.
        """
        fluid = {f.id for f in self.faces_with_role(FLUID)}
        return [e.id for e in self.edges.values() if sum(f in fluid for f in e.faces) == 1]

    def patches(self) -> dict:
        """{patch name: (type, [edge ids])} of the named boundary edges, in edge order."""
        out = {}
        for edge_id in self.boundary_edges():
            b = self.names.get(edge_id)
            if b is not None:
                out.setdefault(b.name, (b.type, []))[1].append(edge_id)
        return out

    def loop_points(self, loop) -> np.ndarray:
        """The closed polygon (n, 2) of a loop of edge ids, edges joined end to end [m]."""
        pts = []
        current = None
        for k, edge_id in enumerate(loop):
            p = self.edges[edge_id].points
            if k == 0 and len(loop) > 1:        # start so that the first edge leads into the second
                nxt = self.edges[loop[1]].points
                ends = (nxt[0], nxt[-1])
                if min(np.linalg.norm(p[0] - e) for e in ends) < min(np.linalg.norm(p[-1] - e) for e in ends):
                    p = p[::-1]
            elif current is not None and np.linalg.norm(p[-1] - current) < np.linalg.norm(p[0] - current):
                p = p[::-1]
            pts.append(p if not pts else p[1:])
            current = p[-1]
        return np.vstack(pts)

    def errors(self) -> list:
        return [text for level, text in self.messages if level == "error"]


def point_at_fraction(points, fraction) -> np.ndarray:
    """The point at `fraction` (0..1) of the length along a polyline."""
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    total = seg.sum()
    if total <= 0.0:
        return np.asarray(points[0], dtype=float)
    s = np.r_[0.0, np.cumsum(seg)]
    target = fraction * total
    k = min(int(np.searchsorted(s, target, side="right")) - 1, len(seg) - 1)
    t = (target - s[k]) / max(seg[k], 1e-300)
    return points[k] + t * (points[k + 1] - points[k])

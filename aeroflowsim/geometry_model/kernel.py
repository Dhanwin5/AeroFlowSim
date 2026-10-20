# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The CAD kernel: the ONLY module that calls Gmsh's OpenCASCADE geometry (gmsh.model.occ).

OpenCASCADE (OCC) is the open-source CAD kernel used by FreeCAD, Salome and Gmsh. Through Gmsh's
Python interface it gives us exact lines, circle arcs and B-splines, booleans (union, subtract,
intersect), 2D fillets and STEP/IGES files. Operations (operations.py) use the Kernel below to
build the geometry; at the end extract() copies the result into plain Python data (built.py).

STABLE EDGE IDS ("lineage")
OCC numbers its curves 1, 2, 3 ... and RENUMBERS them after a boolean (tested: after cutting a
small disk out of a big one, the big circle went from curve 1 to curve 3). A boundary name
stored as "curve 3" would then point at the wrong edge after an edit. So every edge carries an id
that says where it came from: the operation that made it plus a label, e.g. "op1:wall.2".
After an operation that changes the topology (boolean, fillet), relabel() finds each new curve's
origin GEOMETRICALLY:
  1. Before the operation, snapshot() samples every curve densely (2000 points; 2 for a line).
  2. After it, five points inside each new curve are compared with those old curves. If all
     five lie on one old curve (within LINEAGE_TOLERANCE x geometry size), the new curve is that
     curve, or a piece of it: one piece keeps the old id, several pieces get "<old id>#1",
     "#2" ... numbered along the old curve.
  3. If the points lie on several old curves, the new curve was merged from them (OCC joins
     collinear edges after a union): its id is "<id a>+<id b>".
  4. Otherwise the curve is new, e.g. a fillet arc: "<operation id>:fillet".
Transformations (move, rotate, scale, mirror) keep OCC's curve numbers, so ids simply stay.

Gmsh keeps global state, so a geometry is built under the same lock as the meshes
(aeroflowsim/gmsh_mesh.py) and with interruptible=False (the GUI may call it outside the main thread).
"""

import contextlib
import itertools
from dataclasses import dataclass

import numpy as np

from aeroflowsim.geometry_model.built import (
    FLUID, Boundary, BuiltGeometry, Edge, Face, Vertex)
from aeroflowsim.gmsh_mesh import _LOCK, _add_chain, _import_gmsh

DRAW_SAMPLES = 129          # points along a curved edge for drawing and picking [-]
LINEAGE_SAMPLES = 2000      # points along a curved edge when matching edges after a boolean [-]
LINEAGE_TOLERANCE = 1e-5    # a point "lies on" an old curve if closer than this x geometry size [-]
QUADRATURE_TOLERANCE = 1e-14   # face integrals: stop refining when the change is below this x size² [-]
QUADRATURE_MAX_PIECES = 4096   # at most this many quadrature pieces per curve [-]
KINDS = {"Line": "line", "Circle": "arc", "Ellipse": "ellipse", "BSpline": "spline", "Bezier": "spline"}

_models = itertools.count(1)


@contextlib.contextmanager
def gmsh_session():
    """Gmsh started (if it is not already) with a fresh, empty model, under the Gmsh lock."""
    gmsh = _import_gmsh()
    with _LOCK:
        started = not gmsh.isInitialized()
        if started:
            gmsh.initialize(interruptible=False)
        gmsh.option.setNumber("General.Terminal", 0)
        name = f"aeroflowsim_geometry_{next(_models)}"
        gmsh.model.add(name)
        try:
            yield gmsh
        finally:
            if started:
                gmsh.finalize()
            else:
                gmsh.model.setCurrent(name)
                gmsh.model.remove()


@dataclass
class EdgeMeta:
    """What the kernel knows about one OCC curve besides its geometry."""

    id: str
    sources: tuple
    default_name: str = ""
    default_type: str = ""


@dataclass
class FaceMeta:
    id: str
    role: str


class Kernel:
    """One geometry being built by replaying a history (see document.py)."""

    def __init__(self, gmsh):
        self.gmsh = gmsh
        self.occ = gmsh.model.occ
        self.edge_meta = {}          # {OCC curve tag: EdgeMeta}
        self.face_meta = {}          # {OCC surface tag: FaceMeta}
        self.axisymmetric = False
        self.names = []              # [(patterns, Boundary, operation id)], applied in extract()
        self.regions = []            # [Region]
        self.messages = []           # [(level, text)]
        self.failed_operation = ""

    # ---- small helpers -------------------------------------------------------------------------

    def sync(self):
        self.occ.synchronize()

    def curve_tags(self) -> list:
        self.sync()
        return sorted(tag for _, tag in self.gmsh.model.getEntities(1))

    def face_tags(self) -> list:
        self.sync()
        return sorted(tag for _, tag in self.gmsh.model.getEntities(2))

    def message(self, text, level="warning"):
        self.messages.append((level, text))

    def point(self, x, y) -> int:
        return self.occ.addPoint(float(x), float(y), 0.0)

    def line(self, a, b) -> int:
        """A straight line between two point tags."""
        return self.occ.addLine(a, b)

    def name_edge(self, tag, edge_id, default_name="", default_type=""):
        """Give a newly made curve its stable id (and the boundary name it gets by default)."""
        self.edge_meta[tag] = EdgeMeta(edge_id, (edge_id,), default_name, default_type)

    def name_face(self, tag, face_id, role):
        self.face_meta[tag] = FaceMeta(face_id, role)

    def add_chain(self, points, split, closed, op_id, label, default_name="", default_type=""):
        """An outline of points as OCC curves split at `split` points (lines between two points,
        smooth splines through more); the curves get ids "<op>:<label>.1", ".2" ... in order."""
        chain = _add_chain(self.occ, np.asarray(points, dtype=float), split, closed)
        for k, tag in enumerate(chain.curves, start=1):
            self.name_edge(tag, f"{op_id}:{label}.{k}", default_name, default_type)
        return chain

    def label_new(self, tags, op_id, label="e"):
        """Ids "<op>:<label>1", "<op>:<label>2" ... for new curves, numbered by position (x, then y of
        their midpoint), so the same file gives the same ids every time it is replayed."""
        mids = {t: self.sample(t, 3)[1] for t in tags}
        order = sorted(tags, key=lambda t: (round(float(mids[t][0]), 12), round(float(mids[t][1]), 12)))
        for n, tag in enumerate(order, start=1):
            self.name_edge(tag, f"{op_id}:{label}{n}")

    def add_face(self, curves, face_id, role) -> int:
        """A plane face bounded by curve tags given in order round the loop."""
        loop = self.occ.addCurveLoop([abs(c) for c in curves])
        surface = self.occ.addPlaneSurface([loop])
        self.name_face(surface, face_id, role)
        return surface

    # ---- finding entities by their stable ids ----------------------------------------------------

    def face_by_id(self, face_id) -> int:
        for tag, meta in self.face_meta.items():
            if meta.id == face_id:
                return tag
        raise ValueError(f"the face '{face_id}' does not exist (any more)")

    def edge_by_id(self, edge_id) -> int:
        for tag, meta in self.edge_meta.items():
            if meta.id == edge_id:
                return tag
        raise ValueError(f"the edge '{edge_id}' does not exist (any more)")

    def faces_with_role(self, role) -> list:
        return [tag for tag in self.face_tags() if self.face_meta.get(tag, FaceMeta("", "")).role == role]

    def free_curves(self) -> list:
        """Curve tags not used by any face (e.g. an open sketch line)."""
        return [tag for tag in self.curve_tags() if len(self.gmsh.model.getAdjacencies(1, tag)[0]) == 0]

    def dim_tags(self, ids):
        """[(dim, tag)] for stable face and edge ids; empty ids = every face and free curve."""
        if not ids:
            return [(2, t) for t in self.face_tags()] + [(1, t) for t in self.free_curves()]
        out = []
        for entity in ids:
            try:
                out.append((2, self.face_by_id(entity)))
            except ValueError:
                out.append((1, self.edge_by_id(entity)))
        return out

    # ---- geometry of one curve -----------------------------------------------------------------

    def sample(self, tag, n) -> np.ndarray:
        """n points (n, 2) along a curve, evenly spaced in its parameter, start to end [m]."""
        model = self.gmsh.model
        if model.getType(1, tag) == "Line":
            n = 2
        lo, hi = model.getParametrizationBounds(1, tag)
        t = np.linspace(lo[0], hi[0], n)
        return np.asarray(model.getValue(1, tag, t), dtype=float).reshape(-1, 3)[:, :2]

    def face_integrals(self, loops):
        """(area [m²], centroid (2,) [m]) of a face from its loops of curve tags (outer loop and holes).

        Green's theorem turns the area integrals into integrals along the boundary:
            A = 1/2 loop-integral (x dy - y dx),  A x_c = 1/2 loop-integral x² dy,  A y_c = -1/2 loop-integral y² dx
        evaluated with Gauss-Legendre quadrature on the EXACT curves (OpenCASCADE's own surface
        integration loses accuracy, about 0.2 %, on faces that were scaled). Each loop is summed
        in its own direction and taken as positive; holes are subtracted.
        """
        parts = []
        for loop in loops:
            sums, current = np.zeros(3), None
            for tag in loop:
                part, start, end = self._curve_integrals(tag)
                if current is None and len(loop) > 1:       # first curve: point it towards the second
                    nxt = self.sample(loop[1], 2)
                    if min(np.linalg.norm(start - q) for q in nxt) < min(np.linalg.norm(end - q) for q in nxt):
                        part, start, end = -part, end, start
                elif current is not None and np.linalg.norm(end - current) < np.linalg.norm(start - current):
                    part, start, end = -part, end, start    # this curve runs against the loop
                sums += part
                current = end
            parts.append(sums if sums[0] >= 0.0 else -sums)  # every loop counted positive
        parts.sort(key=lambda s: -s[0])                      # outer loop (largest area) first, then holes
        total = parts[0] - sum(parts[1:], np.zeros(3))
        area = float(total[0])
        return area, (total[1:] / area if area > 0.0 else np.zeros(2))

    def _curve_integrals(self, tag, order=8):
        """(1/2 int (x dy - y dx), 1/2 int x² dy, -1/2 int y² dx) along a curve, start and end points.

        Gauss-Legendre quadrature on 2, 4, 8 ... equal parameter pieces until the result stops
        changing (exact curves converge at once; B-spline approximations need more pieces).
        """
        model = self.gmsh.model
        lo, hi = model.getParametrizationBounds(1, tag)
        nodes, weights = np.polynomial.legendre.leggauss(order)

        def integrate(n):
            edges = np.linspace(lo[0], hi[0], n + 1)
            half = 0.5 * np.diff(edges)
            t = (0.5 * (edges[:-1] + edges[1:])[:, None] + half[:, None] * nodes[None, :]).ravel()
            w = (half[:, None] * weights[None, :]).ravel()
            xyz = np.asarray(model.getValue(1, tag, t), dtype=float).reshape(-1, 3)
            d = np.asarray(model.getDerivative(1, tag, t), dtype=float).reshape(-1, 3)
            x, y, dx, dy = xyz[:, 0], xyz[:, 1], d[:, 0], d[:, 1]
            return np.array([0.5 * np.sum(w * (x * dy - y * dx)), 0.5 * np.sum(w * x * x * dy),
                             -0.5 * np.sum(w * y * y * dx)])

        n, part = 2, integrate(2)
        scale = max(float(np.ptp(self.sample(tag, 9), axis=0).max()), 1e-300)
        while n < QUADRATURE_MAX_PIECES:
            n *= 2
            finer = integrate(n)
            converged = np.all(np.abs(finer - part) <= QUADRATURE_TOLERANCE * scale**2 * (1.0 + scale))
            part = finer
            if converged:
                break
        ends = np.asarray(model.getValue(1, tag, [lo[0], hi[0]]), dtype=float).reshape(-1, 3)[:, :2]
        return part, ends[0], ends[1]

    def model_size(self) -> float:
        self.sync()
        x0, y0, _, x1, y1, _ = self.gmsh.model.getBoundingBox(-1, -1)
        return max(float(np.hypot(x1 - x0, y1 - y0)), 1e-300)

    # ---- lineage (see the module docstring) ------------------------------------------------------

    def snapshot(self) -> list:
        """[(EdgeMeta, dense points)] of every current curve, taken BEFORE a topology change."""
        out = []
        for tag in self.curve_tags():
            meta = self.edge_meta.get(tag) or EdgeMeta(f"curve{tag}", (f"curve{tag}",))
            out.append((meta, self.sample(tag, LINEAGE_SAMPLES)))
        return out

    def relabel(self, snapshot, op_id, new_label="edge"):
        """Give every curve after a topology change its id, by matching it to the snapshot."""
        tags = self.curve_tags()
        tol = LINEAGE_TOLERANCE * self.model_size()
        # All old segments in one array: start a, end b, owner = index into snapshot.
        a = np.vstack([pts[:-1] for _, pts in snapshot]) if snapshot else np.zeros((0, 2))
        b = np.vstack([pts[1:] for _, pts in snapshot]) if snapshot else np.zeros((0, 2))
        owner = np.concatenate([np.full(len(pts) - 1, k) for k, (_, pts) in enumerate(snapshot)]) \
            if snapshot else np.zeros(0, dtype=int)
        pieces, merged, new = {}, [], []
        for tag in tags:
            probe = self.sample(tag, 7)[1:-1] if self.gmsh.model.getType(1, tag) != "Line" else \
                np.linspace(*self.sample(tag, 2), 7)[1:-1]
            if len(a) == 0:
                new.append((tag, probe[2]))
                continue
            d, seg = _nearest_segments(probe, a, b)
            if np.all(d <= tol):
                owners = sorted(set(owner[seg].tolist()))
                if len(owners) == 1:
                    pieces.setdefault(owners[0], []).append((tag, probe[2]))
                else:
                    merged.append((tag, owners))
            else:
                new.append((tag, probe[2]))
        meta = {}
        for k, found in pieces.items():
            old, pts = snapshot[k]
            if len(found) == 1:
                meta[found[0][0]] = EdgeMeta(old.id, old.sources, old.default_name, old.default_type)
                continue
            along = [_position_along(pts, mid) for _, mid in found]
            for n, j in enumerate(np.argsort(along), start=1):
                meta[found[j][0]] = EdgeMeta(f"{old.id}#{n}", old.sources, old.default_name, old.default_type)
        for tag, owners in merged:
            olds = [snapshot[k][0] for k in owners]
            same = len({(o.default_name, o.default_type) for o in olds}) == 1
            meta[tag] = EdgeMeta("+".join(o.id for o in olds), tuple(s for o in olds for s in o.sources),
                                 olds[0].default_name if same else "", olds[0].default_type if same else "")
        new.sort(key=lambda item: (round(float(item[1][0]), 12), round(float(item[1][1]), 12)))
        for n, (tag, _) in enumerate(new, start=1):
            edge_id = f"{op_id}:{new_label}" if len(new) == 1 else f"{op_id}:{new_label}{n}"
            meta[tag] = EdgeMeta(edge_id, (edge_id,))
        self.edge_meta = _unique_ids(meta)

    # ---- booleans --------------------------------------------------------------------------------

    def boolean(self, kind, objects, tools, op_id, role=None, remove_tools=True) -> list:
        """Union ("fuse"), subtract ("cut") or intersect faces given by stable id or tag.

        The result faces keep the id of the object face they come from (pieces: "#1", "#2" ...);
        role: the role of the result (None = that of the first object). Returns the result tags.
        """
        obj = [(2, t if isinstance(t, int) else self.face_by_id(t)) for t in objects]
        tool = [(2, t if isinstance(t, int) else self.face_by_id(t)) for t in tools]
        if not obj or not tool:
            raise ValueError("a boolean needs at least one object face and one tool face")
        first = self.face_meta.get(obj[0][1], FaceMeta(f"{op_id}:face", FLUID))
        inputs = [self.face_meta.get(t, FaceMeta(f"{op_id}:face", first.role)) for _, t in obj + tool]
        snap = self.snapshot()
        function = {"union": self.occ.fuse, "subtract": self.occ.cut, "intersect": self.occ.intersect}[kind]
        out, out_map = function(obj, tool, removeObject=True, removeTool=remove_tools)
        self.sync()
        result_tags = [t for d, t in out if d == 2]
        # Each result face takes the id of the first input (objects first) that produced it.
        faces = {}
        for k, produced in enumerate(out_map):
            for d, t in produced:
                if d == 2 and t not in faces:
                    faces[t] = inputs[k]
        kept = {t: m for t, m in self.face_meta.items() if t not in {x for _, x in obj + tool} and
                t not in faces}
        by_id = {}
        for t in result_tags:
            source = faces.get(t, first)
            by_id.setdefault(source.id, []).append(t)
        new_meta = dict(kept)
        for face_id, tags in by_id.items():
            source = next(m for m in inputs + [first] if m.id == face_id)
            for n, t in enumerate(sorted(tags), start=1):
                new_meta[t] = FaceMeta(face_id if len(tags) == 1 else f"{face_id}#{n}", role or source.role)
        if not remove_tools:                      # tools stay as they were (same tags)
            for _, t in tool:
                if t in self.face_meta:
                    new_meta[t] = self.face_meta[t]
        self.face_meta = {t: m for t, m in new_meta.items() if t in self.face_tags()}
        self.relabel(snap, op_id)
        return result_tags

    # ---- the result ------------------------------------------------------------------------------

    def extract(self, triangulate=True) -> BuiltGeometry:
        """Copy the current geometry into plain data (built.py)."""
        model = self.gmsh.model
        self.sync()
        built = BuiltGeometry(axisymmetric=self.axisymmetric, messages=list(self.messages),
                              regions=list(self.regions), failed_operation=self.failed_operation)
        face_ids = {t: (self.face_meta.get(t) or FaceMeta(f"face{t}", FLUID)).id for t in self.face_tags()}
        edge_ids = {}
        for tag in self.curve_tags():
            meta = self.edge_meta.get(tag) or EdgeMeta(f"curve{tag}", (f"curve{tag}",))
            edge_ids[tag] = meta.id
            faces = [face_ids[t] for t in model.getAdjacencies(1, tag)[0] if t in face_ids]
            ends = [t for _, t in model.getBoundary([(1, tag)], combined=False, oriented=False)]
            built.edges[meta.id] = Edge(
                meta.id, KINDS.get(model.getType(1, tag), "curve"), self.sample(tag, DRAW_SAMPLES),
                float(self.occ.getMass(1, tag)), meta.sources, meta.default_name, meta.default_type, faces,
                f"v{ends[0]}" if ends else "", f"v{ends[-1]}" if ends else "")
        for _, tag in model.getEntities(0):
            xy = np.asarray(model.getValue(0, tag, []), dtype=float)[:2]
            edges = [edge_ids[t] for t in model.getAdjacencies(0, tag)[0] if t in edge_ids]
            built.vertices[f"v{tag}"] = Vertex(f"v{tag}", xy, edges)
        _stable_vertex_ids(built)
        for tag in self.face_tags():
            meta = self.face_meta.get(tag) or FaceMeta(f"face{tag}", FLUID)
            _, loop_curves = self.occ.getCurveLoops(tag)
            loops = [[edge_ids[abs(int(c))] for c in curves] for curves in loop_curves]
            area, centre = self.face_integrals([[abs(int(c)) for c in curves] for curves in loop_curves])
            face = Face(meta.id, meta.role, loops, area, centre)
            built.faces[meta.id] = face
        for face in built.faces.values():         # outer loop first (the one enclosing the largest area)
            if len(face.loops) > 1:
                face.loops.sort(key=lambda loop: -abs(_polygon_area(built.loop_points(loop))))
        # Boundary names: first the defaults from the operations, then the user's names in order.
        for edge in built.edges.values():
            if edge.default_name:
                built.names[edge.id] = Boundary(edge.default_name, edge.default_type or edge.default_name)
        for patterns, boundary, op_id in self.names:
            hits = [e for e in built.edges.values() if any(e.matches(p) for p in patterns)]
            for edge in hits:
                built.names[edge.id] = boundary
            if not hits:
                built.messages.append(("warning", f"Boundary name '{boundary.name}' ({op_id}): its edges no longer "
                                                  "exist after the later changes; name the edges again."))
        if triangulate:
            self._triangulate(built, {t: face_ids[t] for t in self.face_tags()})
        return built

    def _triangulate(self, built, face_ids):
        """A coarse triangle mesh of every face, only for drawing it filled (not the CFD mesh)."""
        gmsh = self.gmsh
        if not face_ids:
            return
        size = built.size
        try:
            for option, value in (("Mesh.MeshSizeMax", size / 30.0), ("Mesh.MeshSizeMin", 0.0),
                                  ("Mesh.MeshSizeFromCurvature", 12), ("Mesh.MeshSizeExtendFromBoundary", 1),
                                  ("Mesh.MeshSizeFromPoints", 0), ("Mesh.Algorithm", 6),
                                  ("Mesh.RecombineAll", 0)):
                gmsh.option.setNumber(option, value)
            gmsh.model.mesh.generate(2)
            tags, coords, _ = gmsh.model.mesh.getNodes()
            xy = np.zeros((int(np.max(tags)) + 1, 2))
            xy[np.asarray(tags, dtype=np.int64)] = np.asarray(coords).reshape(-1, 3)[:, :2]
            for tag, face_id in face_ids.items():
                kinds, _, nodes = gmsh.model.mesh.getElements(2, tag)
                tris = [xy[np.asarray(n, dtype=np.int64).reshape(-1, 3)] for k, n in zip(kinds, nodes) if k == 2]
                if tris:
                    built.faces[face_id].triangles = np.vstack(tris)
        except Exception:                          # drawing only: an unfilled face is fine
            pass
        finally:
            gmsh.model.mesh.clear()


# ---- helpers ----------------------------------------------------------------------------------------

def _nearest_segments(points, a, b):
    """Distance from each point (p, 2) to the nearest segment a->b (m, 2), and that segment's index."""
    ab = b - a
    length2 = np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-300)
    dist, index = np.empty(len(points)), np.empty(len(points), dtype=int)
    for k, p in enumerate(points):
        t = np.clip(((p - a) * ab).sum(1) / length2, 0.0, 1.0)
        d = np.linalg.norm(a + t[:, None] * ab - p, axis=1)
        index[k] = int(d.argmin())
        dist[k] = d[index[k]]
    return dist, index


def _position_along(points, p) -> float:
    """Arc length [m] along a polyline of the point nearest to p."""
    a, b = points[:-1], points[1:]
    d, seg = _nearest_segments(np.asarray([p]), a, b)
    k = int(seg[0])
    s = np.r_[0.0, np.cumsum(np.linalg.norm(b - a, axis=1))]
    return float(s[k] + np.linalg.norm(p - a[k]))


def _unique_ids(meta) -> dict:
    """Make edge ids unique (two curves with the same lineage get "~2", "~3" ...)."""
    seen = {}
    for tag in sorted(meta):
        m = meta[tag]
        n = seen.get(m.id, 0) + 1
        seen[m.id] = n
        if n > 1:
            meta[tag] = EdgeMeta(f"{m.id}~{n}", m.sources, m.default_name, m.default_type)
    return meta


def _polygon_area(points) -> float:
    x, y = points[:, 0], points[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _stable_vertex_ids(built):
    """Vertex ids from the edges that meet there (OCC point numbers change between replays)."""
    rename = {}
    for vid, vertex in built.vertices.items():
        rename[vid] = "V(" + "|".join(sorted(vertex.edges)) + ")" if vertex.edges else \
            f"V({vertex.xy[0]:.9g},{vertex.xy[1]:.9g})"
    built.vertices = {rename[v]: Vertex(rename[v], vx.xy, vx.edges) for v, vx in built.vertices.items()}
    for edge in built.edges.values():
        edge.start, edge.end = rename.get(edge.start, edge.start), rename.get(edge.end, edge.end)

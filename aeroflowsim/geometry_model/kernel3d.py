# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The 3D CAD kernel: solids in Gmsh's OpenCASCADE geometry (gmsh.model.occ).

Together with kernel.py (2D) this is the ONLY code calling OpenCASCADE. Operations
(operations3d.py) build bodies with the Kernel3D below; at the end extract() copies the result
into plain Python data (built3d.py).

STABLE FACE IDS ("lineage", the 3D form of the edge lineage of kernel.py)
OCC numbers its surfaces 1, 2, 3 ... and RENUMBERS them after a boolean. A boundary name stored
as "surface 7" would point at the wrong face after an edit, so every face carries an id that says
where it came from: the operation that made it plus a label, e.g. "op1:xmin" or "op2:side".
After an operation that changes the topology (boolean, enclosure), relabel() finds each new
face's origin GEOMETRICALLY, exactly like the 2D edges:
  1. Before the operation, snapshot() makes a COPY of every face (OCC keeps the copy unchanged
     while the boolean rebuilds the bodies).
  2. After it, a few points inside each new face (a grid in the face's parameters, kept only
     where the point is inside the trimmed face) are projected onto the copies. A point "lies on"
     an old face if it is closer than LINEAGE_TOLERANCE x model size AND inside that face.
  3. If all points lie on one old face, the new face is that face or a piece of it: one piece
     keeps the old id, several pieces get "<old id>#1", "#2" ... (ordered by centroid x, y, z).
  4. If they lie on several old faces, the new face was merged from them: "<id a>+<id b>".
  5. Otherwise the face is new: "<operation id>:face".
The copies are deleted afterwards. Transformations (move, rotate, scale, mirror) keep OCC's
surface numbers, so ids simply stay.

Bodies (OCC volumes) keep the id of the operation that made them ("op1"); the result of a boolean
keeps the id of its first object (pieces "#1", "#2" ...).

Gmsh keeps global state, so a geometry is built under the same lock as the meshes (gmsh_session
in kernel.py).
"""

from dataclasses import dataclass

import numpy as np

from aeroflowsim.geometry_model.built3d import FLUID, SOLID, Boundary, Body3D, BuiltGeometry3D, Edge3D, Face3D

LINEAGE_TOLERANCE = 1e-6    # a point "lies on" an old face if closer than this x model size [-]
PROBE_GRID = 7              # probe points: a PROBE_GRID x PROBE_GRID grid in the face parameters [-]
PROBES = 6                  # at most this many probe points per face [-]
EDGE_SAMPLES = 65           # points along a curved edge for drawing and picking [-]
BBOX_PAD = 1e-7            # Gmsh enlarges every OCC bounding box by this much (tested) [m]
DRAW_ELEMENTS = 24          # drawing triangulation: about this many triangles across the model [-]
KINDS = {"Plane": "plane", "Cylinder": "cylinder", "Cone": "cone", "Sphere": "sphere", "Torus": "torus",
         "BSpline surface": "spline", "Bezier surface": "spline", "Surface of Revolution": "revolution",
         "Surface of Extrusion": "extrusion"}


@dataclass
class FaceMeta:
    """What the kernel knows about one OCC surface besides its geometry."""

    id: str
    sources: tuple
    default_name: str = ""
    default_type: str = ""


@dataclass
class BodyMeta:
    id: str
    role: str
    zone: str = ""                  # cell zone name of a fluid body ("" = its id); set by the Fluid zones operation


class Kernel3D:
    """One 3D geometry being built by replaying a history (see document.py)."""

    dimension = 3

    def __init__(self, gmsh):
        self.gmsh = gmsh
        self.occ = gmsh.model.occ
        self.face_meta = {}          # {OCC surface tag: FaceMeta}
        self.body_meta = {}          # {OCC volume tag: BodyMeta}
        self.axisymmetric = False    # (asked by code shared with 2D; never True in 3D)
        self.names = []              # [(patterns, Boundary, operation id)], applied in extract()
        self.regions = []            # [Region]
        self.messages = []           # [(level, text)]
        self.failed_operation = ""

    # ---- small helpers -------------------------------------------------------------------------

    def sync(self):
        self.occ.synchronize()

    def tags(self, dim) -> list:
        self.sync()
        return sorted(tag for _, tag in self.gmsh.model.getEntities(dim))

    def volume_tags(self) -> list:
        return self.tags(3)

    def face_tags(self) -> list:
        return self.tags(2)

    def message(self, text, level="warning"):
        self.messages.append((level, text))

    def faces_of(self, volume) -> list:
        """Surface tags bounding a volume."""
        self.sync()
        return sorted({abs(t) for _, t in self.gmsh.model.getBoundary([(3, volume)], combined=False,
                                                                          oriented=False)})

    def face_centre(self, tag) -> np.ndarray:
        return np.asarray(self.occ.getCenterOfMass(2, tag), dtype=float)

    def face_kind(self, tag) -> str:
        return KINDS.get(self.gmsh.model.getType(2, tag), "surface")

    def model_size(self) -> float:
        self.sync()
        box = np.asarray(self.gmsh.model.getBoundingBox(-1, -1), dtype=float)
        return max(float(np.linalg.norm(box[3:] - box[:3])), 1e-300)

    def bounding_box(self, volumes) -> np.ndarray:
        """(6,) x0 y0 z0 x1 y1 z1 [m] of volumes (Gmsh pads its boxes by BBOX_PAD; removed here)."""
        boxes = np.array([self.occ.getBoundingBox(3, v) for v in volumes], dtype=float)
        box = np.r_[boxes[:, :3].min(axis=0), boxes[:, 3:].max(axis=0)]
        return box + np.r_[[BBOX_PAD] * 3, [-BBOX_PAD] * 3]

    def name_face(self, tag, face_id, default_name="", default_type=""):
        """Give a newly made surface its stable id (and the boundary name it gets by default)."""
        self.face_meta[tag] = FaceMeta(face_id, (face_id,), default_name, default_type)

    def name_body(self, tag, body_id, role):
        self.body_meta[tag] = BodyMeta(body_id, role)

    def body_by_id(self, body_id) -> int:
        for tag, meta in self.body_meta.items():
            if meta.id == body_id:
                return tag
        raise ValueError(f"the body '{body_id}' does not exist (any more)")

    def bodies_with_role(self, role) -> list:
        return [t for t in self.volume_tags() if self.body_meta.get(t, BodyMeta("", FLUID)).role == role]

    def dim_tags(self, ids):
        """[(3, tag)] for stable body ids; empty ids = every body."""
        if not ids:
            return [(3, t) for t in self.volume_tags()]
        return [(3, self.body_by_id(i)) for i in ids]

    def remove_free_points(self):
        """Delete points, curves and surfaces that belong to no body (left over by an operation)."""
        self.sync()
        model = self.gmsh.model
        for dim in (2, 1, 0):
            loose = [(dim, t) for _, t in model.getEntities(dim) if len(model.getAdjacencies(dim, t)[0]) == 0]
            if loose:
                self.occ.remove(loose)
                self.sync()
        self.face_meta = {t: m for t, m in self.face_meta.items() if t in self.face_tags()}

    def label_new_faces(self, volumes, op_id, label="face", default_name="", default_type=""):
        """Ids "<op>:<label>1", "<label>2" ... for faces without an id, numbered by centroid (x, then y, z),
        so the same file gives the same ids every time it is replayed (one face: "<op>:<label>")."""
        tags = sorted({f for v in volumes for f in self.faces_of(v)} - set(self.face_meta))
        order = sorted(tags, key=lambda t: tuple(np.round(self.face_centre(t), 12)))
        for n, tag in enumerate(order, start=1):
            self.name_face(tag, f"{op_id}:{label}" if len(order) == 1 else f"{op_id}:{label}{n}",
                           default_name, default_type)

    # ---- lineage (see the module docstring) ------------------------------------------------------

    def snapshot(self) -> list:
        """[(FaceMeta, copy tag, padded bounding box)] of every current face, taken BEFORE a topology change."""
        return self._with_boxes(self._face_copies())

    def _face_copies(self) -> list:
        """[(FaceMeta, copy tag, original tag)]: a copy of every current face."""
        faces = self.face_tags()
        copies = self.occ.copy([(2, t) for t in faces]) if faces else []
        self.sync()
        return [(self.face_meta.get(tag) or FaceMeta(f"surface{tag}", (f"surface{tag}",)), copy, tag)
                for tag, (_, copy) in zip(faces, copies)]

    def _with_boxes(self, entries) -> list:
        tol = LINEAGE_TOLERANCE * self.model_size()
        return [(meta, copy, np.asarray(self.occ.getBoundingBox(2, copy), dtype=float) + np.r_[[-tol] * 3, [tol] * 3])
                for meta, copy, *_ in entries]

    def transformed(self, targets, apply, op_id, copy=False) -> list:
        """Move / rotate / scale / mirror bodies with apply(dim_tags), keeping their face ids.

        OCC renumbers the faces of a transformed body (tested), so the lineage copies of its faces get the SAME
        transformation and relabel() matches the moved faces to them. copy=True transforms a copy of the bodies;
        the copies get the ids "<id>@<op>" (bodies and faces). Returns the transformed bodies [(3, tag)].
        """
        tags = [t for _, t in targets]
        moving = {f for t in tags for f in self.faces_of(t)}
        entries = self._face_copies()
        moved = [(m, c) for m, c, original in entries if original in moving]
        if copy:
            bodies = self.occ.copy(targets)
            self.sync()
            for (_, a), (_, b) in zip(targets, bodies):
                meta = self.body_meta.get(a)
                if meta is not None:
                    self.name_body(b, f"{meta.id}@{op_id}", meta.role)
            extra = self.occ.copy([(2, c) for _, c in moved])
            self.sync()
            moved = [(FaceMeta(f"{m.id}@{op_id}", tuple(f"{s}@{op_id}" for s in m.sources), m.default_name,
                               m.default_type), c) for (m, _), (_, c) in zip(moved, extra)]
            entries += [(m, c, None) for m, c in moved]
            targets = bodies
        if moved:
            apply(targets + [(2, c) for _, c in moved])
        else:
            apply(targets)
        self.sync()
        self.relabel(self._with_boxes(entries), op_id)
        return targets

    def probes(self, tag) -> np.ndarray:
        """A few points (k, 3) inside a face [m]: a grid in its parameters, kept where inside the trimmed face."""
        model = self.gmsh.model
        lo, hi = model.getParametrizationBounds(2, tag)
        s = (np.arange(PROBE_GRID) + 0.5) / PROBE_GRID
        uv = np.array([[lo[0] + a * (hi[0] - lo[0]), lo[1] + b * (hi[1] - lo[1])] for a in s for b in s])
        inside = [p for p in uv if model.isInside(2, tag, list(p), parametric=True)]
        if not inside:
            return self.face_centre(tag)[None, :]
        pick = np.linspace(0, len(inside) - 1, min(PROBES, len(inside))).round().astype(int)
        uv = np.asarray(inside)[pick].ravel()
        return np.asarray(model.getValue(2, tag, uv), dtype=float).reshape(-1, 3)

    def _on_face(self, copy, point, tol) -> bool:
        model = self.gmsh.model
        xyz, uv = model.getClosestPoint(2, copy, list(point))
        if np.linalg.norm(np.asarray(xyz) - point) > tol:
            return False
        return bool(model.isInside(2, copy, list(uv), parametric=True))

    def relabel(self, snapshot, op_id, new_label="face"):
        """Give every face after a topology change its id, by matching it to the snapshot; delete the copies."""
        copies = {copy for _, copy, _ in snapshot}
        tags = [t for t in self.face_tags() if t not in copies]
        tol = LINEAGE_TOLERANCE * self.model_size()
        pieces, merged, new = {}, [], []
        for tag in tags:
            probe = self.probes(tag)
            centre = self.face_centre(tag)
            on = []                                  # for every probe point: the snapshot entries it lies on
            for p in probe:
                hits = [k for k, (_, copy, box) in enumerate(snapshot)
                        if np.all(p >= box[:3]) and np.all(p <= box[3:]) and self._on_face(copy, p, tol)]
                on.append(hits)
            common = set(on[0]).intersection(*on[1:]) if on and all(on) else set()
            if common:
                pieces.setdefault(min(common), []).append((tag, centre))
            elif all(on):
                merged.append((tag, sorted({k for hits in on for k in hits})))
            else:
                new.append((tag, centre))
        meta = {}
        for k, found in pieces.items():
            old = snapshot[k][0]
            if len(found) == 1:
                meta[found[0][0]] = FaceMeta(old.id, old.sources, old.default_name, old.default_type)
                continue
            found.sort(key=lambda item: tuple(np.round(item[1], 12)))
            for n, (tag, _) in enumerate(found, start=1):
                meta[tag] = FaceMeta(f"{old.id}#{n}", old.sources, old.default_name, old.default_type)
        for tag, owners in merged:
            olds = [snapshot[k][0] for k in owners]
            same = len({(o.default_name, o.default_type) for o in olds}) == 1
            meta[tag] = FaceMeta("+".join(o.id for o in olds), tuple(s for o in olds for s in o.sources),
                                 olds[0].default_name if same else "", olds[0].default_type if same else "")
        new.sort(key=lambda item: tuple(np.round(item[1], 12)))
        for n, (tag, _) in enumerate(new, start=1):
            face_id = f"{op_id}:{new_label}" if len(new) == 1 else f"{op_id}:{new_label}{n}"
            meta[tag] = FaceMeta(face_id, (face_id,))
        if copies:
            self.occ.remove([(2, c) for c in copies], recursive=True)
            self.sync()
        self.face_meta = _unique_ids({t: m for t, m in meta.items() if t in self.face_tags()})

    # ---- booleans --------------------------------------------------------------------------------

    def boolean(self, kind, objects, tools, op_id, role=None, remove_tools=True) -> list:
        """Union ("fuse"), subtract ("cut") or intersect bodies given by stable id or volume tag.

        The result bodies keep the id of the first input body they come from (pieces: "#1", "#2" ...);
        role: the role of the result (None = that of the first object). Returns the result volume tags.
        """
        tag = lambda t: int(t) if isinstance(t, (int, np.integer)) else self.body_by_id(t)
        obj = [(3, tag(t)) for t in objects]
        tool = [(3, tag(t)) for t in tools]
        if not obj or not tool:
            raise ValueError("a boolean needs at least one object body and one tool body")
        first = self.body_meta.get(obj[0][1], BodyMeta(op_id, SOLID))
        inputs = [self.body_meta.get(t, BodyMeta(op_id, first.role)) for _, t in obj + tool]
        snap = self.snapshot()
        function = {"union": self.occ.fuse, "subtract": self.occ.cut, "intersect": self.occ.intersect}[kind]
        try:
            out, out_map = function(obj, tool, removeObject=True, removeTool=remove_tools)
        except Exception:
            self.occ.remove([(2, c) for _, c, _ in snap], recursive=True)
            raise
        self.sync()
        result = [t for d, t in out if d == 3]
        source_of = {}
        for k, produced in enumerate(out_map):
            for d, t in produced:
                if d == 3 and t not in source_of:
                    source_of[t] = inputs[k]
        used = {t for _, t in obj + tool}
        new_meta = {t: m for t, m in self.body_meta.items() if t not in used and t not in source_of}
        if not remove_tools:
            for _, t in tool:
                if t in self.body_meta:
                    new_meta[t] = self.body_meta[t]
        by_id = {}
        for t in result:
            by_id.setdefault(source_of.get(t, first).id, []).append(t)
        for body_id, vols in by_id.items():
            source = next((m for m in inputs if m.id == body_id), first)
            for n, t in enumerate(sorted(vols), start=1):
                new_meta[t] = BodyMeta(body_id if len(vols) == 1 else f"{body_id}#{n}", role or source.role,
                                       source.zone)
        self.body_meta = {t: m for t, m in new_meta.items() if t in self.volume_tags()}
        self.relabel(snap, op_id)
        return result

    def zone_settings(self, sizes, excluded):
        """Per-zone settings of the Fluid zones operation (read by the mesher): {zone: cell size [m]}, [excluded]."""
        for zone, size in sizes.items():
            if not float(size) > 0.0:
                raise ValueError(f"zone '{zone}': the cell size must be positive")
        self.zone_sizes = {str(k): float(v) for k, v in sizes.items()}
        self.zone_excluded = [str(z) for z in excluded]

    def fragment(self, bodies, op_id, names=None) -> list:
        """Gmsh/OpenCASCADE Fragment of fluid bodies (full 3D release stage, multiple zones): overlapping bodies are
        cut into pieces that share their faces (conformal interfaces, one surface mesh on both sides). Each piece is a
        cell zone named after the LAST input body that covers it (a later body has priority, like the region order
        of commercial meshers); names = {body id: zone name} (default: the body id). Pieces keep the id of that body
        ("#1", "#2" ... when one zone has several pieces). Returns the result volume tags."""
        tags = [self.body_by_id(b) if not isinstance(b, (int, np.integer)) else int(b) for b in bodies]
        if len(tags) < 2:
            raise ValueError("fluid zones need at least two fluid bodies")
        inputs = [self.body_meta.get(t, BodyMeta(f"body{t}", FLUID)) for t in tags]
        names = dict(names or {})
        snap = self.snapshot()
        out, out_map = self.occ.fragment([(3, t) for t in tags], [], removeObject=True, removeTool=True)
        self.sync()
        winner = {}
        for k, produced in enumerate(out_map):            # later inputs overwrite: the last body wins
            for d, t in produced:
                if d == 3:
                    winner[t] = inputs[k]
        used = set(tags)
        new_meta = {t: m for t, m in self.body_meta.items() if t not in used and t not in winner}
        by_id = {}
        for t in sorted(winner):
            by_id.setdefault(winner[t].id, []).append(t)
        for body_id, vols in by_id.items():
            source = next(m for m in inputs if m.id == body_id)
            zone = names.get(body_id) or source.zone or body_id
            for n, t in enumerate(vols, start=1):
                new_meta[t] = BodyMeta(body_id if len(vols) == 1 else f"{body_id}#{n}", FLUID, zone)
        self.body_meta = {t: m for t, m in new_meta.items() if t in self.volume_tags()}
        self.relabel(snap, op_id)
        return [t for d, t in out if d == 3]

    # ---- the result ------------------------------------------------------------------------------

    def extract(self, triangulate=True) -> BuiltGeometry3D:
        """Copy the current geometry into plain data (built3d.py)."""
        model, occ = self.gmsh.model, self.occ
        self.sync()
        built = BuiltGeometry3D(messages=list(self.messages), regions=list(self.regions),
                                failed_operation=self.failed_operation)
        body_ids = {t: (self.body_meta.get(t) or BodyMeta(f"body{t}", FLUID)).id for t in self.volume_tags()}
        face_ids = {}
        for tag in self.face_tags():
            meta = self.face_meta.get(tag) or FaceMeta(f"surface{tag}", (f"surface{tag}",))
            face_ids[tag] = meta.id
            bodies = [body_ids[v] for v in model.getAdjacencies(2, tag)[0] if v in body_ids]
            built.faces[meta.id] = Face3D(meta.id, self.face_kind(tag), float(occ.getMass(2, tag)),
                                          self.face_centre(tag), meta.sources, meta.default_name,
                                          meta.default_type, bodies,
                                          box=np.asarray(occ.getBoundingBox(2, tag), dtype=float) +
                                          np.r_[[BBOX_PAD] * 3, [-BBOX_PAD] * 3])
        edges = []
        for _, tag in model.getEntities(1):
            faces = sorted({face_ids[f] for f in model.getAdjacencies(1, tag)[0] if f in face_ids})
            edges.append((tag, faces))
        seen = {}
        edges.sort(key=lambda item: tuple(np.round(self._curve_points(item[0], 3)[1], 12)))
        for tag, faces in edges:
            edge_id = "E(" + "|".join(faces) + ")"
            n = seen.get(edge_id, 0) + 1
            seen[edge_id] = n
            if n > 1:
                edge_id = f"{edge_id}~{n}"
            built.edges[edge_id] = Edge3D(edge_id, self._curve_points(tag, EDGE_SAMPLES), float(occ.getMass(1, tag)),
                                          faces)
            for f in faces:
                built.faces[f].edges.append(edge_id)
        for tag in self.volume_tags():
            meta = self.body_meta.get(tag) or BodyMeta(f"body{tag}", FLUID)
            faces = [face_ids[f] for f in self.faces_of(tag)]
            built.bodies[meta.id] = Body3D(meta.id, meta.role, faces, float(occ.getMass(3, tag)),
                                           float(sum(built.faces[f].area for f in faces)),
                                           np.asarray(occ.getCenterOfMass(3, tag), dtype=float), meta.zone)
        # Boundary names: first the defaults from the operations, then the user's names in order.
        for face in built.faces.values():
            if face.default_name:
                built.names[face.id] = Boundary(face.default_name, face.default_type or face.default_name)
        for patterns, boundary, op_id in self.names:
            hits = [f for f in built.faces.values() if any(f.matches(p) for p in patterns)]
            for face in hits:
                built.names[face.id] = boundary
            if not hits:
                built.messages.append(("warning", f"Boundary name '{boundary.name}' ({op_id}): its faces no longer "
                                                  "exist after the later changes; name the faces again."))
        if triangulate:
            self._triangulate(built, face_ids)
        return built

    def _curve_points(self, tag, n) -> np.ndarray:
        """n points (n, 3) along a curve, evenly spaced in its parameter [m] (2 for a straight line)."""
        model = self.gmsh.model
        if model.getType(1, tag) == "Line":
            n = 2
        lo, hi = model.getParametrizationBounds(1, tag)
        t = np.linspace(lo[0], hi[0], n)
        return np.asarray(model.getValue(1, tag, t), dtype=float).reshape(-1, 3)

    def _triangulate(self, built, face_ids):
        """A coarse triangle mesh of every face, for drawing and picking it (not the CFD mesh)."""
        gmsh = self.gmsh
        if not face_ids:
            return
        try:
            for option, value in (("Mesh.MeshSizeMax", built.size / DRAW_ELEMENTS), ("Mesh.MeshSizeMin", 0.0),
                                  ("Mesh.MeshSizeFromCurvature", 16), ("Mesh.MeshSizeExtendFromBoundary", 1),
                                  ("Mesh.MeshSizeFromPoints", 0), ("Mesh.Algorithm", 6), ("Mesh.RecombineAll", 0)):
                gmsh.option.setNumber(option, value)
            gmsh.model.mesh.generate(2)
            tags, coords, _ = gmsh.model.mesh.getNodes()
            xyz = np.zeros((int(np.max(tags)) + 1, 3))
            xyz[np.asarray(tags, dtype=np.int64)] = np.asarray(coords).reshape(-1, 3)
            for tag, face_id in face_ids.items():
                kinds, _, nodes = gmsh.model.mesh.getElements(2, tag)
                tris = [xyz[np.asarray(n, dtype=np.int64).reshape(-1, 3)] for k, n in zip(kinds, nodes) if k == 2]
                if tris:
                    built.faces[face_id].triangles = np.vstack(tris)
        except Exception:                          # drawing only: an unfilled face is fine
            pass
        finally:
            gmsh.model.mesh.clear()


def _unique_ids(meta) -> dict:
    """Make face ids unique (two faces with the same lineage get "~2", "~3" ...)."""
    seen = {}
    for tag in sorted(meta):
        m = meta[tag]
        n = seen.get(m.id, 0) + 1
        seen[m.id] = n
        if n > 1:
            meta[tag] = FaceMeta(f"{m.id}~{n}", m.sources, m.default_name, m.default_type)
    return meta

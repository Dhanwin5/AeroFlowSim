# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The result of replaying a 3D geometry document: plain Python data (no Gmsh, no Qt).

The 3D counterpart of built.py. After the history has been replayed in the CAD kernel
(kernel3d.py), everything the GUI, the picking code, the checks and the tests need is copied here:

    Body3D    one solid (a "volume" in OpenCASCADE): its role ("fluid" = to be meshed, "solid" = a
              body that is cut out of the fluid), its faces, exact volume, surface area and centroid
    Face3D    one surface: a STABLE id, its kind (plane, cylinder, sphere ...), exact area and
              centroid, the bodies that use it, its edges, and a coarse triangulation for drawing
              and picking
    Edge3D    one curve between faces (for picking edges, e.g. to give them a size): points, length
    BuiltGeometry3D  all of the above + boundary names (per face), refinement regions, messages

Face ids are STABLE: they say where a face came from (see kernel3d.py, "lineage"), e.g.
"op1:xmin" (the x-min side of the box made by op1), "op2:side" (the side of a cylinder) or
"op1:surface#2" (the 2nd piece of a sphere's surface after a boolean). Boundary names refer to
these ids, so they survive later edits. Edge ids are made from the faces that meet there,
"E(op1:side|op1:top)", for the same reason.

Coordinates are metres.
"""

from dataclasses import dataclass, field

import numpy as np

from aeroflowsim.geometry_model.built import FLUID, SOLID, Boundary, Region  # noqa: F401  (shared with 2D)


@dataclass
class Edge3D:
    id: str                         # "E(<face id>|<face id>)" (sorted), stable as the face ids
    points: np.ndarray              # (n, 3) points from start to end [m]
    length: float                   # [m]
    faces: list = field(default_factory=list)   # ids of the faces that meet at this edge


@dataclass
class Face3D:
    id: str                         # stable id, e.g. "op1:xmin"
    kind: str                       # "plane", "cylinder", "cone", "sphere", "torus", "spline" or "surface"
    area: float                     # [m²] (exact, from the CAD kernel)
    centroid: np.ndarray            # (3,) [m]
    sources: tuple = ()             # lineage ids this face comes from (for matching boundary names)
    default_name: str = ""          # name given by the operation that made it, e.g. "farfield"
    default_type: str = ""          # its boundary type
    bodies: list = field(default_factory=list)  # ids of the bodies that use this face
    edges: list = field(default_factory=list)   # ids of its edges
    box: np.ndarray = None          # (6,) bounding box x0 y0 z0 x1 y1 z1 [m]
    triangles: np.ndarray = None    # (m, 3, 3) a coarse triangulation, for drawing and picking

    def matches(self, pattern: str) -> bool:
        """True if a name given to `pattern` applies to this face (the face, its pieces "#n" and the
        faces merged from it), as Edge.matches in 2D."""
        if self.id == pattern or self.id.startswith(pattern + "#"):
            return True
        return any(s == pattern or s.startswith(pattern + "#") for s in self.sources)


@dataclass
class Body3D:
    id: str                         # stable id, e.g. "op1" (the operation that made it)
    role: str                       # FLUID or SOLID
    faces: list                     # ids of its faces
    volume: float                   # [m³] (exact, from the CAD kernel)
    area: float                     # total surface area [m²]
    centroid: np.ndarray            # (3,) [m]


@dataclass
class BuiltGeometry3D:
    dimension: int = 3
    axisymmetric: bool = False      # never (kept so code shared with 2D can ask)
    bodies: dict = field(default_factory=dict)       # {id: Body3D}
    faces: dict = field(default_factory=dict)        # {id: Face3D}
    edges: dict = field(default_factory=dict)        # {id: Edge3D}
    names: dict = field(default_factory=dict)        # {face id: Boundary} for named faces
    regions: list = field(default_factory=list)      # [Region] (shape "box", "sphere" or "cylinder")
    messages: list = field(default_factory=list)     # [(level, text)]
    failed_operation: str = ""                       # id of the operation that failed (replay stopped there)
    construction: list = field(default_factory=list) # (unused in 3D; shared attribute names with 2D)
    dimensions: list = field(default_factory=list)
    sketch_status: dict = field(default_factory=dict)

    # ---- simple facts --------------------------------------------------------------------------

    @property
    def empty(self) -> bool:
        return not self.faces

    def bbox(self):
        """(x_min, y_min, z_min, x_max, y_max, z_max) of all faces [m], or None if there are none."""
        pts = [f.box.reshape(2, 3) for f in self.faces.values() if f.box is not None]
        pts += [e.points for e in self.edges.values()]
        if not pts:
            return None
        pts = np.vstack(pts)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        return (*map(float, lo), *map(float, hi))

    @property
    def size(self) -> float:
        """Size of the geometry (bounding-box diagonal) [m]; 1 if empty."""
        box = self.bbox()
        if box is None:
            return 1.0
        return max(float(np.linalg.norm(np.subtract(box[3:], box[:3]))), 1e-300)

    def bodies_with_role(self, role):
        return [b for b in self.bodies.values() if b.role == role]

    def reference_length(self) -> float:
        """A length for sizing cells and domains [m]: the largest extent of the solid bodies, or of the faces
        of holes in the fluid (bodies already cut out), or of the whole fluid when there are none."""
        solids = self.bodies_with_role(SOLID)
        faces = [f for b in solids for f in b.faces]
        if not faces:
            faces = [f.id for f in self.faces.values() if f.default_type == "wall" or
                     (f.id in self.names and self.names[f.id].type == "wall")]
        if not faces:
            faces = list(self.faces)
        pts = [self.faces[f].box.reshape(2, 3) for f in faces if self.faces[f].box is not None]
        if not pts:
            return 1.0
        return max(float(np.ptp(np.vstack(pts), axis=0).max()), 1e-300)

    def boundary_faces(self) -> list:
        """Ids of the faces on the boundary of the fluid: used by exactly one fluid body.

        These become mesh patches, so every one of them needs a name. Faces between two fluid
        bodies are inside the fluid; faces of solid bodies only are not meshed.
        """
        fluid = {b.id for b in self.bodies_with_role(FLUID)}
        return [f.id for f in self.faces.values() if sum(b in fluid for b in f.bodies) == 1]

    def patches(self) -> dict:
        """{patch name: (type, [face ids])} of the named boundary faces, in face order."""
        out = {}
        for face_id in self.boundary_faces():
            b = self.names.get(face_id)
            if b is not None:
                out.setdefault(b.name, (b.type, []))[1].append(face_id)
        return out

    def fluid_volume(self) -> float:
        """Exact volume of the fluid bodies [m³]."""
        return sum(b.volume for b in self.bodies_with_role(FLUID))

    def errors(self) -> list:
        return [text for level, text in self.messages if level == "error"]

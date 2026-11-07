# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The operations of a 3D geometry history (the 3D counterpart of operations.py).

Same rules as in 2D: every operation has an id, a suppressed flag and plain-number params (saved in
geometry/history.json), and apply(kernel, context) builds its part with the Kernel3D (kernel3d.py).
All lengths are metres and all angles degrees. The faces each operation makes get stable ids:

    Box        "<op>:xmin", ":xmax", ":ymin", ":ymax", ":zmin", ":zmax"
    Cylinder   "<op>:side", ":base", ":top"        Cone: the same (no ":top" when the tip is sharp)
    Sphere     "<op>:surface"
    Revolve    one face per profile edge, "<op>:edge1" ... (a wall profile file: ":wall", ":inlet", ":outlet");
               a partial revolution adds ":start" and ":end"
    Extrude    "<op>:bottom", ":top", ":side1" ... (one per polygon edge)
    Import     "<op>:face1" ... numbered by centroid (x, then y, z), so a file always gives the same ids
    Enclosure  box: ":upstream" (x min), ":downstream" (x max), ":ymin", ":ymax", ":zmin", ":zmax";
               cylinder (axis along x): ":upstream", ":downstream", ":side"; sphere: ":surface";
               half domain: ":symmetry" (the plane y = 0)

Bodies made by an operation get the operation's id as their body id ("op3").
"""

import math

import numpy as np

from aeroflowsim.geometry_model.built3d import FLUID, SOLID, Boundary, Region
from aeroflowsim.geometry_model.operations import Operation

ROLES = (SOLID, FLUID)


def _role(value) -> str:
    if value not in ROLES:
        raise ValueError(f"the role must be 'solid' or 'fluid', not '{value}'")
    return value


def _positive(name, value):
    if not float(value) > 0.0:
        raise ValueError(f"{name} must be positive")
    return float(value)


def _wall_defaults(role):
    """Faces of a solid body are walls by default; faces of a fluid body get no name (the user decides)."""
    return ("wall", "wall") if role == SOLID else ("", "")


class Operation3D(Operation):
    dimension = 3


# =============================================================================================
# Bodies
# =============================================================================================

class Box(Operation3D):
    """A box from the corner (x0, y0, z0) with sides dx, dy, dz [m]."""

    type, title = "box", "Box"
    DEFAULTS = {"x0": 0.0, "y0": 0.0, "z0": 0.0, "dx": 0.1, "dy": 0.1, "dz": 0.1, "role": SOLID}

    def summary(self) -> str:
        p = self.params
        return f"Box {p['dx']:.4g} x {p['dy']:.4g} x {p['dz']:.4g} m ({p['role']})"

    def apply(self, kernel, context):
        p = self.params
        size = [_positive(k, p[k]) for k in ("dx", "dy", "dz")]
        role = _role(p["role"])
        vol = kernel.occ.addBox(float(p["x0"]), float(p["y0"]), float(p["z0"]), *size)
        kernel.sync()
        label_box(kernel, vol, self.id, ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"), *_wall_defaults(role))
        kernel.name_body(vol, self.id, role)


class Cylinder(Operation3D):
    """A cylinder: base centre (x, y, z), axis vector (ax, ay, az) whose length is the height, radius [m]."""

    type, title = "cylinder", "Cylinder"
    DEFAULTS = {"x": 0.0, "y": 0.0, "z": 0.0, "ax": 0.1, "ay": 0.0, "az": 0.0, "radius": 0.05, "role": SOLID}

    def summary(self) -> str:
        p = self.params
        length = math.sqrt(p["ax"] ** 2 + p["ay"] ** 2 + p["az"] ** 2)
        return f"Cylinder r = {p['radius']:.4g} m, length {length:.4g} m ({p['role']})"

    def apply(self, kernel, context):
        p = self.params
        axis = _axis(p)
        role = _role(p["role"])
        vol = kernel.occ.addCylinder(float(p["x"]), float(p["y"]), float(p["z"]), *axis,
                                     _positive("the radius", p["radius"]))
        kernel.sync()
        label_axial(kernel, vol, self.id, (p["x"], p["y"], p["z"]), axis, *_wall_defaults(role))
        kernel.name_body(vol, self.id, role)


class Cone(Operation3D):
    """A cone (or truncated cone): base centre (x, y, z), axis (ax, ay, az), base radius r1, top radius r2 [m]."""

    type, title = "cone", "Cone"
    DEFAULTS = {"x": 0.0, "y": 0.0, "z": 0.0, "ax": 0.1, "ay": 0.0, "az": 0.0, "r1": 0.05, "r2": 0.0, "role": SOLID}

    def summary(self) -> str:
        p = self.params
        return f"Cone r = {p['r1']:.4g} -> {p['r2']:.4g} m ({p['role']})"

    def apply(self, kernel, context):
        p = self.params
        axis = _axis(p)
        role = _role(p["role"])
        if float(p["r2"]) < 0.0:
            raise ValueError("the top radius cannot be negative")
        vol = kernel.occ.addCone(float(p["x"]), float(p["y"]), float(p["z"]), *axis,
                                 _positive("the base radius", p["r1"]), float(p["r2"]))
        kernel.sync()
        label_axial(kernel, vol, self.id, (p["x"], p["y"], p["z"]), axis, *_wall_defaults(role))
        kernel.name_body(vol, self.id, role)


class Sphere(Operation3D):
    """A sphere: centre (xc, yc, zc), radius [m]."""

    type, title = "sphere", "Sphere"
    DEFAULTS = {"xc": 0.0, "yc": 0.0, "zc": 0.0, "radius": 0.05, "role": SOLID}

    def summary(self) -> str:
        return f"Sphere r = {self.params['radius']:.4g} m ({self.params['role']})"

    def apply(self, kernel, context):
        p = self.params
        role = _role(p["role"])
        vol = kernel.occ.addSphere(float(p["xc"]), float(p["yc"]), float(p["zc"]), _positive("the radius", p["radius"]))
        kernel.sync()
        kernel.label_new_faces([vol], self.id, "surface", *_wall_defaults(role))
        kernel.name_body(vol, self.id, role)


class ImportSolid(Operation3D):
    """Solids from a STEP or IGES file (exact CAD surfaces). unit: "file" (what the file says) or mm, m, inch.

    A file with closed surfaces but no solid (a "shell") is sewn into a solid. The file is stored in the
    project (path relative to the project folder) so the project replays the same way everywhere.
    """

    type, title = "import_solid", "Import solid"
    DEFAULTS = {"file": "", "unit": "file", "role": SOLID}

    def summary(self) -> str:
        from pathlib import Path
        return f"Import {Path(self.params['file']).name or '(no file)'} ({self.params['role']})"

    def apply(self, kernel, context):
        from aeroflowsim.geometry_model.importers import UNITS, cad_file_unit
        p = self.params
        role = _role(p["role"])
        path = context.path(p["file"]) if context is not None else p["file"]
        if not str(p["file"]) or not path.is_file():
            raise ValueError(f"the file '{p['file']}' was not found")
        if p["unit"] != "file" and p["unit"] not in UNITS:
            raise ValueError(f"unknown unit '{p['unit']}'")
        gmsh, occ = kernel.gmsh, kernel.occ
        # As in 2D (importers.import_cad): OpenCASCADE reads in millimetres, Gmsh's import scaling gives metres
        # exactly (a later "dilate" would turn exact surfaces into B-spline approximations).
        stated = cad_file_unit(path)
        factor = UNITS["mm"]
        if p["unit"] != "file":
            factor *= UNITS[p["unit"]] / UNITS[stated or "mm"]
        elif stated is None:
            kernel.message("The file does not state its unit; millimetres assumed. Choose the unit if that is wrong.")
        before = set(kernel.volume_tags())
        gmsh.option.setNumber("Geometry.OCCScaling", factor)
        try:
            entities = occ.importShapes(str(path), highestDimOnly=True)
        except Exception as error:
            raise ValueError(f"OpenCASCADE could not read {path.name}: {error}") from None
        finally:
            gmsh.option.setNumber("Geometry.OCCScaling", 1.0)
        kernel.sync()
        if not entities:
            raise ValueError(f"{path.name} contains no geometry.")
        dim = max(d for d, _ in entities)
        if dim == 2:                               # a closed shell: sew it into a solid
            try:
                loop = occ.addSurfaceLoop([t for d, t in entities if d == 2], sewing=True)
                occ.addVolume([loop])
                kernel.sync()
            except Exception:
                raise ValueError(f"{path.name} has surfaces that do not close a solid; a 3D import needs solids "
                                 "(or a closed shell).") from None
            kernel.message(f"{path.name} had a closed shell and no solid; it was sewn into a solid.", "info")
        elif dim < 2:
            raise ValueError(f"{path.name} contains only curves or points; a 3D import needs solids.")
        volumes = sorted(set(kernel.volume_tags()) - before)
        if not volumes:
            raise ValueError(f"{path.name} contains no solid.")
        kernel.label_new_faces(volumes, self.id, "face", *_wall_defaults(role))
        order = sorted(volumes, key=lambda v: tuple(np.round(kernel.occ.getCenterOfMass(3, v), 12)))
        for n, vol in enumerate(order, start=1):
            kernel.name_body(vol, self.id if len(order) == 1 else f"{self.id}.{n}", role)
        kernel.message(f"Imported {len(order)} solid(s) from {path.name}.", "info")


class Revolve(Operation3D):
    """A body of revolution about the x axis: a closed profile in the x-r plane turned by `angle` [deg].

    profile "points": `points` [[x, r], ...] [m], closed automatically; face k comes from edge k
    (from point k to point k+1). Points on the axis (r = 0) make no face there.
    profile "wall": a nozzle wall CSV file (x_mm,r_mm, as everywhere in AeroFlowSim), closed with the inlet,
    the axis and the outlet; its faces are ":wall" (a wall), ":inlet" and ":outlet". The default role of a
    nozzle is fluid (the gas inside it).
    profile "nozzle" (full 3D release stage): the same as "wall", with the wall points [[x, r], ...] [m] given in
    `points` instead of a file (the nozzle_3d template revolves its parametric contour this way).
    names (profile "points", optional): one [name, type] per edge (e.g. the outlets of a plume region); "" = the
    default of the role.
    """

    type, title = "revolve", "Revolve"
    DEFAULTS = {"profile": "points", "points": [[0.0, 0.0], [0.1, 0.0], [0.1, 0.02], [0.0, 0.02]], "file": "",
                "angle": 360.0, "role": SOLID, "names": []}

    def summary(self) -> str:
        p = self.params
        what = f"{len(p['points'])}-point profile" if p["profile"] == "points" else "wall profile file"
        return f"Revolve {what} by {p['angle']:.4g}° about the x axis ({p['role']})"

    def apply(self, kernel, context):
        p = self.params
        role = _role(p["role"])
        angle = float(p["angle"])
        if not 0.0 < angle <= 360.0:
            raise ValueError("the angle of revolution must be more than 0 and at most 360 degrees")
        if p["profile"] in ("wall", "nozzle"):
            points, labels, names = self._wall(context)
        elif p["profile"] == "points":
            points = np.asarray(p["points"], dtype=float)
            if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3:
                raise ValueError("a profile needs at least three [x, r] points")
            labels = [f"edge{k}" for k in range(1, len(points) + 1)]
            names = [_wall_defaults(role)] * len(points)
            for k, entry in enumerate((p.get("names") or [])[:len(points)]):
                if entry and entry[0]:
                    names[k] = (str(entry[0]), str(entry[1] if len(entry) > 1 else entry[0]))
        else:
            raise ValueError(f"unknown profile '{p['profile']}'")
        if np.any(points[:, 1] < -1e-12):
            raise ValueError("a profile to revolve about the x axis needs r >= 0 everywhere")
        points[:, 1] = np.maximum(points[:, 1], 0.0)
        face = _planar_face(kernel, points)
        out = kernel.occ.revolve([(2, face)], 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, math.radians(angle))
        kernel.sync()
        vols = [t for d, t in out if d == 3]
        kernel.remove_free_points()
        size = max(float(np.ptp(points, axis=0).max()), 1e-300)
        for vol in vols:
            for tag in kernel.faces_of(vol):
                probe = kernel.probes(tag)
                theta = np.degrees(np.arctan2(probe[:, 2], probe[:, 1]))
                xr = np.column_stack([probe[:, 0], np.hypot(probe[:, 1], probe[:, 2])])
                if kernel.face_kind(tag) == "plane" and angle < 360.0 and np.ptp(theta) < 1e-6 and \
                        np.all(np.hypot(*(probe[:, 1:].T)) > 1e-9 * size):
                    label = "start" if abs(theta[0]) < 1e-6 else "end"
                    kernel.name_face(tag, f"{self.id}:{label}", "symmetry", "symmetry")
                    continue
                k = _nearest_segment(points, xr)
                kernel.name_face(tag, f"{self.id}:{labels[k]}", *names[k])
            kernel.name_body(vol, self.id, role)

    def _wall(self, context):
        if self.params["profile"] == "nozzle":
            xr = np.asarray(self.params["points"], dtype=float)
            if xr.ndim != 2 or xr.shape[1] != 2 or len(xr) < 2 or np.any(np.diff(xr[:, 0]) <= 0):
                raise ValueError("a nozzle wall needs two or more [x, r] points with x increasing")
            x, r = xr[:, 0], xr[:, 1]
        else:
            from aeroflowsim.geometry import read_profile_csv
            path = context.path(self.params["file"]) if context is not None else self.params["file"]
            wall = read_profile_csv(path)
            x, r = np.asarray(wall.x, dtype=float), np.asarray(wall.r, dtype=float)
        points = np.vstack([np.column_stack([x, r]), [[x[-1], 0.0], [x[0], 0.0]]])
        # edge k runs from point k to point k+1: the wall edges, then outlet, axis, inlet
        n = len(x) - 1
        labels = ["wall"] * n + ["outlet", "axis", "inlet"]
        names = [("wall", "wall")] * n + [("outlet", "outlet"), ("", ""), ("inlet", "inlet")]
        if self.params["role"] == SOLID:
            raise ValueError("a nozzle wall profile makes the gas inside the nozzle: set the role to fluid")
        return points, labels, names


class Extrude(Operation3D):
    """A prism: a closed polygon `points` [[x, y], ...] [m] in the plane z = z0, extruded by `length` along +z."""

    type, title = "extrude", "Extrude"
    DEFAULTS = {"points": [[0.0, 0.0], [0.1, 0.0], [0.1, 0.05], [0.0, 0.05]], "z0": 0.0, "length": 0.1,
                "role": SOLID}

    def summary(self) -> str:
        p = self.params
        return f"Extrude {len(p['points'])}-point outline by {p['length']:.4g} m ({p['role']})"

    def apply(self, kernel, context):
        p = self.params
        role = _role(p["role"])
        points = np.asarray(p["points"], dtype=float)
        if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3:
            raise ValueError("an outline needs at least three [x, y] points")
        length = _positive("the length", p["length"])
        z0 = float(p["z0"])
        face = _planar_face(kernel, points, z0)
        out = kernel.occ.extrude([(2, face)], 0.0, 0.0, length)
        kernel.sync()
        vols = [t for d, t in out if d == 3]
        defaults = _wall_defaults(role)
        for vol in vols:
            for tag in kernel.faces_of(vol):
                c = kernel.face_centre(tag)
                if kernel.face_kind(tag) == "plane" and abs(c[2] - z0) < 1e-9 * (1.0 + length):
                    label = "bottom"
                elif kernel.face_kind(tag) == "plane" and abs(c[2] - z0 - length) < 1e-9 * (1.0 + length):
                    label = "top"
                else:
                    label = f"side{_nearest_segment(points, kernel.probes(tag)[:, :2]) + 1}"
                kernel.name_face(tag, f"{self.id}:{label}", *defaults)
            kernel.name_body(vol, self.id, role)


# =============================================================================================
# Editing
# =============================================================================================

class Transform3D(Operation3D):
    """Move, rotate, scale or mirror bodies (all of them when `targets` is empty), optionally as a copy.

    move: by (dx, dy, dz); rotate: by `angle` [deg] about the axis (ax, ay, az) through (cx, cy, cz);
    scale: by `factor` about (cx, cy, cz); mirror: in the plane through (cx, cy, cz) with normal (ax, ay, az).
    """

    type, title = "transform_3d", "Transform"
    DEFAULTS = {"targets": [], "kind": "move", "dx": 0.0, "dy": 0.0, "dz": 0.0, "cx": 0.0, "cy": 0.0, "cz": 0.0,
                "ax": 0.0, "ay": 0.0, "az": 1.0, "angle": 0.0, "factor": 1.0, "copy": False}
    KINDS = ("move", "rotate", "scale", "mirror")

    def summary(self) -> str:
        p = self.params
        what = "everything" if not p["targets"] else f"{len(p['targets'])} body(ies)"
        text = {"move": f"Move {what} by ({p['dx']:.4g}, {p['dy']:.4g}, {p['dz']:.4g}) m",
                "rotate": f"Rotate {what} by {p['angle']:.4g}° about ({p['ax']:.3g}, {p['ay']:.3g}, {p['az']:.3g})",
                "scale": f"Scale {what} by {p['factor']:.4g}",
                "mirror": f"Mirror {what} in the plane with normal ({p['ax']:.3g}, {p['ay']:.3g}, {p['az']:.3g})"}
        text = text.get(p["kind"], p["kind"])
        return ("Copy and " + text[0].lower() + text[1:]) if p["copy"] else text

    def apply(self, kernel, context):
        p = self.params
        if p["kind"] not in self.KINDS:
            raise ValueError(f"unknown transform '{p['kind']}'")
        targets = kernel.dim_tags(p["targets"])
        if not targets:
            raise ValueError("there is nothing to transform")
        occ = kernel.occ
        c = (float(p["cx"]), float(p["cy"]), float(p["cz"]))
        a = (float(p["ax"]), float(p["ay"]), float(p["az"]))
        if p["kind"] == "move":
            def apply(dim_tags):
                occ.translate(dim_tags, float(p["dx"]), float(p["dy"]), float(p["dz"]))
        elif p["kind"] == "rotate":
            if not any(a):
                raise ValueError("the rotation axis cannot be zero")

            def apply(dim_tags):
                occ.rotate(dim_tags, *c, *a, math.radians(float(p["angle"])))
        elif p["kind"] == "scale":
            f = _positive("the scale factor", p["factor"])

            def apply(dim_tags):
                occ.dilate(dim_tags, *c, f, f, f)
        else:
            if not any(a):
                raise ValueError("the mirror plane needs a normal")

            def apply(dim_tags):
                occ.mirror(dim_tags, *a, -float(np.dot(a, c)))
        kernel.transformed(targets, apply, self.id, bool(p["copy"]))


class Boolean3D(Operation3D):
    """Union, subtract or intersect bodies: `objects` (the first is the body that keeps its id) and `tools`."""

    type, title = "boolean_3d", "Boolean"
    DEFAULTS = {"kind": "union", "objects": [], "tools": []}
    KINDS = ("union", "subtract", "intersect")

    def summary(self) -> str:
        p = self.params
        return f"{p['kind'].capitalize()}: {', '.join(p['objects']) or '?'} with {', '.join(p['tools']) or '?'}"

    def apply(self, kernel, context):
        p = self.params
        if p["kind"] not in self.KINDS:
            raise ValueError(f"unknown boolean '{p['kind']}'")
        result = kernel.boolean(p["kind"], list(p["objects"]), list(p["tools"]), self.id)
        if not result:
            raise ValueError("the result of the boolean is empty (the bodies do not overlap?)")


class SetRole3D(Operation3D):
    """Mark bodies as fluid (meshed) or solid (cut out of the fluid by an enclosure)."""

    type, title = "set_role_3d", "Fluid / solid"
    DEFAULTS = {"bodies": [], "role": SOLID}

    def summary(self) -> str:
        return f"Mark {len(self.params['bodies'])} body(ies) {self.params['role']}"

    def apply(self, kernel, context):
        role = _role(self.params["role"])
        if not self.params["bodies"]:
            raise ValueError("no bodies chosen")
        for body_id in self.params["bodies"]:
            tag = kernel.body_by_id(body_id)
            kernel.body_meta[tag].role = role


class FluidZones3D(Operation3D):
    """Several fluid zones (full 3D release stage): the fluid bodies listed (all fluid bodies when empty) are joined by
    Fragment, so they share their interface faces (a conformal interface: the mesh has one face there, owned by one zone
    and neighboured by the other). Where bodies overlap the LATER body wins (e.g. an enclosure, then a plume region
    inside it: the region becomes the zone "plume", the rest of the enclosure keeps its zone). names: {body id: zone
    name}. Solid bodies are not touched (they are still cut out by the enclosure). sizes: {zone: cell size [m]} (a constant
    size inside the zone, combined with the other size fields by Min); excluded: zones that are not solved ("solid /
    excluded": removed after meshing, their faces with the other zones become the wall patch "<zone>_wall")."""

    type, title = "fluid_zones_3d", "Fluid zones"
    DEFAULTS = {"bodies": [], "names": {}, "sizes": {}, "excluded": [], "name": "", "size": 0.0, "exclude": False}

    def summary(self) -> str:
        n = len(self.params["bodies"])
        return f"Fluid zones: {n} bodies" if n else "Fluid zones: all fluid bodies"

    def apply(self, kernel, context):
        bodies = list(self.params["bodies"]) or [kernel.body_meta[t].id for t in kernel.bodies_with_role(FLUID)
                                                 if t in kernel.body_meta]
        for b in bodies:
            if kernel.body_meta[kernel.body_by_id(b)].role != FLUID:
                raise ValueError(f"body '{b}' is solid: only fluid bodies become zones (mark it fluid first)")
        names, sizes, excluded = _zone_params(self.params, bodies[-1])
        kernel.fragment(bodies, self.id, names)
        kernel.zone_settings(sizes, excluded)


def _zone_params(p, last):
    """(names, sizes, excluded) of a Fluid zones operation, with the flat settings of the form applied to `last`."""
    names, sizes = dict(p.get("names") or {}), dict(p.get("sizes") or {})
    excluded = list(p.get("excluded") or [])
    if p.get("name"):
        names[last] = str(p["name"]).strip()
    zone = names.get(last) or names.get(str(last).split(":")[0]) or last
    if float(p.get("size") or 0.0) > 0.0:
        sizes[zone] = float(p["size"])
    if p.get("exclude") and zone not in excluded:
        excluded.append(zone)
    return names, sizes, excluded


class Delete3D(Operation3D):
    """Delete bodies."""

    type, title = "delete_3d", "Delete"
    DEFAULTS = {"bodies": []}

    def summary(self) -> str:
        return f"Delete {len(self.params['bodies'])} body(ies)"

    def apply(self, kernel, context):
        if not self.params["bodies"]:
            raise ValueError("no bodies chosen")
        tags = [kernel.body_by_id(b) for b in self.params["bodies"]]
        kernel.occ.remove([(3, t) for t in tags], recursive=True)
        kernel.sync()
        for t in tags:
            kernel.body_meta.pop(t, None)


# =============================================================================================
# Domain, names and mesh controls
# =============================================================================================

class Enclosure3D(Operation3D):
    """The fluid domain around the solid bodies (which are subtracted), sized in reference lengths L
    (L = the largest extent of the solid bodies):

        box        upstream (x), downstream (x) and lateral (y and z, each side, from the bodies' bounding box)
        cylinder   axis along x through the bodies' centre: upstream, downstream, radius
        sphere     about the bodies' centre: radius
    half: only y >= 0 is kept, with a symmetry plane at y = 0 (a body symmetric about y = 0 needs half the cells).
    quarter (with half): also only z >= 0, a second symmetry plane at z = 0 (an axisymmetric body or a nozzle at zero
    incidence: a quarter of the cells). Both planes are faces of the one "symmetry" boundary. Read with .get, so
    documents written before the 3D Euler stage (no "quarter" key) replay as before.
    """

    type, title = "enclosure_3d", "Enclosure"
    DEFAULTS = {"kind": "box", "upstream": 5.0, "downstream": 10.0, "lateral": 5.0, "radius": 10.0, "half": False,
                "quarter": False}
    KINDS = ("box", "cylinder", "sphere")

    def summary(self) -> str:
        p = self.params
        size = {"box": f"{p['upstream']:g} L up, {p['downstream']:g} L down, {p['lateral']:g} L to the sides",
                "cylinder": f"{p['upstream']:g} L up, {p['downstream']:g} L down, radius {p['radius']:g} L",
                "sphere": f"radius {p['radius']:g} L"}.get(p["kind"], "")
        part = (", quarter" if p.get("quarter") else ", half") if p["half"] else ""
        return f"Enclosure: {p['kind']} ({size}){part}"

    def apply(self, kernel, context):
        p = self.params
        if p["kind"] not in self.KINDS:
            raise ValueError(f"unknown enclosure '{p['kind']}'")
        bodies = kernel.bodies_with_role(SOLID)
        if not bodies:
            raise ValueError("an enclosure goes around a solid body, and there is none (mark a body as solid)")
        box = kernel.bounding_box(bodies)
        lo, hi = box[:3], box[3:]
        L = float(np.max(hi - lo))                  # reference length [m]
        centre = 0.5 * (lo + hi)
        occ = kernel.occ
        farfield = ("farfield", "farfield")
        if p["kind"] == "box":
            x0, x1 = lo[0] - p["upstream"] * L, hi[0] + p["downstream"] * L
            side = p["lateral"] * L
            y0, z0 = lo[1] - side, lo[2] - side
            vol = occ.addBox(x0, y0, z0, x1 - x0, hi[1] + side - y0, hi[2] + side - z0)
            kernel.sync()
            label_box(kernel, vol, self.id, ("upstream", "downstream", "ymin", "ymax", "zmin", "zmax"), *farfield)
        elif p["kind"] == "cylinder":
            x0, x1 = lo[0] - p["upstream"] * L, hi[0] + p["downstream"] * L
            vol = occ.addCylinder(x0, centre[1], centre[2], x1 - x0, 0.0, 0.0, _positive("the radius", p["radius"]) * L)
            kernel.sync()
            label_axial(kernel, vol, self.id, (x0, centre[1], centre[2]), (x1 - x0, 0.0, 0.0), *farfield,
                        names=("upstream", "downstream", "side"))
        else:
            vol = occ.addSphere(*centre, _positive("the radius", p["radius"]) * L)
            kernel.sync()
            kernel.label_new_faces([vol], self.id, "surface", *farfield)
        kernel.name_body(vol, self.id, FLUID)
        if p["half"]:
            big = 4.0 * kernel.model_size() + float(np.abs(box).max())
            cutter = occ.addBox(-big, -2.0 * big, -big, 2.0 * big, 2.0 * big, 2.0 * big)   # everything with y < 0
            kernel.sync()
            label_box(kernel, cutter, f"{self.id}", ("cut1", "cut2", "cut3", "symmetry", "cut5", "cut6"),
                      "symmetry", "symmetry")
            kernel.name_body(cutter, f"{self.id}:cutter", SOLID)
            kernel.boolean("subtract", [vol], [cutter], self.id, FLUID)
            vol = kernel.body_by_id(self.id)
            if p.get("quarter"):
                cutter = occ.addBox(-big, -big, -2.0 * big, 2.0 * big, 2.0 * big, 2.0 * big)   # everything with z < 0
                kernel.sync()
                label_box(kernel, cutter, f"{self.id}:z", ("cut1", "cut2", "cut3", "cut4", "cut5", "symmetry_z"),
                          "symmetry", "symmetry")
                kernel.name_body(cutter, f"{self.id}:zcutter", SOLID)
                kernel.boolean("subtract", [vol], [cutter], self.id, FLUID)
                vol = kernel.body_by_id(self.id)
        kernel.boolean("subtract", [vol], bodies, self.id, FLUID)


class NameFaces(Operation3D):
    """Give faces a boundary name and type (they become a mesh patch of that name); inflation: grow prism
    layers from them (walls)."""

    type, title = "name_faces", "Name boundary"
    DEFAULTS = {"faces": [], "name": "", "kind": "wall", "inflation": False}

    def summary(self) -> str:
        p = self.params
        return f"Name {len(p['faces'])} face(s) '{p['name']}' ({p['kind']}{', inflation' if p['inflation'] else ''})"

    def apply(self, kernel, context):
        from aeroflowsim.geometry_model.boundaries import check_name, check_type
        p = self.params
        check_name(p["name"])
        check_type(p["kind"])
        if not p["faces"]:
            raise ValueError("no faces chosen")
        kernel.names.append((list(p["faces"]), Boundary(p["name"], p["kind"], bool(p["inflation"]), "user"), self.id))


class Refinement3D(Operation3D):
    """A refinement region where cells are at most `size` [m]:
    box (x0 y0 z0 - x1 y1 z1), sphere (centre xc yc zc, radius) or cylinder (axis from x0 y0 z0 to x1 y1 z1, radius)."""

    type, title = "refinement_3d", "Refinement region"
    DEFAULTS = {"shape": "box", "x0": 0.0, "y0": 0.0, "z0": 0.0, "x1": 1.0, "y1": 1.0, "z1": 1.0,
                "xc": 0.0, "yc": 0.0, "zc": 0.0, "radius": 1.0, "size": 0.01}
    SHAPES = ("box", "sphere", "cylinder")
    KEYS = {"box": ("x0", "y0", "z0", "x1", "y1", "z1"), "sphere": ("xc", "yc", "zc", "radius"),
            "cylinder": ("x0", "y0", "z0", "x1", "y1", "z1", "radius")}

    def summary(self) -> str:
        return f"Refinement {self.params['shape']}: cells ≤ {self.params['size']:.4g} m"

    def apply(self, kernel, context):
        p = self.params
        if p["shape"] not in self.SHAPES:
            raise ValueError(f"unknown refinement region '{p['shape']}'")
        size = _positive("the cell size", p["size"])
        values = {k: float(p[k]) for k in self.KEYS[p["shape"]]}
        if p["shape"] == "box" and not all(values[f"{a}1"] > values[f"{a}0"] for a in "xyz"):
            raise ValueError("a refinement box needs x1 > x0, y1 > y0 and z1 > z0")
        if p["shape"] in ("sphere", "cylinder") and not values["radius"] > 0.0:
            raise ValueError("the radius must be positive")
        if p["shape"] == "cylinder" and not any(values[f"{a}1"] != values[f"{a}0"] for a in "xyz"):
            raise ValueError("a refinement cylinder needs two different end points")
        kernel.regions.append(Region(self.id, p["shape"], values, size))


# =============================================================================================
# Template geometry (follows the template's geometry inputs; see cases/external_3d)
# =============================================================================================

class TemplateBody(Operation3D):
    """The template's body, from its geometry inputs: case.body_3d(params) gives one operation (Sphere, Box ...)
    whose faces and body take THIS operation's id, so old projects and names stay valid."""

    type, title = "template_body", "Template body"

    def summary(self) -> str:
        return "Template body (follows the geometry inputs)"

    def apply(self, kernel, context):
        if context is None or context.case is None or not hasattr(context.case, "body_3d"):
            raise ValueError("this template has no 3D body")
        op = context.case.body_3d(context.params)
        op.id = self.id
        op.apply(kernel, context)


class TemplateEnclosure3D(Operation3D):
    """The template's far-field domain around the body, from its inputs: case.domain_3d(params) gives an
    Enclosure3D whose faces take this operation's id."""

    type, title = "template_enclosure_3d", "Template far field"

    def summary(self) -> str:
        return "Template far field (follows the geometry inputs)"

    def apply(self, kernel, context):
        op = context.case.domain_3d(context.params)
        if op is None:                         # no far field for these inputs (e.g. a nozzle without plume region)
            return
        op.id = self.id
        op.apply(kernel, context)


TEMPLATE_TYPES_3D = ("template_body", "template_enclosure_3d")


# =============================================================================================
# Helpers
# =============================================================================================

def _axis(p):
    axis = (float(p["ax"]), float(p["ay"]), float(p["az"]))
    if not math.sqrt(sum(a * a for a in axis)) > 0.0:
        raise ValueError("the axis (its length is the height) cannot be zero")
    return axis


def label_box(kernel, vol, op_id, labels, default_name="", default_type=""):
    """Name the six faces of a box by their side: labels for x min, x max, y min, y max, z min, z max."""
    faces = kernel.faces_of(vol)
    centres = np.array([kernel.face_centre(t) for t in faces])
    mid = centres.mean(axis=0)
    for tag, c in zip(faces, centres):
        d = c - mid
        axis = int(np.argmax(np.abs(d)))
        kernel.name_face(tag, f"{op_id}:{labels[2 * axis + (d[axis] > 0)]}", default_name, default_type)


def label_axial(kernel, vol, op_id, base, axis, default_name="", default_type="", names=("base", "top", "side")):
    """Name the faces of a cylinder or cone: the flat end at the base, the flat end at the top, the side."""
    base, axis = np.asarray(base, dtype=float), np.asarray(axis, dtype=float)
    length = float(np.linalg.norm(axis))
    for tag in kernel.faces_of(vol):
        if kernel.face_kind(tag) == "plane":
            along = float(np.dot(kernel.face_centre(tag) - base, axis)) / length
            label = names[0] if along < 0.5 * length else names[1]
        else:
            label = names[2]
        kernel.name_face(tag, f"{op_id}:{label}", default_name, default_type)


def _planar_face(kernel, points, z=0.0) -> int:
    """A plane face in z = const from a closed polygon (n, 2) [m] (points closer than 1e-12 m merged)."""
    occ = kernel.occ
    pts = [p for k, p in enumerate(points) if k == 0 or np.linalg.norm(p - points[k - 1]) > 1e-12]
    if np.linalg.norm(pts[0] - pts[-1]) <= 1e-12:
        pts = pts[:-1]
    tags = [occ.addPoint(float(x), float(y), float(z)) for x, y in pts]
    lines = [occ.addLine(tags[k], tags[(k + 1) % len(tags)]) for k in range(len(tags))]
    loop = occ.addCurveLoop(lines)
    face = occ.addPlaneSurface([loop])
    kernel.sync()
    return face


def _nearest_segment(points, probes) -> int:
    """Index k of the polygon edge (point k -> point k+1, closed) nearest to most of the probe points (m, 2)."""
    a = np.asarray(points, dtype=float)
    b = np.roll(a, -1, axis=0)
    votes = []
    for p in np.atleast_2d(probes):
        ab = b - a
        t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-300), 0.0, 1.0)
        votes.append(int(np.argmin(np.linalg.norm(a + t[:, None] * ab - p, axis=1))))
    return max(set(votes), key=votes.count)


OPERATIONS_3D = {cls.type: cls for cls in (Box, Cylinder, Cone, Sphere, ImportSolid, Revolve, Extrude, Transform3D,
                                           Boolean3D, SetRole3D, FluidZones3D, Delete3D, Enclosure3D, NameFaces, Refinement3D,
                                           TemplateBody, TemplateEnclosure3D)}

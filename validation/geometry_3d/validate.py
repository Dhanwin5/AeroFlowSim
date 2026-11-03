# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""3D geometry validation without a solver: the 3D workspace (aeroflowsim/geometry_model/, kernel3d.py) against exact
formulas.

    primitives          volume and surface area of a box, cylinder, sphere and cone made by the operations
    booleans            box minus a sphere centred on a corner (1/8 of the sphere removed), box united with a
                        sphere centred on its top face (half a sphere added), sphere intersected with a box
                        (a hemisphere)
    revolve / extrude   a frustum revolved from its profile, a triangular prism extruded from its outline
    enclosure           box enclosure (5 L up, 10 L down, 5 L to the sides) around a sphere: fluid volume
    STEP round trip     a box united with a sphere written as STEP and read back: volume, area, number of faces
    stable face ids     names given to faces stay on the same faces after the radius of the sphere and the size
                        of the box are changed upstream and a move is inserted before them

The volumes and areas come from OpenCASCADE's exact surfaces (no mesh), so the tolerances are tight.
"""

import math
import tempfile
from pathlib import Path

from aeroflowsim.geometry_model import GeometryDocument, replay
from aeroflowsim.geometry_model.export import export_step
from aeroflowsim.geometry_model.operations3d import (Boolean3D, Box, Cone, Cylinder, Enclosure3D, Extrude, ImportSolid,
                                                     NameFaces, Revolve, Sphere, Transform3D)


def _body(ops):
    built = replay(GeometryDocument(ops, dimension=3), triangulate=False)
    if built.errors():
        raise ValueError("; ".join(built.errors()))
    (body,) = built.bodies.values()
    return built, body


def measure():
    v = {}
    _, b = _body([Box("op1", dx=0.2, dy=0.3, dz=0.5)])
    v["box_volume"], v["box_area"] = b.volume, b.area
    _, b = _body([Cylinder("op1", ax=0.0, ay=0.0, az=0.4, radius=0.1)])
    v["cylinder_volume"], v["cylinder_area"] = b.volume, b.area
    _, b = _body([Sphere("op1", radius=0.25)])
    v["sphere_volume"], v["sphere_area"] = b.volume, b.area
    _, b = _body([Cone("op1", ax=0.3, r1=0.1, r2=0.05)])
    v["cone_volume"], v["cone_area"] = b.volume, b.area

    _, b = _body([Box("op1", dx=1.0, dy=1.0, dz=1.0), Sphere("op2", xc=1.0, yc=1.0, zc=1.0, radius=0.4),
                  Boolean3D("op3", kind="subtract", objects=["op1"], tools=["op2"])])
    v["subtract_volume"], v["subtract_area"] = b.volume, b.area
    _, b = _body([Box("op1", dx=1.0, dy=1.0, dz=1.0), Sphere("op2", xc=0.5, yc=0.5, zc=1.0, radius=0.3),
                  Boolean3D("op3", kind="union", objects=["op1"], tools=["op2"])])
    v["union_volume"], v["union_area"] = b.volume, b.area
    _, b = _body([Sphere("op1", radius=1.0), Box("op2", x0=0.0, y0=-2.0, z0=-2.0, dx=2.0, dy=4.0, dz=4.0),
                  Boolean3D("op3", kind="intersect", objects=["op1"], tools=["op2"])])
    v["intersect_volume"], v["intersect_area"] = b.volume, b.area

    _, b = _body([Revolve("op1", points=[[0.0, 0.0], [1.0, 0.0], [1.0, 0.2], [0.0, 0.4]])])
    v["revolve_volume"], v["revolve_area"] = b.volume, b.area
    _, b = _body([Extrude("op1", points=[[0.0, 0.0], [0.3, 0.0], [0.0, 0.4]], length=0.5)])
    v["extrude_volume"], v["extrude_area"] = b.volume, b.area

    built, b = _body([Sphere("op1", radius=0.5), Enclosure3D("op2", kind="box", upstream=5.0, downstream=10.0,
                                                             lateral=5.0)])
    v["enclosure_volume"] = b.volume

    union = [Box("op1", dx=0.1, dy=0.2, dz=0.3), Sphere("op2", xc=0.05, yc=0.1, zc=0.3, radius=0.03),
             Boolean3D("op3", kind="union", objects=["op1"], tools=["op2"])]
    _, original = _body(union)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "union.step"
        export_step(GeometryDocument(union, dimension=3), None, path)
        built, back = _body([ImportSolid("op1", file=str(path))])
    v["step_volume"], v["step_area"], v["step_faces"] = back.volume, back.area, len(built.faces)
    v["step_volume_reference"] = original.volume

    v["stable_ids"] = _stable_ids()
    return v


def _stable_ids() -> int:
    """How many of the 3 named faces carry their name on the right face after the upstream edits."""
    names = [NameFaces("op4", faces=["op2:surface"], name="sphere", kind="wall", inflation=True),
             NameFaces("op5", faces=["op1:xmin"], name="inlet", kind="inlet"),
             NameFaces("op6", faces=["op1:zmax"], name="top", kind="symmetry")]
    before = [Box("op1", dx=1.0, dy=1.0, dz=1.0), Sphere("op2", xc=1.0, yc=1.0, zc=1.0, radius=0.4),
              Boolean3D("op3", kind="subtract", objects=["op1"], tools=["op2"])]
    after = [Box("op1", dx=1.5, dy=1.2, dz=1.0), Sphere("op2", xc=1.0, yc=1.0, zc=1.0, radius=0.3),
             Transform3D("op7", kind="move", dx=0.1, dy=0.2, dz=0.3),
             Boolean3D("op3", kind="subtract", objects=["op1"], tools=["op2"])]
    built = replay(GeometryDocument(after + names, dimension=3), triangulate=False)
    replay(GeometryDocument(before + names, dimension=3), triangulate=False)      # (both must build)
    ok = 0
    for name, kind, check in (("sphere", "sphere", lambda f: f.kind == "sphere"),
                              ("inlet", "plane", lambda f: abs(f.centroid[0] - 0.1) < 1e-9),
                              ("top", "plane", lambda f: abs(f.centroid[2] - 1.3) < 1e-9)):
        faces = [built.faces[i] for i, b in built.names.items() if b.name == name]
        ok += len(faces) == 1 and faces[0].kind == kind and check(faces[0])
    return ok


def exact():
    """The exact values (written into reference.toml; kept here so they can be checked)."""
    pi = math.pi
    r, s = 0.4, 0.3
    return {
        "box_volume": 0.2 * 0.3 * 0.5, "box_area": 2 * (0.2 * 0.3 + 0.2 * 0.5 + 0.3 * 0.5),
        "cylinder_volume": pi * 0.1 ** 2 * 0.4, "cylinder_area": 2 * pi * 0.1 * 0.4 + 2 * pi * 0.1 ** 2,
        "sphere_volume": 4 / 3 * pi * 0.25 ** 3, "sphere_area": 4 * pi * 0.25 ** 2,
        "cone_volume": pi * 0.3 / 3 * (0.1 ** 2 + 0.1 * 0.05 + 0.05 ** 2),
        "cone_area": pi * (0.1 + 0.05) * math.hypot(0.3, 0.05) + pi * (0.1 ** 2 + 0.05 ** 2),
        "subtract_volume": 1.0 - 4 / 3 * pi * r ** 3 / 8, "subtract_area": 6.0 - 3 * pi * r ** 2 / 4 + 4 * pi * r ** 2 / 8,
        "union_volume": 1.0 + 2 / 3 * pi * s ** 3, "union_area": 6.0 - pi * s ** 2 + 2 * pi * s ** 2,
        "intersect_volume": 2 / 3 * pi, "intersect_area": 3 * pi,
        "revolve_volume": pi / 3 * (0.2 ** 2 + 0.2 * 0.4 + 0.4 ** 2),
        "revolve_area": pi * (0.2 + 0.4) * math.hypot(1.0, 0.2) + pi * (0.2 ** 2 + 0.4 ** 2),
        "extrude_volume": 0.5 * 0.3 * 0.4 * 0.5, "extrude_area": 0.3 * 0.4 + (0.3 + 0.4 + 0.5) * 0.5,
        "enclosure_volume": 16.0 * 11.0 * 11.0 - 4 / 3 * pi * 0.5 ** 3,
        "step_volume": 0.1 * 0.2 * 0.3 + 2 / 3 * pi * 0.03 ** 3,
        "step_area": 2 * (0.1 * 0.2 + 0.1 * 0.3 + 0.2 * 0.3) + pi * 0.03 ** 2,
        "step_faces": 7, "step_volume_reference": 0.1 * 0.2 * 0.3 + 2 / 3 * pi * 0.03 ** 3, "stable_ids": 3,
    }


if __name__ == "__main__":
    m, e = measure(), exact()
    for key in e:
        print(f"{key:<24} {m[key]:<22.15g} exact {e[key]:<22.15g} error {abs(m[key] - e[key]) / abs(e[key]):.2e}")

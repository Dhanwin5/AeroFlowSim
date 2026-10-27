# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Make the small sample mesh files in tests/data/ (run once; the files are committed).

    python tests/data/make_mesh_samples.py

One mesh, five files: a 40 mm x 20 mm rectangle of 4 x 3 cells, half of them quadrilaterals and half triangles, with the
boundaries left, right, bottom, top. The coordinates are in MILLIMETRES (to test the unit choice) and the names are not
type names (to test the boundary map):
    sample_v2.msh, sample_v4.msh   Gmsh 2.2 and 4.1 ASCII (written by aeroflowsim.mesh_io)
    sample.su2, sample.cgns        SU2 and CGNS (the same)
    sample_fluent.msh              Fluent ASCII 2D, written here (AeroFlowSim does not export Fluent files)
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from aeroflowsim import mesh_io                                 # noqa: E402
from aeroflowsim.simple_meshes import rectangle_mesh           # noqa: E402


def sample_mesh():
    mesh = rectangle_mesh(4, 3, 0.0, 40.0, 0.0, 20.0, mixed=True)      # lengths in mm: the file's unit
    return mesh


def write_fluent(mesh, path):
    """Fluent ASCII: dimension (2), nodes (10), cells (12), faces (13) per zone, zone names (45). Hex numbers."""
    h = lambda n: format(int(n), "x")                                  # noqa: E731
    out = ['(0 "AeroFlowSim sample mesh")', "(2 2)", f"(10 (0 1 {h(mesh.n_nodes)} 0 2))",
           f"(10 (1 1 {h(mesh.n_nodes)} 1 2)(", *[f"{x!r} {y!r}" for x, y, _ in mesh.nodes.tolist()], "))",
           f"(12 (0 1 {h(mesh.n_cells)} 0 0))", f"(12 (7 1 {h(mesh.n_cells)} 1 0))"]
    interior = [f for f in range(mesh.n_faces) if mesh.neighbour[f] >= 0]
    zones = [(2, 2, "interior", interior)] + [(3 + k, 3 if p.type == "wall" else 5, p.name, list(p.faces))
                                              for k, p in enumerate(mesh.patches)]
    first = 1
    for zone, bctype, name, faces in zones:
        out.append(f"(13 ({h(zone)} {h(first)} {h(first + len(faces) - 1)} {h(bctype)} 0)(")
        for f in faces:
            nodes = [int(n) + 1 for n in mesh.face_nodes[f] if n >= 0]
            out.append(f"{len(nodes)} " + " ".join(h(n) for n in nodes) + f" {h(mesh.owner[f] + 1)} "
                       f"{h(mesh.neighbour[f] + 1 if mesh.neighbour[f] >= 0 else 0)}")
        out.append("))")
        first += len(faces)
    out += [f'(45 ({h(zone)} {"interior" if bctype == 2 else "wall" if bctype == 3 else "pressure-outlet"} {name})())'
            for zone, bctype, name, _ in zones]
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    mesh = sample_mesh()
    mesh_io.write_gmsh(mesh, HERE / "sample_v2.msh", "2.2")
    mesh_io.write_gmsh(mesh, HERE / "sample_v4.msh", "4.1")
    mesh_io.write_su2(mesh, HERE / "sample.su2")
    mesh_io.write_cgns(mesh, HERE / "sample.cgns")
    write_fluent(mesh, HERE / "sample_fluent.msh")
    print("Written:", ", ".join(sorted(p.name for p in HERE.glob("sample*"))))

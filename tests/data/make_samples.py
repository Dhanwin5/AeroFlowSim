# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Make the small sample geometry files in tests/data/ (run once; the files are committed).

    python tests/data/make_samples.py

Each file has an exactly known area, used by tests/test_geometry_import.py:
    nozzle_domain.dxf      half nozzle + plume region in mm, lines and a throat arc, with a 1e-6 mm gap
    lens.dxf               closed LWPOLYLINE of two bulged (arc) segments: a biconvex lens
    spline_patch.dxf       a square whose top side is a SPLINE (exact NURBS), in metres
    plate_with_hole.step   2D: 40 mm x 20 mm plate minus a 10 mm diameter hole (OpenCASCADE, mm)
    plate_with_hole.igs    the same plate as IGES
    cone_solid.step        3D: a cone (base radius 10 mm, length 30 mm) about the x axis
"""

import math
from pathlib import Path

import ezdxf
import gmsh

HERE = Path(__file__).resolve().parent


def nozzle_dxf():
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4                      # millimetres
    msp = doc.modelspace()
    # Half domain (y >= 0): inlet x = 0, converging line, throat arc (R = 1, centre (5, 2)), diverging line,
    # nozzle lip up to the plume box, plume box to x = 20, axis back to the inlet.
    msp.add_line((0, 0), (0, 3))                     # inlet
    msp.add_line((0, 3), (4, 1.0 + 1e-6))            # converging wall, ends 1e-6 mm from the arc (a gap)
    msp.add_arc((4.0, 2.0), 1.0, 270.0, 300.0)       # throat arc from (4, 1) turning up
    end = (4.0 + math.cos(math.radians(300)), 2.0 + math.sin(math.radians(300)))
    msp.add_line(end, (8, 1.8))                      # diverging wall
    msp.add_line((8, 1.8), (8, 6))                   # nozzle lip (exit plane, outside the jet)
    msp.add_line((8, 6), (20, 6))                    # plume top
    msp.add_line((20, 6), (20, 0))                   # plume outlet
    msp.add_line((20, 0), (0, 0))                    # axis
    msp.add_text("sample")                           # ignored
    doc.saveas(HERE / "nozzle_domain.dxf")


def lens_dxf():
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 6                      # metres
    msp = doc.modelspace()
    b = math.tan(math.radians(20.0) / 1.0)           # bulge = tan(included angle / 4); angle 80 deg
    msp.add_lwpolyline([(0.0, 0.0, b), (1.0, 0.0, b)], format="xyb", close=True)
    doc.saveas(HERE / "lens.dxf")


def spline_dxf():
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((1, 0), (0, 0))
    msp.add_line((0, 0), (0, 1))
    msp.add_line((1, 1), (1, 0))
    # Top side: a quadratic B-spline from (0, 1) to (1, 1) bulging up to y = 1.25 (control point y = 1.5).
    msp.add_open_spline([(0, 1), (0.5, 1.5), (1, 1)], degree=2)
    doc.saveas(HERE / "spline_patch.dxf")


def occ_files():
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    occ = gmsh.model.occ
    gmsh.model.add("plate")
    plate = occ.addRectangle(0, 0, 0, 40, 20)
    hole = occ.addDisk(20, 10, 0, 5, 5)
    occ.cut([(2, plate)], [(2, hole)])
    occ.synchronize()
    gmsh.write(str(HERE / "plate_with_hole.step"))
    gmsh.write(str(HERE / "plate_with_hole.igs"))
    gmsh.model.remove()
    gmsh.model.add("cone")
    occ.addCone(0, 0, 0, 30, 0, 0, 10, 0)            # apex at x = 30, base radius 10 at x = 0
    occ.synchronize()
    gmsh.write(str(HERE / "cone_solid.step"))
    gmsh.finalize()


if __name__ == "__main__":
    nozzle_dxf()
    lens_dxf()
    spline_dxf()
    occ_files()
    print("Written:", ", ".join(sorted(p.name for p in HERE.iterdir() if p.suffix != ".py")))

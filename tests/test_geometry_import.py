# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Import and healing (aeroflowsim/geometry_model/importers.py, healing.py): every sample file in
tests/data/ gives the exact area, units are read or chosen, gaps are closed and reported, open
and crossing outlines are reported, coordinate outlines are cleaned."""

import math
from pathlib import Path

import numpy as np
import pytest

from aeroflowsim.geometry_model import FLUID, SOLID, GeometryDocument, ReplayContext, replay
from aeroflowsim.geometry_model import healing, importers
from aeroflowsim.geometry_model.operations import Enclosure, ImportFile

DATA = Path(__file__).resolve().parent / "data"
MM2 = 1e-6          # one mm² [m²]


def imported(name, **params):
    """Replay a document holding only the import of tests/data/<name>."""
    fmt = importers.file_format(DATA / name)
    doc = GeometryDocument([ImportFile("op1", format=fmt, file=name, **params)])
    return replay(doc, ReplayContext(folder=DATA))


def segment_area(R, angle):
    """Area between a circle arc of radius R, central angle `angle` [rad], and its chord."""
    return 0.5 * R**2 * (angle - math.sin(angle))


def test_file_formats_are_recognised(tmp_path):
    assert importers.file_format("a.STEP") == "step" and importers.file_format("b.igs") == "iges"
    assert importers.file_format(DATA / "lens.dxf") == "dxf"
    wall = tmp_path / "wall.csv"
    wall.write_text("x_mm,r_mm\n0,2\n1,1\n2,1.5\n")
    assert importers.file_format(wall) == "wall_profile"
    (tmp_path / "foil.dat").write_text("NACA\n1 0\n0 0\n1 0.01\n")
    assert importers.file_format(tmp_path / "foil.dat") == "coordinates"
    with pytest.raises(ValueError, match="unknown file type"):
        importers.file_format("model.blend")


def test_cad_units_are_read_from_the_files():
    assert importers.cad_file_unit(DATA / "plate_with_hole.step") == "mm"
    assert importers.cad_file_unit(DATA / "plate_with_hole.igs") == "mm"
    assert importers.dxf_unit(DATA / "nozzle_domain.dxf") == "mm"
    assert importers.dxf_unit(DATA / "lens.dxf") == "m"


def test_dxf_nozzle_domain_heals_the_gap_and_is_fluid():
    built = imported("nozzle_domain.dxf")
    assert not built.errors()
    (face,) = built.faces.values()
    assert face.role == FLUID                     # it has an edge on the axis
    corners = np.array([(0, 0), (0, 3), (4, 1), (4 + math.cos(math.radians(300)), 2 + math.sin(math.radians(300))),
                        (8, 1.8), (8, 6), (20, 6), (20, 0)])
    x, y = corners.T
    polygon = 0.5 * abs(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    exact = (polygon - segment_area(1.0, math.radians(30))) * MM2
    assert face.area == pytest.approx(exact, rel=1e-6)
    texts = " ".join(text for _, text in built.messages)
    assert "Joined" in texts and "Skipped 1 TEXT" not in texts      # text entities are ignored silently
    assert len(built.edges) == 8 and all(e.startswith("op1:e") for e in built.edges)


def test_dxf_bulged_polyline_and_spline_are_exact():
    lens = imported("lens.dxf", role="solid")
    theta = math.radians(80.0)
    R = 0.5 / math.sin(0.5 * theta)
    (face,) = lens.faces.values()
    assert face.role == SOLID
    assert face.area == pytest.approx(2.0 * segment_area(R, theta), rel=1e-9)
    patch = imported("spline_patch.dxf")
    (face,) = patch.faces.values()
    assert face.area == pytest.approx(1.0 + 1.0 / 6.0, rel=1e-9)
    assert sorted(e.kind for e in patch.edges.values()) == ["line", "line", "line", "spline"]


def test_dxf_unit_choice_scales_the_geometry():
    as_metres = imported("nozzle_domain.dxf", unit="m")
    as_mm = imported("nozzle_domain.dxf")
    assert next(iter(as_metres.faces.values())).area == pytest.approx(
        1e6 * next(iter(as_mm.faces.values())).area, rel=1e-9)


@pytest.mark.parametrize("name", ["plate_with_hole.step", "plate_with_hole.igs"])
def test_step_and_iges_faces_with_a_hole(name):
    built = imported(name, role="fluid")
    (face,) = built.faces.values()
    assert face.area == pytest.approx((40 * 20 - math.pi * 5**2) * MM2, rel=1e-7)   # 10-digit numbers in the file
    assert len(face.loops) == 2
    inch = imported(name, unit="inch", role="fluid")
    factor = 25.4                                  # the numbers taken as inches instead of mm
    assert next(iter(inch.faces.values())).area == pytest.approx(factor**2 * face.area, rel=1e-9)


@pytest.mark.parametrize("plane, area", [("xy", 0.5 * 20 * 30), ("xz", 0.5 * 20 * 30)])
def test_a_3d_solid_is_cut_by_a_plane(plane, area):
    built = imported("cone_solid.step", section=plane)
    (face,) = built.faces.values()
    assert face.area == pytest.approx(area * MM2, rel=1e-9)
    assert any("Cut the solid" in text for _, text in built.messages)
    x0, y0, x1, y1 = built.bbox()
    assert (x0, x1) == pytest.approx((0.0, 0.03), abs=1e-9) and (y0, y1) == pytest.approx((-0.01, 0.01), abs=1e-9)


def test_a_plane_missing_the_solid_is_an_error(tmp_path):
    import gmsh
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.occ.addBox(0, 0, 5, 1, 1, 1)
    gmsh.model.occ.synchronize()
    gmsh.write(str(tmp_path / "box.step"))
    gmsh.finalize()
    doc = GeometryDocument([ImportFile("op1", format="step", file="box.step")])
    assert "does not cut the solid" in replay(doc, ReplayContext(folder=tmp_path)).errors()[0]


def test_a_missing_file_is_reported():
    doc = GeometryDocument([ImportFile("op1", format="dxf", file="geometry/nothing.dxf")])
    assert "missing from the project" in replay(doc, ReplayContext(folder=DATA)).errors()[0]


# ---- coordinates and wall profiles ----------------------------------------------------------------

def naca0012_points(n=81):
    """Closed NACA 0012 outline (Selig order: TE -> upper -> LE -> lower), chord 1, closed trailing edge."""
    beta = np.linspace(0.0, math.pi, n)
    x = 0.5 * (1.0 - np.cos(beta))
    t = 0.6 * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4)
    return np.vstack([np.column_stack([x[::-1], t[::-1]]), np.column_stack([x[1:], -t[1:]])])


def test_coordinates_become_a_solid_body_with_points_stored():
    pts = naca0012_points()
    doc = GeometryDocument([ImportFile("op1", format="coordinates", source="naca0012.dat", points=pts.tolist())])
    doc.add(Enclosure(kind="c_domain", radius=10.0, downstream=15.0))
    built = replay(doc)
    (face,) = built.faces.values()
    body = replay(GeometryDocument(doc.operations[:1])).faces["op1:face"]
    assert body.role == SOLID
    exact = 0.5 * math.pi * 10.0**2 + 2 * 10.0 * (0.5 + 15.0)
    assert face.area == pytest.approx(exact - body.area, rel=1e-9)
    x, y = pts[:, 0], pts[:, 1]
    polygon = 0.5 * abs(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    assert body.area == pytest.approx(polygon, rel=2e-3)        # smooth splines through the same points
    assert not built.errors()


def test_wall_profile_csv_becomes_a_nozzle(tmp_path):
    rows = [(0.0, 2.0), (1.0, 1.5), (2.0, 1.0), (3.0, 1.4), (4.0, 1.8)]
    doc = GeometryDocument([ImportFile("op1", format="wall_profile", points=[list(r) for r in rows], unit="mm")])
    built = replay(doc)
    assert built.axisymmetric and set(built.patches()) == {"wall", "inlet", "outlet", "axis"}
    bad = GeometryDocument([ImportFile("op1", format="wall_profile", points=[list(r) for r in rows], unit="inch")])
    assert "always in millimetres" in replay(bad).errors()[0]


def test_clean_outline_reports_each_fix():
    square = np.array([[0, 0], [0, 0], [0, 1], [1, 1], [1, 0], [0, 0]], dtype=float)    # clockwise, repeated
    pts, closed, messages = healing.clean_outline(square)
    texts = " ".join(t for _, t in messages)
    assert closed and len(pts) == 4 and "Removed 1 repeated" in texts and "counter-clockwise" in texts
    open_line = np.array([[0, 0], [1, 0], [1, 1], [0, 1.0]])
    _, _, messages = healing.clean_outline(open_line)
    assert "closed it with a straight segment" in messages[0][1]
    bow_tie = np.array([[0, 0], [1, 1], [1, 0], [0, 1.0]])
    _, _, messages = healing.clean_outline(bow_tie)
    assert messages[-1][0] == "error" and "crosses itself" in messages[-1][1]


def test_open_and_branching_curves_are_reported(tmp_path):
    import ezdxf
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (1, 0))
    msp.add_line((1, 0), (1, 1))                     # open: no line back to (0, 0)
    doc.saveas(tmp_path / "open.dxf")
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (2, 0), (2, 2), (0, 2)], close=True)
    msp.add_line((1, -1), (1, 3))                    # crosses the square
    doc.saveas(tmp_path / "cross.dxf")
    for name, expected in (("open.dxf", "do not form a closed loop"), ("cross.dxf", "cross or branch")):
        built = replay(GeometryDocument([ImportFile("op1", format="dxf", file=name)]), ReplayContext(folder=tmp_path))
        assert any(expected in text for _, text in built.messages), name
        assert not built.faces


def test_axisymmetric_nozzle_domain_gets_axis_inlet_and_outlet_suggestions():
    from aeroflowsim.geometry_model import boundaries
    doc = GeometryDocument([ImportFile("op1", format="dxf", file="nozzle_domain.dxf")], axisymmetric=True)
    built = replay(doc, ReplayContext(folder=DATA))
    sugg = {built.edges[e].midpoint.round(6).tolist().__repr__(): b.type
            for e, b in boundaries.suggestions(built).items()}
    assert sorted(sugg.values()) == ["axis", "inlet", "outlet"]
    assert sugg[[0.0, 0.0015].__repr__()] == "inlet" and sugg[[0.02, 0.003].__repr__()] == "outlet"


def test_a_dxf_circle_inside_a_rectangle_is_a_hole(tmp_path):
    import ezdxf
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4                      # millimetres (a new drawing says metres)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True)
    msp.add_circle((20, 10), 5)
    doc.saveas(tmp_path / "plate.dxf")
    built = replay(GeometryDocument([ImportFile("op1", format="dxf", file="plate.dxf", role="fluid")]),
                   ReplayContext(folder=tmp_path))
    (face,) = built.faces.values()
    assert not built.errors() and len(face.loops) == 2
    assert face.area == pytest.approx((800 - 25 * math.pi) * MM2, rel=1e-9)

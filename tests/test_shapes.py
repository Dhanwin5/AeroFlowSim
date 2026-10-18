# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the shape library (aeroflowsim/shapes/): every outline is closed, counter-clockwise and
does not cross itself; reference values; NACA geometry; coordinates files; half outlines; and the
automatic inputs (registry, prefixed keys, nested show_if). No Gmsh needed."""

import math

import numpy as np
import pytest

from aeroflowsim.parameters import clean_value, defaults, is_shown
from aeroflowsim.shapes import SHAPE_KEY, find_shapes, make_profile, shape_parameters
from aeroflowsim.shapes.naca4 import naca4_surfaces
from aeroflowsim.shapes.profile import ShapeProfile, count_self_intersections, signed_area

PARAMS = shape_parameters()
DEFAULTS = defaults(PARAMS)
SHAPES = [s.name for s in find_shapes().values()]


def profile(shape, **changes):
    key = next(s.key for s in find_shapes().values() if s.name == shape)
    return make_profile({**DEFAULTS, SHAPE_KEY: shape, **{f"{key}.{k}": v for k, v in changes.items()}})


def test_registry_finds_the_first_six_shapes_in_group_order():
    assert len(SHAPES) == 6
    assert set(SHAPES) == {"Wedge", "Diamond airfoil", "NACA 4-digit airfoil", "Circular cylinder",
                           "Conical nose cone", "Custom coordinates file"}
    assert SHAPES[-1] == "Custom coordinates file"        # group "Custom" comes last


@pytest.mark.parametrize("shape", SHAPES)
def test_every_shape_is_closed_counter_clockwise_and_does_not_cross_itself(shape):
    p = profile(shape)
    assert p.n_points >= 3
    assert not np.allclose(p.points[0], p.points[-1])     # the last point is not repeated (closed implicitly)
    assert p.area > 0.0                                     # counter-clockwise
    assert p.self_intersections() == 0
    assert p.reference_length > 0.0 and p.reference_area > 0.0
    assert p.corners.shape == p.refine.shape == (p.n_points,)
    assert p.is_symmetric() == (shape != "Custom coordinates file")   # the example file is NACA 2412


def test_reference_values():
    w = profile("Wedge", half_angle=10.0, length=2.0)
    assert (w.reference_length, w.reference_area) == (2.0, 2.0)
    assert w.area == pytest.approx(2.0 * 2.0 * math.tan(math.radians(10.0)))    # base 2 L tan, height L
    d = profile("Diamond airfoil", chord=1.0, thickness_ratio=0.1, x_max_thickness=0.3)
    assert d.area == pytest.approx(0.5 * 1.0 * 0.1) and d.reference_area == 1.0
    c = profile("Circular cylinder", diameter=0.5)
    assert c.reference_length == 0.5 and c.area == pytest.approx(math.pi * 0.25**2, rel=1e-4)
    cone = profile("Conical nose cone", half_angle=15.0, length=1.0, base="Cone-cylinder", afterbody_length=0.5)
    R = math.tan(math.radians(15.0))
    assert cone.axisymmetric and cone.reference_length == 1.5
    assert cone.reference_area == pytest.approx(math.pi * R**2)
    assert cone.volume_of_revolution() == pytest.approx(math.pi * R**2 * (1.0 / 3.0 + 0.5))


def test_naca_0012_maximum_thickness_is_12_percent_at_30_percent_chord():
    upper, lower = naca4_surfaces("0012", 2000)
    x = np.linspace(0.0, 1.0, 20001)
    thickness = np.interp(x, upper[:, 0], upper[:, 1]) - np.interp(x, lower[:, 0], lower[:, 1])
    i = int(np.argmax(thickness))
    assert thickness[i] == pytest.approx(0.12, rel=0.005)
    assert x[i] == pytest.approx(0.30, abs=0.005)
    assert np.allclose(upper[[0, -1]], lower[[0, -1]])           # closed trailing edge and LE at (0, 0)


def test_naca_2412_has_2_percent_camber_at_40_percent_chord():
    upper, lower = naca4_surfaces("2412", 2000)
    x = np.linspace(0.0, 1.0, 20001)
    mean = 0.5 * (np.interp(x, upper[:, 0], upper[:, 1]) + np.interp(x, lower[:, 0], lower[:, 1]))
    i = int(np.argmax(mean))
    assert mean[i] == pytest.approx(0.02, rel=0.01)
    assert x[i] == pytest.approx(0.40, abs=0.01)


def test_naca_open_trailing_edge_and_bad_digits():
    p = profile("NACA 4-digit airfoil", closed_te=False)
    assert np.count_nonzero(p.corners) == 2                       # the two corners of the blunt edge
    assert np.ptp(p.points[p.corners, 1]) == pytest.approx(2 * 5 * 0.12 * 0.0021, rel=0.01)
    with pytest.raises(ValueError, match="both be 0"):
        profile("NACA 4-digit airfoil", digits="2012")
    digits = next(p for p in PARAMS if p.name == "naca4.digits")
    with pytest.raises(ValueError, match="not allowed"):
        clean_value(digits, "12a4")


def test_upper_half_ends_on_the_symmetry_line():
    for shape in ("Wedge", "Diamond airfoil", "NACA 4-digit airfoil", "Circular cylinder", "Conical nose cone"):
        chain, corners, refine = profile(shape).upper_half()
        assert chain[0, 1] == 0.0 and chain[-1, 1] == 0.0
        assert chain[0, 0] > chain[-1, 0]                         # from the back to the front, over the top
        assert np.all(chain[1:-1, 1] > 0.0) and corners[0] and corners[-1]
    with pytest.raises(ValueError, match="not symmetric"):
        profile("NACA 4-digit airfoil", digits="2412").upper_half()


def test_clockwise_input_is_turned_round_and_corners_follow():
    p = ShapeProfile([(0, 0), (1, 1), (1, -1)], 1.0, 1.0, corners=[1])     # clockwise
    assert p.area > 0 and p.corners.tolist() == [False, False, True]
    assert np.allclose(p.points[2], [1, 1])


def test_self_intersections_are_counted():
    bow_tie = [(0, 0), (1, 1), (1, 0), (0, 1)]
    assert count_self_intersections(bow_tie) == 1
    assert count_self_intersections([(0, 0), (1, 0), (1, 1), (0, 1)]) == 0
    assert signed_area([(0, 0), (1, 0), (1, 1), (0, 1)]) == 1.0


# ---- coordinates files ---------------------------------------------------------------------------

def coords(tmp_path, text, name="body.dat", **inputs):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return profile("Custom coordinates file", file=str(path), **inputs)


def test_selig_file_is_scaled_and_closed(tmp_path):
    text = "my foil\n1.0 0.0\n0.5 0.05\n0.0 0.0\n0.5 -0.05\n1.0 0.0\n"
    p = coords(tmp_path, text, reference_length=2.0)
    assert p.n_points == 4 and np.ptp(p.points[:, 0]) == pytest.approx(2.0)
    assert p.area == pytest.approx(2.0 * 0.2 / 2) and not p.warnings
    assert p.corners.tolist() == [True, False, True, False]       # TE and LE turn > 30 deg, shoulders ~11 deg


def test_lednicer_file_is_recognised(tmp_path):
    text = "my foil\n3. 3.\n\n0.0 0.0\n0.5 0.05\n1.0 0.0\n\n0.0 0.0\n0.5 -0.05\n1.0 0.0\n"
    p = coords(tmp_path, text)
    assert p.n_points == 4 and "Lednicer" in p.name and p.area == pytest.approx(0.05)


def test_csv_with_header_and_open_outline_is_closed_with_a_note(tmp_path):
    text = "x,y\n1.0,0.01\n0.5,0.05\n0.0,0.0\n0.5,-0.05\n1.0,-0.01\n"
    p = coords(tmp_path, text, name="body.csv")
    assert p.n_points == 5 and any("closed with a straight segment" in w for w in p.warnings)


def test_axisymmetric_half_outline_is_mirrored(tmp_path):
    text = "0,0\n1,0.2\n2,0.2\n2,0\n"
    p = coords(tmp_path, text, name="body.csv", body_type="Axisymmetric", reference_length=2.0)
    assert p.axisymmetric and p.is_symmetric()
    assert p.reference_area == pytest.approx(math.pi * 0.2**2)
    assert any("mirrored" in w for w in p.warnings)


def test_crossing_outline_gives_a_warning_and_bad_files_clear_errors(tmp_path):
    p = coords(tmp_path, "0 0\n1 1\n1 0\n0 1\n")
    assert any("crosses itself" in w for w in p.warnings)
    with pytest.raises(ValueError, match="not found"):
        profile("Custom coordinates file", file=str(tmp_path / "missing.dat"))
    with pytest.raises(ValueError, match="exactly two"):
        coords(tmp_path, "0 0 0\n1 1 1\n1 0 0\n")


# ---- automatic inputs ----------------------------------------------------------------------------

def test_shape_inputs_are_prefixed_and_shown_only_for_their_shape():
    names = [p.name for p in PARAMS]
    assert names[0] == SHAPE_KEY and "wedge.half_angle" in names and "naca4.digits" in names
    by_name = {p.name: p for p in PARAMS}
    values = {**DEFAULTS, SHAPE_KEY: "Wedge", "cone.base": "Cone-cylinder"}
    assert is_shown(by_name["wedge.half_angle"], values, PARAMS)
    assert not is_shown(by_name["cone.half_angle"], values, PARAMS)
    # nested show_if: the afterbody length needs "Cone-cylinder" AND the cone shape to be chosen
    assert not is_shown(by_name["cone.afterbody_length"], values, PARAMS)
    assert is_shown(by_name["cone.afterbody_length"], {**values, SHAPE_KEY: "Conical nose cone"}, PARAMS)
    assert by_name["coordinates_file.file"].file_types == ("dat", "csv", "txt")

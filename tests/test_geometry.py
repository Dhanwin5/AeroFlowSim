# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the shared geometry code: conical nozzle, CSV profiles, PCHIP, summary numbers."""

import math

import numpy as np
import pytest

from aeroflowsim.geometry import (WallProfile, conical_nozzle, profile_summary, read_profile_csv,
                           write_profile_csv)

DEG = math.pi / 180.0


def default_cone():
    return conical_nozzle(2.0e-3, 1.33e-3, 30 * DEG, 0.280e-3, 15 * DEG, 0.911e-3)


def test_conical_nozzle_dimensions():
    p = default_cone()
    L_conv = (1.0e-3 - 0.14e-3) / math.tan(30 * DEG)
    L_div = (0.4555e-3 - 0.14e-3) / math.tan(15 * DEG)
    assert p.length == pytest.approx(1.33e-3 + L_conv + L_div)
    assert p.x_throat == pytest.approx(1.33e-3 + L_conv)
    assert p.r_throat == pytest.approx(0.14e-3)
    s = profile_summary(p)
    assert s["d_throat"][0] == pytest.approx(0.28e-3)
    assert s["area_ratio"][0] == pytest.approx((0.911 / 0.28) ** 2)
    # 0.32 mm past the throat the radius is 0.14 + 0.32 tan(15 deg) mm
    assert p.radius_at(p.x_throat + 0.32e-3) == pytest.approx(0.14e-3 + 0.32e-3 * math.tan(15 * DEG))


def test_conical_nozzle_rejects_impossible_shapes():
    with pytest.raises(ValueError, match="throat diameter must be smaller than the exit"):
        conical_nozzle(2e-3, 1e-3, 30 * DEG, 1e-3, 15 * DEG, 0.9e-3)


def write(tmp_path, text):
    path = tmp_path / "profile.csv"
    path.write_text(text, encoding="utf-8")
    return path


GOOD = "x_mm,r_mm\n0,1\n1,1\n2,0.5\n2.5,0.2\n3,0.4\n"


def test_read_good_csv_converts_mm_to_m(tmp_path):
    p = read_profile_csv(write(tmp_path, GOOD))
    assert p.interpolation == "pchip"
    assert np.allclose(p.x, [0, 1e-3, 2e-3, 2.5e-3, 3e-3])
    assert p.r_throat == pytest.approx(0.2e-3)
    assert p.x_throat == pytest.approx(2.5e-3)


@pytest.mark.parametrize("text, message", [
    ("x,r\n0,1\n1,1\n2,1\n3,1\n4,1\n", "must be exactly 'x_mm,r_mm'"),
    ("x_mm,r_mm\n0,1\n1,1\n1,0.5\n2,0.4\n3,0.6\n", "Line 4.*must increase"),
    ("x_mm,r_mm\n0,1\n1,1\n2,0\n3,0.4\n4,0.6\n", "Line 4.*larger than 0"),
    ("x_mm,r_mm\n0,1\n1,1\n2,0.5\n", "only 3 data points"),
    ("x_mm,r_mm\n0,1\n1,abc\n2,0.5\n3,1\n4,1\n", "Line 3.*not two numbers"),
    ("x_mm,r_mm\n0,1,5\n1,1\n2,0.5\n3,1\n4,1\n", "Line 2 .*exactly two"),
    ("", "empty"),
])
def test_bad_csv_gives_clear_message(tmp_path, text, message):
    with pytest.raises(ValueError, match=message):
        read_profile_csv(write(tmp_path, text))


def test_missing_file_message(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        read_profile_csv(tmp_path / "nope.csv")


def test_pchip_never_overshoots_the_data():
    p = WallProfile(x=[0, 1, 2, 3, 4, 5], r=[1.0, 1.0, 0.3, 0.2, 0.6, 0.6], interpolation="pchip")
    x = np.linspace(0, 5, 2001)
    r = p.radius_at(x)
    assert r.min() >= 0.2 - 1e-15 and r.max() <= 1.0 + 1e-15
    assert np.allclose(p.radius_at(p.x), p.r)       # passes through every point
    assert np.all(r[x >= 4] == pytest.approx(0.6))  # flat stays flat


def test_csv_round_trip_of_cone_keeps_throat_and_exit(tmp_path):
    cone = default_cone()
    x = np.unique(np.r_[np.linspace(0, cone.length, 401), cone.x])
    path = tmp_path / "cone.csv"
    write_profile_csv(path, cone, x)
    p = read_profile_csv(path)
    assert p.r_throat == pytest.approx(cone.r_throat, rel=1e-6)
    assert p.x_throat == pytest.approx(cone.x_throat, rel=1e-6)
    assert p.r[-1] == pytest.approx(cone.r[-1], rel=1e-6)
    xs = np.linspace(0, cone.length, 997)
    # PCHIP rounds each sharp corner a little, within one 10 µm interval of it
    assert np.max(np.abs(p.radius_at(xs) - cone.radius_at(xs))) < 1e-2 * cone.r_throat


# ---- rounded throat ------------------------------------------------------------------------------

def rounded(Rcu=1.5, Rcd=0.4):
    return conical_nozzle(2.0e-3, 1.33e-3, 30 * DEG, 0.280e-3, 15 * DEG, 0.911e-3, Rcu, Rcd)


def test_zero_radius_ratios_give_exactly_the_sharp_nozzle():
    sharp, zero = default_cone(), rounded(0.0, 0.0)
    assert np.array_equal(sharp.x, zero.x) and np.array_equal(sharp.r, zero.r) and zero.marks == []


def test_rounded_throat_keeps_throat_and_exit_diameters_exact():
    p = rounded()
    s = profile_summary(p)
    assert s["d_throat"][0] == 0.280e-3 and s["d_exit"][0] == 0.911e-3 and s["d_inlet"][0] == 2.0e-3
    assert p.x_throat == dict((m[0], m[1]) for m in p.marks)["throat"]


def test_throat_arcs_are_tangent_to_the_cones_and_to_each_other():
    p = rounded()
    r_t = 0.14e-3
    marks = {label: (x, r) for label, x, r in p.marks}
    x_t = marks["throat"][0]
    # cone slopes (straight segments next to the tangent points) equal the cone angles
    up = int(np.argmin(np.abs(p.x - marks["upstream tangent point"][0])))
    down = int(np.argmin(np.abs(p.x - marks["downstream tangent point"][0])))
    assert (p.r[up] - p.r[up - 1]) / (p.x[up] - p.x[up - 1]) == pytest.approx(-math.tan(30 * DEG), abs=1e-9)
    assert (p.r[down + 1] - p.r[down]) / (p.x[down + 1] - p.x[down]) == pytest.approx(math.tan(15 * DEG), abs=1e-9)
    # the circle slope at the tangent points, -tan(phi), is the cone slope (phi = cone angle)
    for (x, r), R, sign, angle in ((marks["upstream tangent point"], 1.5 * r_t, -1, 30 * DEG),
                                   (marks["downstream tangent point"], 0.4 * r_t, 1, 15 * DEG)):
        assert math.hypot(x - x_t, r - (r_t + R)) == pytest.approx(R, rel=1e-12)    # on the circle
        slope = (x - x_t) / ((r_t + R) - r)                                          # circle slope dr/dx
        assert slope == pytest.approx(sign * math.tan(angle), abs=1e-9)
    # at the throat both arcs are horizontal: their centres are straight above the throat
    i = int(np.argmin(p.r))
    left = (p.r[i - 1] - p.r[i]) / (p.x[i] - p.x[i - 1])
    right = (p.r[i + 1] - p.r[i]) / (p.x[i + 1] - p.x[i])
    assert abs(left) < 0.01 and abs(right) < 0.01     # chord slopes of a 0.5 deg step -> 0 at the throat
    assert np.all(p.r[p.x < x_t] > r_t) and np.all(p.r[p.x > x_t] > r_t)


def test_arc_that_does_not_fit_gives_a_clear_error():
    with pytest.raises(ValueError, match="upstream throat arc does not fit.*below"):
        rounded(Rcu=60.0)

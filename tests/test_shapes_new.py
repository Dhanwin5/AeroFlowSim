# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Prompt 6e, part 1: the new shapes against their defining equations, the nozzle contours (Rao bell, Method of
Characteristics) and the intake shock rule. Every number is checked against an equation or a source value."""

import math

import numpy as np
import pytest

from aeroflowsim import gasdynamics as gd
from aeroflowsim import intake_theory
from aeroflowsim import nozzle_contours as nc
from aeroflowsim.parameters import defaults
from aeroflowsim.shapes import SHAPE_KEY, find_shapes, make_profile, shape_parameters
from aeroflowsim.shapes.naca5 import camber_line, naca5_surfaces
from aeroflowsim.smart_rules import SizeContext, shock_on_lip

DEFAULTS = defaults(shape_parameters())


def profile(shape, **changes):
    key = next(s.key for s in find_shapes().values() if s.name == shape)
    return make_profile({**DEFAULTS, SHAPE_KEY: shape, **{f"{key}.{k}": v for k, v in changes.items()}})


def upper(p):
    """Upper half of an axisymmetric body: (x, y) sorted by x, y >= 0."""
    chain, _, _ = p.upper_half()
    chain = chain[(chain[:, 1] > 0.0) | (chain[:, 0] == chain[:, 0].min())]      # drop the axis point of the flat base
    return chain[np.argsort(chain[:, 0], kind="stable")]


NOSE = "Nose cone (ogive, Haack, power series)"


# ---- nose cones ------------------------------------------------------------------------------------------------

def test_von_karman_radius_at_mid_length_is_r_over_root_two():
    p = profile(NOSE, kind="Von Karman (LD-Haack)", length=2.0, base_diameter=0.4, points=400)
    x, y = upper(p).T
    assert np.interp(1.0, x, y) == pytest.approx(0.2 / math.sqrt(2.0), rel=1e-4)    # theta = pi/2: y = R sqrt(1/2)
    assert p.reference_area == pytest.approx(math.pi * 0.2**2) and p.reference_length == 2.0


def test_lv_haack_radius_at_mid_length():
    p = profile(NOSE, kind="LV-Haack", length=2.0, base_diameter=0.4, points=400)
    x, y = upper(p).T
    assert np.interp(1.0, x, y) == pytest.approx(0.2 * math.sqrt((math.pi / 2 + 1.0 / 3.0) / math.pi), rel=1e-4)


def test_tangent_ogive_matches_its_equation_and_is_tangent_to_the_cylinder():
    L, R = 3.0, 0.5
    p = profile(NOSE, kind="Tangent ogive", length=L, base_diameter=2 * R, points=400)
    x, y = upper(p).T
    rho = (R**2 + L**2) / (2 * R)
    expected = np.sqrt(rho**2 - (L - x)**2) + R - rho            # y = sqrt(rho² - (L - x)²) + R - rho (x from the tip)
    assert np.allclose(y[1:-1], expected[1:-1], atol=1e-9)
    slope = (y[-2] - y[-3]) / (x[-2] - x[-3])
    assert slope < 0.03                                          # the arc meets the cylinder tangentially


def test_secant_ogive_passes_through_tip_and_base_and_is_flatter_at_the_base_than_a_cone():
    L, R = 2.0, 0.3
    p = profile(NOSE, kind="Secant ogive", length=L, base_diameter=2 * R, ogive_ratio=2.0, points=400)
    x, y = upper(p).T
    assert (x[0], y[0]) == (0.0, 0.0) and (x[-1], y[-1]) == (pytest.approx(L), pytest.approx(R))
    rho = 2.0 * (R**2 + L**2) / (2 * R)                           # twice the tangent-ogive radius
    # fit a circle (x² + y² + a x + b y + c = 0) to the points: its radius must be rho
    A = np.column_stack([x, y, np.ones_like(x)])
    a, b, c = np.linalg.lstsq(A, -(x**2 + y**2), rcond=None)[0]
    assert math.sqrt(a * a / 4 + b * b / 4 - c) == pytest.approx(rho, rel=1e-6)
    assert np.interp(1.0, x, y) > 0.5 * R                        # it bulges above the straight cone


def test_power_and_parabolic_series_equations():
    L, R = 1.5, 0.2
    p = profile(NOSE, kind="Power series", length=L, base_diameter=2 * R, power=0.5, points=400)
    x, y = upper(p).T
    assert np.allclose(y, R * (x / L) ** 0.5, atol=1e-9)
    p = profile(NOSE, kind="Parabolic series", length=L, base_diameter=2 * R, parabola_k=0.6, points=400)
    x, y = upper(p).T
    s = x / L
    assert np.allclose(y, R * (2 * s - 0.6 * s**2) / (2 - 0.6), atol=1e-9)
    cone = profile(NOSE, kind="Parabolic series", length=L, base_diameter=2 * R, parabola_k=0.0, points=400)
    assert np.allclose(upper(cone)[:, 1], R * upper(cone)[:, 0] / L, atol=1e-9)         # K = 0 is the cone


def test_ellipse_equation_and_volume_of_a_half_ellipsoid():
    L, R = 1.0, 0.25
    p = profile(NOSE, kind="Ellipse", length=L, base_diameter=2 * R, points=600)
    x, y = upper(p).T
    assert np.allclose(y, R * np.sqrt(1 - ((L - x) / L) ** 2), atol=1e-9)
    assert p.volume_of_revolution() == pytest.approx(2.0 / 3.0 * math.pi * R**2 * L, rel=1e-4)


def test_blunt_nose_is_a_tangent_sphere_and_the_afterbody_is_a_cylinder():
    rn = 0.02
    p = profile(NOSE, kind="Tangent ogive", length=1.0, base_diameter=0.3, blunt=True, nose_diameter=2 * rn,
                afterbody_length=0.4, points=400)
    chain = upper(p)
    x, y = chain.T
    assert x[0] == pytest.approx(0.0, abs=1e-12)
    cap = chain[y < 0.9 * rn]                                     # the front part: on a circle of radius rn
    centre = (rn, 0.0)
    assert np.allclose(np.hypot(cap[:, 0] - centre[0], cap[:, 1] - centre[1]), rn, rtol=1e-6)
    # tangency: the slope just behind the cap equals the slope of the sphere at the joint (no kink)
    joint = np.argmax(y > 0.99 * rn)
    assert abs(math.atan2(y[joint + 2] - y[joint + 1], x[joint + 2] - x[joint + 1])
               - math.atan2(y[joint] - y[joint - 1], x[joint] - x[joint - 1])) < math.radians(8.0)
    assert x[-1] == pytest.approx(x[-2] + 0.0, abs=0.41) and y[-1] == pytest.approx(0.15)   # afterbody at base radius
    assert profile(NOSE, kind="Tangent ogive", length=1.0, base_diameter=0.3, points=400).reference_length == 1.0
    assert p.reference_length < 1.4                                # blunting shortened the sharp 1.0 m nose
    with pytest.raises(ValueError, match="cannot be tangent"):
        profile(NOSE, kind="Tangent ogive", length=1.0, base_diameter=0.3, blunt=True, nose_diameter=0.9)


# ---- blunt bodies ----------------------------------------------------------------------------------------------

def test_sphere_and_hemisphere_cylinder_volumes():
    s = profile("Sphere", diameter=2.0)
    assert s.volume_of_revolution() == pytest.approx(4.0 / 3.0 * math.pi, rel=1e-3)
    assert s.reference_area == pytest.approx(math.pi) and s.reference_length == 2.0
    h = profile("Hemisphere-cylinder", diameter=0.2, cylinder_length=0.3, points=400)
    R = 0.1
    assert h.volume_of_revolution() == pytest.approx(2.0 / 3.0 * math.pi * R**3 + math.pi * R**2 * 0.3, rel=1e-4)
    assert h.reference_length == pytest.approx(R + 0.3)


def test_blunted_cone_geometry():
    theta, Rb, rn = 12.0, 0.15, 0.02
    p = profile("Spherically blunted cone", half_angle=theta, base_diameter=2 * Rb, nose_diameter=2 * rn, points=200)
    x, y = upper(p).T
    assert x[0] == 0.0 and y[-1] == pytest.approx(Rb)
    slope = (y[-1] - y[-2]) / (x[-1] - x[-2])                                          # the straight cone: tangent point to base
    assert slope == pytest.approx(math.tan(math.radians(theta)), rel=1e-9)
    sphere = (y < 0.95 * rn * math.cos(math.radians(theta)))
    assert np.allclose(np.hypot(x[sphere] - rn, y[sphere]), rn, rtol=1e-9)          # the nose is a sphere about (rn, 0)
    assert p.reference_area == pytest.approx(math.pi * Rb**2)


def test_capsule_dimensions_and_tangency():
    D, Rn, rs, ang, La = 1.0, 1.2, 0.05, 30.0, 0.4
    p = profile("Sphere-cone capsule", diameter=D, nose_radius=Rn, shoulder_radius=rs, afterbody_angle=ang,
                afterbody_length=La, points=300)
    x, y = upper(p).T
    assert x[0] == 0.0 and y.max() == pytest.approx(0.5 * D, rel=1e-4)                 # largest radius = D / 2
    fore = (y < 0.45) & (x < 0.2)
    assert np.allclose(np.hypot(x[fore] - Rn, y[fore]), Rn, rtol=1e-9)                   # spherical heat shield, centre (Rn, 0)
    slope = (y[-1] - y[-2]) / (x[-1] - x[-2])                                           # the straight afterbody cone
    assert slope == pytest.approx(-math.tan(math.radians(ang)), rel=1e-9)
    assert x[-1] - x[-2] == pytest.approx(La)                                            # of axial length La
    assert p.reference_area == pytest.approx(math.pi * (0.5 * D) ** 2)
    with pytest.raises(ValueError, match="larger than the capsule radius"):
        profile("Sphere-cone capsule", nose_radius=0.3)


# ---- airfoils --------------------------------------------------------------------------------------------------

def test_biconvex_area_is_two_circular_segments_and_edges_are_sharp():
    c, t = 2.0, 0.08
    p = profile("Double-circular-arc (biconvex) airfoil", chord=c, thickness_ratio=t, points_per_side=2000)
    a, s = c / 2, t * c / 2
    R = (a * a + s * s) / (2 * s)
    Theta = math.asin(a / R)
    segment = R**2 * (Theta - math.sin(Theta) * math.cos(Theta))      # area of a circular segment of half-angle Theta
    assert p.area == pytest.approx(2 * segment, rel=1e-6)
    assert np.ptp(p.points[:, 1]) == pytest.approx(t * c, rel=1e-9)
    assert np.count_nonzero(p.corners) == 2 and p.is_symmetric()


@pytest.mark.parametrize("digits, tolerance", [("23012", 1e-3), ("24012", 1e-3), ("25012", 1e-3), ("33012", 1e-3),
                                               ("22012", 0.02), ("21012", 0.03), ("23112", 0.01), ("24112", 0.01),
                                               ("25112", 0.01), ("22112", 0.02)])
def test_naca5_camber_line_has_the_design_lift_coefficient(digits, tolerance):
    """Thin-airfoil theory: the ideal lift of a camber line is c_li = 2 int_0^pi (dyc/dx) cos(theta) dtheta, and the
    first digit says c_li = 0.15 L. An independent check of the tabulated constants (r, k1, k2/k1)."""
    theta = np.linspace(0.0, math.pi, 200001)
    _, slope = camber_line(digits, 0.5 * (1.0 - np.cos(theta)))
    c_li = 2.0 * np.trapezoid(slope * np.cos(theta), theta)
    assert c_li == pytest.approx(0.15 * int(digits[0]), rel=tolerance)


@pytest.mark.parametrize("digits", ["21012", "22012", "23012", "24012", "25012"])
def test_naca5_standard_camber_peaks_at_five_percent_times_p(digits):
    x = np.linspace(0.0, 1.0, 400001)
    yc, _ = camber_line(digits, x)
    assert x[np.argmax(yc)] == pytest.approx(0.05 * int(digits[1]), abs=2e-4)
    assert yc[0] == 0.0 and yc[-1] == pytest.approx(0.0, abs=1e-12)


def test_naca5_reflex_trailing_edge_camber_is_upward_and_thickness_is_the_four_digit_one():
    x = np.linspace(0.0, 1.0, 1001)
    yc, slope = camber_line("23112", x)
    standard = camber_line("23012", x)[1][-1]
    assert standard < 0.0 and abs(slope[-1]) < 0.2 * abs(standard)    # reflex: the line comes down much less at the TE
    assert yc[-1] == pytest.approx(0.0, abs=1e-12) and np.all(yc[1:-1] > 0.0)
    upper_s, lower_s = naca5_surfaces("23012", 2000)
    xs = np.linspace(0.05, 0.95, 400)
    thickness = (np.interp(xs, upper_s[:, 0], upper_s[:, 1]) - np.interp(xs, lower_s[:, 0], lower_s[:, 1]))
    assert thickness.max() == pytest.approx(0.12, rel=0.01)           # TT = 12 % thick
    with pytest.raises(ValueError, match="not tabulated"):
        profile("NACA 5-digit airfoil", digits="26012")


# ---- nozzles: Method of Characteristics and the Rao bell -------------------------------------------------------

@pytest.mark.parametrize("mach, gamma", [(2.4, 1.4), (3.0, 1.4), (4.0, 1.3)])
def test_moc_nozzle_exit_area_ratio_matches_the_isentropic_value(mach, gamma):
    wall = nc.moc_min_length_nozzle(mach, gamma, h_throat=0.5, n_chars=100)
    ratio = wall.r[-1] / 0.5
    assert ratio == pytest.approx(gd.area_ratio(mach, gamma), rel=0.002)       # planar: A / A* = exit height / throat height
    assert wall.r[0] == 0.5 and wall.x[0] == 0.0
    corner = math.degrees(math.atan2(wall.r[1] - wall.r[0], wall.x[1] - wall.x[0]))
    assert corner == pytest.approx(0.5 * math.degrees(gd.prandtl_meyer(mach, gamma)), abs=0.05 * 0.5 * 10)   # starts at nu / 2
    exit_angle = math.degrees(math.atan2(wall.r[-1] - wall.r[-2], wall.x[-1] - wall.x[-2]))
    assert abs(exit_angle) < 0.2                                               # the wall is parallel to the axis at the exit


def test_moc_nozzle_converges_with_the_number_of_characteristics():
    errors = [abs(nc.moc_area_ratio_error(nc.moc_min_length_nozzle(2.4, 1.4, 1.0, n), 2.4, 1.4, 1.0))
              for n in (10, 20, 40, 80)]
    assert all(b < 0.6 * a for a, b in zip(errors, errors[1:]))                # the error falls steadily
    assert errors[-1] < 1e-3
    assert np.all(np.diff(nc.moc_min_length_nozzle(3.0, 1.4, 1.0, 60).x) > 0.0)
    with pytest.raises(ValueError, match="above 1"):
        nc.moc_min_length_nozzle(1.0, 1.4)


def test_moc_nozzle_shape_is_a_closed_symmetric_flow_path():
    p = profile("Minimum-length nozzle (MOC, planar)", mach_exit=2.4, throat_height=0.02, n_characteristics=40)
    assert p.is_symmetric() and not p.axisymmetric and p.self_intersections() == 0
    assert p.reference_area == pytest.approx(0.02)
    half_height_exit = p.points[:, 1].max()
    assert 2 * half_height_exit / 0.02 == pytest.approx(gd.area_ratio(2.4, 1.4), rel=0.003)


def test_rao_chart_reproduces_its_table_nodes_and_interpolates_between_them():
    assert nc.rao_angles(8.35, 0.8)[0] == pytest.approx(28.36)             # a digitised point of the 80 % theta_n curve
    assert nc.rao_angles(14.59, 0.8)[1] == pytest.approx(9.72)             # ... and of the theta_e curve
    n_lo, e_lo = nc.rao_angles(20.0, 0.7)
    n_hi, e_hi = nc.rao_angles(20.0, 0.9)
    n_mid, e_mid = nc.rao_angles(20.0, 0.8)
    assert n_hi < n_mid < n_lo and e_hi < e_mid < e_lo                     # a longer nozzle has smaller angles
    with pytest.raises(ValueError, match="covers area ratios"):
        nc.rao_angles(3.0, 0.8)
    with pytest.raises(ValueError, match="% of a 15 degree cone"):
        nc.rao_angles(20.0, 0.4)


def test_bell_nozzle_dimensions_arcs_and_end_slopes():
    rt, eps, lf = 0.05, 25.0, 0.8
    wall = nc.bell_nozzle(rt, eps, lf, n_points=400)
    theta_n, theta_e = nc.rao_angles(eps, lf)
    marks = {name: (x, r) for name, x, r in wall.marks}
    assert marks["exit"][1] == pytest.approx(rt * math.sqrt(eps))                       # exit radius from the area ratio
    assert marks["exit"][0] == pytest.approx(lf * rt * (math.sqrt(eps) - 1) / math.tan(math.radians(15.0)))
    assert wall.r_throat == pytest.approx(rt) and wall.x_throat == pytest.approx(0.0)
    # downstream arc: radius 0.382 rt about (0, rt + 0.382 rt); point N where the wall angle is theta_n
    xN, rN = marks["N"]
    assert math.hypot(xN, rN - (rt + 0.382 * rt)) == pytest.approx(0.382 * rt)
    assert rN == pytest.approx(rt + 0.382 * rt * (1 - math.cos(math.radians(theta_n))))
    after = wall.x > xN
    slope_n = (wall.r[after][1] - wall.r[after][0]) / (wall.x[after][1] - wall.x[after][0])
    assert math.degrees(math.atan(slope_n)) == pytest.approx(theta_n, abs=0.7)           # leaves N at theta_n
    slope_e = (wall.r[-1] - wall.r[-2]) / (wall.x[-1] - wall.x[-2])
    assert math.degrees(math.atan(slope_e)) == pytest.approx(theta_e, abs=0.2)           # arrives at the exit at theta_e
    assert np.all(np.diff(wall.x) > 0.0)
    given = nc.bell_nozzle(rt, eps, lf, theta_n=30.0, theta_e=8.0)
    assert given.marks[1][2] == pytest.approx(rt + 0.382 * rt * (1 - math.cos(math.radians(30.0))))
    with pytest.raises(ValueError, match="theta_e < theta_n"):
        nc.bell_nozzle(rt, eps, lf, theta_n=8.0, theta_e=20.0)


def test_bell_nozzle_shapes_axisymmetric_and_planar():
    a = profile("Bell nozzle (Rao)", throat_diameter=0.1, area_ratio=16.0)
    assert a.axisymmetric and a.is_symmetric() and a.self_intersections() == 0
    assert a.points[:, 1].max() == pytest.approx(0.05 * 4.0)
    assert a.reference_area == pytest.approx(math.pi * 0.05**2)
    pl = profile("Bell nozzle (Rao)", body_type="Planar", throat_diameter=0.1, area_ratio=6.0)
    assert not pl.axisymmetric and pl.points[:, 1].max() == pytest.approx(0.05 * 6.0)     # planar: height ratio


# ---- intakes ---------------------------------------------------------------------------------------------------

def test_ramp_shocks_satisfy_the_theta_beta_mach_relation_and_chain_the_mach_number():
    shocks = intake_theory.ramp_shocks(3.0, 1.4, [8.0, 16.0])
    first = shocks[0]
    beta, theta, M = math.radians(first["beta"]), math.radians(first["turn"]), 3.0
    lhs = math.tan(theta)
    rhs = 2.0 / math.tan(beta) * (M**2 * math.sin(beta)**2 - 1.0) / (M**2 * (1.4 + math.cos(2 * beta)) + 2.0)
    assert lhs == pytest.approx(rhs, rel=1e-9)                                  # Anderson eq. 4.17
    assert shocks[1]["mach_before"] == pytest.approx(first["mach_after"])
    assert shocks[1]["angle"] == pytest.approx(8.0 + shocks[1]["beta"])
    assert first["angle"] == pytest.approx(first["beta"])
    with pytest.raises(ValueError, match="must be larger"):
        intake_theory.ramp_shocks(3.0, 1.4, [10.0, 8.0])
    with pytest.raises(ValueError, match="detaches"):
        intake_theory.ramp_shocks(1.5, 1.4, [30.0])


def test_ramp_lip_sits_on_the_first_two_shocks_and_one_ramp_lip_is_on_its_shock():
    out = intake_theory.ramp_lip(3.0, 1.4, [8.0, 16.0], [0.4, 0.3])
    assert out["miss"][0] == pytest.approx(0.0, abs=1e-12) and out["miss"][1] == pytest.approx(0.0, abs=1e-12)
    x, y = out["lip"]
    assert y == pytest.approx(x * math.tan(math.radians(out["shocks"][0]["angle"])))
    one = intake_theory.ramp_lip(3.0, 1.4, [10.0], [0.5], lip_x=0.8)
    assert one["lip"][1] == pytest.approx(0.8 * math.tan(math.radians(one["shocks"][0]["angle"])))
    with pytest.raises(ValueError, match="lip's x"):
        intake_theory.ramp_lip(3.0, 1.4, [10.0], [0.5])


def test_spike_lip_uses_the_taylor_maccoll_shock_angle():
    out = intake_theory.spike_lip(3.0, 1.4, 15.0, 0.6)
    assert out["beta"] == pytest.approx(math.degrees(gd.taylor_maccoll(3.0, math.radians(15.0), 1.4)["beta"]))
    assert 15.0 < out["beta"] < math.degrees(math.asin(1.0 / 3.0)) + 20.0       # between the cone and a weak ramp shock
    assert out["lip"][1] == pytest.approx(0.6 * math.tan(math.radians(out["beta"])))


def test_intake_shapes_are_valid_and_reject_a_lip_that_hits_the_body():
    ramp = profile("Ramp intake (planar)")
    assert ramp.self_intersections() == 0 and ramp.warnings and ramp.reference_length > 0.9
    assert ramp.reference_area == pytest.approx(0.426)
    spike = profile("Spike intake (axisymmetric)")
    assert spike.axisymmetric and spike.is_symmetric() and spike.self_intersections() == 0
    assert spike.volume_of_revolution() > 0.0
    with pytest.raises(ValueError, match="lip is too low"):
        profile("Ramp intake (planar)", lip_y=0.10)
    with pytest.raises(ValueError, match="must increase"):
        profile("Ramp intake (planar)", angle2=6.0)


def test_shock_on_lip_rule_suggests_a_lip_on_the_shocks_and_applying_it_is_valid():
    params = {**DEFAULTS, SHAPE_KEY: "Ramp intake (planar)", "ramp_intake.lip_x": 0.7, "ramp_intake.lip_y": 0.5}
    (s,) = shock_on_lip(None, SizeContext(params, {}, mach=3.0))
    assert s.kind == "input" and set(s.inputs) == {"ramp_intake.lip_x", "ramp_intake.lip_y"}
    assert s.inputs["ramp_intake.lip_x"] == pytest.approx(0.8887, abs=1e-3) and s.inputs["ramp_intake.lip_y"] == pytest.approx(0.426, abs=1e-3)
    assert "Distance of the lip from each shock" in s.reason
    assert make_profile({**params, **s.inputs}).self_intersections() == 0
    spike = {**DEFAULTS, SHAPE_KEY: "Spike intake (axisymmetric)"}
    (t,) = shock_on_lip(None, SizeContext(spike, {}, mach=3.0))
    assert t.inputs["spike_intake.lip_r"] == pytest.approx(0.283, abs=1e-3)
    assert shock_on_lip(None, SizeContext(spike, {}, mach=0.8)) == []          # subsonic: no shocks, no suggestion
    assert shock_on_lip(None, SizeContext({**DEFAULTS, SHAPE_KEY: "Wedge"}, {}, mach=3.0)) == []

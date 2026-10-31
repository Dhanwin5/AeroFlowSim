# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shapes, grids and mesh import stage geometry validation: new shapes, nozzle contours and structured grids against exact values. No solver is run.

Shapes (exact formulas in the theory manual, section 14):
    von Karman nose            volume of revolution = pi R² L / 2           (Haack C = 0: the integral of y² is exact)
    sphere / hemisphere-cyl.   4/3 pi R³  and  2/3 pi R³ + pi R² L_c
    double-circular-arc airfoil  area = 2 R² (Theta - sin Theta cos Theta)    (two circular segments)
Method-of-Characteristics nozzle (Mach 2.4, gamma 1.4): exit height / throat height against the isentropic A / A*, with 20, 40
and 80 characteristics (the error falls as the fan is resolved).
Rao bell (area ratio 25, 80 %): exit radius sqrt(eps) R_t and length 0.8 (sqrt(eps) - 1) R_t / tan 15 deg (by construction).
Structured grids on three sizes (Coarse, Medium, Fine presets), against the exact areas:
    O-grid of a cylinder      domain area pi (R² - r²), wall length pi D, first-layer height
    C-grid of a NACA 0012     domain area (pi / 2 + 2) R² - body area  (a half circle ahead, a rectangle behind)
    triangle mesh             the unstructured mesh of the same cylinder domain, for the comparison
"""

import math

import numpy as np

from aeroflowsim import gasdynamics as gd
from aeroflowsim import nozzle_contours as nc
from aeroflowsim.discovery import load_case
from aeroflowsim.mesh import DEPTH_2D
from aeroflowsim.parameters import defaults
from aeroflowsim.shapes import SHAPE_KEY, find_shapes, make_profile, shape_parameters
from aeroflowsim.structured_mesh import PRESETS, StructuredSettings, structured_mesh

SHAPE_DEFAULTS = defaults(shape_parameters())
FAR = 20.0                      # far-field radius [reference lengths]
FIRST = 1e-3                    # first layer height [reference lengths]


def shape(name, **changes):
    key = next(s.key for s in find_shapes().values() if s.name == name)
    return make_profile({**SHAPE_DEFAULTS, SHAPE_KEY: name, **{f"{key}.{k}": v for k, v in changes.items()}})


def measure():
    values = {}
    R, L = 0.15, 1.2
    nose = shape("Nose cone (ogive, Haack, power series)", kind="Von Karman (LD-Haack)", length=L, base_diameter=2 * R, points=800)
    values["von_karman_volume"] = nose.volume_of_revolution() / (math.pi * R**2 * L / 2.0)
    values["sphere_volume"] = shape("Sphere", diameter=2.0).volume_of_revolution() / (4.0 / 3.0 * math.pi)
    hc = shape("Hemisphere-cylinder", diameter=0.2, cylinder_length=0.3, points=800)
    values["hemisphere_cylinder_volume"] = hc.volume_of_revolution() / (2.0 / 3.0 * math.pi * 0.1**3 + math.pi * 0.1**2 * 0.3)
    c, t = 2.0, 0.08
    a, s = c / 2, t * c / 2
    radius = (a * a + s * s) / (2 * s)
    theta = math.asin(a / radius)
    biconvex = shape("Double-circular-arc (biconvex) airfoil", chord=c, thickness_ratio=t, points_per_side=1000)
    values["biconvex_area"] = biconvex.area / (2 * radius**2 * (theta - math.sin(theta) * math.cos(theta)))
    for n in (20, 40, 80):
        wall = nc.moc_min_length_nozzle(2.4, 1.4, 1.0, n)
        values[f"moc_area_ratio_{n}"] = wall.r[-1] / gd.area_ratio(2.4, 1.4)
    bell = nc.bell_nozzle(0.05, 25.0, 0.8)
    exit_x, exit_r = bell.marks[-1][1:]
    values["bell_exit_radius"] = exit_r / (0.05 * 5.0)
    values["bell_length"] = exit_x / (0.8 * 0.05 * 4.0 / math.tan(math.radians(15.0)))

    cylinder, naca = shape("Circular cylinder", diameter=1.0), shape("NACA 4-digit airfoil")
    for level, (n_body, n_normal, n_wake) in PRESETS.items():
        s = StructuredSettings(n_body, n_normal, n_wake, FIRST, 1.6, FAR)
        o = structured_mesh(cylinder, s)
        key = level.lower()
        values[f"ogrid_area_{key}"] = o.cell_volumes.sum() / DEPTH_2D / (math.pi * (FAR**2 - 0.25))
        values[f"ogrid_wall_{key}"] = o.face_areas[o.patch("wall").faces].sum() / DEPTH_2D / math.pi
        faces = o.patch("wall").faces
        values[f"ogrid_first_layer_{key}"] = float(np.median(o.cell_volumes[o.owner[faces]] / o.face_areas[faces])) / FIRST
        c_mesh = structured_mesh(naca, s)
        exact = (math.pi / 2 + 2.0) * FAR**2 - naca.area
        values[f"cgrid_area_{key}"] = c_mesh.cell_volumes.sum() / DEPTH_2D / exact
        values[f"cgrid_cells_{key}"] = c_mesh.n_cells / (n_body + 2 * n_wake) / n_normal
    external = load_case("cases/external_2d")
    base = defaults(external.parameters())
    for level, k in {"default": 1.0, "fine": 2.0}.items():
        p = {**base, "shape": "Circular cylinder", "surface_size": base["surface_size"] / k,
             "farfield_size": base["farfield_size"] / k}
        mesh = external.build_mesh(p)
        values[f"triangle_area_{level}"] = mesh.cell_volumes.sum() / DEPTH_2D / (math.pi * (FAR**2 - 0.25))
    return values

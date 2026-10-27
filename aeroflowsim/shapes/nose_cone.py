# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Nose cones of revolution: ogives, Haack series (von Karman, LV-Haack), power series, parabolic series, ellipse.

x runs from the tip (x = 0) to the base (x = L); R is the base radius; y is the radius of the body at x.
Equations (Crowell, "The Descriptive Geometry of Nose Cones", 1996; Wikipedia "Nose cone design" lists them all):

    Haack series      theta = arccos(1 - 2 x / L)
                      y = R sqrt((theta - sin(2 theta) / 2 + C sin³(theta)) / pi)
                      C = 0: LD-Haack = von Karman (least wave drag for a given length and diameter)
                      C = 1/3: LV-Haack (least wave drag for a given length and volume)
    Ogive             the profile is a circular arc of radius rho through the tip (0, 0) and the base edge (L, R)
                      (the arc bulges outwards). rho_t = (R² + L²) / (2 R) is the TANGENT ogive (the arc is
                      tangent to the body cylinder at the base). A SECANT ogive has a larger radius,
                      rho = ratio x rho_t with ratio > 1 (the arc then cuts the cylinder at an angle).
    Power series      y = R (x / L)^n, 0 < n <= 1 (n = 1 is the cone, 1/2 the parabola, 3/4 the 3/4 power)
    Parabolic series  y = R (2 x / L - K (x / L)²) / (2 - K), 0 <= K <= 1 (K = 0 cone, K = 1 the parabola with
                      its axis at the base)
    Ellipse           y = R sqrt(1 - ((L - x) / L)²)  (rounded tip, tangent to the cylinder at the base)

A spherical blunt nose of radius r_n is the sphere with its centre on the axis that is tangent to the profile: the
profile is cut where the circle touches it and the sphere fills the front. The blunted body is shorter than the sharp
profile: the length given is that of the SHARP profile. An optional cylindrical afterbody follows the base.
Reference length = total body length; reference area = base area pi R².
"""

import math

import numpy as np
from scipy.optimize import brentq

from aeroflowsim.shapes.revolution import silhouette

HAACK_C = {"Von Karman (LD-Haack)": 0.0, "LV-Haack": 1.0 / 3.0}


def sharp_radius(kind, x, L, R, inputs):
    """Radius y [m] of the sharp nose profile at x [m] (arrays allowed), 0 <= x <= L."""
    s = np.clip(np.asarray(x, dtype=float) / L, 0.0, 1.0)
    if kind in HAACK_C:
        theta = np.arccos(1.0 - 2.0 * s)
        return R * np.sqrt(np.maximum(theta - 0.5 * np.sin(2.0 * theta) + HAACK_C[kind] * np.sin(theta)**3, 0.0) / math.pi)
    if kind in ("Tangent ogive", "Secant ogive"):
        ratio = 1.0 if kind == "Tangent ogive" else inputs["ogive_ratio"]
        rho_t = (R**2 + L**2) / (2.0 * R)
        rho = ratio * rho_t
        chord = math.hypot(L, R)
        d = math.sqrt(max(rho**2 - 0.25 * chord**2, 0.0))             # centre's distance from the chord's midpoint
        cx, cy = 0.5 * L + d * R / chord, 0.5 * R - d * L / chord      # the centre lies below the chord
        return cy + np.sqrt(np.maximum(rho**2 - (s * L - cx)**2, 0.0))
    if kind == "Power series":
        return R * s ** inputs["power"]
    if kind == "Parabolic series":
        K = inputs["parabola_k"]
        return R * (2.0 * s - K * s**2) / (2.0 - K)
    if kind == "Ellipse":
        return R * np.sqrt(np.maximum(1.0 - (1.0 - s)**2, 0.0))
    raise ValueError(f"Unknown nose profile '{kind}'.")


def nose_chain(kind, L, R, inputs, n, nose_radius=0.0):
    """Upper chain (x, y) of the nose from the tip on the axis to the base (x = L after blunting: shifted)."""
    # cosine spacing: dense at the tip, where the curvature is highest
    x = L * 0.5 * (1.0 - np.cos(np.linspace(0.0, math.pi, n)))
    y = sharp_radius(kind, x, L, R, inputs)
    y[0] = 0.0
    chain = np.column_stack([x, y])
    if nose_radius <= 0.0:
        return chain
    # blunting: find x_t where the circle centred on the axis is tangent to the profile at (x_t, y(x_t)) with radius r_n.
    # Tangent circle: centre (x_t + y y', 0), radius y sqrt(1 + y'²).
    h = 1e-7 * L

    def radius_at(xt):
        slope = (sharp_radius(kind, xt + h, L, R, inputs) - sharp_radius(kind, xt - h, L, R, inputs)) / (2 * h)
        return float(sharp_radius(kind, xt, L, R, inputs)) * math.sqrt(1.0 + slope**2)

    lo, hi = 1e-6 * L, L * (1.0 - 1e-6)
    if not radius_at(lo) < nose_radius < radius_at(hi):
        raise ValueError(f"A spherical nose of radius {nose_radius:g} m cannot be tangent to this '{kind}' profile "
                         f"(it fits radii between {radius_at(lo):g} and {radius_at(hi):g} m): change the nose "
                         "radius or the profile.")
    xt = brentq(lambda t: radius_at(t) - nose_radius, lo, hi, xtol=1e-14 * L)
    slope = (sharp_radius(kind, xt + h, L, R, inputs) - sharp_radius(kind, xt - h, L, R, inputs)) / (2 * h)
    yt = float(sharp_radius(kind, xt, L, R, inputs))
    xc = xt + yt * slope                                           # sphere centre on the axis [m]
    alpha_t = math.asin(min(yt / nose_radius, 1.0))                # polar angle of the tangent point [rad]
    n_cap = max(n // 4, 12)
    a = np.linspace(0.0, alpha_t, n_cap)
    cap = np.column_stack([xc - nose_radius * np.cos(a), nose_radius * np.sin(a)])
    rest = chain[chain[:, 0] > xt + 1e-9 * L]
    out = np.vstack([cap, rest])
    out[:, 0] -= out[0, 0]                                         # the blunt tip is at x = 0
    return out


def profile(inputs):
    kind = inputs["kind"]
    L = inputs["length"]                                  # sharp-profile length [m]
    R = 0.5 * inputs["base_diameter"]                     # base radius [m]
    r_n = 0.5 * inputs["nose_diameter"] if inputs["blunt"] else 0.0
    chain = nose_chain(kind, L, R, inputs, inputs["points"], r_n)
    x_base = chain[-1, 0]                                 # end of the nose [m]
    after = inputs["afterbody_length"]
    if after > 0.0:
        chain = np.vstack([chain, [x_base + after, R]])
    total = chain[-1, 0]                                  # body length [m]
    return silhouette(chain, reference_length=total, reference_area=math.pi * R**2,
                      name=f"{kind}{', blunt' if r_n else ''}")

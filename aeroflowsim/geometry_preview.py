# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The geometry of a template as named boundary curves, for the Geometry step of the GUI (no GUI code).

Every geometry source (parametric nozzle, CSV profile, shape library) already produces a
WallProfile or a ShapeProfile (aeroflowsim/geometry.py, aeroflowsim/shapes/). This module turns
that object into the boundaries the mesh will have, each with its name and patch type:
    nozzle (WallProfile):         wall, inlet, outlet, axis
    body in a free stream:        wall (the body), farfield, and symmetry / axis on y = 0 for a half domain
so the user sees and checks the boundaries before meshing. Geometry workspace stage
replaces this read-only preview by an editable geometry with boundaries named by clicking.
"""

from dataclasses import dataclass, field

import numpy as np

from aeroflowsim.case import get_geometry
from aeroflowsim.geometry import WallProfile, profile_summary

CIRCLE_POINTS = 241   # points on a far-field circle (drawing only)


@dataclass
class Curve:
    """One named boundary: points (n, 2) in metres, in drawing order."""

    name: str          # e.g. "wall"
    type: str          # patch type: wall, inlet, outlet, axis, farfield, symmetry
    points: np.ndarray


@dataclass
class GeometryPreview:
    curves: list                                  # [Curve]
    summary: dict = field(default_factory=dict)   # {label: (value, unit)} shown next to the drawing
    warnings: list = field(default_factory=list)  # e.g. from the shape library
    axisymmetric: bool = False


def _nozzle(profile: WallProfile) -> GeometryPreview:
    if profile.interpolation == "pchip":     # draw the same smooth curve the mesh follows
        x = np.unique(np.r_[np.linspace(profile.x[0], profile.x[-1], 801), profile.x_throat])
    else:
        x = profile.x
    r = profile.radius_at(x)
    curves = [Curve("wall", "wall", np.column_stack([x, r])),
              Curve("inlet", "inlet", np.array([[x[0], 0.0], [x[0], r[0]]])),
              Curve("outlet", "outlet", np.array([[x[-1], 0.0], [x[-1], r[-1]]])),
              Curve("axis", "axis", np.array([[x[0], 0.0], [x[-1], 0.0]]))]
    summary = {key.replace("_", " "): value for key, value in profile_summary(profile).items()}
    return GeometryPreview(curves, summary, axisymmetric=True)


def _body(profile, domain) -> GeometryPreview:
    """A ShapeProfile, with the far-field boundary when the case defines one (case.domain)."""
    half = domain is not None and (domain.half or profile.axisymmetric)
    if half:
        chain = profile.upper_half()[0]               # right end on y = 0 ... left end on y = 0
        body = Curve("wall", "wall", chain)
    else:
        body = Curve("wall", "wall", profile.closed_points())
    curves = [body]
    if domain is not None:
        x0, y0, x1, y1 = profile.bbox
        xc = 0.5 * (x0 + x1)                          # body centre on the axis, as in gmsh_mesh [m]
        if domain.shape == "Circle":
            angle = np.linspace(0.0, np.pi if half else 2.0 * np.pi, CIRCLE_POINTS)
            far = np.column_stack([xc + domain.radius * np.cos(angle), domain.radius * np.sin(angle)])
            left, right = xc - domain.radius, xc + domain.radius
        else:
            left, right, h = x0 - domain.upstream, x1 + domain.downstream, domain.height
            far = np.array([[right, 0.0], [right, h], [left, h], [left, 0.0]]) if half else \
                np.array([[right, -h], [right, h], [left, h], [left, -h], [right, -h]])
        curves.append(Curve("farfield", "farfield", far))
        if half:
            kind = "axis" if profile.axisymmetric else "symmetry"
            curves.append(Curve(kind, kind, np.array([[left, 0.0], [chain[-1, 0], 0.0]])))
            curves.append(Curve(kind, kind, np.array([[chain[0, 0], 0.0], [right, 0.0]])))
    summary = {"reference length": (profile.reference_length, "m"),
               "reference area": (profile.reference_area, "m²"),
               "symmetry": ("axisymmetric" if profile.axisymmetric else "planar", ""),
               "outline points": (profile.n_points, "")}
    return GeometryPreview(curves, summary, list(profile.warnings), profile.axisymmetric)


def geometry_preview(case, params) -> GeometryPreview | None:
    """Named boundary curves of the case for these (validated) inputs; None if the case draws no geometry.

    Raises ValueError (with the case's own 'what to fix' message) if the geometry is invalid.
    """
    profile = get_geometry(case, params)
    if profile is None:
        return None
    if isinstance(profile, WallProfile):
        return _nozzle(profile)
    domain = case.domain(params, profile) if hasattr(case, "domain") else None
    return _body(profile, domain)

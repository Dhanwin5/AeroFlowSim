# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Geometric constraints and driving dimensions of a sketch, and their solver (no window needed).

A sketch (operations.SketchGroup) is points P_i = (x_i, y_i) and entities between them (lines,
arcs, circles, splines). A constraint is a rule such as "this line is horizontal" or "this
distance is 25 mm". Each rule is written as one or more equations f(x) = 0 (its "residuals"):

    coincident      P_i - P_j = 0                               (2 equations)
    horizontal      y_b - y_a = 0           vertical  x_b - x_a = 0
    parallel        d1 x d2 / (|d1| |d2|) = 0                   (2D cross product of the directions)
    perpendicular   d1 . d2 / (|d1| |d2|) = 0
    equal           L1 - L2 = 0             (lengths of lines, or radii of arcs / circles)
    tangent         meeting at a shared end point Q: line-arc  t . (Q - c)/|Q - c| = 0 (t = line direction);
                    arc-arc  (Q - c1) x (Q - c2) / (|Q - c1| |Q - c2|) = 0 (centres and Q in line);
                    otherwise line-arc: (distance from the centre to the line) - r = 0;
                    arc-arc:  |c1 - c2| - (r1 + r2) = 0 or |c1 - c2| - |r1 - r2| = 0 (the nearer one)
    point on        a point on a line (its distance to the line) or on a circle (|P - c| - r)
    fix             P_i - (its drawn position) = 0
    distance        |P_i - P_j| - value = 0;  distance_x: x_j - x_i - value;  distance_y likewise
    length          |b - a| - value = 0       radius  r - value = 0
    angle           the angle from line 1 to line 2 - value = 0 (as sin and cos, no jump at 180°)
Arcs also keep both ends at the same distance from their centre (added automatically).

SOLVER: all coordinates (and circle radii) are the unknowns x. A sketch usually has fewer
equations than unknowns (under-constrained: it can still move), so the solver minimises
    sum of residuals²  +  w² |x - x_drawn|²,      w = REGULARISATION (small)
with Levenberg-Marquardt (scipy.optimize.least_squares): among all shapes that satisfy the
constraints it picks the one nearest to what was drawn - the same idea as FreeCAD's sketcher.
Lengths are scaled by the sketch size, so millimetre and metre sketches solve alike.

STATUS: the degrees of freedom left = number of unknowns - rank of the Jacobian (the matrix of
derivatives of the residuals); 0 = fully constrained. Residuals that cannot be made zero mean
conflicting constraints (an error naming them); equations that add no rank are redundant.
"""

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

REGULARISATION = 1e-4      # weight of "stay near the drawn position" (scaled units) [-]
TOLERANCE = 1e-13          # a constraint is satisfied when its residual is below this x sketch size [-]
RANK_TOLERANCE = 1e-8      # singular values below this (relative) do not count for the rank [-]
TYPES = ("coincident", "horizontal", "vertical", "parallel", "perpendicular", "equal", "tangent", "point_on",
         "fix", "distance", "distance_x", "distance_y", "length", "radius", "angle")
DIMENSIONS = ("distance", "distance_x", "distance_y", "length", "radius", "angle")   # constraints with a value


@dataclass
class SolveResult:
    points: np.ndarray                       # solved points (n, 2) [m]
    entities: list                           # entities with solved circle radii
    dof: int                                 # degrees of freedom left (0 = fully constrained)
    conflicting: list = field(default_factory=list)   # indices of constraints that cannot be satisfied
    redundant: int = 0                       # number of equations that repeat others

    @property
    def status(self) -> str:
        if self.conflicting:
            return "conflicting"
        if self.dof == 0:
            return "fully constrained"
        return f"{self.dof} degree{'s' if self.dof != 1 else ''} of freedom left"


def _layout(points, entities):
    """Unknown vector layout: all point coordinates, then the radius of every circle."""
    circles = [k for k, e in enumerate(entities) if e.get("type") == "circle"]
    x0 = np.concatenate([np.asarray(points, dtype=float).ravel(), [float(entities[k]["r"]) for k in circles]])
    return x0, circles


def residual_functions(points, entities, constraints):
    """[(constraint index, f(x) -> residuals)] for every constraint, plus the arcs' own equal-radius rule."""
    n = len(points)
    circles = [k for k, e in enumerate(entities) if e.get("type") == "circle"]
    radius_slot = {k: 2 * n + m for m, k in enumerate(circles)}
    P = lambda x, i: x[2 * i:2 * i + 2]

    def line_ends(x, k):
        e = entities[k]
        if e.get("type") != "line":
            raise ValueError(f"constraint on entity {k + 1}: it must be a line")
        return P(x, e["p"][0]), P(x, e["p"][1])

    def circle_of(x, k):
        """(centre, radius) of an arc or circle entity."""
        e = entities[k]
        if e.get("type") == "arc":
            c = P(x, e["c"])
            return c, np.linalg.norm(P(x, e["p"][0]) - c)
        if e.get("type") == "circle":
            return P(x, e["c"]), x[radius_slot[k]]
        raise ValueError(f"constraint on entity {k + 1}: it must be an arc or a circle")

    def length_of(x, k):
        e = entities[k]
        if e.get("type") == "line":
            a, b = line_ends(x, k)
            return np.linalg.norm(b - a)
        return circle_of(x, k)[1]

    def unit(v):
        return v / max(np.linalg.norm(v), 1e-300)

    funcs = []
    for idx, c in enumerate(constraints):
        kind = c.get("type")
        if kind not in TYPES:
            raise ValueError(f"unknown constraint '{kind}'")
        v = float(c.get("value", 0.0))
        if kind == "coincident":
            i, j = c["p"]
            f = lambda x, i=i, j=j: P(x, i) - P(x, j)
        elif kind in ("horizontal", "vertical"):
            k = c["e"]
            axis = 1 if kind == "horizontal" else 0
            f = lambda x, k=k, axis=axis: np.array([line_ends(x, k)[1][axis] - line_ends(x, k)[0][axis]])
        elif kind in ("parallel", "perpendicular"):
            k, l = c["e"]

            def f(x, k=k, l=l, kind=kind):
                a1, b1 = line_ends(x, k)
                a2, b2 = line_ends(x, l)
                d1, d2 = unit(b1 - a1), unit(b2 - a2)
                return np.array([d1[0] * d2[1] - d1[1] * d2[0]]) if kind == "parallel" else np.array([d1 @ d2])
        elif kind == "equal":
            k, l = c["e"]
            f = lambda x, k=k, l=l: np.array([length_of(x, k) - length_of(x, l)])
        elif kind == "tangent":
            k, l = c["e"]
            if entities[k].get("type") != "line" and entities[l].get("type") == "line":
                k, l = l, k                                   # line first

            shared = set(entities[k].get("p", [])) & set(entities[l].get("p", []))
            joint = min(shared) if shared else None   # a point where the two meet (an end of both)

            def f(x, k=k, l=l, joint=joint):
                if joint is not None:
                    # They meet at a shared end point: the radius there is perpendicular to the line
                    # (or, for two arcs, both centres and the joint lie on one line). The distance form
                    # below has zero slope when the arc already touches the line (a minimum), so it would
                    # give the solver no information there.
                    q = P(x, joint)
                    if entities[k].get("type") == "line":
                        a, b = line_ends(x, k)
                        return np.array([unit(b - a) @ unit(q - circle_of(x, l)[0])])
                    u1, u2 = unit(q - circle_of(x, k)[0]), unit(q - circle_of(x, l)[0])
                    return np.array([u1[0] * u2[1] - u1[1] * u2[0]])
                if entities[k].get("type") == "line":
                    a, b = line_ends(x, k)
                    centre, r = circle_of(x, l)
                    d = b - a
                    dist = abs(d[0] * (centre - a)[1] - d[1] * (centre - a)[0]) / max(np.linalg.norm(d), 1e-300)
                    return np.array([dist - r])
                c1, r1 = circle_of(x, k)
                c2, r2 = circle_of(x, l)
                gap = np.linalg.norm(c1 - c2)
                return np.array([min(gap - (r1 + r2), gap - abs(r1 - r2), key=abs)])
        elif kind == "point_on":
            i, k = c["p"], c["e"]

            def f(x, i=i, k=k):
                q = P(x, i)
                if entities[k].get("type") == "line":
                    a, b = line_ends(x, k)
                    d = b - a
                    return np.array([(d[0] * (q - a)[1] - d[1] * (q - a)[0]) / max(np.linalg.norm(d), 1e-300)])
                centre, r = circle_of(x, k)
                return np.array([np.linalg.norm(q - centre) - r])
        elif kind == "fix":
            i = c["p"]
            target = np.asarray(c.get("at", points[i]), dtype=float)
            f = lambda x, i=i, target=target: P(x, i) - target
        elif kind == "distance":
            i, j = c["p"]
            f = lambda x, i=i, j=j, v=v: np.array([np.linalg.norm(P(x, j) - P(x, i)) - v])
        elif kind in ("distance_x", "distance_y"):
            i, j = c["p"]
            axis = 0 if kind == "distance_x" else 1
            f = lambda x, i=i, j=j, v=v, axis=axis: np.array([P(x, j)[axis] - P(x, i)[axis] - v])
        elif kind == "length":
            k = c["e"]
            f = lambda x, k=k, v=v: np.array([length_of(x, k) - v])
        elif kind == "radius":
            k = c["e"]
            f = lambda x, k=k, v=v: np.array([circle_of(x, k)[1] - v])
        else:                                                 # angle from line 1 to line 2 [deg]
            k, l = c["e"]
            a = math.radians(v)

            def f(x, k=k, l=l, a=a):
                a1, b1 = line_ends(x, k)
                a2, b2 = line_ends(x, l)
                d1, d2 = unit(b1 - a1), unit(b2 - a2)
                rot = np.array([math.cos(a) * d1[0] - math.sin(a) * d1[1], math.sin(a) * d1[0] + math.cos(a) * d1[1]])
                return np.array([rot[0] * d2[1] - rot[1] * d2[0], 1.0 - rot @ d2])   # d2 = d1 turned by a
        funcs.append((idx, f))
    for k, e in enumerate(entities):                          # an arc's ends are both on its circle
        if e.get("type") == "arc":
            s, t = e["p"]
            ci = e["c"]
            funcs.append((None, lambda x, s=s, t=t, ci=ci: np.array(
                [np.linalg.norm(P(x, t) - P(x, ci)) - np.linalg.norm(P(x, s) - P(x, ci))])))
    return funcs


def solve(points, entities, constraints) -> SolveResult:
    """Points and entities that satisfy the constraints, nearest to the drawn ones (see the module text)."""
    points = np.asarray(points, dtype=float).reshape(-1, 2)
    entities = [dict(e) for e in entities]
    x0, circles = _layout(points, entities)
    size = max(float(np.ptp(points, axis=0).max()) if len(points) else 0.0,
               max([abs(float(c.get("value", 0.0))) for c in constraints if c.get("type") in DIMENSIONS
                    and c.get("type") != "angle"] or [0.0]), 1e-12)
    funcs = residual_functions(points, entities, constraints)
    if not funcs:
        return SolveResult(points, entities, len(x0))
    scale = 1.0 / size                                        # solve in units of the sketch size
    def meet(c):                                              # tangent at a shared end point (no length unit)
        return c.get("type") == "tangent" and bool(set(entities[c["e"][0]].get("p", [])) &
                                                   set(entities[c["e"][1]].get("p", [])))
    angular = {i for i, c in enumerate(constraints)
               if c.get("type") in ("parallel", "perpendicular", "angle") or meet(c)}   # residuals without a length

    def constraint_residuals(z):
        x = z / scale
        out = []
        for idx, f in funcs:
            r = np.atleast_1d(f(x))
            out.append(r if idx in angular else r * scale)
        return np.concatenate(out)

    def residuals(z):
        return np.concatenate([constraint_residuals(z), REGULARISATION * (z - x0 * scale)])

    z0 = x0 * scale
    fit = least_squares(residuals, z0, method="lm", xtol=1e-15, ftol=1e-15, gtol=1e-15, max_nfev=2000 * (len(z0) + 1))
    z = fit.x
    # Polish: the tiny regularisation pull leaves the equations met only to about REGULARISATION².
    # A few Gauss-Newton steps then find the point on the constraint surface NEAREST to the drawing:
    # with J the Jacobian and r the residuals at z, the new point z0 + w has the smallest w = z' - z0
    # that meets the linearised equations J (z' - z) = -r, i.e. w = J⁺ (J (z - z0) - r) (J⁺ the
    # pseudo-inverse). So coordinates no constraint touches stay exactly where they were drawn.
    for _ in range(30):
        r = constraint_residuals(z)
        J = _jacobian(constraint_residuals, z)
        new = z0 + np.linalg.lstsq(J, J @ (z - z0) - r, rcond=None)[0]
        moved = np.abs(new - z).max()
        z = new
        if np.abs(r).max() <= TOLERANCE and moved <= 1e-14:
            break
    x = z / scale
    r = constraint_residuals(z)
    J = _jacobian(constraint_residuals, z)
    singular = np.linalg.svd(J, compute_uv=False) if J.size else np.zeros(0)
    rank = int(np.count_nonzero(singular > RANK_TOLERANCE * max(singular.max() if singular.size else 0.0, 1.0)))
    dof = len(z) - rank
    conflicting = []
    offset = 0
    for idx, f in funcs:                                       # which constraints are not satisfied
        m = len(np.atleast_1d(f(x)))
        if idx is not None and np.abs(r[offset:offset + m]).max() > 1e-6:
            conflicting.append(idx)
        offset += m
    n = len(points)
    solved = x[:2 * n].reshape(-1, 2)
    for m, k in enumerate(circles):
        entities[k]["r"] = float(x[2 * n + m])
    return SolveResult(solved, entities, dof, conflicting, max(0, len(r) - rank))


def _jacobian(func, z, h=1e-7):
    """Derivatives of func at z by central differences (columns: unknowns)."""
    f0 = func(z)
    J = np.empty((len(f0), len(z)))
    for k in range(len(z)):
        dz = np.zeros_like(z)
        dz[k] = h
        J[:, k] = (func(z + dz) - func(z - dz)) / (2.0 * h)
    return J

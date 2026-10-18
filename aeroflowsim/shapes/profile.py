# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The closed outline of a body (airfoil, wedge, cylinder, nose cone, ...): ShapeProfile.

Every shape in the shape library returns one, whatever its inputs. Mesh generators (Gmsh,
aeroflowsim/gmsh_mesh.py) only use this object, so a new shape never needs new mesh code.

In plain words, a ShapeProfile is:
    points        the outline as a list of (x, y) points [m], going round the body once
                  counter-clockwise (the body is on the left when walking along the points).
                  The last point is NOT repeated: the outline closes from the last point back
                  to the first one.
    corners       which points are sharp corners (a wedge tip, a trailing edge, a base edge).
                  Between corners the outline is smooth, so the mesher may draw a smooth curve
                  (spline) through the points; at corners it must keep the kink.
    refine        which points need smaller cells (corners, leading and trailing edges).
    axisymmetric  False: a planar 2D body (1 m deep). True: a body of revolution about the x axis;
                  the outline is then the full silhouette, symmetric about y = 0.
    reference_length [m], reference_area [m²]: used to size the domain and the cells now, and
                  for the force coefficients (Cl, Cd, Cm) from Prompt 7:
                      planar        reference area = reference length x 1 m depth
                      axisymmetric  reference area = base area pi R²
"""

from dataclasses import dataclass, field

import numpy as np

CLOSE_TOLERANCE = 1e-9   # points closer than this fraction of the body size are "the same point" [-]


@dataclass
class ShapeProfile:
    """The closed outline of a body; see the module docstring."""

    points: np.ndarray            # (N, 2) outline points [m], counter-clockwise, last point not repeated
    reference_length: float       # [m]
    reference_area: float         # [m²]
    axisymmetric: bool = False
    corners: np.ndarray = None    # (N,) True at sharp corners (a list of point numbers is also accepted)
    refine: np.ndarray = None     # (N,) True where cells should be smaller (corners are always refined)
    name: str = ""                # e.g. "NACA 2412"
    warnings: list = field(default_factory=list)   # things the user should know (shown in the GUI)

    def __post_init__(self):
        points = np.asarray(self.points, dtype=float)
        if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3:
            raise ValueError("A shape outline needs at least 3 points (x, y).")
        if not np.all(np.isfinite(points)):
            raise ValueError("A shape outline contains an infinite or NaN coordinate.")
        self.corners = _mask(self.corners, len(points))
        self.refine = _mask(self.refine, len(points)) | self.corners
        # Remove a repeated last point (an outline given as closed) and repeated neighbours.
        size = float(np.ptp(points, axis=0).max())
        if size <= 0.0:
            raise ValueError("A shape outline must have a size (all its points are the same).")
        step = np.linalg.norm(np.diff(points, axis=0, append=points[:1]), axis=1)
        keep = step > CLOSE_TOLERANCE * size        # point i is kept if it differs from point i + 1
        points, self.corners, self.refine = points[keep], self.corners[keep], self.refine[keep]
        if len(points) < 3:
            raise ValueError("A shape outline needs at least 3 different points.")
        if signed_area(points) < 0.0:              # clockwise: turn round (keep point 0 first)
            order = np.r_[0, np.arange(len(points) - 1, 0, -1)]
            points, self.corners, self.refine = points[order], self.corners[order], self.refine[order]
        self.points = points
        if self.reference_length <= 0.0 or self.reference_area <= 0.0:
            raise ValueError("The reference length and area of a shape must be positive.")

    # ---- simple facts --------------------------------------------------------------------------

    @property
    def n_points(self) -> int:
        return len(self.points)

    @property
    def area(self) -> float:
        """Area enclosed by the outline [m²] (positive: counter-clockwise)."""
        return signed_area(self.points)

    @property
    def perimeter(self) -> float:
        """Length of the outline [m]."""
        return float(np.linalg.norm(np.diff(self.points, axis=0, append=self.points[:1]), axis=1).sum())

    @property
    def bbox(self) -> tuple:
        """(x_min, y_min, x_max, y_max) [m]."""
        (x0, y0), (x1, y1) = self.points.min(axis=0), self.points.max(axis=0)
        return float(x0), float(y0), float(x1), float(y1)

    def closed_points(self) -> np.ndarray:
        """The outline with the first point repeated at the end (handy for plotting)."""
        return np.vstack([self.points, self.points[:1]])

    def self_intersections(self) -> int:
        """Number of pairs of outline segments that cross each other (0 for a valid outline)."""
        return count_self_intersections(self.points)

    def is_symmetric(self, tolerance=1e-6) -> bool:
        """True if the outline is the same when mirrored about y = 0 (within tolerance x size)."""
        mirrored = self.points * [1.0, -1.0]
        return _max_distance_to_outline(mirrored, self.points) <= tolerance * max(self.reference_length, 1e-300)

    def volume_of_revolution(self) -> float:
        """Volume [m³] of the body of revolution (axisymmetric shapes): Pappus on the upper half."""
        chain, _, _ = self.upper_half()
        x, y = chain[:, 0], chain[:, 1]
        # Closed polygon "upper outline + axis": volume = 2 pi x area x y_centroid = (2 pi) sum over
        # edges of the first moment of area, written with the shoelace formula.
        xs, ys = np.r_[x, x[:1]], np.r_[y, y[:1]]
        cross = xs[:-1] * ys[1:] - xs[1:] * ys[:-1]
        moment = np.sum(cross * (ys[:-1] + ys[1:])) / 6.0      # area x y_centroid [m³]
        return float(2.0 * np.pi * abs(moment))

    # ---- half outline for half domains ---------------------------------------------------------

    def upper_half(self, tolerance=1e-6):
        """The part of the outline with y >= 0, for a half domain (symmetry plane or axis at y = 0).

        Returns (chain, corners, refine): an open line of points from its right end on y = 0, over
        the top, to its left end on y = 0 (counter-clockwise order), with its corner and refine
        flags. The two end points lie exactly on y = 0 and count as corners (there the body meets
        the symmetry line). Raises ValueError if the body is not symmetric about y = 0.
        """
        if not self.is_symmetric(tolerance):
            raise ValueError(f"'{self.name or 'This shape'}' is not symmetric about y = 0, so a half domain "
                             "would change the body. Switch the half domain off.")
        size = self.reference_length
        pts, corners, refine = [], [], []
        n = self.n_points
        for i in range(n):                          # insert the points where the outline crosses y = 0
            p, q = self.points[i], self.points[(i + 1) % n]
            yp = 0.0 if abs(p[1]) <= tolerance * size else p[1]
            pts.append([p[0], yp])
            corners.append(self.corners[i])
            refine.append(self.refine[i])
            yq = 0.0 if abs(q[1]) <= tolerance * size else q[1]
            if yp * yq < 0.0:
                t = yp / (yp - yq)
                pts.append([p[0] + t * (q[0] - p[0]), 0.0])
                corners.append(True)
                refine.append(True)
        pts, corners, refine = np.array(pts), np.array(corners), np.array(refine)
        on_axis = np.flatnonzero(pts[:, 1] == 0.0)
        if len(on_axis) != 2:
            raise ValueError("The outline must touch y = 0 at exactly two points (front and back) to "
                             f"make a half domain; it touches it at {len(on_axis)} points.")
        # Start at the axis point after which the outline goes up (y > 0), walk to the other one.
        start = next(i for i in on_axis if pts[(i + 1) % len(pts), 1] > 0.0)
        end = on_axis[0] if start == on_axis[1] else on_axis[1]
        idx = (start + np.arange((end - start) % len(pts) + 1)) % len(pts)
        corners, refine = corners[idx].copy(), refine[idx].copy()
        corners[[0, -1]] = refine[[0, -1]] = True
        return pts[idx], corners, refine


# ---- helpers ------------------------------------------------------------------------------------

def _mask(value, n) -> np.ndarray:
    """A boolean array of length n from None, a boolean array or a list of point numbers."""
    if value is None:
        return np.zeros(n, dtype=bool)
    value = np.asarray(value)
    if value.dtype == bool:
        if value.shape != (n,):
            raise ValueError("A corner / refine mask needs one True/False per outline point.")
        return value.copy()
    mask = np.zeros(n, dtype=bool)
    mask[value.astype(int)] = True
    return mask


def signed_area(points) -> float:
    """Shoelace formula: area of a closed polygon [m²], positive if counter-clockwise."""
    x, y = np.asarray(points, dtype=float).T
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def count_self_intersections(points, closed=True) -> int:
    """Number of pairs of non-neighbouring edges that cross (proper crossings only).

    closed=True: a polygon (the last point joins the first); False: an open line of points.
    """
    p = np.asarray(points, dtype=float)
    a, b = p, np.roll(p, -1, axis=0)                  # edge k goes from a[k] to b[k]
    n = len(p)
    if not closed:                                    # drop the closing edge n-1
        a, b, n = a[:-1], b[:-1], n - 1
        if n < 3:
            return 0

    def orient(p1, p2, p3):                           # > 0 left turn, < 0 right turn
        return ((p2[..., 0] - p1[..., 0]) * (p3[..., 1] - p1[..., 1])
                - (p2[..., 1] - p1[..., 1]) * (p3[..., 0] - p1[..., 0]))

    count = 0
    for i in range(n - 2):                            # compare edge i with every later edge j > i + 1
        j = np.arange(i + 2, n if (i > 0 or not closed) else n - 1)   # closed: edges 0 and n-1 are neighbours
        if len(j) == 0:
            continue
        d1, d2 = orient(a[j], b[j], a[i]), orient(a[j], b[j], b[i])
        d3, d4 = orient(a[i], b[i], a[j]), orient(a[i], b[i], b[j])
        count += int(np.count_nonzero((d1 * d2 < 0.0) & (d3 * d4 < 0.0)))
    return count


def _max_distance_to_outline(points, outline) -> float:
    """Largest distance [m] of `points` from the closed polygon `outline`."""
    a, b = outline, np.roll(outline, -1, axis=0)
    ab = b - a
    length2 = np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-300)
    worst = 0.0
    for start in range(0, len(points), 256):          # in blocks, to keep memory small
        pts = points[start:start + 256, None, :]      # (m, 1, 2)
        t = np.clip(np.einsum("mkj,kj->mk", pts - a, ab) / length2, 0.0, 1.0)
        nearest = a + t[..., None] * ab               # nearest point on every edge (m, k, 2)
        distance = np.linalg.norm(pts - nearest, axis=2).min(axis=1)
        worst = max(worst, float(distance.max()))
    return worst


def turning_corners(points, angle_deg=30.0) -> np.ndarray:
    """(N,) True where the outline turns by more than angle_deg at a point (a sharp corner)."""
    p = np.asarray(points, dtype=float)
    before = p - np.roll(p, 1, axis=0)
    after = np.roll(p, -1, axis=0) - p
    cosine = np.einsum("ij,ij->i", before, after) / np.maximum(
        np.linalg.norm(before, axis=1) * np.linalg.norm(after, axis=1), 1e-300)
    return np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))) > angle_deg

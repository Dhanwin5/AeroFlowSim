# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Structured O-grids and C-grids of quadrilaterals around a body (ShapeProfile), made in NumPy.

Both are ONE block of (i, j) points: i runs along the body (and, for the C-grid, along the wake), j runs from the
wall to the far field. Every grid line j = const is a layer, every line i = const leaves the wall at a right angle.

    O-grid   closed smooth bodies (cylinder, sphere, ...). i goes round the body; the far field is a circle of radius R
             about the body's centre. Half domain (axisymmetric bodies, or symmetric ones with half_domain on): i goes from
             the front axis point over the top to the rear axis point, the far field is a half circle, and the lines
             i = first and i = last lie on y = 0 (patch axis / symmetry).
    C-grid   airfoils (a smooth outline with one leading edge and one SHARP trailing edge). i goes along the lower wake
             (from the outflow to the trailing edge), along the lower surface to the leading edge, along the upper surface to
             the trailing edge and along the upper wake to the outflow. The far field is a semicircle of radius R about the
             trailing edge, in front of the airfoil, closed by two horizontal lines at y = y_TE +- R behind it, and the
             two vertical sides at x = x_TE + R (outflow). The wake lines (j = 0 behind the trailing edge) are a CUT: their
             two copies are one set of nodes, so cells on both sides share them. Half domain (symmetric airfoils): only
             the part above y = 0 is built; the wake line and the line in front of the nose are the patch symmetry.

How each grid line is made. For every i there is a point P on the wall (inner line) and a point Q on the far-field boundary.
The line from P to Q has
    distance from the wall      d_j = D s_j,  D = |Q - P|, s_j = a geometric series: s_1 D is exactly the FIRST LAYER HEIGHT
                                h0, the next cells grow by the constant ratio r that makes n_normal layers fill D
                                (solved from h0 (r^n - 1) / (r - 1) = D; the series ends exactly on Q),
    direction                   u = normalise((1 - w) n + w e), n the wall normal, e = (Q - P) / D, w = s^0.7: the line leaves
                                the wall along the normal (right angle) and bends towards the far-field point.
So the wall-normal spacing is exactly what the user types; the growth ratio follows from the far-field distance and the
number of layers and is checked against the maximum growth rate the user allows. Along the body the points are placed
by arc length with cosine clustering towards the leading and trailing edges (C-grid) or uniformly (O-grid).

Patches are named exactly like the unstructured mesh of aeroflowsim/gmsh_mesh.py: wall, farfield and, for a half domain,
symmetry (planar) or axis (axisymmetric): the solver switches between the mesh types without any change.
"""

import math
from dataclasses import dataclass

import numpy as np

from aeroflowsim.mesh import QUAD, Mesh

MIN_FACTOR_LAYERS = 4          # the far field must be at least this many first-layer heights away [-]
MAX_CELLS = 2_000_000          # same limit as the unstructured mesher [-]
BEND_POWER = 0.7               # the grid line bends from the wall normal to the far-field point as s^BEND_POWER [-]
CLUSTER = 0.8                  # C-grid surface points: share of cosine (end) clustering in the arc-length spacing [-]
FAN = 0.5                      # C-grid far-field points: share of the wall spacing kept (0: evenly spread, 1: as the wall) [-]
TE_POWER = 1.0                  # ... with this power of the remaining distance [-]
TE_BLEND = 0.5                 # C-grid: the wall normals turn to the wake direction over this many chords at the TE [-]
PRESETS = {                    # (cells around the body, cells normal to the wall, cells along the wake)
    "Coarse": (80, 40, 25),
    "Medium": (160, 60, 50),
    "Fine": (320, 90, 100),
}


@dataclass
class StructuredSettings:
    """How to build a structured grid (all lengths in metres)."""

    n_body: int                 # cells around the body: all of it (O-grid; with a half domain only the half) or the
                                # upper and lower surface together (C-grid)
    n_normal: int               # cells from the wall to the far field
    n_wake: int                 # cells along each wake line (C-grid)
    first_height: float         # height of the cell layer touching the wall [m]
    max_growth: float           # largest allowed growth ratio between neighbouring layers [-]
    far_distance: float         # far-field radius R [m]: from the body's centre (O-grid) or from the trailing edge (C-grid)
    half: bool = False          # only the upper half (symmetry plane / axis at y = 0)

    def check(self):
        if self.n_body < 8 or self.n_normal < 2 or self.n_wake < 0:
            raise ValueError("A structured grid needs at least 8 cells around the body, 2 normal to the wall and 2 "
                             "along the wake.")
        if self.n_body % 2:
            raise ValueError("The number of cells around the body must be even (half on each side).")
        if not (self.first_height > 0.0 and self.far_distance > 0.0):
            raise ValueError("The first layer height and the far-field distance must be positive.")
        if self.max_growth <= 1.0:
            raise ValueError("The maximum growth rate must be larger than 1.")


# ---- which grid fits which body ---------------------------------------------------------------------------------

def grid_kind(profile, half=False) -> str:
    """"C" or "O": the structured grid that fits this body. ValueError saying why if none does (the GUI shows it)."""
    name = profile.name or "This shape"
    if profile.self_intersections():
        raise ValueError(f"{name}: the outline crosses itself.")
    pts = profile.points
    tip = 1e-6 * profile.reference_length
    flagged = np.flatnonzero(profile.corners)
    if profile.axisymmetric:
        return _smooth_o(profile, name)
    x = pts[:, 0]
    le, te = int(np.argmin(x)), int(np.argmax(x))
    if te not in flagged:                                   # no sharp trailing edge: a smooth closed body (cylinder, ellipse)
        return _smooth_o(profile, name)
    if np.count_nonzero(x > x.max() - tip) > 1:
        raise ValueError(f"{name} has a blunt trailing edge: the C-grid needs a sharp one (close the trailing edge). Use the "
                         "unstructured mesh for blunt edges.")
    if np.any(~np.isin(flagged, [le, te])):
        raise ValueError(f"{name} has corners other than its leading and trailing edge, so a C-grid (which resamples the "
                         "surface) would cut them. Use the unstructured mesh.")
    return "C"


def _smooth_o(profile, name):
    """"O" if the body (or its upper half) has no corners except the two axis points, else ValueError."""
    if profile.axisymmetric or profile.is_symmetric():
        _, corners, _ = profile.upper_half()
        sharp = bool(np.any(corners[1:-1]))
    else:
        sharp = bool(np.any(profile.corners))
    if sharp:
        raise ValueError(f"{name} has sharp corners, so an O-grid (which needs a smooth body) does not fit. Use the "
                         "unstructured mesh, or a smooth shape (cylinder, sphere).")
    return "O"


# ---- grid lines ------------------------------------------------------------------------------------------------

def geometric_fractions(h0, D, n):
    """Distances s_j D (j = 0 ... n) from the wall as fractions s_j of D: geometric with first cell h0, ending at 1.

    D may be an array (one value per grid line). Returns (s (len(D), n + 1), ratio (len(D),)). ValueError if even a
    ratio of 1 (equal cells) is too coarse: n h0 > D."""
    D = np.atleast_1d(np.asarray(D, dtype=float))
    if np.any(n * h0 > D * (1.0 + 1e-12)):
        raise ValueError(f"The first layer is too thick: {n} layers of {h0:g} m already reach {n * h0:g} m, more than "
                         f"the {D.min():g} m to the far field. Lower the first layer height or use fewer layers.")

    def total(r):                                   # h0 (r^n - 1) / (r - 1), safe near r = 1
        lr = np.log(r)
        return h0 * np.where(np.abs(lr) < 1e-9, n, np.expm1(n * lr) / np.expm1(lr))

    lo, hi = np.full(len(D), 1.0), np.full(len(D), 4.0)
    for _ in range(80):                             # bisection on the ratio: total(r) rises with r
        mid = 0.5 * (lo + hi)
        big = total(mid) > D
        hi, lo = np.where(big, mid, hi), np.where(big, lo, mid)
    r = 0.5 * (lo + hi)
    j = np.arange(n + 1)[None, :]
    lr = np.log(r)[:, None]
    dist = h0 * np.where(np.abs(lr) < 1e-9, j, np.expm1(j * lr) / np.expm1(lr))
    s = dist / D[:, None]
    s[:, -1] = 1.0                                  # end exactly on the far-field point
    return s, r


def _normals(P, periodic):
    """Unit wall normals of the polyline P (n, 2) travelled with the fluid on the LEFT: (-t_y, t_x)."""
    if periodic:
        t = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
    else:
        t = np.empty_like(P)
        t[1:-1] = P[2:] - P[:-2]
        t[0], t[-1] = P[1] - P[0], P[-1] - P[-2]
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    return np.column_stack([-t[:, 1], t[:, 0]])


def grid_lines(P, Q, n_normal, first_height, normals):
    """The points X (n_normal + 1, len(P), 2) of the lines from the wall points P to the far-field points Q."""
    D = np.linalg.norm(Q - P, axis=1)
    s, ratio = geometric_fractions(first_height, D, n_normal)            # (i, j)
    e = (Q - P) / D[:, None]
    w = s ** BEND_POWER                                                   # 0 at the wall, 1 at the far field
    u = (1.0 - w)[..., None] * normals[:, None, :] + w[..., None] * e[:, None, :]
    u /= np.linalg.norm(u, axis=2, keepdims=True)
    X = P[:, None, :] + (D[:, None] * s)[..., None] * u                   # (i, j, 2)
    X[:, -1, :] = Q                                                       # the last layer sits exactly on the far field
    return np.transpose(X, (1, 0, 2)), ratio


def _resample(polyline, n, cluster):
    """n + 1 points along the open polyline, by arc length; cluster=True: cosine spacing (dense at both ends)."""
    seg = np.linalg.norm(np.diff(polyline, axis=0), axis=1)
    arc = np.r_[0.0, np.cumsum(seg)]
    u = np.linspace(0.0, 1.0, n + 1)
    if cluster:                                     # part uniform, part cosine: dense at both ends, but not extreme
        u = (1.0 - CLUSTER) * u + CLUSTER * 0.5 * (1.0 - np.cos(np.pi * u))
    s = u * arc[-1]
    return np.column_stack([np.interp(s, arc, polyline[:, 0]), np.interp(s, arc, polyline[:, 1])]), u


def _quads(n_i, n_j):
    """Quad cells (cells, 4) of an (n_i + 1) x (n_j + 1) point block, counter-clockwise for i to the right, j up."""
    i, j = np.meshgrid(np.arange(n_i), np.arange(n_j), indexing="ij")
    ids = lambda a, b: b * (n_i + 1) + a                                   # noqa: E731
    return np.column_stack([ids(i, j).ravel(), ids(i + 1, j).ravel(), ids(i + 1, j + 1).ravel(), ids(i, j + 1).ravel()])


def _finish(X, ids, cells, patches, axisymmetric, info):
    """Merge duplicate points (ids maps every block point to its node), renumber and make the Mesh."""
    block = X.reshape(-1, 2)
    unique, first = np.unique(ids, return_index=True)
    node_of = np.empty(len(block), dtype=np.int64)
    node_of[:] = np.searchsorted(unique, ids)
    nodes = block[first]
    cells = node_of[cells]
    boundary = {name: (kind, node_of[faces]) for name, (kind, faces) in patches.items()}
    if axisymmetric:
        nodes[:, 1] = np.maximum(nodes[:, 1], 0.0)
    return Mesh.from_cells(nodes, QUAD, cells, boundary, dim=2, axisymmetric=axisymmetric, info=info)


def _edge(ids_a, ids_b):
    return np.column_stack([ids_a, ids_b])


# ---- O-grid ----------------------------------------------------------------------------------------------------

def o_grid(profile, settings: StructuredSettings) -> Mesh:
    """O-grid around a closed smooth body (see the module docstring)."""
    settings.check()
    half = settings.half or profile.axisymmetric
    if grid_kind(profile, half) != "O":
        raise ValueError(f"{profile.name or 'This shape'} needs a C-grid, not an O-grid.")
    x0, y0, x1, y1 = profile.bbox
    centre = np.array([0.5 * (x0 + x1), 0.0])
    if half:
        chain, _, _ = profile.upper_half()
        line = chain[::-1]                                                 # front axis point -> over the top -> rear axis point
        P, _ = _resample(line, settings.n_body // 2, False)
        P[0, 1] = P[-1, 1] = 0.0
        periodic = False
    else:
        closed = profile.points[::-1]                                      # clockwise: the fluid is on the left
        loop = np.vstack([closed, closed[:1]])
        P, _ = _resample(loop, settings.n_body, False)
        P = P[:-1]                                                         # the last point is the first again
        periodic = True
    far = settings.far_distance
    reach = np.hypot(profile.points[:, 0] - centre[0], profile.points[:, 1]).max()
    if far <= 1.5 * reach:
        raise ValueError(f"The far field (radius {far:g} m) must be well outside the body (more than {1.5 * reach:.3g} m).")
    radial = P - centre
    Q = centre + far * radial / np.linalg.norm(radial, axis=1, keepdims=True)
    if half:
        Q[0], Q[-1] = [centre[0] - far, 0.0], [centre[0] + far, 0.0]       # the ends stay on the axis
    n_i = len(P) if periodic else len(P) - 1
    if periodic:
        P_ext, Q_ext, normals = np.vstack([P, P[:1]]), np.vstack([Q, Q[:1]]), np.vstack([_normals(P, True), _normals(P, True)[:1]])
    else:
        P_ext, Q_ext, normals = P, Q, _normals(P, False)
    if half:
        normals[0], normals[-1] = [-1.0, 0.0], [1.0, 0.0]
    n_j = settings.n_normal
    _check_size(n_i * n_j)
    X, ratio = grid_lines(P_ext, Q_ext, n_j, settings.first_height, normals)           # (j, i, 2)
    _check_growth(ratio, settings)
    n_pts = n_i + 1
    ids = np.arange(n_pts * (n_j + 1)).reshape(n_j + 1, n_pts)
    if periodic:
        ids[:, -1] = ids[:, 0]                                                        # close the ring: last column is the first
    cells = _quads(n_i, n_j)
    ring = ids
    patches = {"wall": ("wall", _edge(ring[0, :-1], ring[0, 1:])), "farfield": ("farfield", _edge(ring[-1, :-1], ring[-1, 1:]))}
    if half:
        kind = "axis" if profile.axisymmetric else "symmetry"
        patches[kind] = (kind, np.vstack([_edge(ring[:-1, 0], ring[1:, 0]), _edge(ring[:-1, -1], ring[1:, -1])]))
    info = _info("O", profile, settings, ratio, n_i * n_j, half)
    return _finish(X, ring.ravel(), cells, patches, bool(profile.axisymmetric), info)


# ---- C-grid ----------------------------------------------------------------------------------------------------

def c_grid(profile, settings: StructuredSettings) -> Mesh:
    """C-grid around an airfoil with a sharp trailing edge (see the module docstring)."""
    settings.check()
    if grid_kind(profile, False) != "C":
        raise ValueError(f"{profile.name or 'This shape'} needs an O-grid, not a C-grid.")
    pts = profile.points
    le, te = int(np.argmin(pts[:, 0])), int(np.argmax(pts[:, 0]))
    # counter-clockwise: TE -> upper surface -> LE -> lower surface -> TE
    upper = _walk(pts, te, le)[::-1]                                        # LE -> TE along the upper surface
    lower = _walk(pts, le, te)                                              # LE -> TE along the lower surface
    if upper[:, 1].mean() < lower[:, 1].mean():
        upper, lower = lower, upper                                         # (the outline was clockwise after all)
    if settings.half and not profile.is_symmetric():
        raise ValueError("A half domain needs a body that is symmetric about y = 0.")
    n_s = settings.n_body // 2
    U, _ = _resample(upper, n_s, True)                                      # LE -> TE
    Lw, _ = _resample(lower, n_s, True)                                     # LE -> TE
    te_pt = U[-1].copy()
    R = settings.far_distance
    if R <= 2.0 * profile.reference_length:
        raise ValueError(f"The far field (radius {R:g} m from the trailing edge) must be more than two body lengths away.")
    # wake: x from the trailing edge to the outflow, first cell = the last surface cell, geometric
    h_te = float(np.linalg.norm(U[-1] - U[-2]))
    s_w, r_w = geometric_fractions(h_te, np.array([R]), settings.n_wake)
    wake_x = te_pt[0] + R * s_w[0]                                          # TE ... outflow, settings.n_wake + 1 points
    wake = np.column_stack([wake_x, np.full_like(wake_x, te_pt[1])])
    n_w = settings.n_wake
    centre = te_pt
    # inner line, travelled with the fluid on the left: lower wake (outflow -> TE), lower surface (TE -> LE),
    # upper surface (LE -> TE), upper wake (TE -> outflow)
    inner = np.vstack([wake[::-1], Lw[::-1][1:], U[1:], wake[1:]])
    # far-field points: the matching sections of the C
    lower_arc = _arc(centre, R, -math.pi, -0.5 * math.pi, _fan(Lw))        # LE (-180 deg) ... TE (-90 deg)
    upper_arc = _arc(centre, R, math.pi, 0.5 * math.pi, _fan(U))           # LE (180 deg) ... TE (90 deg)
    far_x = te_pt[0] + R * (FAN * s_w[0] + (1.0 - FAN) * np.linspace(0.0, 1.0, n_w + 1))      # the far-field columns fan out
    far_lower_wake = np.column_stack([far_x[::-1], np.full(n_w + 1, centre[1] - R)])
    far_upper_wake = np.column_stack([far_x, np.full(n_w + 1, centre[1] + R)])
    outer = np.vstack([far_lower_wake, lower_arc[::-1][1:], upper_arc[1:], far_upper_wake[1:]])
    normals = _normals(inner, False)
    # at the trailing edge the normal of the wake line (vertical) is the right one for both surfaces' last points
    i_te_lower, i_le, i_te_upper = n_w, n_w + n_s, n_w + 2 * n_s
    # Near the trailing edge the surface normals of a wedge point backwards and the lines would cross the vertical wake
    # lines: over the last TE_BLEND chords of each surface the normal is turned smoothly to the wake direction (0, -+1).
    for surface, first, wake_normal, starts_at_te in ((Lw[::-1], i_te_lower, (0.0, -1.0), True),
                                                      (U, i_le, (0.0, 1.0), False)):
        arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(surface, axis=0), axis=1))]
        to_te = arc if starts_at_te else arc[-1] - arc                      # distance of each point from the trailing edge [m]
        b = (1.0 - np.minimum(to_te / (TE_BLEND * profile.reference_length), 1.0)) ** TE_POWER
        sl = slice(first, first + n_s + 1)
        blended = (1.0 - b)[:, None] * normals[sl] + b[:, None] * np.array(wake_normal)
        normals[sl] = blended / np.linalg.norm(blended, axis=1, keepdims=True)
    n_j = settings.n_normal
    if settings.half:
        keep = slice(i_le, None)                                           # only the upper half: LE ... outflow
        inner, outer, normals = inner[keep], outer[keep], normals[keep]
        normals[0] = [-1.0, 0.0]
        inner[0, 1] = 0.0
    n_i = len(inner) - 1
    _check_size(n_i * n_j)
    X, ratio = grid_lines(inner, outer, n_j, settings.first_height, normals)           # (j, i, 2)
    _check_growth(ratio, settings)
    if settings.half:
        X[:, 0, 1] = 0.0                                                    # the line in front of the nose lies on y = 0
        X[0, n_s:, 1] = 0.0                                                 # ... and the wake line behind the trailing edge
    n_pts = n_i + 1
    ids = np.arange(n_pts * (n_j + 1)).reshape(n_j + 1, n_pts)
    cells = _quads(n_i, n_j)
    patches = {}
    if settings.half:
        wall_i = np.arange(0, n_s + 1)                                      # LE ... TE
        wake_i = np.arange(n_s, n_i + 1)
        patches["wall"] = ("wall", _edge(ids[0, wall_i[:-1]], ids[0, wall_i[1:]]))
        patches["symmetry"] = ("symmetry", np.vstack([_edge(ids[0, wake_i[:-1]], ids[0, wake_i[1:]]),
                                                      _edge(ids[:-1, 0], ids[1:, 0])]))
        patches["farfield"] = ("farfield", np.vstack([_edge(ids[-1, :-1], ids[-1, 1:]), _edge(ids[:-1, -1], ids[1:, -1])]))
    else:
        # the wake cut: lower wake i = a (0 ... n_w) and upper wake i = n_i - n_w + k (k = n_w - a) are the same points
        for a in range(n_w + 1):
            ids[0, n_i - a] = ids[0, a]                                     # the points of the cut are shared (lower copy kept)
        wall_i = np.arange(n_w, n_w + 2 * n_s + 1)                          # TE (lower) ... LE ... TE (upper)
        patches["wall"] = ("wall", _edge(ids[0, wall_i[:-1]], ids[0, wall_i[1:]]))
        patches["farfield"] = ("farfield", np.vstack([_edge(ids[-1, :-1], ids[-1, 1:]), _edge(ids[:-1, 0], ids[1:, 0]),
                                                       _edge(ids[:-1, -1], ids[1:, -1])]))
    info = _info("C", profile, settings, ratio, n_i * n_j, settings.half)
    info["wake_growth"] = float(r_w[0])
    info["n_wake"] = int(n_w)
    return _finish(X, ids.ravel(), cells, patches, False, info)


def _walk(points, start, stop):
    """The outline points from index start to index stop going forward (counter-clockwise), both included."""
    n = len(points)
    count = (stop - start) % n
    return points[(start + np.arange(count + 1)) % n]


def _fan(surface):
    """Where the grid lines of a surface end on the far-field arc: the arc-length fractions of its points, partly evened out."""
    f = _frac(surface)
    return FAN * f + (1.0 - FAN) * np.linspace(0.0, 1.0, len(f))


def _frac(surface):
    """Arc-length fraction (0 ... 1) of the points of a polyline."""
    arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(surface, axis=0), axis=1))]
    return arc / arc[-1]


def _arc(centre, R, a0, a1, fraction):
    """Points on the circle of radius R about centre, from angle a0 to a1 [rad], at the given fractions of the way."""
    a = a0 + (a1 - a0) * fraction
    return np.column_stack([centre[0] + R * np.cos(a), centre[1] + R * np.sin(a)])


def _check_size(n_cells):
    if n_cells > MAX_CELLS:
        raise ValueError(f"This grid would have {n_cells:,} cells (limit {MAX_CELLS:,}). Use fewer cells.")


def _check_growth(ratio, settings):
    if float(ratio.max()) > settings.max_growth * (1.0 + 1e-9):
        need = math.ceil(settings.n_normal * math.log(float(ratio.max())) / math.log(settings.max_growth))
        raise ValueError(f"With {settings.n_normal} layers, a first layer of {settings.first_height:g} m and the far field at "
                         f"{settings.far_distance:g} m the layers must grow by {float(ratio.max()):.3f} per cell, more than the "
                         f"allowed {settings.max_growth:g}. Use at least {need} layers, a thicker first layer, or a nearer "
                         "far field.")


def _info(kind, profile, settings, ratio, n_cells, half):
    return {
        "generator": "structured_" + kind.lower() + "grid", "shape": profile.name, "axisymmetric": bool(profile.axisymmetric),
        "reference_length": float(profile.reference_length), "reference_area": float(profile.reference_area),
        "half_domain": bool(half), "grid": kind, "n_body": int(settings.n_body), "n_normal": int(settings.n_normal),
        "first_layer_height": float(settings.first_height), "growth_max": float(ratio.max()), "growth_min": float(ratio.min()),
        "far_distance": float(settings.far_distance),
    }


def structured_mesh(profile, settings: StructuredSettings) -> Mesh:
    """The O-grid or C-grid that fits the body (ValueError saying why if none does)."""
    kind = grid_kind(profile, settings.half)
    return o_grid(profile, settings) if kind == "O" else c_grid(profile, settings)


def estimate_structured_cells(profile, settings: StructuredSettings) -> int:
    """Number of cells the grid will have (no meshing)."""
    kind = grid_kind(profile, settings.half)
    if kind == "O":
        around = settings.n_body // 2 if (settings.half or profile.axisymmetric) else settings.n_body
        return around * settings.n_normal
    around = settings.n_body // 2 + settings.n_wake if settings.half else settings.n_body + 2 * settings.n_wake
    return around * settings.n_normal

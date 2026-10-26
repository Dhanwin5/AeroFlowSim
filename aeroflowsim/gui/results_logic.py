# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Decisions of the 2D Results view that need no window (no Qt, no VTK), so they are tested directly.

A Scene is everything that defines one picture of a 2D result: the field, how it is coloured (smooth from node
values, flat per cell, banded), contour lines, colour map and range, overlays (mesh edges, boundaries), vectors,
streamlines, mirror / 3D revolve, and the camera. Scenes are saved in the project (key `scenes`) and restored with
one click. prepare() turns a Scene and a post.Solution into plain arrays in the user's display units; the VTK view
(gui/flow_view.py) only draws them.
"""

import math
import dataclasses
from dataclasses import dataclass

import numpy as np

from aeroflowsim.post.fields import FieldError, available_fields, field_info, field_values, node_values

SMOOTH, FLAT, BANDED = "Smooth (node values)", "Cell values", "Banded"
COLOURINGS = (SMOOTH, FLAT, BANDED)
RANGE_AUTO, RANGE_TYPED, RANGE_SNAPSHOTS, RANGE_CLIP = ("Automatic", "Typed", "Over all snapshots",
                                                       "Automatic, clip 1 % at each end")
RANGE_MODES = (RANGE_AUTO, RANGE_TYPED, RANGE_SNAPSHOTS, RANGE_CLIP)
BAR_POSITIONS = ("Bottom", "Right", "Hidden")
VECTOR_FIELDS = {"velocity": ("u", "v", "Velocity", "m/s"), "grad_p": (None, None, "Pressure gradient", "Pa/m"),
                 "grad_rho": (None, None, "Density gradient", "kg/m⁴")}
LAYOUTS = {"Single view": 1, "Two views": 2, "Four views": 4}


@dataclass
class Scene:
    """One picture of a 2D result (stored in the project as a dict)."""

    field: str = "M"
    colouring: str = SMOOTH
    n_bands: int = 12
    contour_lines: bool = False
    n_levels: int = 12
    levels: list = dataclasses.field(default_factory=list)   # typed levels [display units]; empty = n_levels evenly spaced
    line_labels: bool = False
    cmap: str = "turbo"
    range_mode: str = RANGE_AUTO
    vmin: float | None = None                     # typed range [display units]
    vmax: float | None = None
    log_scale: bool = False
    bar_position: str = "Bottom"
    bar_format: str = "%.4g"
    edges: bool = False
    boundaries: bool = True
    vectors: bool = False
    vector_field: str = "velocity"
    vector_scale: float = 1.0                     # x the automatic arrow length
    vector_skip: int = 1                          # draw every n-th cell (uniform density: cells chosen on a grid)
    vector_uniform: bool = True
    vector_colour_by: str = ""                    # "" = one colour, else a field name
    vector_fixed_length: bool = False
    streamlines: bool = False
    stream_seeds: str = ""                        # surface name (line / rake) whose points seed the streamlines
    stream_points: list = dataclasses.field(default_factory=list)   # clicked seed points [m]
    stream_n: int = 20                            # seeds along a line surface
    stream_colour_by: str = ""
    stream_arrows: bool = True
    mirror: bool = False
    revolve: bool = False                         # 3D surface of revolution (axisymmetric results)
    revolve_angle: float = 270.0                  # [deg]
    camera: list = dataclasses.field(default_factory=list)    # VTK camera position [(position), (focal point), (view up)]

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d) -> "Scene":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in dict(d or {}).items() if k in known})


def default_scenes(kind) -> dict:
    """The standard scenes of a template kind (shown in the report and offered in the view)."""
    out = {"Mach number": Scene("M"), "Pressure": Scene("p", cmap="viridis")}
    if kind == "external":
        out["Pressure coefficient"] = Scene("Cp", cmap="coolwarm", contour_lines=True)
    out["Numerical schlieren"] = Scene("schlieren", cmap="gray", colouring=FLAT)
    return out


def field_choices(sol) -> list:
    """[(label shown, field name)] grouped as in the field list of the view."""
    out = []
    for info in available_fields(sol):
        out.append((f"{info.label}" + (f"  ({info.group})" if info.group not in ("Flow",) else ""), info.name))
    return out


def display_values(values, unit, prefs):
    """(values in the display unit, unit label) for the user's unit preferences."""
    if prefs is not None and prefs.unit_for(unit) is not None:
        conv = prefs.unit_for(unit)
        return np.asarray(conv.from_si(np.asarray(values, dtype=float))), conv.name
    return np.asarray(values, dtype=float), unit


def to_display_number(value, unit, prefs):
    v, _ = display_values(np.array([value]), unit, prefs)
    return float(v[0])


def colour_range(values, scene, other_values=()):
    """(vmin, vmax) of the colour bar [display units] for the scene's range mode; other_values: the same field of
    the snapshots (range over all snapshots)."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return 0.0, 1.0
    if scene.range_mode == RANGE_TYPED and scene.vmin is not None and scene.vmax is not None and scene.vmax > scene.vmin:
        return float(scene.vmin), float(scene.vmax)
    if scene.range_mode == RANGE_SNAPSHOTS and len(other_values):
        allv = np.concatenate([v] + [np.asarray(o, dtype=float)[np.isfinite(o)] for o in other_values])
        return float(allv.min()), float(allv.max())
    if scene.range_mode == RANGE_CLIP:
        return float(np.percentile(v, 1.0)), float(np.percentile(v, 99.0))
    lo, hi = float(v.min()), float(v.max())
    if hi <= lo:
        hi = lo + max(abs(lo), 1.0) * 1e-6
    return lo, hi


def contour_levels(scene, vmin, vmax) -> np.ndarray:
    """Contour-line levels [display units]: the typed ones inside the range, or n_levels evenly (or log) spaced
    strictly inside (vmin, vmax)."""
    if scene.levels:
        return np.array(sorted(float(x) for x in scene.levels if vmin <= float(x) <= vmax))
    n = max(int(scene.n_levels), 1)
    if scene.log_scale and vmin > 0:
        return np.logspace(math.log10(vmin), math.log10(vmax), n + 2)[1:-1]
    return np.linspace(vmin, vmax, n + 2)[1:-1]


def scene_problem(sol, scene) -> str:
    """'' if the scene can be drawn on this solution, else why not (plain words)."""
    try:
        field_info(sol, scene.field)
    except FieldError as exc:
        return str(exc)
    if scene.revolve and not sol.axisymmetric:
        return "The 3D revolved view is for axisymmetric results only."
    if scene.log_scale:
        v = field_values(sol, scene.field)
        if np.nanmin(v) <= 0:
            return f"A log scale needs positive values; {scene.field} reaches {float(np.nanmin(v)):.3g}."
    return ""


@dataclass
class SceneData:
    """What the view draws, in display units."""

    cell: np.ndarray            # (C,) values per cell
    node: np.ndarray            # (N,) values per node
    unit: str
    label: str
    vmin: float
    vmax: float
    levels: np.ndarray
    vectors: np.ndarray | None = None      # (C, 3) vector per cell (display units) or None
    vector_colour: np.ndarray | None = None
    vector_cells: np.ndarray | None = None
    node_velocity: np.ndarray | None = None   # (N, 3) for streamlines [m/s]
    seeds: np.ndarray | None = None           # (k, 3) streamline seeds [m]
    stream_colour_node: np.ndarray | None = None
    title: str = ""


def _uniform_cells(sol, target):
    """About `target` cells spread evenly over the domain (one per square of a grid): uniform arrow density."""
    c = sol.geom.cell_centres[:, :2]
    lo, hi = c.min(axis=0), c.max(axis=0)
    span = np.maximum(hi - lo, 1e-12)
    n = max(int(math.sqrt(target * span[0] / span[1])), 1), max(int(math.sqrt(target * span[1] / span[0])), 1)
    ij = np.floor((c - lo) / span * np.array(n)).astype(int).clip(0, np.array(n) - 1)
    key = ij[:, 0] * (n[1] + 1) + ij[:, 1]
    _, first = np.unique(key, return_index=True)
    return np.sort(first)


def prepare(sol, scene, prefs=None, snapshots=(), seed_surfaces=None) -> SceneData:
    """All arrays of a scene. snapshots: other Solutions on the same mesh for the "over all snapshots" range;
    seed_surfaces: {name: Surface} for streamline seeds."""
    info = field_info(sol, scene.field)
    cell, unit = display_values(field_values(sol, scene.field), info.unit, prefs)
    node, _ = display_values(node_values(sol, scene.field), info.unit, prefs)
    others = []
    for s in snapshots:
        try:
            others.append(display_values(field_values(s, scene.field), info.unit, prefs)[0])
        except FieldError:
            pass
    shown = cell if scene.colouring == FLAT else node
    vmin, vmax = colour_range(shown, scene, others)
    levels = contour_levels(scene, vmin, vmax)
    data = SceneData(cell, node, unit, info.label, vmin, vmax, levels,
                     title=f"{info.label} [{unit}]" if unit and unit != "-" else info.label)
    if scene.vectors:
        cells = _uniform_cells(sol, 1500 / max(scene.vector_skip, 1)) if scene.vector_uniform \
            else np.arange(sol.mesh.n_cells)[::max(scene.vector_skip, 1)]
        if scene.vector_field == "velocity":
            vec = np.column_stack([sol.fields["u"], sol.fields["v"], np.zeros(sol.mesh.n_cells)])
        else:
            from aeroflowsim.post.sampling import field_gradient
            g = field_gradient(sol, "p" if scene.vector_field == "grad_p" else "rho")
            vec = np.column_stack([g[0], g[1], np.zeros(sol.mesh.n_cells)])
        data.vectors = vec
        data.vector_cells = cells
        if scene.vector_colour_by:
            ci = field_info(sol, scene.vector_colour_by)
            data.vector_colour = display_values(field_values(sol, scene.vector_colour_by), ci.unit, prefs)[0]
    if scene.streamlines:
        u, v = node_values(sol, "u"), node_values(sol, "v")
        data.node_velocity = np.column_stack([u, v, np.zeros_like(u)])
        seeds = [list(p) + [0.0] for p in scene.stream_points]
        if scene.stream_seeds and seed_surfaces and scene.stream_seeds in seed_surfaces:
            s = seed_surfaces[scene.stream_seeds]
            if s.type in ("line", "rake", "x_line", "y_line"):
                if s.type in ("line", "rake"):
                    a, b = np.array(s.start), np.array(s.end)
                else:
                    from aeroflowsim.post.surfaces import evaluate_surface
                    d = evaluate_surface(sol, s)
                    a, b = (d.a[0], d.b[-1]) if d.n else (np.zeros(2), np.zeros(2))
                n = s.n_points if s.type == "rake" else scene.stream_n
                for t in np.linspace(0.02, 0.98, max(n, 1)):
                    p = a + t * (b - a)
                    seeds.append([float(p[0]), float(p[1]), 0.0])
            elif s.type == "point":
                seeds.append([s.start[0], s.start[1], 0.0])
        data.seeds = np.array(seeds) if seeds else None
        if scene.stream_colour_by:
            ci = field_info(sol, scene.stream_colour_by)
            data.stream_colour_node = display_values(node_values(sol, scene.stream_colour_by), ci.unit, prefs)[0]
    return data


def histogram(sol, name, bins=40, weighted=False, prefs=None):
    """(counts, edges, stats) of a field: cell count or volume-weighted fraction per bin; stats {min, mean, max}
    (mean volume-weighted) in display units."""
    info = field_info(sol, name)
    v, unit = display_values(field_values(sol, name), info.unit, prefs)
    V = sol.geom.volumes
    w = V / V.sum() if weighted else None
    counts, edges = np.histogram(v, bins=bins, weights=w)
    stats = {"min": float(v.min()), "mean": float(np.sum(v * V) / V.sum()), "max": float(v.max()), "unit": unit}
    return counts, edges, stats


def probe_rows(sol, xy, prefs=None, names=("rho", "u", "v", "p", "T", "M", "p0", "T0", "Cp")):
    """[(label, value text, unit)] of the fields at a point (linear reconstruction in the containing cell)."""
    from aeroflowsim.gui.logic import readable
    from aeroflowsim.post.sampling import locate, values_at
    cell = locate(sol, np.array([xy]))
    if cell[0] < 0:
        return [("Point", "outside the mesh", "")]
    rows = [("Cell", str(int(cell[0])), "")]
    for n in names:
        try:
            info = field_info(sol, n)
        except FieldError:
            continue
        value = float(values_at(sol, n, np.array([xy]), cell)[0])
        rows.append((info.label, *readable(value, info.unit, digits=6, prefs=prefs)))
    return rows


def hover_text(sol, scene, xy, prefs=None) -> str:
    """Tooltip text: the shown field's value at the point (or '' outside the mesh)."""
    from aeroflowsim.post.sampling import CELL, LINEAR, values_at
    info = field_info(sol, scene.field)
    v = float(values_at(sol, scene.field, np.array([xy]), mode=CELL if scene.colouring == FLAT else LINEAR)[0])
    if not math.isfinite(v):
        return ""
    shown, unit = display_values(np.array([v]), info.unit, prefs)
    return f"{info.label}: {shown[0]:.5g} {unit}"

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Smart rules: suggestions for the setup, each with a one-line reason (CLAUDE.md "Intelligence").

Intelligence assists, never replaces physics: a rule only SUGGESTS. The GUI shows every suggestion
with its reason and an Apply button; nothing is applied automatically, and whatever is applied is
then checked by the validity checks like any other input.

Each rule is ONE small function, like a check:

    def my_rule(built, context) -> list[Suggestion]

built: the replayed workspace geometry (BuiltGeometry); context: SizeContext below (the template,
its inputs, where its size inputs are). To add a rule, write one function and add it to RULES.

First rules (Prompt 6d): suggested sizes from the geometry -
  wall cell size   at most L / 100 (L: reference length) and at most a quarter of the smallest wall
                   feature, so that every wall feature gets at least about 4 cells;
  largest size     about 1/25 of the domain (internal flow), or 2 L but at most 1/20 of the domain
                   (external flow), so the far field is not under-resolved;
  enclosure        subsonic or unknown Mach number: the far field at least 20 L from the body (the
                   disturbance of the body must have decayed there); supersonic (Mach > 1): a
                   rectangle, 2 L upstream (disturbances cannot travel upstream; the bow shock
                   stands close to the body), 5 L downstream, and high enough that the Mach waves
                   from the body (angle mu = asin(1/M)) leave through the outlet, not the top;
  corner refinement  on when the walls have sharp corners (turning more than 30 degrees).
"""

import math
from dataclasses import dataclass, field

from aeroflowsim.geometry_model import FLUID

SHARP_CORNER = 30.0          # a wall corner turning more than this is "sharp" [deg]
CELLS_PER_L = 100.0          # wall cells per reference length (at most this size) [-]
CELLS_PER_FEATURE = 4.0      # cells along the smallest wall feature [-]
SUBSONIC_FAR_FIELD = 20.0    # far field at least this many reference lengths from a body [-]


@dataclass
class Suggestion:
    title: str                   # e.g. "Wall cell size"
    text: str                    # the suggested value as text, e.g. "0.05 mm"
    reason: str                  # one line: why
    kind: str                    # "input" (set template inputs) or "operation" (add / replace a geometry step)
    inputs: dict = field(default_factory=dict)   # kind "input": {input key: value}
    operation: object = None     # kind "operation": the Operation (with the id of the one it replaces, or "")


@dataclass
class SizeContext:
    params: dict                 # the template inputs
    sizes: dict                  # case.size_inputs(params, built): {"surface": (key, scale), "max": (key, scale),
                                 #  "edge_refinement": key}; an input value = metres / scale
    mach: float | None = None    # free-stream Mach number, if the template has one
    document: object = None      # the geometry history (for enclosure suggestions)


def length_text(metres) -> str:
    """A length as people write it: "12.5 mm", "1.13 m" or "3.2 µm"."""
    if metres >= 1.0:
        return f"{metres:.3g} m"
    if metres >= 1e-3:
        return f"{metres * 1e3:.3g} mm"
    return f"{metres * 1e6:.3g} µm"


def _wall_edges(built):
    return [built.edges[e] for e in built.boundary_edges() if e in built.names and built.names[e].type == "wall"]


def _has_bodies(built) -> bool:
    return any(len(f.loops) > 1 for f in built.faces_with_role(FLUID))


def _input(context, which, metres, title, reason):
    if which not in context.sizes:
        return []
    key, scale = context.sizes[which]
    value = float(f"{metres / scale:.2g}")
    return [Suggestion(title, f"{length_text(metres)}  ({key} = {value:g})", reason, "input", {key: value})]


def surface_size(built, context):
    walls = _wall_edges(built)
    if not walls:
        return []
    L = built.reference_length()
    feature = min(e.length for e in walls)
    h = min(L / CELLS_PER_L, feature / CELLS_PER_FEATURE)
    limit = "the smallest wall feature" if feature / CELLS_PER_FEATURE < L / CELLS_PER_L else "the reference length"
    reason = (f"Smallest wall feature {length_text(feature)} and L = {length_text(L)}: at least "
              f"{CELLS_PER_FEATURE:g} cells along every feature and {CELLS_PER_L:g} along L (set by {limit}).")
    return _input(context, "surface", h, "Wall cell size", reason)


def largest_size(built, context):
    box = built.bbox()
    if box is None or not built.faces:
        return []
    domain = math.hypot(box[2] - box[0], box[3] - box[1])
    if _has_bodies(built):
        h = min(2.0 * built.reference_length(), domain / 20.0)
        reason = "External flow: cells up to about 2 L far from the body, and at least 20 across the domain."
    else:
        h = domain / 25.0
        reason = "Internal flow (no body): at least about 25 cells across the domain away from the walls."
    return _input(context, "max", h, "Largest cell size", reason)


def corner_refinement(built, context):
    from aeroflowsim.geometry_model.kernel import turning_angle
    key = context.sizes.get("edge_refinement")
    if key is None or context.params.get(key):
        return []
    walls = {e.id for e in _wall_edges(built)}
    sharp = [v for v in built.vertices.values() if len(v.edges) == 2 and set(v.edges) & walls
             and turning_angle(built, v) > SHARP_CORNER]
    if not sharp:
        return []
    return [Suggestion("Corner refinement", "on", f"{len(sharp)} sharp wall corner(s) (turning more than "
                       f"{SHARP_CORNER:g}°): flow gradients are large there, so the cells should be smaller.",
                       "input", {key: True})]


def enclosure_size(built, context):
    from aeroflowsim.geometry_model.operations import Enclosure
    if context.document is None or not _has_bodies(built):
        return []
    current = next((op for op in reversed(context.document.operations)
                    if op.type == "enclosure" and not op.suppressed and op.params["kind"] in Enclosure.KINDS[:3]), None)
    if context.mach is not None and context.mach > 1.0:
        mu = math.asin(1.0 / context.mach)
        up, down = 2.0, 5.0
        height = max(3.0, math.tan(mu) * (up + 1.0 + down) + 1.0)
        op = Enclosure(current.id if current else "", kind="rectangle", upstream=up, downstream=down,
                       height=float(f"{height:.2g}"), half=bool(current and current.params["half"]))
        reason = (f"Supersonic (Mach {context.mach:g}): disturbances cannot travel upstream, so 2 L upstream is "
                  f"enough; Mach waves at mu = {math.degrees(mu):.3g}° must leave through the outlet.")
        return [Suggestion("Enclosure", f"rectangle {up:g} L up, {down:g} L down, {height:.2g} L high", reason,
                           "operation", operation=op)]
    if current is not None:
        p = current.params
        far = {"circle": p["radius"], "c_domain": min(p["radius"], p["downstream"]),
               "rectangle": min(p["upstream"], p["downstream"], p["height"])}[p["kind"]]
        if far >= SUBSONIC_FAR_FIELD:
            return []
        op = Enclosure(current.id, **{**p, "radius": max(p["radius"], SUBSONIC_FAR_FIELD),
                                      "upstream": max(p["upstream"], SUBSONIC_FAR_FIELD),
                                      "downstream": max(p["downstream"], SUBSONIC_FAR_FIELD),
                                      "height": max(p["height"], SUBSONIC_FAR_FIELD)})
        text = f"far field at least {SUBSONIC_FAR_FIELD:g} L from the body"
    else:
        return []
    reason = (f"{'Subsonic' if context.mach is not None else 'Mach number not set (subsonic assumed)'}: the body "
              f"disturbs the flow far away, so the far field should be at least {SUBSONIC_FAR_FIELD:g} L away "
              f"(now {far:g} L).")
    return [Suggestion("Enclosure", text, reason, "operation", operation=op)]


RULES = [surface_size, largest_size, corner_refinement, enclosure_size]


def suggestions(built, context) -> list[Suggestion]:
    """Every rule's suggestions (a rule that fails is skipped: a suggestion is never essential)."""
    out = []
    for rule in RULES:
        try:
            out += rule(built, context)
        except Exception:
            continue
    return out

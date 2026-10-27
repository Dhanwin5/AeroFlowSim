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
    flow: dict | None = None     # flow_scales() of the template inputs (first-layer height), if known


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


def shock_on_lip(built, context):
    """Intake shapes: put the cowl lip on the shocks of the ramps (planar) or of the spike cone (axisymmetric).

    Needs the free-stream Mach number (context.mach). Ramps: the lip is where shock 1 and shock 2 cross (one ramp: on
    shock 1 at the lip's x); the later shocks miss it by the distances in the reason. Spike: the lip radius on the
    Taylor-Maccoll conical shock at the lip's x. See aeroflowsim/intake_theory.py."""
    from aeroflowsim import intake_theory
    from aeroflowsim.shapes import SHAPE_KEY
    p, mach = context.params, context.mach
    shape = p.get(SHAPE_KEY)
    if mach is None or mach <= 1.0 or shape not in ("Ramp intake (planar)", "Spike intake (axisymmetric)"):
        return []
    gamma = 1.4
    try:
        from aeroflowsim.gases import gas_model
        gamma = float(gas_model(p["gas"]).gamma)
    except Exception:
        pass                                                   # no gas input: air-like gamma
    if shape == "Spike intake (axisymmetric)":
        out = intake_theory.spike_lip(mach, gamma, p["spike_intake.cone_half_angle"], p["spike_intake.lip_x"])
        r = float(f"{out['lip'][1]:.4g}")
        return [Suggestion("Cowl lip on the spike shock", f"{length_text(out['lip'][1])}  (spike_intake.lip_r = {r:g})",
                           f"At Mach {mach:g} the conical shock of the {p['spike_intake.cone_half_angle']:g} deg spike "
                           f"leaves the tip at {out['beta']:.2f} deg, so at x = {length_text(out['lip'][0])} it is at this radius.",
                           "input", {"spike_intake.lip_r": r})]
    n = int(p["ramp_intake.n_ramps"])
    angles = [p[f"ramp_intake.angle{i}"] for i in range(1, n + 1)]
    lengths = [p[f"ramp_intake.length{i}"] for i in range(1, n + 1)]
    out = intake_theory.ramp_lip(mach, gamma, angles, lengths, lip_x=p["ramp_intake.lip_x"])
    x, y = (float(f"{v:.4g}") for v in out["lip"])
    angles_text = ", ".join(f"{s['angle']:.2f}" for s in out["shocks"])
    misses = ", ".join(length_text(m) for m in out["miss"])
    reason = (f"At Mach {mach:g} the {n} ramp shock(s) leave at {angles_text} deg from the free stream. "
              + ("The lip sits on shock 1 at your lip x." if n == 1 else "Shocks 1 and 2 meet here.")
              + f" Distance of the lip from each shock: {misses}.")
    inputs = {"ramp_intake.lip_y": y} if n == 1 else {"ramp_intake.lip_x": x, "ramp_intake.lip_y": y}
    text = f"lip at x = {length_text(x)}, height {length_text(y)}" if n > 1 else f"lip height {length_text(y)}"
    return [Suggestion("Cowl lip on the ramp shocks", text, reason, "input", inputs)]


RULES = [surface_size, largest_size, corner_refinement, enclosure_size, shock_on_lip]   # first_layer is added below


def suggestions(built, context) -> list[Suggestion]:
    """Every rule's suggestions (a rule that fails is skipped: a suggestion is never essential)."""
    out = []
    for rule in RULES:
        try:
            out += rule(built, context)
        except Exception:
            continue
    return out


# ==================================================================================================
# Flow rules (Prompt 7): numerics from the flow inputs, first-layer height, failure diagnosis
# ==================================================================================================
#
# These rules use the flow inputs (Mach number, reservoir or free-stream state, gas), so they complete
# the 6d rules. Signature:  def rule(case, params, result=None) -> list[Suggestion]. A Suggestion of kind
# "advice" has no Apply button (something to check by hand, e.g. a boundary value).

TARGET_Y_PLUS = 1.0          # wall-resolved boundary layers (laminar / low-Re models) [-]
STRONG_SHOCK_MACH = 3.0      # free-stream Mach number above which the bow shock counts as strong [-]
LOW_MACH = 0.3               # below this an explicit density-based solver converges slowly [-]


def flow_scales(case, params) -> dict | None:
    """Reference density [kg/m³], velocity [m/s], viscosity [Pa s], length [m] and Reynolds number of the
    flow, from the template inputs: the free stream of a body (mach, p_inf, T_inf), or the sonic throat
    state of a nozzle (p0, T0, throat diameter). None if the template has neither."""
    from aeroflowsim import gasdynamics as gd
    if not hasattr(case, "gas"):
        return None
    gas = case.gas(params)
    if "mach" in params and "p_inf" in params:
        T = params["T_inf"]
        rho = params["p_inf"] / (gas.R * T)
        U = params["mach"] * float(gas.sound_speed(T))
        L = float(case.reference_length(params)) if hasattr(case, "reference_length") else 1.0
        where = "free stream"
    elif "p0" in params and hasattr(case, "geometry"):
        g = float(gas.gamma(params["T0"]))
        T = params["T0"] / gd.t0_over_t(1.0, g)
        rho = params["p0"] / gd.p0_over_p(1.0, g) / (gas.R * T)
        U = float(gas.sound_speed(T))
        L = 2.0 * case.geometry(params).r_throat
        where = "throat"
    else:
        return None
    mu = float(gas.mu(T))
    return {"rho": rho, "U": U, "mu": mu, "L": L, "Re": rho * U * L / mu, "where": where}


def first_layer_height(flow, y_plus=TARGET_Y_PLUS) -> float:
    """Wall-normal height [m] of the first cell for a target y+, from a flat-plate skin friction estimate:
        Cf = 0.026 Re^(-1/7)  (turbulent flat plate, White 2006 eq. 6-70),  tau_w = Cf rho U²/2,
        u_tau = sqrt(tau_w / rho),  y = y+ mu / (rho u_tau).
    (For laminar flow it errs on the small, safe side.)"""
    cf = 0.026 * flow["Re"] ** (-1.0 / 7.0)
    u_tau = math.sqrt(0.5 * cf) * flow["U"]
    return y_plus * flow["mu"] / (flow["rho"] * u_tau)


def first_layer(built, context):
    """Inflation layers on: the first-layer height for y+ = 1 at the flow's Reynolds number."""
    flow = context.flow
    key = context.sizes.get("first_layer")
    if not flow or key is None or not context.params.get("inflation"):
        return []
    key, scale = key
    h = first_layer_height(flow)
    value = float(f"{h / scale:.2g}")
    reason = (f"Re = {flow['Re']:.3g} (based on the {flow['where']} state and L = {length_text(flow['L'])}): "
              f"y+ = {TARGET_Y_PLUS:g} needs a first cell about {length_text(h)} high (flat-plate estimate). "
              "Inviscid (Euler) runs do not need inflation layers; they are for viscous flow (Phase 4).")
    return [Suggestion("First layer height", f"{length_text(h)}  ({key} = {value:g})", reason, "input", {key: value})]


def numerics_suggestions(case, params) -> list:
    """CFL number, first-order start and initial solution from the flow inputs (before a run)."""
    out = []
    mach = params.get("mach")
    if mach is not None and mach >= STRONG_SHOCK_MACH:
        out.append(Suggestion("Strong-shock start", "CFL 0.5, 500 first-order iterations, carbuncle fix on",
                              f"Mach {mach:g}: the bow shock is strong (pressure ratio "
                              f"{_normal_shock_ratio(mach, case, params):.3g}). A first-order start lets it form "
                              "without overshoots, a lower CFL keeps the start stable, and the HLLE blend prevents the "
                              "carbuncle.", "input", {"cfl": 0.5, "first_order_iterations": 500, "carbuncle_fix": True}))
    elif mach is not None and mach > 1.0:
        out.append(Suggestion("Supersonic start", "200 first-order iterations",
                              f"Mach {mach:g}: shocks form at the start; a short first-order start is more robust.",
                              "input", {"first_order_iterations": 200}))
    elif mach is not None and mach < LOW_MACH:
        out.append(Suggestion("Low Mach number", f"Mach {mach:g}", "An explicit density-based solver converges "
                              "slowly below about Mach 0.3 (acoustic waves are much faster than the flow); expect many "
                              "iterations. Low-Mach preconditioning comes in Prompt 8b.", "advice"))
    if params.get("initialisation") == "Uniform (free stream)" and "p0" in params:
        out.append(Suggestion("Initial solution", "Quasi-1D solution", "A nozzle started from the quasi-1D flow already "
                              "has its throat and supersonic expansion; from a uniform state it must find them, which "
                              "takes far more iterations and can fail.", "input",
                              {"initialisation": "Quasi-1D solution"}))
    if params.get("time_scheme") == "Jameson 4-stage" and params.get("cfl", 0.0) > 2.0:
        out.append(Suggestion("CFL number", "1.5", "The four-stage scheme is stable up to about CFL 2 with "
                              "second-order upwind fluxes.", "input", {"cfl": 1.5}))
    elif params.get("time_scheme") == "SSP-RK3" and params.get("cfl", 0.0) > 1.0:
        out.append(Suggestion("CFL number", "0.8", "SSP-RK3 with second-order upwind fluxes is stable up to about "
                              "CFL 1 (the solver halves a too large CFL by itself, which costs iterations).", "input",
                              {"cfl": 0.8}))
    return out


def _normal_shock_ratio(mach, case, params):
    from aeroflowsim import gasdynamics as gd
    g = float(case.gas(params).gamma(params.get("T_inf", 300.0))) if hasattr(case, "gas") else 1.4
    return gd.normal_shock(mach, g)["p2_p1"]


def diagnose(case, params, result) -> list:
    """What to try after a run that diverged or needed CFL reductions, each with its reason (never applied
    automatically). Uses Result.info of the 2D solver: status, where it diverged, CFL reductions."""
    info = getattr(result, "info", None) or {}
    status = info.get("status")
    if status != "diverged" and not info.get("cfl_reductions"):
        return []
    out = []
    cfl = min(float(params.get("cfl", 0.8)), float(info.get("cfl_final", 0.8)))
    out.append(Suggestion("Lower CFL", f"{cfl / 2:.2g}", f"The solution became unphysical with CFL "
                          f"{info.get('cfl_final', cfl):g}: a smaller time step damps the start-up transients.",
                          "input", {"cfl": float(f"{cfl / 2:.2g}")}))
    if params.get("first_order_iterations", 0) < 500:
        out.append(Suggestion("First-order start", "500 iterations", "First order is far more robust: shocks and "
                              "expansions form smoothly before the second-order reconstruction is switched on.",
                              "input", {"first_order_iterations": 500}))
    if params.get("initialisation") == "Uniform (free stream)" and "p0" in params:
        out.append(Suggestion("Initial solution", "Quasi-1D solution", "A uniform start forces the whole nozzle flow "
                              "to develop from nothing, with violent transients at the throat.", "input",
                              {"initialisation": "Quasi-1D solution"}))
    p_back = params.get("p_back")
    if p_back is not None and "p0" in params and p_back >= params["p0"]:
        out.append(Suggestion("Boundary conditions", "back pressure below p0",
                              "The back pressure is not below the total pressure: no flow can go through the nozzle "
                              "(it would run backwards). Check the outlet and inlet values in the boundary table.",
                              "advice"))
    where = info.get("diverged_at")
    if where is not None and hasattr(case, "geometry") and "p0" in params:
        try:
            profile = case.geometry(params)
            near = abs(where[0] - profile.x_throat) < 0.1 * profile.length
        except (ValueError, AttributeError):
            near = False
        if near and params.get("mesh_type") == "Structured":
            out.append(Suggestion("Throat refinement", "clustering Strong", "The solution broke down near the throat, "
                                  "where the flow turns fastest: smaller cells there resolve the expansion.", "input",
                                  {"throat_clustering": True, "clustering_strength": "Strong"}))
        elif near:
            out.append(Suggestion("Throat refinement", "edge refinement on", "The solution broke down near the throat; "
                                  "smaller cells at the throat and corners resolve the expansion.", "input",
                                  {"edge_refinement": True}))
    if where is not None:
        out.append(Suggestion("Where it failed", f"x = {length_text(abs(where[0]))}{' (negative)' if where[0] < 0 else ''}, "
                              f"y = {length_text(abs(where[1]))}", "The first cell with a negative density or pressure. "
                              "Look at the mesh there (Mesh step: aspect ratio, skewness) and at the nearest boundary.",
                              "advice"))
    return out


RULES.append(first_layer)

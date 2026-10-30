# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""From a template's inputs to a finished Euler run: shared inputs, boundary conditions, monitors, Result.

Templates with  euler_solver = true  in their schema.toml get the inputs of solver_parameters() (the
Numerics group and the boundary-condition table) added automatically, so the numerics look the same in
every template and are written only here. A template's case.py then only says what is special about it:

    nozzle_problem(...)    internal flow (nozzle, duct): mass flows, thrust two ways, Isp, Cf, Cd
    external_problem(...)  a body in a free stream: Cl, Cd, Cm in body and wind axes, Cp along the wall

and calls solve(problem, params, mesh, progress, restart). The boundary condition of each patch is the
case's default for its kind (inlet, outlet, wall, ...) unless the user changed it in the Setup table.
"""

import contextvars
import math
import os
from dataclasses import dataclass, field

import numpy as np

from aeroflowsim import gasdynamics as gd
from aeroflowsim.euler import forces
from aeroflowsim.euler.boundary import BC_TYPES, DEFAULT_FOR_KIND, BoundaryCondition, boundary_problems
from aeroflowsim.euler.gradients import METHODS as GRADIENT_METHODS
from aeroflowsim.euler.initial import QUASI_1D, RESTART, UNIFORM, quasi1d_state, restart_state
from aeroflowsim.euler.limiters import LIMITERS
from aeroflowsim.euler.solver import CONVERGED, DIVERGED, LUSGS, TIME_SCHEMES, Continuation, EulerSolver, Numerics
from aeroflowsim.euler.state import (entropy, mach_number, primitive_to_conserved, state_from_mach, temperature,
                                     total_pressure, total_temperature, uniform_state)
from aeroflowsim.geometry import WallProfile
from aeroflowsim.parameters import Parameter, clean_value
from aeroflowsim.results import Field, Result

SECOND_ORDER, FIRST_ORDER = "Second order (MUSCL)", "First order"
# Every monitor a template may report: name -> (label, SI unit). The GUI uses this table for its live plots.
MONITOR_LABELS = {
    "thrust": ("Thrust (vacuum), exit plane", "N"), "thrust_wall": ("Thrust (vacuum), wall + inlet", "N"),
    "mdot_in": ("Mass flow in", "kg/s"), "mdot_out": ("Mass flow out", "kg/s"),
    "Cd": ("Drag coefficient Cd", "-"), "Cl": ("Lift coefficient Cl", "-"), "Cm": ("Moment coefficient Cm", "-"),
}
EQUATIONS = ("mass", "x-momentum", "y-momentum", "energy")
G0 = forces.G0


def _number(key, label, unit, default, lo, hi, help, kind="float"):
    return Parameter(key, label, unit, default, lo, hi, help, type=kind, group="Numerics", step="setup")


def _choice(key, label, options, default, help):
    return Parameter(key, label, "", default, help=help, type="choice", options=tuple(options), group="Numerics",
                     step="setup")


# The Numerics default. AEROFLOWSIM_TIME_SCHEME overrides it (developer knob: run the validation with another scheme).
DEFAULT_TIME_SCHEME = os.environ.get("AEROFLOWSIM_TIME_SCHEME", LUSGS)   # LU-SGS since Prompt 8-2 (validated)


def solver_parameters(overrides=None) -> list:
    """The inputs every Euler template gets (Numerics group + boundary-condition table).

    overrides: {key: default} from the template's [case] solver_defaults.
    """
    inputs = [
        Parameter("boundaries", "Boundary conditions", "", {}, help="The condition on every named boundary of the "
                  "mesh. Each boundary starts from the default for its kind (inlet, outlet, wall, ...); "
                  "change the type or its values in the table.", type="boundaries", group="Boundary conditions",
                  step="setup"),
        _number("cfl", "CFL number", "-", 0.8, 0.01, 5.0, "Courant number: the time step as a fraction of the "
                "largest stable one. Lower it (0.3) if a run diverges; the solver halves it by itself at most "
                "4 times."),
        _choice("order", "Order of accuracy", (SECOND_ORDER, FIRST_ORDER), SECOND_ORDER,
                "Second order (MUSCL reconstruction with a limiter) for results; first order is very robust "
                "but smears shocks and expansions."),
        _number("first_order_iterations", "First-order iterations at the start", "-", 0, 0, 1_000_000,
                "Run this many first-order iterations before switching to second order (a robust start for "
                "strong shocks).", "int"),
        _choice("limiter", "Limiter", LIMITERS, LIMITERS[0], "Venkatakrishnan: smooth, converges well (default). "
                "Barth-Jespersen: strict, may stall the residual. None: no limiting (smooth flows only; "
                "oscillates at shocks)."),
        _number("venkat_k", "Venkatakrishnan K", "-", 5.0, 0.0, 100.0, "Larger K = less limiting in smooth "
                "regions (0 = as strict as Barth-Jespersen).", ),
        _number("freeze_limiter", "Freeze the limiter after a drop of", "orders", 4.0, 0.0, 15.0,
                "Keep the limiter fixed once the residual has dropped this many orders of magnitude, so it "
                "cannot stall the convergence. 0 = never freeze."),
        _choice("gradient", "Gradients", GRADIENT_METHODS, GRADIENT_METHODS[0], "Weighted least squares (exact "
                "for linear fields on any cell) or Green-Gauss."),
        _choice("time_scheme", "Time stepping", TIME_SCHEMES, DEFAULT_TIME_SCHEME, "Implicit LU-SGS: large time "
                "steps (the CFL number grows from the value above up to 100 while the residual falls), several "
                "times fewer iterations, for steady flows. SSP-RK3: explicit, robust, the reference. Jameson: "
                "explicit four-stage (a larger CFL number than SSP-RK3)."),
        _number("max_iter", "Maximum iterations", "-", 20000, 1, 10_000_000, "The run stops at this iteration "
                "number if it has not converged, counted over the whole run (a continued run carries on numbering: "
                "raise it to go further).", "int"),
        _number("tol", "Residual tolerance", "-", 1e-6, 1e-15, 1.0, "Converged when the normalised residual is "
                "below this (1e-6 = six orders of magnitude) AND the monitors have settled."),
        _number("monitor_tol", "Monitor tolerance", "-", 1e-4, 1e-12, 1.0, "The monitors (thrust, mass flow, "
                "Cd, ...) have settled when they change less than this fraction over the monitor window."),
        _number("monitor_window", "Monitor window", "-", 500, 2, 1_000_000, "Number of iterations over which the "
                "monitors must have settled.", "int"),
        Parameter("carbuncle_fix", "Carbuncle fix (HLLE near strong shocks)", "", True, help="Blend the flux "
                  "towards the more dissipative HLLE only near strong shocks, which prevents the 'carbuncle' "
                  "shock instability.", type="bool", group="Numerics", step="setup"),
    ]
    for key, value in (overrides or {}).items():
        p = next((q for q in inputs if q.name == key), None)
        if p is None:
            raise ValueError(f"solver_defaults: '{key}' is not an Euler solver input.")
        p.default = clean_value(p, value)
    return inputs


def numerics(params, steady=True) -> Numerics:
    """The Numerics of the template inputs."""
    return Numerics(cfl=params["cfl"], order=2 if params["order"] == SECOND_ORDER else 1,
                    gradient=params["gradient"], limiter=params["limiter"], venkat_k=params["venkat_k"],
                    freeze_limiter_orders=params["freeze_limiter"],
                    first_order_iterations=params["first_order_iterations"], time_scheme=params["time_scheme"],
                    local_time_stepping=steady, max_iterations=params["max_iter"],
                    residual_drop=-math.log10(params["tol"]), monitor_tolerance=params["monitor_tol"],
                    monitor_window=params["monitor_window"], carbuncle_fix=params["carbuncle_fix"])


# ---- boundary conditions ------------------------------------------------------------------------------

def conditions(params, mesh, defaults) -> dict:
    """{patch name: BoundaryCondition}: the user's entry from the table, else the default for its kind.

    defaults: {patch kind: BoundaryCondition} of the template (e.g. inlet -> total-pressure inlet with the
    template's p0 and T0); kinds it does not list get DEFAULT_FOR_KIND with that type's default values.
    Raises ValueError (in plain words) if a patch has no valid condition.
    """
    table = params.get("boundaries") or {}
    out = {}
    for p in mesh.patches:
        if p.name in table:
            out[p.name] = BoundaryCondition.from_dict(table[p.name])
        elif p.type in defaults:
            out[p.name] = defaults[p.type]
        else:
            out[p.name] = BoundaryCondition(DEFAULT_FOR_KIND[p.type])
    names = [p.name for p in mesh.patches]
    problems = boundary_problems(out, names)
    problems += [f"There is a boundary condition for '{name}', but the mesh has no such boundary (the mesh has: "
                 f"{', '.join(names)})." for name in table if name not in names]
    if problems:
        raise ValueError("Boundary conditions: " + " ".join(problems))
    return out


def table_rows(params, mesh, defaults) -> list:
    """[(patch name, patch kind, BoundaryCondition, changed by the user)] for the Setup table."""
    table = params.get("boundaries") or {}
    effective = conditions({"boundaries": {}}, mesh, defaults)
    rows = []
    for p in mesh.patches:
        bc = BoundaryCondition.from_dict(table[p.name]) if p.name in table else effective[p.name]
        rows.append((p.name, p.type, bc, p.name in table))
    return rows


# ---- problems -----------------------------------------------------------------------------------------

@dataclass
class Problem:
    """What a template hands to solve(): gas, conditions, initial state and how to measure the run."""

    kind: str                       # "nozzle" or "external"
    gas: object
    conditions: dict
    W0: np.ndarray
    L_ref: float                    # [m] (limiter eps, Cm)
    scales: tuple                   # reference size of rho, u, v, p
    initialisation: str = UNIFORM
    monitor: object = None          # function(solver, W) -> {name: value}
    monitor_labels: dict = field(default_factory=dict)   # name -> (label, unit)
    converge_on: tuple = ()
    monitor_scales: dict = field(default_factory=dict)
    finish: object = None           # function(solver, W, out) -> key_numbers dict
    series: object = None           # function(solver, W) -> {name: array} (e.g. wall Cp)
    continuation: object = None     # Continuation of the previous result this run carries on from, or None


def mesh_wall_profile(mesh, wall_names):
    """The wall radius r(x) of an axisymmetric internal flow, from the nodes of its wall patches.

    Only wall faces with the gas below them (outward normal pointing up, n_y > 0) count, so the outer surface
    of a nozzle lip inside a plume region is not taken for the nozzle wall.
    """
    nodes = []
    for p in mesh.patches:
        if p.name in wall_names:
            faces = np.arange(p.start, p.start + p.count)
            faces = faces[mesh.face_normals[faces, 1] > 0.0]
            f = mesh.face_nodes[faces]
            nodes.append(f[f >= 0])
    if not nodes:
        raise ValueError("The mesh has no wall: the nozzle profile (for the quasi-1D start and the throat "
                         "area) cannot be found.")
    xy = mesh.nodes[np.unique(np.concatenate(nodes)), :2]
    x, inverse = np.unique(np.round(xy[:, 0], 12), return_inverse=True)
    r = np.zeros(len(x))
    np.maximum.at(r, inverse, xy[:, 1])
    return WallProfile(x, r)


CONTINUED = "Continued from the previous result"   # Problem.initialisation of a continued run
INTERPOLATED = "Interpolated from the result on the previous mesh"

# Extras of a project run that are not template inputs (set by aeroflowsim.engine.run_case for the duration of one
# run): {"report_definitions": [dicts], "surfaces": [dicts], "init_patches": [dicts],
#        "interpolate": {"centres": (C_old, 2) array, "W": (4, C_old) array} or None}
RUN_EXTRAS = contextvars.ContextVar("aeroflowsim_run_extras", default=None)


def _extras() -> dict:
    return RUN_EXTRAS.get() or {}


def apply_patches(W, mesh, gas, patches):
    """Patch (initialisation) regions on top of a fresh initial state (Fluent's "Patch"), in the given order.

    patches: [{"region": {box / circle / polygon, as aeroflowsim.post.integrals.region_cells}, "values": {"p": Pa,
    "T": K, "u": m/s, "v": m/s}}]; cells whose centroid is inside get the given values (missing ones keep theirs;
    density follows from p and T with the gas constant). Returns (W, number of cells patched)."""
    from matplotlib.path import Path as MplPath
    W = W.copy()
    c = mesh.cell_centres[:, :2]
    total = 0
    for patch in patches or []:
        region = patch.get("region") or {}
        kind = region.get("type")
        if kind == "box":
            lo, hi = np.asarray(region["min"], float), np.asarray(region["max"], float)
            inside = np.all((c >= np.minimum(lo, hi)) & (c <= np.maximum(lo, hi)), axis=1)
        elif kind == "circle":
            inside = np.linalg.norm(c - np.asarray(region["centre"], float), axis=1) <= float(region["radius"])
        elif kind == "polygon":
            inside = MplPath(np.asarray(region["points"], float)).contains_points(c)
        else:
            raise ValueError(f"Patch region type '{kind}' is not known; use box, circle or polygon.")
        values = patch.get("values") or {}
        T_old = temperature(W, gas)
        if "p" in values:
            W[-1, inside] = float(values["p"])
        if "u" in values:
            W[1, inside] = float(values["u"])
        if "v" in values:
            W[2, inside] = float(values["v"])
        T = np.where(inside, float(values["T"]) if "T" in values else T_old, T_old)
        W[0, inside] = W[-1, inside] / (gas.R * T[inside])
        total += int(np.count_nonzero(inside))
    return W, total


def _start(restart, mesh, fresh, init, gas=None):
    """(initial state W0, how it was made): the previous result when there is one (the run continues); else the
    previous solution interpolated onto this new mesh when the project asks for it; else the template's fresh start
    (initialisation input: uniform or quasi-1D) with the project's patch regions on top."""
    if restart is not None:
        return restart_state(restart, mesh), CONTINUED
    extras = _extras()
    old = extras.get("interpolate")
    if old is not None:
        from aeroflowsim.post.sampling import interpolate_cells
        return interpolate_cells(old["centres"], old["W"], mesh.cell_centres[:, :2]), INTERPOLATED
    if init == RESTART:                          # an old project that still asks for "Previous result"
        raise ValueError("There is no previous result on this mesh to continue: run once first (the run starts from "
                         "the Initial solution, uniform or quasi-1D).")
    W0 = fresh()
    patches = extras.get("init_patches")
    if patches and gas is not None:
        W0, n = apply_patches(W0, mesh, gas, patches)
        if n:
            init = f"{init} + {len(patches)} patch region(s) ({n:,} cells)"
    return W0, init


def interpolated_norm(mesh):
    """A Continuation holding only the residual normalisation for a start interpolated from another mesh, or None.

    The residual is dU/dt per unit volume; for the same flow error it grows like 1/h, so the old run's normalisation
    is scaled by h_old / h_new = sqrt(C_new / C_old) (same domain). Without this, a good interpolated start would
    be normalised by its own (already small) first residuals and have to drop the full number of orders again."""
    old = _extras().get("interpolate")
    if not old or old.get("norm") is None:
        return None
    scale = math.sqrt(mesh.n_cells / max(len(old["centres"]), 1))
    return Continuation(iterations=0, residuals=np.zeros((0, len(old["norm"]))), monitors={},
                        norm=np.asarray(old["norm"], dtype=float) * scale)


def continuation_of(restart):
    """The Continuation of a previous result (restart dict of aeroflowsim.result_io.continuation_data), or None
    when there is none or it holds fields only (then only the flow is reused, numbering starts again)."""
    if not isinstance(restart, dict) or "series" not in restart:
        return None
    series, info = restart["series"], restart.get("info") or {}
    names = [f"residual_{e}" for e in info.get("equations", EQUATIONS)]
    if not all(n in series for n in names):
        return None
    residuals = np.column_stack([np.asarray(series[n], dtype=float) for n in names])
    monitors = {k[len("monitor_"):]: np.asarray(v, dtype=float) for k, v in series.items() if k.startswith("monitor_")}
    norm = info.get("residual_norm")
    return Continuation(iterations=len(residuals), residuals=residuals, monitors=monitors,
                        norm=None if norm is None else np.asarray(norm, dtype=float),
                        limiter=series.get("limiter_frozen"), limiter_frozen_at=info.get("limiter_frozen_at"),
                        cfl=info.get("cfl_final"))


def _inlet_total_state(bcs, params):
    """(p0 [Pa], T0 [K]) of the first total-pressure inlet, else of the template inputs."""
    for bc in bcs.values():
        if bc.type == "total_pressure_inlet":
            return bc.values["p0"], bc.values["T0"]
    return params["p0"], params["T0"]


def nozzle_problem(params, mesh, gas, defaults, restart=None) -> Problem:
    """Internal (nozzle) flow: total-pressure inlet, pressure outlet, walls, axis.

    params needs p0, T0, p_back and initialisation. defaults: {kind: BoundaryCondition}.
    """
    bcs = conditions(params, mesh, defaults)
    inlets = forces.patch_names_of(bcs, "total_pressure_inlet", "mass_flow_inlet", "supersonic_inlet")
    outlets = forces.patch_names_of(bcs, "pressure_outlet", "supersonic_outlet")
    walls = forces.patch_names_of(bcs, "slip_wall")
    if not inlets or not outlets:
        raise ValueError("A nozzle needs at least one inlet and one outlet boundary condition.")
    p0, T0 = _inlet_total_state(bcs, params)
    p_back = next((bc.values["p"] for bc in bcs.values() if bc.type == "pressure_outlet"), params["p_back"])
    profile = mesh_wall_profile(mesh, walls)
    r_t = float(profile.r.min())                                       # throat radius [m]
    A_t = math.pi * r_t**2 if mesh.axisymmetric else r_t * 1.0         # planar: half height x 1 m (half domain)
    init = params.get("initialisation", QUASI_1D)

    def fresh():
        if init == QUASI_1D:
            return quasi1d_state(mesh, profile, gas, p0, T0)
        T = 0.95 * T0
        return uniform_state(mesh.n_cells, p0 / (gas.R * T) * 0.9, (0.1 * float(gas.sound_speed(T)), 0.0), 0.9 * p0)

    W0, init = _start(restart, mesh, fresh, init, gas)
    rho0 = p0 / (gas.R * T0)
    c0 = float(gas.sound_speed(T0))
    g = float(gas.gamma(T0))
    mdot_1d = gd.choked_mass_flow(p0, T0, A_t, g, gas.R)               # [kg/s]
    labels = {k: MONITOR_LABELS[k] for k in ("thrust", "thrust_wall", "mdot_in", "mdot_out")}

    def monitor(solver, W):
        k = forces.nozzle_numbers(solver, inlets, outlets, walls)
        return {"thrust": k["thrust_exit"], "thrust_wall": k["thrust_wall"], "mdot_in": k["mdot_in"],
                "mdot_out": k["mdot_out"]}

    def finish(solver, W, out):
        k = forces.nozzle_numbers(solver, inlets, outlets, walls)
        mdot = k["mdot_out"]
        F_vac, F_wall = k["thrust_exit"], k["thrust_wall"]
        exit_area = abs(k["exit_area_x"])
        # Exit-plane averages: Mach number weighted by mass flux, pressure by area
        local = np.concatenate([loc for name, _bc, loc, _info in solver.patches if name in outlets])
        mass_w = solver.stage0_boundary_flux[0, local]                       # mass flow per face
        cells = solver.geom.boundary_owner[local]
        areas = solver.geom.flux_areas[solver.geom.n_interior + local]
        M = mach_number(W, gas)
        M_exit = float(np.sum(mass_w * M[cells]) / np.sum(mass_w)) if np.sum(mass_w) > 0 else float("nan")
        p_exit = float(np.sum(areas * W[-1, cells]) / np.sum(areas))
        p0_cells = total_pressure(W, gas)[cells]
        p0_exit = float(np.sum(mass_w * p0_cells) / np.sum(mass_w)) if np.sum(mass_w) > 0 else float("nan")
        isp_1d = _ideal_isp(profile, mesh.axisymmetric, gas, p0, T0)
        numbers = {
            "mdot": (mdot, "kg/s"), "mdot_inlet": (k["mdot_in"], "kg/s"), "mdot_exit": (mdot, "kg/s"),
            "mdot_1D": (mdot_1d, "kg/s"), "discharge_coefficient": (mdot / mdot_1d, "-"),
            "M_exit": (M_exit, "-"), "p_exit": (p_exit, "Pa"), "p0_exit": (p0_exit, "Pa"),
            "F_vacuum": (F_vac, "N"), "F_vacuum_wall": (F_wall, "N"),
            "thrust_difference": (100.0 * abs(F_vac - F_wall) / abs(F_vac) if F_vac else 0.0, "%"),
            "F_at_p_back": (F_vac - p_back * exit_area, "N"),
            "Isp_vacuum": (F_vac / (mdot * G0) if mdot > 0 else 0.0, "s"),
            "Isp_vacuum_wall": (F_wall / (mdot * G0) if mdot > 0 else 0.0, "s"),
            "Cf_vacuum": (F_vac / (p0 * A_t), "-"),
            "Isp_quasi1D": (isp_1d, "s"),
            "Isp_2D_over_quasi1D": (F_vac / (mdot * G0) / isp_1d if mdot > 0 and isp_1d else 0.0, "-"),
            "A_throat": (A_t, "m²"),
        }
        return numbers

    def series(solver, W):
        x, p = forces.wall_pressure(solver, walls)
        return {"wall_x": x[:, 0], "wall_y": x[:, 1], "wall_p": p, "wall_p_over_p0": p / p0}

    return Problem("nozzle", gas, bcs, W0, L_ref=2.0 * r_t, scales=(rho0, c0, c0, p0), initialisation=init,
                   monitor=monitor, monitor_labels=labels, converge_on=("thrust", "mdot_out"),
                   monitor_scales={}, finish=finish, series=series, continuation=continuation_of(restart) or interpolated_norm(mesh))


def _ideal_isp(profile, axisymmetric, gas, p0, T0):
    """Vacuum Isp of the ideal (isentropic quasi-1D) nozzle with this profile's exit and throat [s]."""
    g = float(gas.gamma(T0))
    if axisymmetric:
        ratio = (profile.r[-1] / profile.r.min()) ** 2
    else:
        ratio = profile.r[-1] / profile.r.min()
    if ratio <= 1.0:
        return 0.0
    M_e = gd.mach_from_area_ratio(ratio, g, True)
    T_e = T0 / gd.t0_over_t(M_e, g)
    p_e = p0 / gd.p0_over_p(M_e, g)
    u_e = M_e * float(gas.sound_speed(T_e))
    A_t = 1.0
    mdot = gd.choked_mass_flow(p0, T0, A_t, g, gas.R)
    return (mdot * u_e + p_e * A_t * ratio) / (mdot * G0)


def external_problem(params, mesh, gas, defaults, A_ref, L_ref, x_ref, restart=None) -> Problem:
    """A body in a free stream: far field (or supersonic inlet/outlet) around slip walls.

    params needs mach, p_inf, T_inf, alpha and initialisation (Uniform). With restart (a previous result on this mesh)
    the run carries on from it.
    """
    bcs = conditions(params, mesh, defaults)
    walls = forces.patch_names_of(bcs, "slip_wall")
    if not walls:
        raise ValueError("A body in a free stream needs at least one slip-wall boundary (the body surface).")
    M, p_inf, T_inf, alpha = params["mach"], params["p_inf"], params["T_inf"], params["alpha"]
    direction = (math.cos(math.radians(alpha)), math.sin(math.radians(alpha)))
    rho, vel = state_from_mach(gas, M, p_inf, T_inf, direction)
    speed = float(np.linalg.norm(vel))
    q_inf = 0.5 * rho * speed**2                                        # dynamic pressure [Pa]
    W0, init = _start(restart, mesh, lambda: uniform_state(mesh.n_cells, rho, vel, p_inf),
                      params.get("initialisation", UNIFORM), gas)
    half = any(p.type == "symmetry" for p in mesh.patches) and not mesh.axisymmetric
    mirror = 2.0 if half else 1.0
    c = float(gas.sound_speed(T_inf))
    labels = {k: MONITOR_LABELS[k] for k in ("Cd", "Cl", "Cm")}

    def coefficients(solver):
        return forces.body_forces(solver, walls, p_inf, q_inf, alpha, A_ref, L_ref, x_ref, mirror)

    def monitor(solver, W):
        f = coefficients(solver)
        return {"Cd": f["Cd"], "Cl": f["Cl"], "Cm": f["Cm"]}

    def finish(solver, W, out):
        f = coefficients(solver)
        force_unit = "N" if mesh.axisymmetric else "N/m"
        return {"Cd": (f["Cd"], "-"), "Cl": (f["Cl"], "-"), "Cm": (f["Cm"], "-"),
                "drag": (f["D"], force_unit), "lift": (f["L"], force_unit),
                "Fx": (f["Fx"], force_unit), "Fy": (f["Fy"], force_unit),
                "q_inf": (q_inf, "Pa"), "A_ref": (A_ref, "m²"), "L_ref": (L_ref, "m")}

    def series(solver, W):
        x, p = forces.wall_pressure(solver, walls)
        return {"wall_x": x[:, 0], "wall_y": x[:, 1], "wall_p": p, "wall_Cp": (p - p_inf) / q_inf}

    return Problem("external", gas, bcs, W0, L_ref=L_ref, scales=(rho, max(speed, c), max(speed, c), p_inf),
                   initialisation=init, monitor=monitor, monitor_labels=labels,
                   converge_on=("Cd", "Cl"), monitor_scales={"Cd": 0.01, "Cl": 0.01, "Cm": 0.01},
                   finish=finish, series=series, continuation=continuation_of(restart) or interpolated_norm(mesh))


# ---- solve ----------------------------------------------------------------------------------------------

def mesh_signature(mesh) -> str:
    """A short fingerprint of the mesh's nodes and cells: a run may only carry on from a result of the SAME mesh
    (a new mesh with the same number of cells is still a different mesh)."""
    import hashlib
    digest = hashlib.sha256()
    for array in (mesh.nodes, mesh.cell_nodes):
        digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()[:16]


def flow_fields(W, gas) -> dict:
    """The Result fields of a primitive state (all per cell, SI)."""
    fields = {"rho": Field(W[0].copy(), "kg/m³", "Density"), "u": Field(W[1].copy(), "m/s", "Velocity x"),
              "v": Field(W[2].copy(), "m/s", "Velocity y (radial)"), "p": Field(W[-1].copy(), "Pa", "Pressure"),
              "T": Field(temperature(W, gas), "K", "Temperature"), "M": Field(mach_number(W, gas), "-", "Mach number"),
              "p0": Field(total_pressure(W, gas), "Pa", "Total pressure"),
              "T0": Field(total_temperature(W, gas), "K", "Total temperature"),
              "s": Field(entropy(W, gas), "J/(kg K)", "Entropy")}
    return fields


def solve(problem, params, mesh, progress=None) -> Result:
    """Run the solver for a Problem and return the Result (fields, residuals, key numbers, history)."""
    previous = problem.continuation
    if previous is not None and previous.iterations >= params["max_iter"]:
        raise ValueError(f"The run already has {previous.iterations:,} iterations and Maximum iterations is "
                         f"{params['max_iter']:,} (counted over the whole run): raise Maximum iterations to continue "
                         "it, or start from scratch.")
    solver = EulerSolver(mesh, problem.gas, problem.conditions, numerics(params), L_ref=problem.L_ref,
                         scales=problem.scales)

    def forward(it, res, info):
        if progress is not None:
            return progress(it, res, info)      # True = the user pressed Stop (keep the flow as it is)
        return False

    monitor, converge_on, rules = problem.monitor, tuple(problem.converge_on), {}
    labels = dict(problem.monitor_labels)
    user = [d for d in (_extras().get("report_definitions") or []) if d.get("monitor")]
    if user:                                     # the project's report definitions marked "monitor"
        from aeroflowsim.post.definitions import MonitorEvaluator, definitions_from
        from aeroflowsim.post.surfaces import surfaces_from
        defs = definitions_from(user)
        evaluator = MonitorEvaluator(mesh, problem.gas, problem.conditions, params, defs,
                                     surfaces_from(_extras().get("surfaces")))
        evaluator.sol.info["kind"] = problem.kind

        def monitor(solver_, W_, base=problem.monitor):
            values = base(solver_, W_) if base is not None else {}
            values.update(evaluator(solver_, W_))
            return values
        for d in defs:
            labels["user_" + d.name] = (d.name, "")
            if d.converge:
                converge_on += ("user_" + d.name,)
                rules["user_" + d.name] = (float(d.tolerance), int(d.window))
    out = solver.solve(problem.W0, forward, monitor, problem.monitor_scales, converge_on,
                       problem.continuation, monitor_rules=rules)
    W = out.W
    # One more residual evaluation of the final state, so the boundary fluxes (forces, mass flows) belong to it
    solver.residual(primitive_to_conserved(W, problem.gas), params["order"] == SECOND_ORDER, W)
    solver.stage0_boundary_flux = solver.boundary_flux
    numbers = problem.finish(solver, W, out) if problem.finish else {}
    numbers.update({"wall_time": (out.wall_time_s, "s"), "positivity_events": (float(out.positivity_events), "-"),
                    "cfl_final": (out.cfl_final, "-")})
    series = {f"residual_{name}": out.residuals[:, i] for i, name in enumerate(EQUATIONS[:W.shape[0]])}
    series.update({f"monitor_{k}": v for k, v in out.monitors.items()})
    if problem.series:
        series.update(problem.series(solver, W))
    if out.limiter is not None:                  # a frozen limiter stays frozen when the run is continued
        series["limiter_frozen"] = out.limiter
    series["boundary_flux"] = solver.boundary_flux.copy()   # flux x area of every boundary face (post-processing)
    series["cell_centres"] = mesh.cell_centres[:, :2].copy()  # [m]: lets a later run interpolate onto a new mesh
    info = {"status": out.status, "first_iteration": out.first_iteration, "mesh_signature": mesh_signature(mesh),
            "continued_from": None if previous is None else previous.iterations,
            "residual_norm": None if out.norm is None else [float(v) for v in out.norm], "message": out.message, "kind": problem.kind, "axisymmetric": mesh.axisymmetric,
            "positivity_events": int(out.positivity_events), "positivity_last": int(out.positivity_last),
            "cfl_reductions": int(out.cfl_reductions), "cfl_final": float(out.cfl_final),
            "wall_time_s": float(out.wall_time_s), "limiter_frozen_at": out.limiter_frozen_at,
            "backend": out.backend, "threads": int(out.threads), "backend_note": solver.backend_note,
            "diverged_at": None if out.diverged_at is None else list(out.diverged_at),
            "L_ref": float(problem.L_ref), "scales": [float(v) for v in problem.scales],
            "initialisation": problem.initialisation, "equations": list(EQUATIONS[:W.shape[0]]),
            "monitor_labels": {k: list(v) for k, v in labels.items()},
            "converge_on": list(converge_on), "monitor_rules": {k: list(v) for k, v in rules.items()}, "monitor_tol": params["monitor_tol"],
            "monitor_window": params["monitor_window"], "tol": params["tol"], "cfl": params["cfl"],
            "boundaries": {name: bc.to_dict() for name, bc in problem.conditions.items()},
            "gamma": float(problem.gas.gamma(float(np.median(temperature(W, problem.gas)))))}
    residual_level = out.residuals.max(axis=1) if len(out.residuals) else np.zeros(0)
    return Result(fields=flow_fields(W, problem.gas), residuals=residual_level.tolist(), key_numbers=numbers,
                  iterations=out.iterations, converged=out.status == CONVERGED, series=series, info=info)



__all__ = ["solver_parameters", "numerics", "conditions", "table_rows", "nozzle_problem", "external_problem",
           "solve", "flow_fields", "mesh_wall_profile", "Problem", "DIVERGED", "BC_TYPES"]

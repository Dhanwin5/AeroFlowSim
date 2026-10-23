# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Quasi-1D nozzle: steady inviscid flow of a gas (default N2) through a converging-diverging nozzle.

Numerics: finite volumes for the quasi-1D Euler equations (aeroflowsim/quasi1d.py) with the HLLC flux,
MUSCL/minmod reconstruction and SSP-RK2 of aeroflowsim/euler1d.py, marched to steady state with local
time stepping. Reservoir inlet (p0, T0), back pressure at the exit. Compared with isentropic
area-Mach theory and, when a shock stands in the nozzle, normal-shock relations
(aeroflowsim/gasdynamics.py). Geometry from aeroflowsim/geometry.py (conical or CSV). The gas comes from
the gas library (aeroflowsim/gases/): a calorically perfect gas, so this case needs its gamma and R only.
See README.md.
"""

import math
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

from aeroflowsim import gasdynamics as gd
from aeroflowsim.gases import gas_model
from aeroflowsim.euler1d import (conserved_to_primitive, face_fluxes, muscl_reconstruct, primitive_to_conserved,
                          sound_speed, ssp_rk2_step)
from aeroflowsim.geometry import conical_nozzle, profile_summary, read_profile_csv
from aeroflowsim.mesh import Mesh1D
from aeroflowsim.quasi1d import local_time_steps, nozzle_boundary, quasi1d_rhs
from aeroflowsim.results import Field, Result

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent   # relative CSV paths start here
PARAMETRIC = "Parametric (conical)"     # options of the geometry_source input (schema.toml)
CUSTOM_CSV = "Custom profile (CSV)"
DEG = math.pi / 180.0   # one degree [rad]
G0 = 9.80665            # standard gravity, used to define Isp [m/s²]


# ---- gas --------------------------------------------------------------------------------------

def gas(params):
    """The GasModel of the "gas" input (a relative custom-gas path is read from the project folder)."""
    return gas_model(params["gas"], base=PROJECT_DIR)


def _gamma_R(params):
    """gamma [-] and R [J/(kg K)] of the gas: the two numbers this inviscid 1D solver needs."""
    g = gas(params)
    return g.gamma_value, g.R


def reservoir_state(params):
    """Chamber (total) state checked by the gas validity checks: (p0 [Pa], T0 [K])."""
    return params["p0"], params["T0"]


# ---- geometry and mesh ------------------------------------------------------------------------

def geometry(params):
    """The nozzle wall as a WallProfile [m]; ValueError with a 'what to fix' message if invalid."""
    if params["geometry_source"] == CUSTOM_CSV:
        path = Path(params["profile_csv"])
        if not path.is_absolute():
            path = PROJECT_DIR / path
        return read_profile_csv(path)
    return conical_nozzle(params["d_inlet"], params["L_inlet"], params["half_angle_conv"] * DEG,
                          params["d_throat"], params["half_angle_div"] * DEG, params["d_exit"],
                          params["Rcu_ratio"], params["Rcd_ratio"])


def _graded_side(length, n, dx_first):
    """n cell widths summing to `length`, starting at dx_first and growing by a constant factor."""
    if n * dx_first >= length:                      # no room to grow: evenly spread cells
        return np.full(n, length / n)
    # The growth factor q solves dx_first (q^n - 1)/(q - 1) = length. Upper end of the search: the q
    # at which the LAST cell alone, dx_first q^(n-1), is already as long as the whole side - the
    # answer is always smaller. (A fixed upper end such as q = 10 overflows: 10^450 is no float.)
    q_max = (length / dx_first) ** (1.0 / (n - 1))
    growth = brentq(lambda q: dx_first * (q**n - 1.0) / (q - 1.0) - length, 1.0 + 1e-12, q_max)
    return dx_first * growth ** np.arange(n)


def build_mesh(params):
    """Cell faces with one face exactly at the throat; cells finest there, growing to both ends.

    A face at the throat makes the smallest face area exactly the throat area. Small cells around
    a sharp throat resolve the steep Mach rise there (M - 1 grows like the square root of the
    distance to a sharp throat). Local time stepping makes small cells cost nothing extra.
    """
    profile = geometry(params)
    x0, x_t, x_e = profile.x[0], profile.x_throat, profile.x[-1]   # [m]
    if not x0 < x_t < x_e:
        raise ValueError("The narrowest point of the profile must lie strictly between the inlet and "
                         "the exit, otherwise this is not a converging-diverging nozzle.")
    n = params["n_cells"]
    n_conv = min(max(round(n * (x_t - x0) / (x_e - x0)), 2), n - 2)   # cells before the throat
    dx_throat = (x_e - x0) / n / params["throat_refinement"]          # [m]
    conv = _graded_side(x_t - x0, n_conv, dx_throat)[::-1]             # widths, inlet -> throat
    div = _graded_side(x_e - x_t, n - n_conv, dx_throat)               # widths, throat -> exit
    x = np.concatenate([[x0], x0 + np.cumsum(conv)[:-1], [x_t], x_t + np.cumsum(div)[:-1], [x_e]])
    return Mesh1D(x=x)


def _throat_face(mesh, profile):
    """Index of the mesh face at the throat."""
    return int(np.argmin(np.abs(mesh.x - profile.x_throat)))


# ---- theory -----------------------------------------------------------------------------------

def theory(params, profile):
    """Exact quasi-1D solution data: regime, A* [m²], shock position and the downstream state.

    Returns a dict with: regime, A_star, and for a shock x_shock [m], M1 (upstream Mach),
    p02 (total pressure after the shock) [Pa]; for subsonic flow A_star is the virtual sonic area.
    """
    g, p0, pb = _gamma_R(params)[0], params["p0"], params["p_back"]
    A_t, A_e = math.pi * profile.r_throat**2, math.pi * profile.r[-1] ** 2   # [m²]
    info = gd.nozzle_flow_regime(p0, pb, A_e / A_t, g)
    info["A_star"] = A_t
    if info["regime"] == "subsonic":
        M_e = gd.mach_from_p0_over_p(p0 / pb, g) if pb > 0 else 0.0
        info["A_star"] = A_e / gd.area_ratio(M_e, g) if M_e > 0 else 0.0   # 0 = gas at rest
    elif info["regime"] == "shock in nozzle":
        A_s = info["area_shock"] * A_t
        info["x_shock"] = brentq(lambda x: profile.area_at(x) - A_s, profile.x_throat, profile.x[-1])
        info["M1"] = gd.mach_from_area_ratio(info["area_shock"], g, supersonic=True)
        info["p02"] = p0 * gd.normal_shock(info["M1"], g)["p02_p01"]
    return info


def derived(params):
    """Read-only design numbers shown under the inputs (ideal isentropic nozzle theory, no solver run).

    Design exit state: supersonic isentropic flow at A_exit/A_throat. Critical back pressures: above
    p_b1 the nozzle is not choked (subsonic everywhere); between p_b1 and p_b2 a normal shock stands
    inside the divergent part; below p_b2 the flow leaves the exit supersonic.
    """
    (g, R), p0, T0, pb = _gamma_R(params), params["p0"], params["T0"], params["p_back"]
    profile = geometry(params)
    A_t = math.pi * profile.r_throat**2                  # [m²]
    A_e = math.pi * profile.r[-1] ** 2                   # [m²]
    ratio = A_e / A_t                                    # [-]
    M_e = gd.mach_from_area_ratio(ratio, g, supersonic=True)
    p_e = p0 / gd.p0_over_p(M_e, g)                      # [Pa]
    T_e = T0 / gd.t0_over_t(M_e, g)                      # [K]
    u_e = M_e * math.sqrt(g * R * T_e)                   # [m/s]
    mdot = gd.choked_mass_flow(p0, T0, A_t, g, R)        # [kg/s]
    F_vac = mdot * u_e + p_e * A_e                       # [N]
    p_b1 = p0 / gd.p0_over_p(gd.mach_from_area_ratio(ratio, g, supersonic=False), g)   # [Pa]
    p_b2 = gd.exit_pressure_with_shock(p0, ratio, ratio, g)                             # [Pa]
    gas_used = gas(params)
    return {
        "Gas": (gas_used.name, ""),
        "Gas: ratio of specific heats gamma": (g, "-"),
        "Gas: specific gas constant R": (R, "J/(kg·K)"),
        "Throat area": (A_t, "m²"),
        "Exit area": (A_e, "m²"),
        "Area ratio A_exit/A_throat": (ratio, "-"),
        "Design exit Mach number": (M_e, "-"),
        "Design exit pressure": (p_e, "Pa"),
        "Design exit temperature": (T_e, "K"),
        "Choked mass flow": (mdot, "kg/s"),
        "Ideal vacuum thrust": (F_vac, "N"),
        "Ideal vacuum Isp": (F_vac / (mdot * G0), "s"),
        "Flow at this back pressure": (gd.nozzle_flow_regime(p0, pb, ratio, g)["regime"], ""),
        "Back pressure: choking limit p_b1": (p_b1, "Pa"),
        "Back pressure: shock at exit p_b2": (p_b2, "Pa"),
    }


def _isentropic_state(M, p0, T0, gamma, R):
    """Primitive states [rho, u, p] for Mach numbers M with total conditions p0 [Pa], T0 [K]."""
    T = T0 / gd.t0_over_t(M, gamma)      # [K]
    p = p0 / gd.p0_over_p(M, gamma)      # [Pa]
    return np.array([p / (R * T), M * np.sqrt(gamma * R * T), p])


def exact_state(params, profile, x, info, initial_guess=False):
    """Theory at positions x [m] as primitive states [rho, u, p].

    initial_guess=True gives the solver's start: the right isentropic branch everywhere, but with
    no shock - for a shock case the flow after the throat starts subsonic, so the outlet "hears"
    the back pressure and the shock forms and settles by itself.
    """
    (g, R), p0, T0 = _gamma_R(params), params["p0"], params["T0"]
    A = profile.area_at(x)
    if info["A_star"] == 0.0:                                       # back pressure = p0: gas at rest
        return _isentropic_state(np.zeros_like(x), p0, T0, g, R)
    regime = info["regime"]
    supersonic = x > profile.x_throat
    if regime == "subsonic" or (regime == "shock in nozzle" and initial_guess):
        supersonic = np.zeros_like(x, dtype=bool)
    M = np.array([gd.mach_from_area_ratio(max(a / info["A_star"], 1.0), g, s) for a, s in zip(A, supersonic)])
    W = _isentropic_state(M, p0, T0, g, R)
    if regime == "shock in nozzle" and not initial_guess:
        after = x > info["x_shock"]                                 # subsonic, lower total pressure
        A_star2 = info["A_star"] * p0 / info["p02"]                 # [m²]
        M2 = np.array([gd.mach_from_area_ratio(a / A_star2, g, False) for a in A[after]])
        W[:, after] = _isentropic_state(M2, info["p02"], T0, g, R)
    return W


# ---- solver -----------------------------------------------------------------------------------

def _fields(W, gamma, R):
    """Output fields at the cell centres from primitive states W = [rho, u, p]."""
    rho, u, p = W
    return {
        "M": Field(values=u / sound_speed(W, gamma), unit="-", label="Mach number"),
        "p": Field(values=p, unit="Pa", label="Pressure"),
        "T": Field(values=p / (rho * R), unit="K", label="Temperature"),
        "rho": Field(values=rho, unit="kg/m³", label="Density"),
        "u": Field(values=u, unit="m/s", label="Velocity"),
    }


def _shock_position(xc, M, x_throat):
    """Where the Mach number falls through 1 downstream of the throat [m] (nan if it does not)."""
    i = np.where((xc[:-1] > x_throat) & (M[:-1] > 1.0) & (M[1:] <= 1.0))[0]
    if len(i) == 0:
        return float("nan")
    i = i[0]
    return float(xc[i] + (1.0 - M[i]) * (xc[i + 1] - xc[i]) / (M[i + 1] - M[i]))


def run(params, mesh, progress):
    """March to steady state with local time stepping; progress(iteration, residual) every iteration."""
    g, R = _gamma_R(params)                       # [-], [J/(kg·K)]
    p0, T0, pb = params["p0"], params["T0"], params["p_back"]   # [Pa], [K], [Pa]
    if pb > p0:
        raise ValueError("The back pressure is higher than the chamber pressure: the gas would flow "
                         "backwards into the reservoir, which this case does not model.")
    profile = geometry(params)
    A = profile.area_at(mesh.x)                    # face areas [m²]
    dx = mesh.dx                                   # cell widths [m]
    volumes = 0.5 * (A[:-1] + A[1:]) * dx          # cell volumes [m³] (trapezoidal)
    info = theory(params, profile)

    W = exact_state(params, profile, mesh.xc, info, initial_guess=True)
    U = primitive_to_conserved(W, g)
    boundary = nozzle_boundary(p0, T0, pb, g, R)
    rhs = lambda V: quasi1d_rhs(V, A, volumes, g, boundary)

    residuals = []    # RMS of the density right-hand side, normalised by the first one [-]
    r0 = None
    converged = False
    iteration = 0
    while iteration < params["max_iter"]:
        U = ssp_rk2_step(U, local_time_steps(U, dx, g, params["cfl"]), rhs)
        iteration += 1
        W = conserved_to_primitive(U, g)
        if not (np.all(np.isfinite(W)) and W[0].min() > 0.0 and W[2].min() > 0.0):
            raise RuntimeError(f"Negative density or pressure at iteration {iteration}. "
                               "Try a smaller CFL number.")
        r = float(np.sqrt(np.mean(rhs(U)[0] ** 2)))   # [kg/(m³·s)]
        if r0 is None:
            r0 = r if r > 0.0 else 1.0                 # gas exactly at rest: residual 0 from the start
        residuals.append(r / r0)
        progress(iteration, residuals[-1])             # the GUI's Stop button raises an exception in here
        if residuals[-1] <= params["tol"]:
            converged = True
            break

    W = conserved_to_primitive(U, g)
    fields = _fields(W, g, R)
    return Result(fields=fields, residuals=residuals, iterations=iteration, converged=converged,
                  key_numbers=_key_numbers(params, mesh, profile, info, U, W, boundary),
                  shape=profile, shape_note="quasi-1D: varies along x only")


def _key_numbers(params, mesh, profile, info, U, W, boundary):
    """Performance and validation numbers {name: (value, unit)} from the converged solution."""
    (g, R), pb = _gamma_R(params), params["p_back"]
    A = profile.area_at(mesh.x)                              # face areas [m²]
    F = face_fluxes(U, g, boundary) * A                      # mass, momentum, energy through faces
    i_t = _throat_face(mesh, profile)
    xc, A_e = mesh.xc, A[-1]
    M = W[1] / sound_speed(W, g)
    # Exit-plane state: the MUSCL state just inside the exit face, i.e. exactly the state the
    # solver's exit flux (and so the thrust) is computed from. For a supersonic exit the ghost
    # cells copy the last cell, so this is the last cell's value; the steady balance of that cell
    # then makes it the exit-plane state (not the state at its centre).
    rho_e, u_e, p_e = muscl_reconstruct(boundary(W))[0][:, -1]
    c_e = math.sqrt(g * p_e / rho_e)                          # [m/s]
    mdot = F[0, -1]                                          # [kg/s]
    F_vac = F[1, -1]                                         # (rho u² + p) A_e = mdot u_e + p_e A_e [N]
    k = {
        "mdot": (mdot, "kg/s"),
        "mdot_inlet": (F[0, 0], "kg/s"),
        "mdot_throat": (F[0, i_t], "kg/s"),
        "mdot_exit": (F[0, -1], "kg/s"),
        "M_throat": (float(np.interp(mesh.x[i_t], xc, M)), "-"),   # between the two throat cells
        "M_exit": (u_e / c_e, "-"),
        "p_exit": (p_e, "Pa"),
        "T_exit": (p_e / (rho_e * R), "K"),
        "u_exit": (u_e, "m/s"),
        "F_vacuum": (F_vac, "N"),
        "Isp_vacuum": (F_vac / (mdot * G0) if mdot > 0 else 0.0, "s"),
        "F_at_p_back": (F_vac - pb * A_e, "N"),
    }
    if info["regime"] != "subsonic":
        k["mdot_theory"] = (gd.choked_mass_flow(params["p0"], params["T0"], info["A_star"], g, R), "kg/s")
    for name, value in profile_summary(profile).items():
        k[name] = value
    if info["regime"] == "shock in nozzle":
        k["x_shock"] = (_shock_position(xc, M, profile.x_throat), "m")
        k["x_shock_exact"] = (info["x_shock"], "m")
        k["M_before_shock_exact"] = (info["M1"], "-")
    return k


def reference(params, mesh):
    """Isentropic area-Mach solution at the cell centres (with the normal shock if there is one)."""
    profile = geometry(params)
    W = exact_state(params, profile, mesh.xc, theory(params, profile))
    return _fields(W, *_gamma_R(params))

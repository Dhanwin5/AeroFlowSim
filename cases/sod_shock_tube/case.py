"""Sod shock tube: unsteady 1D Euler equations (ideal gas) from a Riemann initial condition.

Numerics: finite volumes with HLLC flux, MUSCL/minmod reconstruction, SSP-RK2 time
stepping and transmissive ends (all in aeroflowsim/euler1d.py). Compared with the exact Riemann
solution (aeroflowsim/riemann_exact.py). See README.md.
"""

import numpy as np

from aeroflowsim.euler1d import (cfl_time_step, conserved_to_primitive, flux_divergence,
                          primitive_to_conserved, sound_speed, ssp_rk2_step)
from aeroflowsim.mesh import Mesh1D
from aeroflowsim.parameters import Parameter
from aeroflowsim.results import Field, Line, Result, SnapshotRecorder
from aeroflowsim.riemann_exact import exact_solution, wave_structure

NAME = "Sod shock tube"
DESCRIPTION = ("Unsteady 1D Euler equations from a diaphragm burst (Riemann problem); "
               "HLLC + MUSCL finite volumes compared with the exact Riemann solution.")


def parameters():
    """Inputs of this case (all SI). Defaults = the standard Sod problem."""
    return [
        Parameter("rho_L", "Left density", "kg/m³", 1.0, 1e-6, 1e4, "Initial density left of the diaphragm."),
        Parameter("u_L", "Left velocity", "m/s", 0.0, -1e4, 1e4, "Initial velocity left of the diaphragm."),
        Parameter("p_L", "Left pressure", "Pa", 1.0, 1e-6, 1e9, "Initial pressure left of the diaphragm."),
        Parameter("rho_R", "Right density", "kg/m³", 0.125, 1e-6, 1e4, "Initial density right of the diaphragm."),
        Parameter("u_R", "Right velocity", "m/s", 0.0, -1e4, 1e4, "Initial velocity right of the diaphragm."),
        Parameter("p_R", "Right pressure", "Pa", 0.1, 1e-6, 1e9, "Initial pressure right of the diaphragm."),
        Parameter("gamma", "Ratio of specific heats", "-", 1.4, 1.01, 3.0, "cp/cv of the (calorically perfect) gas."),
        Parameter("L", "Tube length", "m", 1.0, 1e-3, 1e3, "The tube runs from x = 0 to x = L."),
        Parameter("x0", "Diaphragm position", "m", 0.5, 0.0, 1e3, "Initial position of the diaphragm (0 < x0 < L)."),
        Parameter("t_end", "End time", "s", 0.2, 1e-9, 1e3,
                  "Simulated time. Results are only valid while waves have not reached the tube ends."),
        Parameter("n_cells", "Number of cells", "-", 400, 10, 20000, "Number of equal finite-volume cells."),
        Parameter("cfl", "CFL number", "-", 0.5, 0.05, 1.0,
                  "Time step = CFL x cell width / fastest wave speed. 0.5 is a safe choice."),
    ]


def build_mesh(params):
    """Uniform mesh. The nodes are the cell faces; the solution lives at the cell centres."""
    x_faces = np.linspace(0.0, params["L"], params["n_cells"] + 1)  # [m]
    return Mesh1D(x=x_faces)


def _left_right(params):
    """Initial left and right states as (rho [kg/m³], u [m/s], p [Pa])."""
    return ((params["rho_L"], params["u_L"], params["p_L"]),
            (params["rho_R"], params["u_R"], params["p_R"]))


def initial_state(params, mesh):
    """Primitive states [rho, u, p] in every cell at t = 0 (cells left of x0 get the left state)."""
    left, right = _left_right(params)
    is_left = mesh.xc < params["x0"]
    return np.array([np.where(is_left, left[k], right[k]) for k in range(3)])


def _fields(W, gamma):
    """Output fields at the cell centres from primitive states W = [rho, u, p]."""
    rho, u, p = W
    e = p / ((gamma - 1.0) * rho)                 # specific internal energy [J/kg]
    mach = np.abs(u) / sound_speed(W, gamma)      # [-]
    return {
        "rho": Field(values=rho, unit="kg/m³", label="Density"),
        "u": Field(values=u, unit="m/s", label="Velocity"),
        "p": Field(values=p, unit="Pa", label="Pressure"),
        "e": Field(values=e, unit="J/kg", label="Specific internal energy"),
        "M": Field(values=mach, unit="-", label="Mach number"),
    }


def _crossing(x, f, level, x_a, x_b):
    """First x in [x_a, x_b] where f crosses `level`, by linear interpolation (nan if none)."""
    idx = np.where((x >= x_a) & (x <= x_b))[0]
    for i, j in zip(idx[:-1], idx[1:]):
        if (f[i] - level) * (f[j] - level) <= 0.0 and f[i] != f[j]:
            return float(x[i] + (level - f[i]) * (x[j] - x[i]) / (f[j] - f[i]))
    return float("nan")


def wave_positions(params, mesh, rho, p):
    """Numerical and exact positions [m] of the contact and (if there is one) the right shock.

    Contact: where the density crosses halfway between rho*_L and rho*_R.
    Shock:   where the pressure crosses halfway between p* and p_R.
    Each is searched only in the region between its neighbouring waves (exact positions).
    Returns a dict with keys x_contact, x_contact_exact and, for a right shock,
    x_shock, x_shock_exact.
    """
    left, right = _left_right(params)
    w = wave_structure(left, right, params["gamma"])
    x0, t, L = params["x0"], params["t_end"], params["L"]
    x = mesh.xc

    x_left_wave = x0 + t * (w["S_L"] if w["left_wave"] == "shock" else w["S_tail_L"])
    x_right_wave = x0 + t * (w["S_R"] if w["right_wave"] == "shock" else w["S_tail_R"])
    x_contact_exact = x0 + t * w["u_star"]

    positions = {
        "x_contact": _crossing(x, rho, 0.5 * (w["rho_star_L"] + w["rho_star_R"]),
                               0.5 * (x_left_wave + x_contact_exact),
                               0.5 * (x_contact_exact + x_right_wave)),
        "x_contact_exact": x_contact_exact,
    }
    if w["right_wave"] == "shock":
        positions["x_shock"] = _crossing(x, p, 0.5 * (w["p_star"] + right[2]),
                                         0.5 * (x_contact_exact + x_right_wave), L)
        positions["x_shock_exact"] = x_right_wave
    return positions


def run(params, mesh, progress):
    """March the Euler equations in time from t = 0 to t_end; report progress every step."""
    gamma = params["gamma"]       # [-]
    t_end = params["t_end"]       # [s]
    dx = mesh.dx[0]               # cell width [m] (uniform mesh)
    if not 0.0 < params["x0"] < params["L"]:
        raise ValueError("The diaphragm position x0 must lie inside the tube (0 < x0 < L).")

    U = primitive_to_conserved(initial_state(params, mesh), gamma)
    rhs = lambda V: flux_divergence(V, dx, gamma)   # transmissive ends (the default)

    t = 0.0             # simulated time [s]
    step = 0            # number of time steps taken
    residuals = []      # RMS density change rate per step, normalised by the first one [-]
    r0 = None
    recorder = SnapshotRecorder(max_snapshots=200)   # fields over time, for the x-t diagram
    recorder.add(0, t, _fields(conserved_to_primitive(U, gamma), gamma))
    while t_end - t > 1e-12 * t_end:
        dt = min(cfl_time_step(U, dx, gamma, params["cfl"]), t_end - t)  # last step lands on t_end
        U_new = ssp_rk2_step(U, dt, rhs)
        W = conserved_to_primitive(U_new, gamma)
        if not (np.all(np.isfinite(W)) and W[0].min() > 0.0 and W[2].min() > 0.0):
            raise RuntimeError(f"Negative density or pressure at t = {t:.4g} s. "
                               "Try a smaller CFL number.")
        r = float(np.sqrt(np.mean((U_new[0] - U[0]) ** 2))) / dt   # [kg/(m³·s)]
        if r0 is None:
            r0 = r if r > 0.0 else 1.0
        U, t, step = U_new, t + dt, step + 1
        if step % recorder.every == 0:   # build the output fields only for steps that are stored
            recorder.add(step, t, _fields(W, gamma))
        residuals.append(r / r0)
        progress(step, residuals[-1])   # the GUI's Stop button raises an exception in here

    W = conserved_to_primitive(U, gamma)
    fields = _fields(W, gamma)
    recorder.add_final(step, t, fields)   # the last snapshot is exactly the final solution
    left, right = _left_right(params)
    w = wave_structure(left, right, gamma)
    key_numbers = {
        "t_final": (t, "s"),
        "p_star_exact": (w["p_star"], "Pa"),
        "u_star_exact": (w["u_star"], "m/s"),
    }
    for name, value in wave_positions(params, mesh, W[0], W[2]).items():
        key_numbers[name] = (value, "m")

    return Result(fields=fields, residuals=residuals, key_numbers=key_numbers,
                  iterations=step, converged=True,   # "converged" = reached t_end
                  snapshots=recorder.snapshots())


def reference(params, mesh):
    """Exact Riemann solution at t_end, sampled at the cell centres."""
    left, right = _left_right(params)
    gamma = params["gamma"]
    rho, u, p = exact_solution(left, right, gamma, mesh.xc, params["x0"], params["t_end"])
    return _fields(np.array([rho, u, p]), gamma)


def reference_lines(params, mesh):
    """Exact wave paths x = x0 + S t (0 <= t <= t_end) for the x-t diagram.

    A rarefaction gives two lines (head and tail of the fan), a shock one line,
    and the contact surface moves with the star-region velocity u*.
    """
    left, right = _left_right(params)
    w = wave_structure(left, right, params["gamma"])
    x0, t_end = params["x0"], params["t_end"]   # [m], [s]
    t = np.array([0.0, t_end])                  # straight lines: two points are enough [s]

    def path(label, speed, style):
        return Line(label=label, x=x0 + speed * t, y=t, style=style)

    lines = []
    for side, name in (("L", "left"), ("R", "right")):
        if w[f"{name}_wave"] == "shock":
            lines.append(path(f"{name} shock", w[f"S_{side}"], "-"))
        else:
            lines.append(path(f"{name} rarefaction head", w[f"S_head_{side}"], "--"))
            lines.append(path(f"{name} rarefaction tail", w[f"S_tail_{side}"], "--"))
        if side == "L":
            lines.append(path("contact surface", w["u_star"], ":"))
    return lines

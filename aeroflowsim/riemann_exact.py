"""Exact solution of the Riemann problem for the 1D Euler equations (ideal gas).

Reference: E.F. Toro, "Riemann Solvers and Numerical Methods for Fluid Dynamics",
3rd ed., Springer 2009, chapter 4.

The Riemann problem: two constant gas states (left and right) touch at x = x0 at t = 0.
The solution is self-similar (depends only on xi = (x - x0)/t) and has three waves:

    left wave (shock or rarefaction) | contact | right wave (shock or rarefaction)

Across the contact, pressure and velocity are continuous (p*, u*); density jumps.
Each outer wave connects its outside state K (L or R) to the star state, which gives
    u* = u_L - f_L(p*)     and     u* = u_R + f_R(p*)
with f_K from Rankine-Hugoniot (shock, p* > p_K) or the isentropic Riemann invariant
(rarefaction, p* <= p_K). Equating the two u* values gives one equation for p*:
    f(p) = f_L(p) + f_R(p) + (u_R - u_L) = 0,
solved here with Newton-Raphson. Then every point is "sampled": we decide on which side
of each wave the point xi lies and return the corresponding state.

A state is a tuple (rho [kg/m³], u [m/s], p [Pa]). Nothing here imports the GUI.
"""

import math

import numpy as np


def _sound_speed(rho, p, gamma):
    """Speed of sound c = sqrt(gamma p / rho)  [m/s]."""
    return math.sqrt(gamma * p / rho)


def _f_and_derivative(p, state, gamma):
    """Toro eq. (4.6)-(4.7): f_K(p) [m/s] and df_K/dp [m/(s·Pa)] for one side K."""
    rho_k, _, p_k = state
    c_k = _sound_speed(rho_k, p_k, gamma)
    if p > p_k:  # shock
        A = 2.0 / ((gamma + 1.0) * rho_k)            # [m³/kg]
        B = (gamma - 1.0) / (gamma + 1.0) * p_k      # [Pa]
        root = math.sqrt(A / (p + B))
        f = (p - p_k) * root
        df = root * (1.0 - 0.5 * (p - p_k) / (B + p))
    else:        # rarefaction
        ratio = p / p_k
        f = 2.0 * c_k / (gamma - 1.0) * (ratio ** ((gamma - 1.0) / (2.0 * gamma)) - 1.0)
        df = 1.0 / (rho_k * c_k) * ratio ** (-(gamma + 1.0) / (2.0 * gamma))
    return f, df


def star_state(left, right, gamma, tol=1e-12, max_iter=100):
    """Pressure p* [Pa] and velocity u* [m/s] in the star region (between the outer waves)."""
    rho_l, u_l, p_l = left
    rho_r, u_r, p_r = right
    c_l = _sound_speed(rho_l, p_l, gamma)
    c_r = _sound_speed(rho_r, p_r, gamma)

    # Pressure positivity condition (Toro eq. 4.40): otherwise a vacuum forms in the middle.
    if 2.0 / (gamma - 1.0) * (c_l + c_r) <= u_r - u_l:
        raise ValueError("The two states move apart so fast that a vacuum forms; "
                         "this exact solver does not handle vacuum.")

    # Initial guess: the two-rarefaction approximation (Toro eq. 4.46). It is exact when
    # both waves are rarefactions and a good start otherwise.
    z = (gamma - 1.0) / (2.0 * gamma)
    p = ((c_l + c_r - 0.5 * (gamma - 1.0) * (u_r - u_l))
         / (c_l / p_l**z + c_r / p_r**z)) ** (1.0 / z)

    # Newton-Raphson on f(p) = f_L + f_R + du = 0. f is increasing and concave,
    # so the iteration converges quickly; p is kept positive in case a step overshoots.
    for _ in range(max_iter):
        f_l, df_l = _f_and_derivative(p, left, gamma)
        f_r, df_r = _f_and_derivative(p, right, gamma)
        p_new = p - (f_l + f_r + u_r - u_l) / (df_l + df_r)
        p_new = max(p_new, tol * min(p_l, p_r))
        change = abs(p_new - p) / (0.5 * (p_new + p))
        p = p_new
        if change < tol:
            break
    else:
        raise RuntimeError("Newton iteration for p* did not converge.")

    f_l, _ = _f_and_derivative(p, left, gamma)
    f_r, _ = _f_and_derivative(p, right, gamma)
    u = 0.5 * (u_l + u_r) + 0.5 * (f_r - f_l)   # Toro eq. (4.9)
    return p, u


def wave_structure(left, right, gamma):
    """Everything about the three waves, as a dict (speeds in m/s, densities in kg/m³).

    Keys: p_star, u_star, rho_star_L, rho_star_R, left_wave / right_wave ("shock" or
    "rarefaction"), and the wave speeds: shock speed "S_L"/"S_R" for a shock, or head and
    tail speeds "S_head_L", "S_tail_L" / "S_head_R", "S_tail_R" for a rarefaction.
    The contact moves with u_star.
    """
    rho_l, u_l, p_l = left
    rho_r, u_r, p_r = right
    c_l = _sound_speed(rho_l, p_l, gamma)
    c_r = _sound_speed(rho_r, p_r, gamma)
    p_s, u_s = star_state(left, right, gamma)
    g1 = (gamma - 1.0) / (gamma + 1.0)
    info = {"p_star": p_s, "u_star": u_s}

    if p_s > p_l:   # left shock (Toro eq. 4.50, 4.52)
        r = p_s / p_l
        info["left_wave"] = "shock"
        info["rho_star_L"] = rho_l * (r + g1) / (g1 * r + 1.0)
        info["S_L"] = u_l - c_l * math.sqrt((gamma + 1.0) / (2.0 * gamma) * r
                                            + (gamma - 1.0) / (2.0 * gamma))
    else:           # left rarefaction (Toro eq. 4.53-4.55)
        info["left_wave"] = "rarefaction"
        info["rho_star_L"] = rho_l * (p_s / p_l) ** (1.0 / gamma)
        c_star_l = c_l * (p_s / p_l) ** ((gamma - 1.0) / (2.0 * gamma))
        info["S_head_L"] = u_l - c_l
        info["S_tail_L"] = u_s - c_star_l

    if p_s > p_r:   # right shock (Toro eq. 4.57, 4.59)
        r = p_s / p_r
        info["right_wave"] = "shock"
        info["rho_star_R"] = rho_r * (r + g1) / (g1 * r + 1.0)
        info["S_R"] = u_r + c_r * math.sqrt((gamma + 1.0) / (2.0 * gamma) * r
                                            + (gamma - 1.0) / (2.0 * gamma))
    else:           # right rarefaction (Toro eq. 4.60-4.62)
        info["right_wave"] = "rarefaction"
        info["rho_star_R"] = rho_r * (p_s / p_r) ** (1.0 / gamma)
        c_star_r = c_r * (p_s / p_r) ** ((gamma - 1.0) / (2.0 * gamma))
        info["S_head_R"] = u_r + c_r
        info["S_tail_R"] = u_s + c_star_r
    return info


def _sample_point(xi, left, right, gamma, w):
    """State (rho, u, p) at one similarity value xi = (x - x0)/t  [m/s] (Toro section 4.5)."""
    rho_l, u_l, p_l = left
    rho_r, u_r, p_r = right
    p_s, u_s = w["p_star"], w["u_star"]
    g = gamma

    if xi <= u_s:  # left of the contact
        if w["left_wave"] == "shock":
            if xi <= w["S_L"]:
                return left
            return w["rho_star_L"], u_s, p_s
        if xi <= w["S_head_L"]:
            return left
        if xi > w["S_tail_L"]:
            return w["rho_star_L"], u_s, p_s
        # inside the left rarefaction fan (Toro eq. 4.56)
        c_l = _sound_speed(rho_l, p_l, g)
        bracket = 2.0 / (g + 1.0) + (g - 1.0) / ((g + 1.0) * c_l) * (u_l - xi)
        return (rho_l * bracket ** (2.0 / (g - 1.0)),
                2.0 / (g + 1.0) * (c_l + 0.5 * (g - 1.0) * u_l + xi),
                p_l * bracket ** (2.0 * g / (g - 1.0)))

    # right of the contact
    if w["right_wave"] == "shock":
        if xi >= w["S_R"]:
            return right
        return w["rho_star_R"], u_s, p_s
    if xi >= w["S_head_R"]:
        return right
    if xi < w["S_tail_R"]:
        return w["rho_star_R"], u_s, p_s
    # inside the right rarefaction fan (Toro eq. 4.63)
    c_r = _sound_speed(rho_r, p_r, g)
    bracket = 2.0 / (g + 1.0) - (g - 1.0) / ((g + 1.0) * c_r) * (u_r - xi)
    return (rho_r * bracket ** (2.0 / (g - 1.0)),
            2.0 / (g + 1.0) * (-c_r + 0.5 * (g - 1.0) * u_r + xi),
            p_r * bracket ** (2.0 * g / (g - 1.0)))


def exact_solution(left, right, gamma, x, x0, t):
    """Exact density [kg/m³], velocity [m/s] and pressure [Pa] at positions x [m] and time t [s].

    left, right: initial states (rho, u, p); x0: initial diaphragm position [m].
    Returns three numpy arrays the same length as x.
    """
    x = np.asarray(x, dtype=float)
    if t <= 0.0:  # initial condition
        is_left = x <= x0
        return tuple(np.where(is_left, left[k], right[k]) for k in range(3))
    w = wave_structure(left, right, gamma)
    states = np.array([_sample_point((xk - x0) / t, left, right, gamma, w) for xk in x])
    return states[:, 0], states[:, 1], states[:, 2]

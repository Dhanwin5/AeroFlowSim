# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Derived fields, custom field functions and node values of a 2D / axisymmetric Solution.

Every field is one value per cell in SI units, computed on demand from the primitive state W = (rho, u, v, p),
the gas model and the least-squares gradients of the solver (euler/gradients.py):

    speed           |V| = sqrt(u² + v²)
    h, h0           static enthalpy e(T) + p/rho, total enthalpy h + |V|²/2
    Cp              (p - p_inf) / q_inf (external flow) or p / p0 (internal flow, p0 of the inlet)
    grad_rho        |grad rho|
    schlieren       exp(-k |grad rho| / max|grad rho|), k = 15: numerical schlieren (dark = strong gradient)
    vorticity       omega_z = dv/dx - du/dy
    divergence      div V = du/dx + dv/dy (+ v/r axisymmetric)
    mach_normal     M_n = V . grad p / (c |grad p|): Mach number normal to the pressure gradient; a shock is where
                    M_n crosses 1 (Lovely & Haimes 1999, "Shock detection from computational fluid dynamics
                    results", AIAA 99-3285)
    quality fields  aspect ratio, non-orthogonality, volume ratio, cell size, minimum angle, skewness (mesh_quality)
    residual_*      |dU/dt| of the final state per cell, normalised like the residual history (finds stalls)

Custom field functions: a formula of fields and constants, e.g. "p / 101325", "sqrt(u**2 + v**2)", "rho * u".
The text is parsed with Python's ast module and only a whitelist of syntax is accepted (numbers, field names,
+ - * / ** %, unary minus, calls of whitelisted numpy functions); there is NO eval of the text, so a formula
can never run code (attribute access, imports, lambdas, subscripts, keywords are refused). Units are derived
where possible (a sum of two different units is an error; transcendental functions give a dimensionless result).

Node values (smooth contours, streamlines, interpolation): each node gets the inverse-distance-weighted mean of
the cells around it; boundary nodes instead take the mean of their boundary-face values (the boundary
condition's state, see solution.py), so wall and axis values are right.
"""

import ast
import math
from dataclasses import dataclass

import numpy as np
from scipy import sparse


class FieldError(ValueError):
    """A field or formula cannot be computed (plain-language message)."""


@dataclass(frozen=True)
class FieldInfo:
    name: str
    label: str
    unit: str
    group: str            # "Flow", "Derived", "Gradients", "Mesh quality", "Residual", "Custom"


_BASE = {
    "rho": ("Density", "kg/m³"), "u": ("Velocity x", "m/s"), "v": ("Velocity y (radial)", "m/s"),
    "p": ("Pressure", "Pa"), "T": ("Temperature", "K"), "M": ("Mach number", "-"),
    "p0": ("Total pressure", "Pa"), "T0": ("Total temperature", "K"), "s": ("Entropy", "J/(kg K)"),
}
_DERIVED = {
    "speed": ("Velocity magnitude", "m/s", "Derived"),
    "h": ("Static enthalpy", "J/kg", "Derived"),
    "h0": ("Total enthalpy", "J/kg", "Derived"),
    "Cp": ("Pressure coefficient", "-", "Derived"),
    "mach_normal": ("Mach number normal to the pressure gradient (shock indicator)", "-", "Derived"),
    "grad_rho": ("Density gradient magnitude", "kg/m⁴", "Gradients"),
    "schlieren": ("Numerical schlieren", "-", "Gradients"),
    "vorticity": ("Vorticity", "1/s", "Gradients"),
    "divergence": ("Velocity divergence", "1/s", "Gradients"),
    "aspect_ratio": ("Cell aspect ratio", "-", "Mesh quality"),
    "non_orthogonality": ("Cell non-orthogonality", "deg", "Mesh quality"),
    "volume_ratio": ("Cell volume ratio", "-", "Mesh quality"),
    "cell_size": ("Cell size", "m", "Mesh quality"),
    "min_angle": ("Cell minimum angle", "deg", "Mesh quality"),
    "skewness": ("Cell equiangle skewness", "-", "Mesh quality"),
    "residual_density": ("Residual of the last iteration (density)", "-", "Residual"),
    "residual_energy": ("Residual of the last iteration (energy)", "-", "Residual"),
    "x": ("x coordinate", "m", "Mesh quality"),
    "y": ("y coordinate (radius)", "m", "Mesh quality"),
}
SCHLIEREN_K = 15.0


def field_info(sol, name) -> FieldInfo:
    """Label, unit and group of a field of this solution (built-in, derived or custom)."""
    if name in _BASE:
        label, unit = _BASE[name]
        return FieldInfo(name, sol.labels.get(name, label), sol.units.get(name, unit), "Flow")
    if name in _DERIVED:
        label, unit, group = _DERIVED[name]
        if name == "Cp" and sol.kind != "external":
            label = "Pressure ratio p/p0"
        if name == "y" and sol.axisymmetric:
            label = "Radius r"
        return FieldInfo(name, label, unit, group)
    if name in sol.custom_fields:
        spec = sol.custom_fields[name]
        try:
            unit = _formula_unit(sol, spec["formula"], set())
        except FieldError:
            unit = ""
        return FieldInfo(name, spec.get("label") or name, unit, "Custom")
    if name in sol.fields:
        return FieldInfo(name, sol.labels.get(name, name), sol.units.get(name, ""), "Flow")
    raise FieldError(f"There is no field called '{name}'.")


def available_fields(sol) -> list:
    """Every field this solution can show, in a sensible order (FieldInfo list)."""
    names = [k for k in _BASE if k in sol.fields] + [k for k in sol.fields if k not in _BASE]
    names += list(_DERIVED) + list(sol.custom_fields)
    return [field_info(sol, n) for n in names]


def field_values(sol, name) -> np.ndarray:
    """(C,) cell values of a field [SI]. Cached per solution."""
    cache = sol._cache.setdefault("fields", {})
    if name not in cache:
        cache[name] = np.asarray(_compute(sol, name, set()), dtype=float)
    return cache[name]


def _compute(sol, name, stack):
    if name in sol.fields:
        return sol.fields[name]
    W, gas = sol.W, sol.gas
    rho, u, v, p = W
    if name in ("T", "M", "p0", "T0", "s"):
        from aeroflowsim.euler import state
        fn = {"T": state.temperature, "M": state.mach_number, "p0": state.total_pressure,
              "T0": state.total_temperature, "s": state.entropy}[name]
        return fn(W, gas)
    if name == "speed":
        return np.hypot(u, v)
    if name in ("h", "h0"):
        T = p / (rho * gas.R)
        h = gas.internal_energy(T) + p / rho
        return h if name == "h" else h + 0.5 * (u * u + v * v)
    if name == "Cp":
        p_ref, q_ref, _ = sol.reference_pressure()
        return (p - p_ref) / q_ref
    if name in ("grad_rho", "schlieren"):
        g = sol.gradients[0]
        mag = np.sqrt(np.sum(g * g, axis=0))
        if name == "grad_rho":
            return mag
        top = float(mag.max()) if mag.size and mag.max() > 0 else 1.0
        return np.exp(-SCHLIEREN_K * mag / top)
    if name in ("vorticity", "divergence"):
        gu, gv = sol.gradients[1], sol.gradients[2]
        if name == "vorticity":
            return gv[0] - gu[1]
        div = gu[0] + gv[1]
        if sol.axisymmetric:
            r = sol.geom.cell_centres[:, 1]
            div = div + np.where(r > 0.0, v / np.where(r > 0.0, r, 1.0), gv[1])   # v/r -> dv/dr on the axis
        return div
    if name == "mach_normal":
        from aeroflowsim.euler.state import sound_speed
        gp = sol.gradients[3]
        mag = np.sqrt(np.sum(gp * gp, axis=0))
        c = sound_speed(W, gas)
        return np.where(mag > 0.0, (u * gp[0] + v * gp[1]) / (c * np.where(mag > 0.0, mag, 1.0)), 0.0)
    if name in ("aspect_ratio", "non_orthogonality", "volume_ratio", "cell_size", "min_angle", "skewness"):
        from aeroflowsim import mesh_quality as mq
        fn = {"aspect_ratio": mq.aspect_ratio, "non_orthogonality": mq.non_orthogonality,
              "volume_ratio": mq.volume_ratio, "cell_size": mq.cell_size, "min_angle": mq.min_angle,
              "skewness": mq.equiangle_skewness}[name]
        return fn(sol.mesh)
    if name in ("residual_density", "residual_energy"):
        R = sol.cell_residual
        k = 0 if name == "residual_density" else R.shape[0] - 1
        norm = sol.info.get("residual_norm")
        scale = float(norm[k]) if norm and norm[k] > 0 else float(np.sqrt(np.mean(R[k] ** 2)) or 1.0)
        return np.abs(R[k]) / scale
    if name in ("x", "y"):
        return sol.geom.cell_centres[:, 0 if name == "x" else 1]
    if name in sol.custom_fields:
        if name in stack:
            raise FieldError(f"The custom field '{name}' uses itself (directly or through another custom field).")
        return _evaluate_formula(sol, sol.custom_fields[name]["formula"], stack | {name})
    raise FieldError(f"There is no field called '{name}'.")


# ---- node values ------------------------------------------------------------------------------------

def _node_operator(sol):
    """Sparse matrices (N x C) and (N x B): node value = A @ cell values + Bm @ boundary-face values."""
    key = "_node_operator"
    if key in sol._cache:
        return sol._cache[key]
    mesh, g = sol.mesh, sol.geom
    N = mesh.n_nodes if hasattr(mesh, "n_nodes") else len(mesh.nodes)
    cn = mesh.cell_nodes
    cells, slots = np.nonzero(cn >= 0)
    nodes = cn[cells, slots]
    d = np.linalg.norm(mesh.nodes[nodes, :2] - g.cell_centres[cells, :2], axis=1)
    w = 1.0 / np.maximum(d, 1e-300)
    A = sparse.csr_matrix((w, (nodes, cells)), shape=(N, g.n_cells))
    # boundary nodes: the mean of the boundary-face values around them (inverse distance to the face centres)
    fn = mesh.face_nodes[g.boundary_faces]
    bf, bs = np.nonzero(fn >= 0)
    bnodes = fn[bf, bs]
    db = np.linalg.norm(mesh.nodes[bnodes, :2] - g.face_centres[g.boundary_faces[bf], :2], axis=1)
    wb = 1.0 / np.maximum(db, 1e-300)
    Bm = sparse.csr_matrix((wb, (bnodes, bf)), shape=(N, g.n_boundary))
    on_boundary = np.asarray(Bm.sum(axis=1)).ravel() > 0.0
    A = sparse.diags(np.where(on_boundary, 0.0, 1.0)) @ A           # boundary nodes use the faces only
    total = np.asarray(A.sum(axis=1)).ravel() + np.asarray(Bm.sum(axis=1)).ravel()
    scale = sparse.diags(1.0 / np.where(total > 0.0, total, 1.0))
    sol._cache[key] = (scale @ A).tocsr(), (scale @ Bm).tocsr()
    return sol._cache[key]


def boundary_face_values(sol, name, values=None) -> np.ndarray:
    """(B,) value of a field at the boundary faces: for rho, u, v, p (and fields made from them pointwise) the
    boundary condition's face state; for other fields the value of the cell next to the face."""
    g = sol.geom
    Wb = sol.boundary_values
    pointwise = {"rho": lambda: Wb[0], "u": lambda: Wb[1], "v": lambda: Wb[2], "p": lambda: Wb[3]}
    if name in pointwise:
        return pointwise[name]()
    if name in ("T", "M", "p0", "T0", "s", "speed", "h", "h0", "Cp"):
        face_sol = _FaceState(sol, Wb)
        return np.asarray(_compute(face_sol, name, set()), dtype=float)
    vals = field_values(sol, name) if values is None else values
    return vals[g.boundary_owner]


class _FaceState:
    """A Solution-like view of the boundary-face states (for pointwise fields at the boundary)."""

    def __init__(self, sol, Wb):
        self.W, self.gas, self.fields, self.custom_fields = Wb, sol.gas, {}, {}
        self.kind, self.params, self.conditions = sol.kind, sol.params, sol.conditions
        self.reference_pressure = sol.reference_pressure


def node_values(sol, name, values=None) -> np.ndarray:
    """(N,) values at the mesh nodes (inverse-distance mean of the cells; boundary nodes from the boundary faces)."""
    cell = field_values(sol, name) if values is None else np.asarray(values, dtype=float)
    A, Bm = _node_operator(sol)
    return A @ cell + Bm @ boundary_face_values(sol, name, cell if values is not None else None)


# ---- custom field functions -----------------------------------------------------------------------

_FUNCTIONS = {
    "sqrt": np.sqrt, "exp": np.exp, "log": np.log, "log10": np.log10, "abs": np.abs, "sin": np.sin, "cos": np.cos,
    "tan": np.tan, "arcsin": np.arcsin, "arccos": np.arccos, "arctan": np.arctan, "arctan2": np.arctan2,
    "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh, "minimum": np.minimum, "maximum": np.maximum,
    "min": np.minimum, "max": np.maximum, "sign": np.sign, "floor": np.floor, "ceil": np.ceil,
    "degrees": np.degrees, "radians": np.radians,
}
_CONSTANTS = {"pi": math.pi, "e": math.e, "g0": 9.80665}
_BINARY = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide, ast.Pow: np.power,
           ast.Mod: np.mod}
MAX_FORMULA_LENGTH = 500


def _names(sol):
    return set(sol.fields) | set(_BASE) | set(_DERIVED) | set(sol.custom_fields)


def _parse(text):
    if not isinstance(text, str) or not text.strip():
        raise FieldError("The formula is empty.")
    if len(text) > MAX_FORMULA_LENGTH:
        raise FieldError(f"The formula is too long (more than {MAX_FORMULA_LENGTH} characters).")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as exc:
        raise FieldError(f"The formula is not valid: {exc.msg} (at character {exc.offset}).") from None
    return tree.body


def _check(node, sol, used):
    """Refuse anything outside the whitelist; collect the field names used."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FieldError("Only numbers may appear as constants in a formula.")
    elif isinstance(node, ast.Name):
        if node.id in _CONSTANTS or node.id in ("gamma", "R"):
            return
        if node.id not in _names(sol):
            raise FieldError(f"Unknown name '{node.id}'. Fields: {', '.join(sorted(_names(sol)))}; "
                             f"constants: pi, e, g0, gamma, R.")
        used.add(node.id)
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in _BINARY:
            raise FieldError("Only + - * / ** and % may be used as operators.")
        _check(node.left, sol, used)
        _check(node.right, sol, used)
    elif isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.USub, ast.UAdd)):
            raise FieldError("Only a minus or plus sign may stand in front of a value.")
        _check(node.operand, sol, used)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            name = node.func.id if isinstance(node.func, ast.Name) else "this"
            raise FieldError(f"The function '{name}' is not allowed. Allowed: {', '.join(sorted(_FUNCTIONS))}.")
        if node.keywords:
            raise FieldError("Functions in a formula take plain values only (no name=value arguments).")
        if not node.args:
            raise FieldError(f"The function '{node.func.id}' needs a value in its brackets.")
        for a in node.args:
            _check(a, sol, used)
    else:
        raise FieldError(f"'{type(node).__name__}' is not allowed in a formula: use numbers, field names, + - * / **, "
                         "and functions like sqrt(...).")


def _gas_constants(sol):
    T = float(np.median(np.asarray(_compute(sol, "T", set()))))
    return {"gamma": float(sol.gas.gamma(T)), "R": float(sol.gas.R)}


def _eval(node, sol, stack):
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        if node.id in ("gamma", "R"):
            return _gas_constants(sol)[node.id]
        return np.asarray(_compute(sol, node.id, stack), dtype=float)
    if isinstance(node, ast.BinOp):
        return _BINARY[type(node.op)](_eval(node.left, sol, stack), _eval(node.right, sol, stack))
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, sol, stack)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.Call):
        fn = _FUNCTIONS[node.func.id]
        try:
            return fn(*[_eval(a, sol, stack) for a in node.args])
        except TypeError:
            raise FieldError(f"The function '{node.func.id}' was given the wrong number of values.") from None
    raise FieldError("Formula element not allowed.")      # never reached: _check refused it


def _evaluate_formula(sol, text, stack):
    node = _parse(text)
    _check(node, sol, set())
    _formula_unit(sol, text, stack)          # raises on a sum of different units
    with np.errstate(all="ignore"):
        out = _eval(node, sol, stack)
    out = np.broadcast_to(np.asarray(out, dtype=float), (sol.mesh.n_cells,)).copy()
    return out


def custom_field_problem(sol, name, formula) -> str:
    """'' if the custom field can be defined, else the problem in plain words (name clash, syntax, units, ...)."""
    if not name or not name.isidentifier():
        return "A field name must start with a letter and use only letters, digits and _ (for example p_kPa)."
    if name in (set(sol.fields) | set(_BASE) | set(_DERIVED) | set(_CONSTANTS) | set(_FUNCTIONS) | {"gamma", "R"}):
        return f"'{name}' is already the name of a built-in field, constant or function; choose another name."
    trial = dict(sol.custom_fields)
    trial[name] = {"formula": formula}
    old = sol.custom_fields
    sol.custom_fields = trial
    try:
        _evaluate_formula(sol, formula, {name})
    except FieldError as exc:
        return str(exc)
    finally:
        sol.custom_fields = old
        sol._cache.get("fields", {}).pop(name, None)
    return ""


# ---- units of a formula ---------------------------------------------------------------------------
# A unit is a dict of base-unit exponents {kg, m, s, K}; None = unknown (a bare number adapts to its partner).

_BASE_UNITS = {
    "-": {}, "": {}, "kg/m³": {"kg": 1, "m": -3}, "m/s": {"m": 1, "s": -1}, "Pa": {"kg": 1, "m": -1, "s": -2},
    "K": {"K": 1}, "J/(kg K)": {"m": 2, "s": -2, "K": -1}, "J/kg": {"m": 2, "s": -2}, "kg/m⁴": {"kg": 1, "m": -4},
    "1/s": {"s": -1}, "m": {"m": 1}, "deg": {},
}


def _unit_of_field(sol, name, stack):
    if name in sol.custom_fields:
        if name in stack:
            raise FieldError(f"The custom field '{name}' uses itself (directly or through another custom field).")
        return _unit_tree(sol, _parse(sol.custom_fields[name]["formula"]), stack | {name})
    unit = field_info(sol, name).unit
    return dict(_BASE_UNITS[unit]) if unit in _BASE_UNITS else None


def _unit_tree(sol, node, stack):
    if isinstance(node, ast.Constant):
        return "number"
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS or node.id == "gamma":
            return {}
        if node.id == "R":
            return {"m": 2, "s": -2, "K": -1}
        return _unit_of_field(sol, node.id, stack)
    if isinstance(node, ast.UnaryOp):
        return _unit_tree(sol, node.operand, stack)
    if isinstance(node, ast.BinOp):
        a, b = _unit_tree(sol, node.left, stack), _unit_tree(sol, node.right, stack)
        if isinstance(node.op, (ast.Add, ast.Sub, ast.Mod)):
            if a == "number":
                return b
            if b == "number" or a is None or b is None:
                return a if b == "number" else None
            if {k: v for k, v in a.items() if v} != {k: v for k, v in b.items() if v}:
                raise FieldError(f"The formula adds or subtracts values with different units ({_unit_text(a)} and "
                                 f"{_unit_text(b)}).")
            return a
        if isinstance(node.op, (ast.Mult, ast.Div)):
            a = {} if a == "number" else a
            b = {} if b == "number" else b
            if a is None or b is None:
                return None
            sign = 1 if isinstance(node.op, ast.Mult) else -1
            out = dict(a)
            for k, v in b.items():
                out[k] = out.get(k, 0) + sign * v
            return out
        if isinstance(node.op, ast.Pow):
            if a in ("number", None) or not a:
                return a if a != "number" else "number"
            if isinstance(node.right, ast.Constant):
                return {k: v * float(node.right.value) for k, v in a.items()}
            return None
    if isinstance(node, ast.Call):
        args = [_unit_tree(sol, x, stack) for x in node.args]
        fn = node.func.id
        if fn == "sqrt":
            a = args[0]
            return a if a in ("number", None) else {k: v / 2 for k, v in a.items()}
        if fn in ("abs", "minimum", "maximum", "min", "max", "floor", "ceil"):
            known = [a for a in args if a not in ("number", None)]
            return known[0] if known else args[0]
        return {}                                   # transcendental functions: dimensionless
    return None


def _formula_unit(sol, text, stack) -> str:
    unit = _unit_tree(sol, _parse(text), stack)
    if unit == "number":
        return "-"
    return "" if unit is None else _unit_text(unit)


def _unit_text(unit) -> str:
    unit = {k: v for k, v in unit.items() if v}
    for text, base in _BASE_UNITS.items():
        if text not in ("", "deg") and base == unit:
            return text
    if not unit:
        return "-"
    parts = []
    for k in ("kg", "m", "s", "K"):
        v = unit.get(k, 0)
        if v:
            parts.append(k if v == 1 else f"{k}^{v:g}")
    return " ".join(parts)

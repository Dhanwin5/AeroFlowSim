# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Boundary conditions as ghost states: one function per boundary-condition type.

How a boundary condition works, in plain words: a boundary face has a cell on one side only. The solver
invents the state on the missing side, the "ghost" state, from the inside state W_i and the boundary
data (e.g. p0 and T0 of a reservoir). Then the SAME Riemann solver as inside the domain computes the
boundary flux. A wall's ghost is the mirror image of the inside state (normal velocity reversed), so the
Riemann solver gives exactly zero mass flux and the wall pressure; a supersonic outlet's ghost is a copy
of the inside (everything leaves); a supersonic inlet's ghost is the fixed free stream.
How many values may be imposed follows the characteristics (waves): at a subsonic inlet two waves
enter and one leaves, so one quantity must come from inside; at a subsonic outlet one wave enters, so
exactly one quantity (the pressure) is imposed.

Every function:  ghost(W_i, normals, values, gas, patch) -> W_ghost, both shape (dim + 2, n_faces),
normals (n_faces, dim) pointing OUT of the domain. `values` holds the inputs of the type (SI units);
`patch` has the patch's total flux area (for the mass-flow inlet). References: Blazek (2015) ch. 8,
Hirsch (2007) ch. 7, Carlson (2011, NASA TM-2011-217181), Toro (2009) sec. 6.3.

BC_TYPES lists every type with its label, help text, inputs (Parameter objects, so the GUI draws them
like every other input) and the mesh patch kinds it suits (used for defaults and the error check).
"""

import math
from dataclasses import dataclass, field

import numpy as np

from aeroflowsim.euler.flux import normal_velocity
from aeroflowsim.euler.state import sound_speed
from aeroflowsim.parameters import Parameter

DEG = math.pi / 180.0
NORMAL_DIRECTION = "Normal to the boundary"
ANGLE_DIRECTION = "Angle to the x axis"


# ---- the ghost-state functions -----------------------------------------------------------------

def slip_wall(Wi, normals, values, gas, patch):
    """Inviscid wall: mirror the normal velocity (u_g = u - 2 (u.n) n); rho and p unchanged."""
    Wg = Wi.copy()
    un = normal_velocity(Wi, normals)
    Wg[1:-1] -= 2.0 * un * normals.T
    return Wg


def symmetry(Wi, normals, values, gas, patch):
    """Mirror plane: the same mirror state as a slip wall (no flow through, no shear)."""
    return slip_wall(Wi, normals, values, gas, patch)


def axis(Wi, normals, values, gas, patch):
    """Axis of an axisymmetric flow (r = 0): mirror image in r. Its faces have zero flux area, so the
    mirror state matters only for the gradients next to the axis (dv/dr, and zero dp/dr)."""
    return slip_wall(Wi, normals, values, gas, patch)


def _direction(values, normals, dim):
    """Unit flow direction of an inflow: -n (into the domain) or the given angle to the x axis."""
    if values.get("direction", NORMAL_DIRECTION) == ANGLE_DIRECTION:
        a = values["flow_angle"] * DEG
        d = np.zeros((dim, normals.shape[0]))
        d[0], d[1] = math.cos(a), math.sin(a)
        return d
    return -normals.T


def _free_stream(values, gas, dim, n):
    """Primitive free-stream state from Mach, p, T and the angle (of attack) to the x axis."""
    T, p = values["T"], values["p"]
    speed = values["mach"] * float(gas.sound_speed(T))          # [m/s]
    a = values.get("flow_angle", 0.0) * DEG
    W = np.empty((dim + 2, n))
    W[0] = p / (gas.R * T)
    W[1:-1] = 0.0
    W[1], W[2] = speed * math.cos(a), speed * math.sin(a)
    W[-1] = p
    return W


def supersonic_inlet(Wi, normals, values, gas, patch):
    """Supersonic inflow: every wave enters, so the whole state is imposed (Mach, p, T, direction)."""
    return _free_stream(values, gas, Wi.shape[0] - 2, Wi.shape[1])


def supersonic_outlet(Wi, normals, values, gas, patch):
    """Supersonic outflow: every wave leaves, so the whole state comes from inside (a copy)."""
    return Wi.copy()


def far_field(Wi, normals, values, gas, patch):
    """Characteristic far field with Riemann invariants (Blazek 2015 sec. 8.5; Hirsch sec. 7.5).

    Along the face normal two Riemann invariants travel:  R+ = u_n + 2c/(gamma-1)  (outgoing, taken from
    inside) and  R- = u_n - 2c/(gamma-1)  (incoming, taken from the free stream). Their sum and difference
    give u_n and c at the boundary. Entropy p/rho^gamma and the tangential velocity come from the free
    stream at inflow faces (u_n < 0) and from inside at outflow faces. Supersonic faces: all free stream
    (inflow) or all inside (outflow). gamma is the gas's gamma at the free-stream temperature.
    """
    dim, n = Wi.shape[0] - 2, Wi.shape[1]
    Winf = _free_stream(values, gas, dim, n)
    g = float(gas.gamma(values["T"]))
    un_i, c_i = normal_velocity(Wi, normals), sound_speed(Wi, gas)
    un_f, c_f = normal_velocity(Winf, normals), sound_speed(Winf, gas)
    r_plus = un_i + 2.0 * c_i / (g - 1.0)
    r_minus = un_f - 2.0 * c_f / (g - 1.0)
    un_b = 0.5 * (r_plus + r_minus)                               # [m/s]
    c_b = 0.25 * (g - 1.0) * (r_plus - r_minus)                   # [m/s]
    inflow = un_b < 0.0
    src = np.where(inflow, Winf, Wi)                              # entropy and tangential velocity source
    un_src = np.where(inflow, un_f, un_i)
    s = src[-1] / src[0] ** g                                     # p / rho^gamma
    rho_b = (c_b**2 / (g * s)) ** (1.0 / (g - 1.0))
    Wg = np.empty_like(Wi)
    Wg[0] = rho_b
    Wg[1:-1] = src[1:-1] + (un_b - un_src) * normals.T
    Wg[-1] = rho_b * c_b**2 / g
    supersonic_in = un_f <= -c_f                                   # free stream enters supersonically
    supersonic_out = un_i >= c_i
    Wg = np.where(supersonic_in, Winf, Wg)
    return np.where(supersonic_out & ~supersonic_in, Wi, Wg)


def _isentropic_inflow(speed, direction, p0, T0, gas):
    """State with total pressure p0 and total temperature T0 moving at `speed` along `direction`."""
    cp = float(gas.cp(T0))
    g = float(gas.gamma(T0))
    T = np.maximum(T0 - speed**2 / (2.0 * cp), 1e-3 * T0)          # [K] (kept positive while starting)
    p = p0 * (T / T0) ** (g / (g - 1.0))                          # [Pa]
    W = np.empty((direction.shape[0] + 2, speed.shape[0]))
    W[0] = p / (gas.R * T)
    W[1:-1] = speed * direction
    W[-1] = p
    return W


def total_pressure_inlet(Wi, normals, values, gas, patch):
    """Reservoir inlet: total pressure p0 and total temperature T0 imposed, flow direction given.

    At a subsonic inlet one wave leaves the domain, so one quantity comes from inside: the speed (the
    inside velocity projected on the flow direction, never negative), exactly as at the validated
    quasi-1D inlet (aeroflowsim/quasi1d.py). Then T = T0 - |u|²/(2 cp), p = p0 (T/T0)^(gamma/(gamma-1)).
    """
    d = _direction(values, normals, Wi.shape[0] - 2)
    speed = np.maximum(np.einsum("kn,kn->n", Wi[1:-1], d), 0.0)  # [m/s]
    return _isentropic_inflow(speed, d, values["p0"], values["T0"], gas)


def mass_flow_inlet(Wi, normals, values, gas, patch):
    """Mass-flow inlet: mass flow and total temperature T0 imposed, flow normal to the boundary.

    The mass flux G = mass flow / patch area is the same on every face (patch area per radian x 2 pi for
    axisymmetric meshes; per metre of depth for planar 2D). The static pressure comes from inside (the
    one outgoing wave); then  rho u = G,  T = T0 - u²/(2 cp),  p = rho R T  give a quadratic for u:
        a u² + u - b = 0,  a = G R / (2 cp p),  b = G R T0 / p.
    """
    G = values["mass_flow"] / patch.total_area                    # [kg/(m² s)]
    T0, p = values["T0"], Wi[-1]
    cp = float(gas.cp(T0))
    a = G * gas.R / (2.0 * cp * p)
    b = G * gas.R * T0 / p
    u = 2.0 * b / (1.0 + np.sqrt(1.0 + 4.0 * a * b))             # stable root of a u² + u - b = 0 [m/s]
    T = T0 - u**2 / (2.0 * cp)
    Wg = np.empty_like(Wi)
    Wg[0] = p / (gas.R * T)
    Wg[1:-1] = -u * normals.T
    Wg[-1] = p
    return Wg


def pressure_outlet(Wi, normals, values, gas, patch):
    """Static pressure outlet. Subsonic outflow: p = p_back imposed, rho and u corrected along the
    outgoing characteristics (Blazek 2015 eq. 8.30):  rho_b = rho_i + (p_b - p_i)/c²,
    u_b = u_i + n (p_i - p_b)/(rho c). Where the outflow is supersonic (u_n >= c) nothing can be imposed
    and everything is taken from inside, automatically, face by face."""
    p_b = values["p"]
    c = sound_speed(Wi, gas)
    un = normal_velocity(Wi, normals)
    Wg = Wi.copy()
    dp = Wi[-1] - p_b
    Wg[0] = np.maximum(Wi[0] - dp / c**2, 1e-6 * Wi[0])
    Wg[1:-1] = Wi[1:-1] + (dp / (Wi[0] * c)) * normals.T
    Wg[-1] = p_b
    return np.where(un >= c, Wi, Wg)


# ---- the table of types ----------------------------------------------------------------------------

def _p(key, label, unit, default, lo=None, hi=None, help="", type="", options=(), show_if=None):
    return Parameter(key, label, unit, default, lo, hi, help, type=type, options=tuple(options),
                     show_if=show_if)


_ANGLE_INPUTS = [
    _p("direction", "Flow direction", "", NORMAL_DIRECTION, help="Inflow normal to the boundary, or at a given "
       "angle to the x axis.", type="choice", options=(NORMAL_DIRECTION, ANGLE_DIRECTION)),
    _p("flow_angle", "Flow angle to the x axis", "deg", 0.0, -180.0, 180.0, "Direction of the inflow, "
       "measured from the +x axis (counter-clockwise positive).", show_if=("direction", ANGLE_DIRECTION)),
]
_FREE_STREAM = [
    _p("mach", "Mach number", "-", 2.0, 0.0, 50.0, "Free-stream Mach number."),
    _p("p", "Static pressure", "Pa", 101325.0, 1e-3, 1e9, "Free-stream static pressure."),
    _p("T", "Static temperature", "K", 288.15, 1.0, 1e5, "Free-stream static temperature."),
    _p("flow_angle", "Angle of attack", "deg", 0.0, -90.0, 90.0, "Flow direction measured from the +x axis "
       "(counter-clockwise positive): the angle of attack of a body at zero incidence."),
]


@dataclass(frozen=True)
class BCType:
    """One boundary-condition type."""

    label: str
    function: object
    help: str
    inputs: tuple = ()          # Parameter objects (SI units)
    suits: tuple = ()           # mesh patch kinds (mesh.PATCH_TYPES) this type is meant for


BC_TYPES = {
    "slip_wall": BCType("Slip wall", slip_wall, "Inviscid solid wall: no flow through it, the gas slides along.",
                        (), ("wall",)),
    "symmetry": BCType("Symmetry", symmetry, "Mirror plane of a planar flow (half domain).", (), ("symmetry",)),
    "axis": BCType("Axis", axis, "Axis of an axisymmetric flow (r = 0).", (), ("axis",)),
    "far_field": BCType("Far field", far_field, "Free stream far from the body (characteristic, Riemann "
                        "invariants): lets waves leave without reflection.", tuple(_FREE_STREAM), ("farfield",)),
    "supersonic_inlet": BCType("Supersonic inlet", supersonic_inlet, "Supersonic inflow: Mach, p, T and "
                               "direction all fixed.", tuple(_FREE_STREAM), ("inlet", "farfield")),
    "supersonic_outlet": BCType("Supersonic outlet", supersonic_outlet, "Supersonic outflow: everything "
                                "extrapolated from inside.", (), ("outlet", "farfield")),
    "total_pressure_inlet": BCType(
        "Total-pressure inlet", total_pressure_inlet, "Reservoir (chamber) inlet: total pressure p0 and total "
        "temperature T0 fixed.",
        (_p("p0", "Total pressure", "Pa", 5e5, 1e-3, 1e9, "Stagnation (chamber) pressure."),
         _p("T0", "Total temperature", "K", 293.15, 1.0, 1e5, "Stagnation (chamber) temperature."),
         *_ANGLE_INPUTS), ("inlet",)),
    "mass_flow_inlet": BCType(
        "Mass-flow inlet", mass_flow_inlet, "Mass flow and total temperature fixed; the flow enters normal to "
        "the boundary.",
        (_p("mass_flow", "Mass flow", "kg/s", 1e-4, 1e-12, 1e6, "Total mass flow through this boundary "
            "(axisymmetric: the whole circle; planar 2D: per metre of depth)."),
         _p("T0", "Total temperature", "K", 293.15, 1.0, 1e5, "Stagnation temperature of the inflow.")),
        ("inlet",)),
    "pressure_outlet": BCType(
        "Pressure outlet", pressure_outlet, "Static (back) pressure fixed where the outflow is subsonic; "
        "extrapolated automatically where it is supersonic.",
        (_p("p", "Back pressure", "Pa", 101325.0, 1e-3, 1e9, "Static pressure outside the outlet."),),
        ("outlet",)),
}

# The default type for each mesh patch kind (the Setup table starts from these)
DEFAULT_FOR_KIND = {"inlet": "total_pressure_inlet", "outlet": "pressure_outlet", "wall": "slip_wall",
                    "axis": "axis", "farfield": "far_field", "symmetry": "symmetry"}


@dataclass
class BoundaryCondition:
    """The condition on one patch: its type and the values of the type's inputs (SI units)."""

    type: str
    values: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.type not in BC_TYPES:
            raise ValueError(f"'{self.type}' is not a boundary-condition type; choose one of "
                             f"{', '.join(BC_TYPES)}.")
        full = {p.name: p.default for p in BC_TYPES[self.type].inputs}
        full.update(self.values)
        self.values = full

    @property
    def label(self) -> str:
        return BC_TYPES[self.type].label

    def to_dict(self) -> dict:
        return {"type": self.type, **self.values}

    @classmethod
    def from_dict(cls, data) -> "BoundaryCondition":
        data = dict(data)
        kind = data.pop("type")
        known = {p.name for p in BC_TYPES[kind].inputs} if kind in BC_TYPES else set()
        return cls(kind, {k: v for k, v in data.items() if k in known})


@dataclass
class PatchInfo:
    """What a boundary function may need to know about its patch."""

    name: str
    total_area: float        # flux area of the whole patch [m²] (axisymmetric: x 2 pi, the full circle)


def boundary_problems(conditions, patch_names) -> list:
    """Plain-language problems: patches without a condition, conditions for unknown patches, bad types."""
    problems = []
    for name in patch_names:
        if name not in conditions:
            problems.append(f"Boundary '{name}' has no boundary condition.")
    for name, bc in conditions.items():
        if name not in patch_names:
            problems.append(f"There is a boundary condition for '{name}', but the mesh has no such boundary.")
        elif isinstance(bc, BoundaryCondition):
            for p in BC_TYPES[bc.type].inputs:
                v = bc.values.get(p.name)
                if p.is_number and (v is None or (p.min is not None and v < p.min)
                                    or (p.max is not None and v > p.max)):
                    problems.append(f"Boundary '{name}' ({bc.label}): {p.label} must be between {p.min:g} and "
                                    f"{p.max:g} {p.unit}.")
    return problems


def ghost_state(bc, Wi, normals, gas, patch):
    """Ghost states of one patch's faces for the condition bc."""
    return BC_TYPES[bc.type].function(Wi, normals, bc.values, gas, patch)

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Gas data files: one TOML file per gas, read into a GasData object (no Qt, no solver).

Built-in gases live next to this module (aeroflowsim/gases/N2.toml, ...); custom gases use the same
format in the user's own folder and inside projects. Everything is in SI units, and every value
names its source in a *_source line or a `source` key. Format (only the starred fields are required;
a custom gas needs no more):

    id = "N2"                      * short name used in project files
    name = "Nitrogen"              * shown in the GUI
    formula = "N2"
    model = "calorically perfect"    the GasModel class (only this one so far)
    note = "..."                     warnings shown with the gas (e.g. R-236fa)

    [constants]
    molar_mass = 0.0280134         * [kg/mol]   (or give R; one of the two is needed)
    R = 296.8                        [J/(kg K)] optional: a tabulated value; else R = R_u / molar_mass
    gamma = 1.4                    * [-]        (or give cp [J/(kg K)] instead)
    T_min = 63.151, T_max = 600      [K] where constant cp and gamma are good (thermo range)

    [transport]
    viscosity = { law = "sutherland", ref = 1.6766e-5, T_ref = 273.15, S = 116.1 }    *
    conductivity = { law = "sutherland", ref = 0.02425, T_ref = 273.15, S = 163.6 }    (optional:
                                     without it, k = mu cp / Pr)
    prandtl = 0.717                * [-]
    T_min = 100, T_max = 1000        [K] where the laws agree with the source data
    max_error_percent = 3.1          largest deviation from the source data in that range

    [critical]                       for the ideal-gas (compressibility) check and real-gas models
    T = 126.192                      [K]
    p = 3.3958e6                     [Pa]
    acentric_factor = 0.0372         [-]

    [vapour_pressure]                saturation curve: T [K] ascending from the triple point, p [Pa]
    T = [...]
    p = [...]

    [nasa7]                          NASA 7-coefficient polynomials (for a later thermally perfect gas)
    T = [200.0, 1000.0, 3500.0]      [K] low, middle, high
    low = [a1, ..., a7]              cp/R = a1 + a2 T + a3 T^2 + a4 T^3 + a5 T^4 (T_low ... T_mid)
    high = [a1, ..., a7]             (T_mid ... T_high)

    [reference]                      source data the tests compare with (arrays, same length)
    T = [...], cp = [...], cv = [...], mu = [...], k = [...]
"""

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from aeroflowsim.gases.model import R_UNIVERSAL, TransportLaw

UNLIMITED = (0.0, math.inf)   # temperature range when the data file gives none [K]


@dataclass
class VapourPressure:
    """Saturation curve p_sat(T) from tabulated points (T ascending, from the triple point).

    Between the points, ln p is interpolated linearly in 1/T (the Clausius-Clapeyron form, nearly
    exact over short intervals). Below the first point (the triple point) the curve is continued with
    the slope of the first interval, i.e. Clausius-Clapeyron with the vaporisation enthalpy at the
    triple point: an ESTIMATE of the sublimation curve. The true one is steeper (its enthalpy is the
    vaporisation PLUS the fusion enthalpy, about 10 % more for N2), so the true frost point is higher:
    about 0.6 K for N2 at 3.4 kPa, more for gases with a large fusion enthalpy (CO2) or far below the
    triple point. A margin computed from this curve is therefore an upper limit.
    Above the last point (the critical point) the gas cannot condense.
    """

    T: np.ndarray       # [K]
    p: np.ndarray       # [Pa]
    source: str = ""

    def __post_init__(self):
        self.T = np.asarray(self.T, dtype=float)
        self.p = np.asarray(self.p, dtype=float)
        if len(self.T) < 2 or len(self.T) != len(self.p) or np.any(np.diff(self.T) <= 0) or np.any(self.p <= 0):
            raise ValueError("vapour_pressure needs at least 2 points with T ascending and p > 0.")
        self._x = 1.0 / self.T                       # 1/T, descending
        self._y = np.log(self.p)
        self._slope_low = (self._y[1] - self._y[0]) / (self._x[1] - self._x[0])   # = -h_vap / R_specific [K]

    @property
    def T_triple(self) -> float:
        return float(self.T[0])

    @property
    def T_critical(self) -> float:
        return float(self.T[-1])

    def p_sat(self, T):
        """Saturation pressure [Pa] at T [K]; inf above the critical temperature (no condensation)."""
        T = np.asarray(T, dtype=float)
        x = 1.0 / T
        inside = np.interp(-x, -self._x, self._y)                     # np.interp needs ascending x
        below = self._y[0] + self._slope_low * (x - self._x[0])       # extrapolated below the triple point
        lnp = np.where(T < self.T[0], below, inside)
        return np.where(T > self.T[-1], np.inf, np.exp(lnp))

    def T_sat(self, p):
        """Saturation (or estimated frost) temperature [K] at pressure p [Pa]; nan above p_critical."""
        p = np.asarray(p, dtype=float)
        y = np.log(p)
        inside = 1.0 / np.interp(y, self._y, self._x)                  # ln p ascending with T
        below = 1.0 / (self._x[0] + (y - self._y[0]) / self._slope_low)
        T = np.where(p < self.p[0], below, inside)
        return np.where(p > self.p[-1], np.nan, T)

    def extrapolated(self, T) -> bool:
        """True if any temperature lies below the tabulated curve (triple point)."""
        return bool(np.any(np.asarray(T) < self.T[0]))


@dataclass
class GasData:
    """Everything stored about one gas (see the module docstring for the file format)."""

    id: str
    name: str
    R: float                                   # [J/(kg K)]
    gamma: float                               # [-]
    viscosity: TransportLaw
    prandtl: float                             # [-]
    molar_mass: float = math.nan               # [kg/mol]
    formula: str = ""
    model: str = "calorically perfect"
    note: str = ""
    conductivity: TransportLaw | None = None
    thermo_range: tuple = UNLIMITED            # [K]
    transport_range: tuple = UNLIMITED         # [K]
    transport_error_percent: float | None = None
    T_critical: float | None = None            # [K]
    p_critical: float | None = None            # [Pa]
    acentric_factor: float | None = None       # [-]
    vapour_pressure: VapourPressure | None = None
    nasa7: dict | None = None
    reference: dict | None = None              # source data points for the tests
    sources: dict = field(default_factory=dict)   # {what: source text}
    path: Path | None = None                   # file it was read from
    builtin: bool = False

    @property
    def cp(self) -> float:
        return self.gamma * self.R / (self.gamma - 1.0)

    @property
    def has_critical_point(self) -> bool:
        return None not in (self.T_critical, self.p_critical, self.acentric_factor)


def _number(table, key, where, positive=True):
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: '{key}' must be a number.")
    if positive and not value > 0:
        raise ValueError(f"{where}: '{key}' must be positive.")
    return float(value)


def _law(table, where):
    if not isinstance(table, dict):
        raise ValueError(f"{where} must look like {{ law = \"sutherland\", ref = ..., T_ref = ..., S = ... }}.")
    law = table.get("law", "")
    if law not in ("sutherland", "power"):
        raise ValueError(f"{where}: law must be 'sutherland' or 'power'.")
    return TransportLaw(law=law, ref=_number(table, "ref", where), T_ref=_number(table, "T_ref", where),
                        S=_number(table, "S", where, positive=False) if law == "sutherland" else 0.0,
                        n=_number(table, "n", where, positive=False) if law == "power" else 0.0)


def _range(table, where):
    if "T_min" not in table and "T_max" not in table:
        return UNLIMITED
    lo, hi = _number(table, "T_min", where), _number(table, "T_max", where)
    if not lo < hi:
        raise ValueError(f"{where}: T_min must be smaller than T_max.")
    return (lo, hi)


def parse_gas(data: dict, path=None, builtin=False) -> GasData:
    """GasData from the dict of a gas TOML file; ValueError with a 'what to fix' message."""
    where = Path(path).name if path else "gas data"
    for key in ("id", "name"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"{where}: '{key}' (text) is missing.")
    model = data.get("model", "calorically perfect")
    if model != "calorically perfect":
        raise ValueError(f"{where}: model '{model}' is not available yet (only 'calorically perfect').")
    const = data.get("constants") or {}
    sources = {k[: -len("_source")]: v for k, v in const.items() if k.endswith("_source")}
    molar_mass = _number(const, "molar_mass", f"{where} [constants]") if "molar_mass" in const else math.nan
    if "R" in const:
        R = _number(const, "R", f"{where} [constants]")
    elif molar_mass == molar_mass:
        R = R_UNIVERSAL / molar_mass
    else:
        raise ValueError(f"{where} [constants]: give the molar mass [kg/mol] or the gas constant R [J/(kg K)].")
    if molar_mass != molar_mass:
        molar_mass = R_UNIVERSAL / R
    if "gamma" in const:
        gamma = _number(const, "gamma", f"{where} [constants]")
    elif "cp" in const:
        cp = _number(const, "cp", f"{where} [constants]")
        if not cp > R:
            raise ValueError(f"{where} [constants]: cp must be larger than R = {R:.4g} J/(kg K).")
        gamma = cp / (cp - R)
    else:
        raise ValueError(f"{where} [constants]: give gamma or cp.")
    if not 1.0 < gamma <= 5.0 / 3.0 + 1e-6:      # (a rounded 5/3 such as 1.6666667 is allowed)
        raise ValueError(f"{where} [constants]: gamma must lie between 1 and 5/3 (monatomic gas), got {gamma:g}.")
    transport = data.get("transport") or {}
    if "viscosity" not in transport or "prandtl" not in transport:
        raise ValueError(f"{where}: [transport] needs a viscosity law and a prandtl number.")
    viscosity = _law(transport["viscosity"], f"{where} [transport] viscosity")
    conductivity = _law(transport["conductivity"], f"{where} [transport] conductivity") \
        if "conductivity" in transport else None
    prandtl = _number(transport, "prandtl", f"{where} [transport]")
    if "source" in transport:
        sources["transport"] = transport["source"]
    gas = GasData(id=data["id"].strip(), name=data["name"].strip(), R=R, gamma=gamma, viscosity=viscosity,
                  prandtl=prandtl, molar_mass=molar_mass, formula=data.get("formula", ""), model=model,
                  note=data.get("note", "").strip(), conductivity=conductivity,
                  thermo_range=_range(const, f"{where} [constants]"),
                  transport_range=_range(transport, f"{where} [transport]"),
                  transport_error_percent=transport.get("max_error_percent"),
                  sources=sources, path=Path(path) if path else None, builtin=builtin)
    critical = data.get("critical")
    if critical:
        gas.T_critical = _number(critical, "T", f"{where} [critical]")
        gas.p_critical = _number(critical, "p", f"{where} [critical]")
        gas.acentric_factor = _number(critical, "acentric_factor", f"{where} [critical]", positive=False)
        sources["critical"] = critical.get("source", "")
    vapour = data.get("vapour_pressure")
    if vapour:
        try:
            gas.vapour_pressure = VapourPressure(vapour["T"], vapour["p"], vapour.get("source", ""))
        except (KeyError, ValueError) as error:
            raise ValueError(f"{where} [vapour_pressure]: {error}") from None
        sources["vapour_pressure"] = vapour.get("source", "")
    if data.get("nasa7"):
        gas.nasa7 = dict(data["nasa7"])
        sources["nasa7"] = gas.nasa7.get("source", "")
    if data.get("reference"):
        gas.reference = dict(data["reference"])
    return gas


def read_gas_file(path, builtin=False) -> GasData:
    """Read one gas TOML file; ValueError naming the file if it is invalid."""
    path = Path(path)
    try:
        with open(path, "rb") as file:
            data = tomllib.load(file)
    except FileNotFoundError:
        raise ValueError(f"Gas file not found: {path}") from None
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"{path.name}: {error}") from None
    return parse_gas(data, path, builtin)


def _toml_value(value) -> str:
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml_value(v)}" for k, v in value.items()) + " }"
    return repr(float(value)) if isinstance(value, float) else str(value)


def custom_gas_toml(name, gid, R=None, molar_mass=None, gamma=None, cp=None, viscosity=None, prandtl=0.71,
                    note="", critical=None) -> str:
    """The TOML text of a custom gas (the form of the GUI writes this). viscosity: dict of a law;
    critical: optional (T_critical [K], p_critical [Pa], acentric factor [-]) for the ideal-gas check."""
    lines = ["# Custom gas made with AeroFlowSim (calorically perfect gas).", "",
             f"id = {_toml_value(gid)}", f"name = {_toml_value(name)}", 'model = "calorically perfect"']
    if note:
        lines.append(f"note = {_toml_value(note)}")
    lines += ["", "[constants]"]
    if molar_mass is not None:
        lines.append(f"molar_mass = {_toml_value(float(molar_mass))}   # kg/mol")
    if R is not None:
        lines.append(f"R = {_toml_value(float(R))}   # J/(kg K)")
    if gamma is not None:
        lines.append(f"gamma = {_toml_value(float(gamma))}")
    if cp is not None:
        lines.append(f"cp = {_toml_value(float(cp))}   # J/(kg K)")
    lines += ["constants_source = \"entered by the user\"", "", "[transport]",
              f"viscosity = {_toml_value(viscosity)}", f"prandtl = {_toml_value(float(prandtl))}",
              'source = "entered by the user"', ""]
    if critical is not None:
        T_c, p_c, omega = (float(x) for x in critical)
        lines += ["[critical]", f"T = {_toml_value(T_c)}   # K", f"p = {_toml_value(p_c)}   # Pa",
                  f"acentric_factor = {_toml_value(omega)}", 'source = "entered by the user"', ""]
    text = "\n".join(lines)
    parse_gas(tomllib.loads(text))            # never write a file that cannot be read back
    return text

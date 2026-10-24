# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Units for display: the user chooses a unit per quantity (length in mm, pressure in kPa, ...);
everything is still STORED and COMPUTED in SI. Only the GUI converts, when it shows a number and when
it reads a typed one. Project files, the command line, summary.yaml and the validation report stay SI.

A unit converts with  value_SI = value * scale / divide + offset  (and back). Every factor is exact
by definition (inch = 0.0254 m, pound = 0.45359237 kg, standard gravity 9.80665 m/s² for the
pound-force). Single numbers (what the user types and reads) are converted in DECIMAL arithmetic from
their shortest decimal form, then rounded once: 0.28 mm gives exactly the float 0.00028 that a user
typing metres gets (plain float arithmetic gives 0.28 / 1000 = 0.00028000000000000003). Arrays
(plots, CSV columns) use ordinary float arithmetic.

Which numbers are converted is decided by their SI unit text, as written in schema.toml and in the
results: "m" -> length, "Pa" -> pressure, "K" -> temperature, "kg/s" -> mass flow, "N" -> force,
"m²" -> area, "m/s" -> velocity. Other units (deg, -, J/(kg K), kg/m³ ...) are shown as they are.
"""

from dataclasses import dataclass
from decimal import Decimal

import numpy as np

INCH = 0.0254                  # [m] (exact)
POUND = 0.45359237             # [kg] (exact)
G0 = 9.80665                   # [m/s²] standard gravity (exact)
PSI = POUND * G0 / INCH**2     # [Pa] = 6894.757...


@dataclass(frozen=True)
class Unit:
    name: str                  # shown, e.g. "mm"
    quantity: str              # e.g. "length"
    scale: float = 1.0
    divide: float = 1.0
    offset: float = 0.0        # only temperatures (degC)

    def _decimal(self, value, forward):
        d = lambda x: Decimal(repr(float(x)))           # the shortest decimal that is this float
        if not np.isfinite(value):
            return float(value * self.scale / self.divide + self.offset if forward
                         else (value - self.offset) * self.divide / self.scale)
        if forward:
            return float(d(value) * d(self.scale) / d(self.divide) + d(self.offset))
        return float((d(value) - d(self.offset)) * d(self.divide) / d(self.scale))

    def to_si(self, value):
        """Value in this unit -> SI (numbers or arrays)."""
        if np.ndim(value) == 0:
            return self._decimal(float(value), True)
        return np.asarray(value, dtype=float) * self.scale / self.divide + self.offset

    def from_si(self, value):
        """SI value -> this unit (numbers or arrays)."""
        if np.ndim(value) == 0:
            return self._decimal(float(value), False)
        return (np.asarray(value, dtype=float) - self.offset) * self.divide / self.scale


def _units(quantity, *rows):
    return {row[0]: Unit(row[0], quantity, *row[1:]) for row in rows}


QUANTITIES = {   # quantity: (SI unit, {name: Unit}) - the first unit is the SI one
    "length": ("m", _units("length", ("m",), ("mm", 1.0, 1e3), ("µm", 1.0, 1e6), ("in", INCH))),
    "pressure": ("Pa", _units("pressure", ("Pa",), ("kPa", 1e3), ("MPa", 1e6), ("bar", 1e5), ("psi", PSI))),
    "temperature": ("K", _units("temperature", ("K",), ("°C", 1.0, 1.0, 273.15))),
    "mass flow": ("kg/s", _units("mass flow", ("kg/s",), ("g/s", 1.0, 1e3), ("mg/s", 1.0, 1e6), ("lb/s", POUND))),
    "force": ("N", _units("force", ("N",), ("mN", 1.0, 1e3), ("µN", 1.0, 1e6), ("lbf", POUND * G0))),
    "area": ("m²", _units("area", ("m²",), ("mm²", 1.0, 1e6), ("cm²", 1.0, 1e4), ("in²", INCH**2))),
    "velocity": ("m/s", _units("velocity", ("m/s",), ("km/s", 1e3), ("ft/s", 0.3048))),
}
QUANTITY_OF = {si: quantity for quantity, (si, _) in QUANTITIES.items()}       # "Pa" -> "pressure"

SI = {q: si for q, (si, _) in QUANTITIES.items()}
SMALL_PROPULSION = {"length": "mm", "pressure": "kPa", "temperature": "K", "mass flow": "mg/s",
                    "force": "mN", "area": "mm²", "velocity": "m/s"}
IMPERIAL = {"length": "in", "pressure": "psi", "temperature": "K", "mass flow": "lb/s", "force": "lbf",
            "area": "in²", "velocity": "ft/s"}
PRESETS = {"Small propulsion (mm, kPa, mg/s, mN)": SMALL_PROPULSION, "SI (m, Pa, kg/s, N)": SI,
           "Imperial (in, psi, lb/s, lbf)": IMPERIAL}
DEFAULTS = SMALL_PROPULSION


SCALABLE_UNITS = ("Pa", "N", "W", "J", "m", "m²", "kg/s")   # SI units written with k / m / µ prefixes
PREFIXES = ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"))
AREA_PREFIXES = ((1.0, ""), (1e-6, "m"), (1e-12, "µ"))         # m², mm², µm²


def prefixed(value, unit, digits=4, scalable=SCALABLE_UNITS):
    """(value text, unit) in SI with a prefix that keeps the number between 1 and 1000, e.g.
    3369.88 Pa -> ("3.37", "kPa"), 7.16e-5 kg/s -> ("71.6", "mg/s"), 2.8e-4 m -> ("280", "µm"),
    6.16e-8 m² -> ("0.06158", "mm²"). digits = significant digits; scalable = which units may get a
    prefix (others keep their unit). Used where no unit preference applies (command line, SI text)."""
    value = float(value)
    if unit not in scalable or value == 0.0 or not np.isfinite(value):
        return f"{value:.{digits}g}", "" if unit == "-" else unit
    if unit == "m²":                         # area: the prefix is squared (1 mm² = 1e-6 m²)
        for factor, prefix in AREA_PREFIXES:
            if abs(value) >= 1e-2 * factor or factor == AREA_PREFIXES[-1][0]:
                return f"{value / factor:.{digits}g}", f"{prefix}m²"
    if unit == "kg/s":                       # prefixes go on the gram: g/s, mg/s, ...
        if abs(value) >= 1.0:
            return f"{value:.{digits}g}", "kg/s"
        value, unit = value * 1e3, "g/s"
    for factor, prefix in PREFIXES:
        if abs(value) >= factor or factor == PREFIXES[-1][0]:
            return f"{value / factor:.{digits}g}", prefix + unit


@dataclass(frozen=True)
class Quantity:
    """A number with its SI unit inside a message (e.g. a check message): written in SI with a readable
    prefix by default, or in the user's chosen unit. delta = a difference (temperature margins: a
    difference in degC equals one in K, so no 273.15 offset)."""

    value: float
    unit: str
    digits: int = 4
    delta: bool = False

    def text(self, prefs=None) -> str:
        unit = prefs.unit_for(self.unit) if prefs is not None else None
        if unit is not None and np.isfinite(self.value):
            shown = self.value * unit.divide / unit.scale if self.delta else unit.from_si(self.value)
            return f"{shown:.{self.digits}g} {unit.name}"
        number, name = prefixed(self.value, self.unit, self.digits)
        return f"{number} {name}".strip()

    def as_dict(self) -> dict:
        return {"value": float(self.value), "unit": self.unit, "digits": self.digits, "delta": self.delta}


class UnitPreferences:
    """The chosen display unit per quantity; converts SI numbers for display and typed numbers back."""

    def __init__(self, choices=None):
        self.choices = dict(DEFAULTS)
        for quantity, name in (choices or {}).items():
            self.set(quantity, name)

    def set(self, quantity, name):
        if quantity not in QUANTITIES or name not in QUANTITIES[quantity][1]:
            raise ValueError(f"unknown unit '{name}' for {quantity}.")
        self.choices[quantity] = name

    def unit_for(self, si_unit) -> Unit | None:
        """The display Unit for numbers whose SI unit is si_unit, or None (shown unconverted)."""
        quantity = QUANTITY_OF.get(si_unit)
        return QUANTITIES[quantity][1][self.choices[quantity]] if quantity else None

    def display(self, value, si_unit):
        """(value in the display unit, unit text) for an SI value (number or array)."""
        unit = self.unit_for(si_unit)
        return (value, si_unit) if unit is None else (unit.from_si(value), unit.name)

    def to_si(self, value, si_unit):
        """A number typed in the display unit -> SI."""
        unit = self.unit_for(si_unit)
        return value if unit is None else unit.to_si(value)

    def label(self, si_unit) -> str:
        unit = self.unit_for(si_unit)
        return si_unit if unit is None else unit.name

    def as_dict(self) -> dict:
        return dict(self.choices)

    def __eq__(self, other):
        return isinstance(other, UnitPreferences) and other.choices == self.choices

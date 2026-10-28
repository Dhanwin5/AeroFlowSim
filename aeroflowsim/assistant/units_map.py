# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Units a proposal may use, converted to the unit schema.toml gives the input.

Reuses the unit table of the GUI (aeroflowsim/units.py) and adds a few common ones (atm, cm, ft, kN,
degrees and radians). A proposal's unit must belong to the same QUANTITY as the input's unit (a pressure
cannot be proposed for a temperature); an unknown unit is rejected, never guessed.
"""

import math

from aeroflowsim.units import QUANTITIES, QUANTITY_OF, Unit

ANGLE = {"deg": Unit("deg", "angle"), "rad": Unit("rad", "angle", 180.0 / math.pi)}   # "SI" unit: degrees
EXTRA = [Unit("atm", "pressure", 101325.0), Unit("cm", "length", 1.0, 100.0), Unit("ft", "length", 0.3048),
         Unit("kN", "force", 1e3)]

UNITS = {}                                          # exact name -> Unit
for _quantity, (_si, _table) in QUANTITIES.items():
    UNITS.update(_table)
UNITS.update(ANGLE)
UNITS.update({u.name: u for u in EXTRA})
ALIASES = {"degrees": "deg", "degree": "deg", "°": "deg", "radians": "rad", "radian": "rad", "c": "°C",
           "celsius": "°C", "degc": "°C", "kelvin": "K", "um": "µm", "micron": "µm", "psia": "psi",
           "lbs/s": "lb/s", "m^2": "m²", "mm^2": "mm²"}
LOWER = {name.lower(): unit for name, unit in UNITS.items()}
LOWER.update({alias: UNITS[target] for alias, target in ALIASES.items()})


def find_unit(text):
    """The Unit named by text (exact spelling first, then ignoring case), or None."""
    text = str(text).strip().replace("degC", "°C")
    return UNITS.get(text) or LOWER.get(text.lower())


def dimension_of(schema_unit: str) -> str:
    """Quantity of an input's unit: 'pressure', 'length', ..., 'angle', 'dimensionless' or 'unit:<the unit>'."""
    if schema_unit in ("", "-"):
        return "dimensionless"
    if schema_unit in ANGLE:
        return "angle"
    return QUANTITY_OF.get(schema_unit, f"unit:{schema_unit}")


def to_schema_unit(value, unit_text, schema_unit):
    """Convert a value written in unit_text to the input's unit. Raises ValueError for a wrong or missing unit."""
    dimension = dimension_of(schema_unit)
    unit_text = str(unit_text or "").strip()
    if dimension == "dimensionless":
        if unit_text in ("", "-"):
            return float(value)
        raise ValueError(f"this input has no unit, but the proposal gives '{unit_text}'.")
    if dimension.startswith("unit:"):               # a unit we cannot convert: it must be written exactly
        if unit_text == schema_unit:
            return float(value)
        raise ValueError(f"the unit must be '{schema_unit}', not '{unit_text or 'missing'}'.")
    if not unit_text:
        raise ValueError(f"a unit is needed ({dimension}, e.g. {schema_unit}).")
    unit = find_unit(unit_text)
    if unit is None:
        raise ValueError(f"unknown unit '{unit_text}'.")
    if unit.quantity != dimension:
        raise ValueError(f"'{unit_text}' is a unit of {unit.quantity}, but this input is a {dimension} ({schema_unit}).")
    return float(unit.to_si(float(value)))


def readings_of(number: float, dimension: str) -> list[float]:
    """The number read in every unit of a quantity, in the schema unit: 300 -> 300 Pa, 3e5 Pa (bar), ...

    Used to check that a model's value can be traced back to a number the user wrote."""
    units = [u for u in UNITS.values() if u.quantity == dimension]
    return [float(u.to_si(number)) for u in units] if units else [float(number)]

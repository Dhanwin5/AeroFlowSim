# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Definition of a case input ("parameter") and helpers to get defaults and check values.

A case lists its inputs in its schema.toml file (read by aeroflowsim/schema.py into a list of
Parameter objects). The GUI uses this list to draw input boxes automatically, and the
command-line runner uses it to get the default values and check typed values.

Input types:
    "float"   a real number with a unit and an allowed range [min, max] (the usual type)
    "int"     a whole number with an allowed range, e.g. the number of cells
    "bool"    yes / no (a checkbox in the GUI)
    "choice"  one text option out of a list, e.g. the geometry source
    "file"    the path of a file, e.g. a wall-profile CSV
An input can be shown only when another input has a given value (show_if), e.g. the CSV file
only when the geometry source is "Custom profile (CSV)".
"""

from dataclasses import dataclass

TYPES = ("float", "int", "bool", "choice", "file")
NUMBER_TYPES = ("float", "int")


@dataclass
class Parameter:
    """One user input of a case, e.g. the length of a rod."""

    name: str      # short name used in code (the "key" in schema.toml), e.g. "L"
    label: str     # human-readable name shown in the GUI, e.g. "Rod length"
    unit: str      # SI unit as text, e.g. "m" ("-" for dimensionless, "" for text inputs)
    default: object  # default value (float, int, bool or text, depending on the type)
    min: float | None = None   # smallest allowed value (numbers only)
    max: float | None = None   # largest allowed value (numbers only)
    help: str = ""  # one-sentence explanation shown as a tooltip in the GUI
    type: str = ""  # one of TYPES; "" = guess from the default (bool, int or float)
    options: tuple = ()           # allowed values of a "choice"
    show_if: tuple | None = None  # (other parameter name, value): show only when it has that value
    group: str = ""               # heading the GUI puts this input under, e.g. "Geometry"

    def __post_init__(self):
        if not self.type:   # guess the type from the default value (bool first: True is also an int)
            if isinstance(self.default, bool):
                self.type = "bool"
            elif isinstance(self.default, int):
                self.type = "int"
            else:
                self.type = "float"
        if self.type not in TYPES:
            raise ValueError(f"Input '{self.name}': unknown type '{self.type}' (use one of {', '.join(TYPES)}).")

    @property
    def is_number(self) -> bool:
        """True for "float" and "int" inputs (they have a unit and a range)."""
        return self.type in NUMBER_TYPES

    @property
    def is_integer(self) -> bool:
        """True when the input must be a whole number (e.g. number of mesh nodes)."""
        return self.type == "int"


def choice_parameter(name, label, options, default, help="", show_if=None, group="") -> Parameter:
    """An input that is one of a few text options."""
    return Parameter(name, label, "", default, None, None, help, type="choice",
                     options=tuple(options), show_if=show_if, group=group)


def file_parameter(name, label, default, help="", show_if=None, group="") -> Parameter:
    """An input that is a file path (relative paths are read from the project folder)."""
    return Parameter(name, label, "", default, None, None, help, type="file", show_if=show_if, group=group)


def is_shown(p: Parameter, values: dict) -> bool:
    """True if parameter p should be shown, given the current values of all parameters."""
    if p.show_if is None:
        return True
    other, wanted = p.show_if
    return values.get(other) == wanted


def defaults(param_list: list[Parameter]) -> dict:
    """Return {name: default value} for a list of parameters."""
    return {p.name: p.default for p in param_list}


def clean_value(p: Parameter, value):
    """Check one value of parameter p and return it with the right Python type.

    Raises ValueError with a readable message if the value is not allowed.
    """
    if p.type == "choice":
        if value not in p.options:
            raise ValueError(f"'{p.name}' ({p.label}) = '{value}' is not one of: {', '.join(p.options)}.")
        return value
    if p.type == "file":
        value = str(value).strip()
        if not value:
            raise ValueError(f"'{p.name}' ({p.label}): please give a file.")
        return value
    if p.type == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"'{p.name}' ({p.label}) must be true or false, got {value!r}.")
        return value
    # float or int
    if isinstance(value, bool):   # True/False is not a number here
        raise ValueError(f"'{p.name}' ({p.label}) must be a number, got {value!r}.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{p.name}' ({p.label}) must be a number, got {value!r}.") from None
    if p.is_integer:
        if number != int(number):
            raise ValueError(f"'{p.name}' ({p.label}) must be a whole number, got {value}.")
        number = int(number)
    if not (p.min <= number <= p.max):
        raise ValueError(f"'{p.name}' ({p.label}) = {number} {p.unit} is outside the allowed range "
                         f"[{p.min}, {p.max}] {p.unit}.")
    return number


def check_values(param_list: list[Parameter], values: dict) -> dict[str, str]:
    """Check every value; return {name: problem message} (an empty dict means all values are fine).

    Unlike validate(), this collects ALL problems, so the GUI can show each message next to its box.
    """
    problems = {}
    for p in param_list:
        if p.name not in values:
            problems[p.name] = f"Missing parameter '{p.name}' ({p.label})."
            continue
        try:
            clean_value(p, values[p.name])
        except ValueError as error:
            problems[p.name] = str(error)
    return problems


def validate(param_list: list[Parameter], values: dict) -> dict:
    """Check that every parameter has an allowed value (numbers inside [min, max]).

    Returns a clean copy of the values (integers converted to int).
    Raises ValueError with a readable message for the first problem found.
    """
    clean = {}
    for p in param_list:
        if p.name not in values:
            raise ValueError(f"Missing parameter '{p.name}' ({p.label}).")
        clean[p.name] = clean_value(p, values[p.name])
    return clean


def parse_value(p: Parameter, text: str):
    """Turn command-line text into a value of the right type for parameter p (checked later)."""
    if p.type == "bool":
        lowered = text.strip().lower()
        if lowered in ("true", "yes", "1", "on"):
            return True
        if lowered in ("false", "no", "0", "off"):
            return False
        raise ValueError(f"'{text}' is not true or false.")
    if not p.is_number:
        return text
    return int(text) if p.is_integer and float(text) == int(float(text)) else float(text)

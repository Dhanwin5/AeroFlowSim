"""Definition of a case input ("parameter") and helpers to get defaults and check values.

A case lists its inputs in parameters(). The GUI uses this list to draw input boxes,
and the command-line runner uses it to get the default values.
"""

from dataclasses import dataclass


@dataclass
class Parameter:
    """One user input of a case, e.g. the length of a rod."""

    name: str      # short name used in code, e.g. "L"
    label: str     # human-readable name shown in the GUI, e.g. "Rod length"
    unit: str      # SI unit as text, e.g. "m" ("-" for dimensionless)
    default: float  # default value; if this is an int, the input is treated as a whole number
    min: float     # smallest allowed value
    max: float     # largest allowed value
    help: str = ""  # one-sentence explanation shown as a tooltip in the GUI

    @property
    def is_integer(self) -> bool:
        """True when the input must be a whole number (e.g. number of mesh nodes)."""
        return isinstance(self.default, int)


def defaults(param_list: list[Parameter]) -> dict:
    """Return {name: default value} for a list of parameters."""
    return {p.name: p.default for p in param_list}


def validate(param_list: list[Parameter], values: dict) -> dict:
    """Check that every parameter has a value inside [min, max].

    Returns a clean copy of the values (integers converted to int).
    Raises ValueError with a readable message if something is wrong.
    """
    clean = {}
    for p in param_list:
        if p.name not in values:
            raise ValueError(f"Missing parameter '{p.name}' ({p.label}).")
        value = values[p.name]
        if p.is_integer:
            if float(value) != int(value):
                raise ValueError(f"'{p.name}' ({p.label}) must be a whole number, got {value}.")
            value = int(value)
        else:
            value = float(value)
        if not (p.min <= value <= p.max):
            raise ValueError(
                f"'{p.name}' ({p.label}) = {value} {p.unit} is outside the allowed range "
                f"[{p.min}, {p.max}] {p.unit}."
            )
        clean[p.name] = value
    return clean

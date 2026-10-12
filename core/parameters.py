"""Definition of a case input ("parameter") and helpers to get defaults and check values.

A case lists its inputs in parameters(). The GUI uses this list to draw input boxes,
and the command-line runner uses it to get the default values.

Three kinds of input:
    "number"  a number with a unit and an allowed range (the usual kind)
    "choice"  one text option out of a list, e.g. the geometry source   -> choice_parameter()
    "file"    the path of a file, e.g. a wall-profile CSV               -> file_parameter()
An input can be shown only when another input has a given value (show_if), e.g. the CSV file
only when the geometry source is "Custom profile (CSV)".
"""

from dataclasses import dataclass


@dataclass
class Parameter:
    """One user input of a case, e.g. the length of a rod."""

    name: str      # short name used in code, e.g. "L"
    label: str     # human-readable name shown in the GUI, e.g. "Rod length"
    unit: str      # SI unit as text, e.g. "m" ("-" for dimensionless, "" for text inputs)
    default: float  # default value; if this is an int, the input is treated as a whole number
    min: float     # smallest allowed value (numbers only)
    max: float     # largest allowed value (numbers only)
    help: str = ""  # one-sentence explanation shown as a tooltip in the GUI
    kind: str = "number"          # "number", "choice" or "file"
    options: tuple = ()           # allowed values of a "choice"
    show_if: tuple | None = None  # (other parameter name, value): show only when it has that value

    @property
    def is_integer(self) -> bool:
        """True when the input must be a whole number (e.g. number of mesh nodes)."""
        return self.kind == "number" and isinstance(self.default, int)


def choice_parameter(name, label, options, default, help="", show_if=None) -> Parameter:
    """An input that is one of a few text options."""
    return Parameter(name, label, "", default, None, None, help, kind="choice",
                     options=tuple(options), show_if=show_if)


def file_parameter(name, label, default, help="", show_if=None) -> Parameter:
    """An input that is a file path (relative paths are read from the project folder)."""
    return Parameter(name, label, "", default, None, None, help, kind="file", show_if=show_if)


def is_shown(p: Parameter, values: dict) -> bool:
    """True if parameter p should be shown, given the current values of all parameters."""
    if p.show_if is None:
        return True
    other, wanted = p.show_if
    return values.get(other) == wanted


def defaults(param_list: list[Parameter]) -> dict:
    """Return {name: default value} for a list of parameters."""
    return {p.name: p.default for p in param_list}


def validate(param_list: list[Parameter], values: dict) -> dict:
    """Check that every parameter has an allowed value (numbers inside [min, max]).

    Returns a clean copy of the values (integers converted to int).
    Raises ValueError with a readable message if something is wrong.
    """
    clean = {}
    for p in param_list:
        if p.name not in values:
            raise ValueError(f"Missing parameter '{p.name}' ({p.label}).")
        value = values[p.name]
        if p.kind == "choice":
            if value not in p.options:
                raise ValueError(f"'{p.name}' ({p.label}) = '{value}' is not one of: "
                                 f"{', '.join(p.options)}.")
        elif p.kind == "file":
            value = str(value).strip()
            if not value:
                raise ValueError(f"'{p.name}' ({p.label}): please give a file.")
        else:
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


def parse_value(p: Parameter, text: str):
    """Turn command-line text into a value of the right type for parameter p (checked later)."""
    if p.kind != "number":
        return text
    return int(text) if p.is_integer and float(text) == int(float(text)) else float(text)

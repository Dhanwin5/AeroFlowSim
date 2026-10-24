# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the input panel shows, decided WITHOUT any window (no Qt import), so it can be unit-tested.

The Qt panel (aeroflowsim/gui/panel.py) only draws what this module decides:
  - one WidgetSpec per input of schema.toml: which kind of box, label with unit, tooltip with the
    allowed range, options of a dropdown and which of them need a package that is not installed;
  - the groups (headings) in the order they first appear in schema.toml;
  - which inputs are visible for the current values (show_if, including nested show_if);
  - the problem message of every bad value (aeroflowsim.parameters.check_values);
  - the units: numbers are shown and typed in the user's chosen units (aeroflowsim/units.py), but the
    values going in and out of the panel are always SI (text_to_value / display_text convert).
A new case or shape therefore needs zero GUI code.
"""

import math
from dataclasses import dataclass, field

from aeroflowsim.parameters import check_values, install_hint, is_shown, module_available
from aeroflowsim.units import Unit, UnitPreferences

NO_GROUP = "Inputs"   # heading for inputs without a group in schema.toml


def float_step(p, unit=None):
    """Step for the arrow keys / wheel of a float input: about 1/10 of the default's order of magnitude
    (in the display unit, when one is given)."""
    convert = (lambda x: x) if unit is None else unit.from_si
    size = abs(convert(p.default)) if p.default != 0 else abs(convert(p.max) - convert(p.min)) / 10.0
    if size <= 0.0:
        return 1.0
    return 10.0 ** (math.floor(math.log10(size)) - 1)


def file_filter(file_types):
    """File-dialog filter for the allowed endings, e.g. ('dat', 'csv') -> 'Allowed files (*.dat *.csv)'."""
    patterns = " ".join(f"*.{t}" for t in file_types)
    return f"Allowed files ({patterns});;All files (*)"


@dataclass(frozen=True)
class WidgetSpec:
    """Everything the GUI needs to draw the box of one input."""

    name: str                  # input key, e.g. "d_throat" or "naca4.digits"
    kind: str                  # "float", "int", "bool", "choice", "text", "file" or "gas"
    label: str                 # shown text, with the unit for numbers, e.g. "Throat diameter [mm]"
    unit: str                  # unit shown (the display unit; "" for non-numbers)
    help: str                  # the help text of schema.toml (shown by the "?" button)
    tooltip: str               # help + allowed range (shown when the mouse rests on the box)
    group: str                 # heading
    step: str                  # workflow step: "geometry", "mesh" or "setup"
    default: object = None     # the template's default value (SI)
    minimum: float | None = None   # allowed range, in the display unit
    maximum: float | None = None
    step_size: float = 1.0     # change per arrow key / wheel notch (numbers, display unit)
    options: tuple = ()        # dropdown options (choice)
    missing: dict = field(default_factory=dict)   # option -> "needs gmsh: install it with ..." (not installed)
    file_filter: str = ""      # file dialog filter (file)
    si_unit: str = ""          # the SI unit of schema.toml (numbers)
    display: Unit | None = None    # the display unit when it differs from SI (None: shown in SI)


def _number(x) -> str:
    """A display number: 12 significant digits at most, so 0.28000000000000003 shows as 0.28."""
    return value_to_text(float(f"{x:.12g}"))


def widget_spec(p, units: UnitPreferences | None = None) -> WidgetSpec:
    """The WidgetSpec of one Parameter (numbers in the chosen units, if any)."""
    common = dict(name=p.name, kind=p.type, help=p.help, group=p.group or NO_GROUP, step=p.step, default=p.default)
    if p.is_number:
        unit = units.unit_for(p.unit) if (units is not None and not p.is_integer) else None
        if unit is not None and unit.name == p.unit:
            unit = None                                   # the chosen unit is the SI one: nothing to convert
        shown = p.unit if unit is None else unit.name
        lo, hi = (p.min, p.max) if unit is None else (unit.from_si(p.min), unit.from_si(p.max))
        tooltip = f"{p.help}\nAllowed range: {_number(lo)} to {_number(hi)} {shown}.".strip()
        return WidgetSpec(label=f"{p.label} [{shown}]", tooltip=tooltip, minimum=lo, maximum=hi, unit=shown,
                          step_size=1.0 if p.is_integer else float_step(p, unit), si_unit=p.unit, display=unit,
                          **common)
    common["unit"] = ""
    if p.type == "choice":
        missing = {option: f"'{option}' needs {package}: install it with  {install_hint(package)}"
                   for option, package in p.requires.items() if not module_available(package)}
        return WidgetSpec(label=p.label, tooltip=p.help, options=tuple(p.options), missing=missing, **common)
    if p.type == "gas":
        return WidgetSpec(label=p.label, tooltip=p.help, **common)
    if p.type == "file":
        tooltip = f"{p.help}\nFile types: {', '.join(p.file_types)}.".strip()
        return WidgetSpec(label=p.label, tooltip=tooltip, file_filter=file_filter(p.file_types), **common)
    return WidgetSpec(label=p.label, tooltip=p.help, **common)   # bool and text


def details(spec: WidgetSpec, value=None, base=None) -> list[tuple[str, str]]:
    """Facts shown in the Details area under the panel: [(label, text)], depending on the input type.
    value (and base, the project folder) are needed for a gas: its properties and their sources."""
    rows = []
    if spec.kind == "gas":
        from aeroflowsim.gui.gas_logic import gas_detail_rows
        rows += gas_detail_rows(value if value is not None else spec.default, base)
    if spec.kind in ("float", "int"):
        unit = "-" if spec.unit in ("", "-") else spec.unit
        stored = f" (stored and computed in {spec.si_unit}, SI; change the unit in View > Units)" if spec.display else ""
        rows.append(("Unit", ("dimensionless (-)" if unit == "-" else unit) + stored))
        rows.append(("Allowed range", f"{_number(spec.minimum)} to {_number(spec.maximum)}"
                     + ("" if unit == "-" else f" {unit}")))
        rows.append(("Type", "whole number" if spec.kind == "int" else "number (e.g. 2.8e-4)"))
    elif spec.kind == "choice":
        options = [f"{o} (needs a package that is not installed)" if o in spec.missing else o for o in spec.options]
        rows.append(("Options", "; ".join(options)))
    elif spec.kind == "bool":
        rows.append(("Type", "yes / no"))
    elif spec.kind == "file":
        rows.append(("File types", spec.file_filter.split(";;")[0].replace("Allowed files ", "")))
    elif spec.kind == "text":
        rows.append(("Type", "text"))
    elif spec.kind == "boundaries":
        rows.append(("Type", "a table: one boundary condition per named boundary of the mesh"))
        return rows + [("Workflow step", spec.step.capitalize())]
    if spec.default is not None:
        default = "yes" if spec.default is True else "no" if spec.default is False else display_text(spec, spec.default)
        rows.append(("Default", default + (f" {spec.unit}" if spec.unit not in ("", "-") else "")))
    rows.append(("Workflow step", spec.step.capitalize()))
    return rows


class PanelModel:
    """The input panel of one case (all inputs, or only those of one workflow step)."""

    def __init__(self, param_list, step=None, units: UnitPreferences | None = None):
        self.all_params = list(param_list)    # show_if may refer to inputs of another step
        self.params = [p for p in self.all_params if step is None or p.step == step]
        self.units = units
        self.specs = [widget_spec(p, units) for p in self.params]

    def spec(self, name) -> WidgetSpec:
        return next(s for s in self.specs if s.name == name)

    def groups(self) -> dict[str, list[WidgetSpec]]:
        """{heading: [WidgetSpec]} in the order the groups first appear in schema.toml."""
        groups = {}
        for s in self.specs:
            groups.setdefault(s.group, []).append(s)
        return groups

    def visible(self, values) -> set[str]:
        """Names of the inputs to show for these values (show_if, nested show_if included)."""
        return {p.name for p in self.params if is_shown(p, values, self.all_params)}

    def visible_groups(self, values) -> list[str]:
        """Headings that have at least one visible input (empty groups are hidden)."""
        shown = self.visible(values)
        return [g for g, specs in self.groups().items() if any(s.name in shown for s in specs)]

    def problems(self, values) -> dict[str, str]:
        """{name: message} for every bad value among this panel's inputs (shown or hidden); a number
        outside its range is described in the display unit, as the user typed it."""
        problems = check_values(self.params, values)
        for spec in self.specs:
            value = values.get(spec.name)
            if spec.name in problems and spec.display is not None and isinstance(value, (int, float)) \
                    and not isinstance(value, bool):
                problems[spec.name] = (f"{spec.label.rsplit(' [', 1)[0]} = {display_text(spec, value)} {spec.unit} is "
                                       f"outside the allowed range {_number(spec.minimum)} to "
                                       f"{_number(spec.maximum)} {spec.unit}.")
        return problems

    def shown_problems(self, values) -> dict[str, str]:
        """Only the problems of visible inputs: the ones the user can see and fix in this panel."""
        shown = self.visible(values)
        return {k: v for k, v in self.problems(values).items() if k in shown}


def text_to_value(spec: WidgetSpec, text: str):
    """Typed text (in the display unit) -> SI value for a number box: a float/int when it reads as a
    number, else the text.

    The text is kept as it is when it is not a number, so check_values gives the usual message
    ("must be a number") instead of the box silently changing what the user typed.
    """
    text = text.strip()
    try:
        number = float(text)
    except ValueError:
        return text
    if spec.kind == "int" and number == int(number):
        return int(number)
    return number if spec.display is None else spec.display.to_si(number)


def display_text(spec: WidgetSpec, value) -> str:
    """SI value -> text in the box, in the display unit (numbers); other values as value_to_text."""
    if spec.display is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return value_to_text(value)
    return _number(spec.display.from_si(value))


def value_to_text(value) -> str:
    """Value -> text for a number box: short, but exact (repr round-trips every float)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, int):
        return str(value)
    short = f"{value:g}"
    return short if float(short) == value else repr(value)

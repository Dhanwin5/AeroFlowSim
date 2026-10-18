# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read a case's schema.toml: its name, description and the list of its inputs.

Every case folder holds a schema.toml file that DESCRIBES the inputs (it contains no code).
The GUI builds its input boxes from it automatically, and the command line uses it for the
defaults, so a new case needs no GUI code at all. TOML is a simple text format; Python reads it
with its built-in module tomllib.

Example (one [case] table, then one [[input]] table per input, in the order shown in the GUI):

    [case]
    name = "Quasi-1D nozzle"          # shown in the case list
    description = "Steady ..."        # one or two sentences
    steady = true                     # true: marched to a steady state (used by the validity checks)
    solver = true                     # optional (default true); false = mesh only, no solver yet
    solver_message = "..."            # optional: shown instead of the Run button when solver = false

    [[input]]
    key = "d_throat"                  # name used in the code: params["d_throat"]
    label = "Throat diameter"         # shown in the GUI
    unit = "m"                        # SI unit ("-" = dimensionless)
    type = "float"                    # float, int, bool, choice or file
    default = 0.280e-3
    min = 1e-6                        # allowed range (float and int only)
    max = 1.0
    group = "Geometry"                # heading in the GUI
    help = "Smallest diameter."       # tooltip
    show_if = { geometry_source = "Parametric (conical)" }   # optional: show only for this choice

A "choice" input lists its options:  options = ["Parametric (conical)", "Custom profile (CSV)"]
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from aeroflowsim.parameters import NUMBER_TYPES, TYPES, Parameter, clean_value

SCHEMA_FILE = "schema.toml"
INPUT_FIELDS = {"key", "label", "unit", "type", "default", "min", "max", "help", "group", "options", "show_if"}


@dataclass
class Schema:
    """Everything schema.toml says about a case."""

    title: str                  # human-readable case name, e.g. "Quasi-1D nozzle"
    description: str            # one or two sentences
    steady: bool                # True: steady case (residual must drop); False: time-accurate case
    inputs: list[Parameter] = field(default_factory=list)   # in the order they appear in the file
    solver: bool = True         # False: the case has no solver yet (mesh only)
    solver_message: str = "This case has no solver yet."   # shown instead of the Run button


def _input_to_parameter(entry: dict, number: int) -> Parameter:
    """Turn one [[input]] table into a Parameter, with a clear message if something is wrong."""
    where = f"input #{number} ('{entry.get('key', '?')}')"
    unknown = set(entry) - INPUT_FIELDS
    if unknown:
        raise ValueError(f"{where}: unknown field(s) {', '.join(sorted(unknown))}.")
    for name in ("key", "label", "type", "default"):
        if name not in entry:
            raise ValueError(f"{where}: missing field '{name}'.")
    kind = entry["type"]
    if kind not in TYPES:
        raise ValueError(f"{where}: type '{kind}' is not one of {', '.join(TYPES)}.")
    if kind in NUMBER_TYPES:
        for name in ("unit", "min", "max"):
            if name not in entry:
                raise ValueError(f"{where}: a {kind} input needs '{name}'.")
        if not entry["min"] <= entry["max"]:
            raise ValueError(f"{where}: min must not be larger than max.")
    if kind == "choice" and not entry.get("options"):
        raise ValueError(f"{where}: a choice input needs a list of 'options'.")
    show_if = entry.get("show_if")
    if show_if is not None:
        if not (isinstance(show_if, dict) and len(show_if) == 1):
            raise ValueError(f"{where}: show_if must look like {{ other_key = \"value\" }}.")
        show_if = next(iter(show_if.items()))
    default = entry["default"]
    if kind == "float" and isinstance(default, int) and not isinstance(default, bool):
        default = float(default)   # TOML reads "1" as an integer; a float input keeps float values
    p = Parameter(name=entry["key"], label=entry["label"], unit=entry.get("unit", ""), default=default,
                  min=entry.get("min"), max=entry.get("max"), help=entry.get("help", ""), type=kind,
                  options=tuple(entry.get("options", ())), show_if=show_if, group=entry.get("group", ""))
    try:
        clean_value(p, default)
    except ValueError as error:
        raise ValueError(f"{where}: the default is not allowed: {error}") from None
    return p


def parse_schema(data: dict) -> Schema:
    """Build a Schema from already-read TOML data (a dict). Raises ValueError if it is invalid."""
    info = data.get("case")
    if not isinstance(info, dict):
        raise ValueError("missing the [case] table (with name, description and steady).")
    for name, kind in (("name", str), ("description", str), ("steady", bool)):
        if not isinstance(info.get(name), kind):
            raise ValueError(f"[case] needs '{name}' ({kind.__name__}).")
    inputs = [_input_to_parameter(entry, i + 1) for i, entry in enumerate(data.get("input", []))]
    keys = [p.name for p in inputs]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ValueError(f"input key(s) used twice: {', '.join(duplicates)}.")
    for p in inputs:
        if p.show_if is not None and p.show_if[0] not in keys:
            raise ValueError(f"input '{p.name}': show_if refers to unknown input '{p.show_if[0]}'.")
    solver = info.get("solver", True)
    if not isinstance(solver, bool):
        raise ValueError("[case] 'solver' must be true or false.")
    message = info.get("solver_message", Schema.solver_message)
    if not isinstance(message, str):
        raise ValueError("[case] 'solver_message' must be text.")
    return Schema(title=info["name"], description=info["description"], steady=info["steady"], inputs=inputs,
                  solver=solver, solver_message=message)


def load_schema(path) -> Schema:
    """Read and check a schema.toml file. Raises ValueError naming the file if it is invalid."""
    path = Path(path)
    try:
        with open(path, "rb") as file:      # tomllib wants the file opened in binary mode
            data = tomllib.load(file)
        return parse_schema(data)
    except FileNotFoundError:
        raise ValueError(f"{path.name} not found in {path.parent}.") from None
    except (tomllib.TOMLDecodeError, ValueError) as error:
        raise ValueError(f"{path.name}: {error}") from None

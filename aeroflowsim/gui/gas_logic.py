# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the gas dropdown, the gas Details and the custom-gas form show, decided WITHOUT a window
(no Qt import), so it is unit-tested directly. The Qt side is in panel.py (dropdown) and
gas_dialog.py (form).

The dropdown lists, in this order: the built-in gases, the gas the project already uses (when it is a
custom gas), the user's own gases ("My gases"), and "New custom gas...". Choosing one of "My gases"
copies its file into the project (Project.import_gas), so the project stays reproducible.
"""

import math
from dataclasses import dataclass
from pathlib import Path

from aeroflowsim.gases import (builtin_gas, builtin_ids, custom_gas_toml, gas_data, is_builtin, read_gas_file,
                               user_gases)
from aeroflowsim.gases.model import R_UNIVERSAL

NEW_GAS = "<new custom gas>"     # item data of the "New custom gas..." entry


@dataclass(frozen=True)
class GasChoice:
    text: str          # shown in the dropdown
    data: str          # built-in id, project-relative path, absolute user-library path, or NEW_GAS
    kind: str          # "builtin", "project", "user" or "new"


def gas_choices(current=None, base=None) -> list[GasChoice]:
    """The dropdown entries (see the module docstring); current = the input's value, base = project folder."""
    choices = [GasChoice(f"{gid} - {builtin_gas(gid).name}", gid, "builtin") for gid in builtin_ids()]
    if current and not is_builtin(current):
        try:
            name = gas_data(current, base).name
        except ValueError:
            name = f"{Path(str(current)).stem} (file missing)"
        choices.append(GasChoice(f"{name} (custom, in this project)", str(current), "project"))
    for path in user_gases():
        try:
            name = read_gas_file(path).name
        except ValueError:
            continue                                  # an unreadable file is simply not offered
        choices.append(GasChoice(f"{name} (my gases)", str(path), "user"))
    choices.append(GasChoice("New custom gas...", NEW_GAS, "new"))
    return choices


def _range(r) -> str:
    return "not given" if r[1] == math.inf else f"{r[0]:g} to {r[1]:g} K"


def gas_detail_rows(value, base=None) -> list[tuple[str, str]]:
    """[(label, text)] for the Details area: the values the gas gives the solver, each with its source."""
    try:
        g = gas_data(value, base)
    except ValueError as error:
        return [("Gas", f"cannot be read: {error}")]
    src = lambda key: f" ({g.sources[key]})" if g.sources.get(key) else ""
    rows = [("Gas", f"{g.name} ({'built-in' if g.builtin else 'custom gas file'})"),
            ("Ratio of specific heats gamma", f"{g.gamma:.6g}{src('gamma')}"),
            ("Specific gas constant R", f"{g.R:.6g} J/(kg K){src('R') or src('molar_mass')}"),
            ("cp (constant)", f"{g.cp:.6g} J/(kg K)"),
            ("Molar mass", f"{g.molar_mass * 1e3:.6g} g/mol"),
            ("Model", f"{g.model} gas, valid {_range(g.thermo_range)}{src('T_range')}"),
            ("Viscosity", g.viscosity.describe("Pa s")),
            ("Conductivity", g.conductivity.describe("W/(m K)") if g.conductivity else f"k = mu cp / Pr"),
            ("Prandtl number", f"{g.prandtl:.4g}"),
            ("Transport laws valid", _range(g.transport_range)
             + (f", within {g.transport_error_percent:g} % of the data" if g.transport_error_percent else "")
             + src("transport"))]
    if g.has_critical_point:
        rows.append(("Critical point", f"{g.T_critical:g} K, {g.p_critical / 1e5:.5g} bar, "
                                       f"acentric factor {g.acentric_factor:g}{src('critical')}"))
    rows.append(("Saturation curve", "stored (condensation check)" if g.vapour_pressure else "none"))
    if g.note:
        rows.append(("Note", g.note))
    rows.append(("Used by the solver", "gamma and R only (inviscid); viscosity and conductivity from Prompt 7 on"))
    return rows


# ---- the custom-gas form ---------------------------------------------------------------------------

FORM_FIELDS = (   # key, label, unit, default
    ("name", "Name", "", "My gas"),
    ("molar_mass", "Molar mass", "g/mol", "28.0134"),
    ("gamma", "Ratio of specific heats gamma", "-", "1.4"),
    ("mu_ref", "Viscosity at the reference temperature", "Pa s", "1.663e-5"),
    ("T_ref", "Reference temperature", "K", "273.15"),
    ("S", "Sutherland temperature S (or exponent n)", "K", "107"),
    ("prandtl", "Prandtl number", "-", "0.71"),
)
SPECIFY = ("Molar mass", "Gas constant R")                 # first choice of the form
HEAT = ("gamma", "cp")                                     # second choice
LAWS = ("Sutherland", "Power law")                         # third choice


def form_from_gas(value, base=None) -> dict:
    """Form fields filled from an existing gas (to make a variant of it)."""
    g = gas_data(value, base)
    law = g.viscosity
    return {"name": f"{g.name} (custom)", "specify": SPECIFY[0], "molar_mass": f"{g.molar_mass * 1e3:.8g}",
            "R": f"{g.R:.8g}", "heat": HEAT[0], "gamma": f"{g.gamma:.8g}", "cp": f"{g.cp:.8g}",
            "law": LAWS[0] if law.law == "sutherland" else LAWS[1], "mu_ref": f"{law.ref:.6g}",
            "T_ref": f"{law.T_ref:g}", "S": f"{law.S if law.law == 'sutherland' else law.n:g}",
            "prandtl": f"{g.prandtl:.4g}"}


def form_to_toml(form: dict) -> tuple[str, str]:
    """(gas name, TOML text) from the form fields; ValueError with a clear message for a bad field."""
    def number(key, label, positive=True):
        try:
            x = float(str(form.get(key, "")).strip())
        except ValueError:
            raise ValueError(f"{label}: please type a number.") from None
        if positive and not x > 0:
            raise ValueError(f"{label} must be positive.")
        return x
    name = str(form.get("name", "")).strip()
    if not name:
        raise ValueError("Please give the gas a name.")
    if is_builtin(name):
        raise ValueError(f"'{name}' is the name of a built-in gas; please choose another name.")
    kw = {}
    if form.get("specify", SPECIFY[0]) == SPECIFY[0]:
        kw["molar_mass"] = number("molar_mass", "Molar mass") * 1e-3          # g/mol -> kg/mol
        R = R_UNIVERSAL / kw["molar_mass"]
    else:
        kw["R"] = R = number("R", "Gas constant R")
    if form.get("heat", HEAT[0]) == HEAT[0]:
        kw["gamma"] = number("gamma", "gamma")
        if not 1.0 < kw["gamma"] <= 5.0 / 3.0 + 1e-6:          # (a rounded 5/3 such as 1.6666667 is fine)
            raise ValueError("gamma must lie between 1 and 5/3 (a monatomic gas has 5/3, air 1.4).")
    else:
        kw["cp"] = number("cp", "cp")
        if not kw["cp"] > R:
            raise ValueError(f"cp must be larger than R = {R:.5g} J/(kg K).")
    T_ref = number("T_ref", "Reference temperature")
    mu_ref = number("mu_ref", "Viscosity")
    if form.get("law", LAWS[0]) == LAWS[0]:
        viscosity = {"law": "sutherland", "ref": mu_ref, "T_ref": T_ref, "S": number("S", "Sutherland temperature S", False)}
        if viscosity["S"] < 0:
            raise ValueError("The Sutherland temperature S must not be negative.")
    else:
        viscosity = {"law": "power", "ref": mu_ref, "T_ref": T_ref, "n": number("S", "Exponent n", False)}
    prandtl = number("prandtl", "Prandtl number")
    gid = "custom-" + "".join(c if c.isalnum() else "_" for c in name)
    return name, custom_gas_toml(name, gid, viscosity=viscosity, prandtl=prandtl, **kw)

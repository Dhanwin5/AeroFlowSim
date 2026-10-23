# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Display units (aeroflowsim/units.py): exact conversions, round trips for every unit, and proof that
choosing other units never changes a stored input or a result (everything stays SI inside)."""

import io

import numpy as np
import pytest

from aeroflowsim.discovery import find_cases, load_case
from aeroflowsim.gui.logic import display_field, key_number_rows, key_result_tiles, readable
from aeroflowsim.gui.panel_model import PanelModel, display_text, text_to_value
from aeroflowsim.parameters import defaults
from aeroflowsim.results import Field, Result
from aeroflowsim.runner import save_fields_csv
from aeroflowsim.units import DEFAULTS, IMPERIAL, PRESETS, QUANTITIES, SI, UnitPreferences

EVERY_UNIT = [(q, name) for q, (_, units) in QUANTITIES.items() for name in units]


@pytest.mark.parametrize("quantity, name", EVERY_UNIT)
def test_round_trip_of_every_unit(quantity, name):
    unit = QUANTITIES[quantity][1][name]
    values = np.array([1e-7, 0.28, 1.0, 293.15, 5e5, 123456.789])
    atol = 1e-9 if unit.offset else 0.0                       # degC: an offset of 273.15 K
    assert np.allclose(unit.to_si(unit.from_si(values)), values, rtol=1e-14, atol=atol)
    assert np.allclose(unit.from_si(unit.to_si(values)), values, rtol=1e-14, atol=atol)
    for x in values:                                          # single numbers (decimal arithmetic)
        assert unit.to_si(unit.from_si(float(x))) == pytest.approx(x, rel=1e-15, abs=atol)
    assert isinstance(unit.to_si(1.0), float)


def test_conversions_against_their_definitions():
    u = lambda q, n: QUANTITIES[q][1][n]
    assert u("length", "mm").to_si(0.28) == 0.00028                    # exactly what a metre user would type
    assert u("length", "in").to_si(1.0) == 0.0254
    assert u("pressure", "kPa").to_si(500.0) == 5e5 and u("pressure", "bar").to_si(3.0) == 3e5
    assert u("pressure", "psi").to_si(1.0) == pytest.approx(6894.757293168, rel=1e-12)
    assert u("temperature", "°C").to_si(20.0) == 293.15 and u("temperature", "°C").from_si(70.33) == pytest.approx(-202.82)
    assert u("mass flow", "mg/s").from_si(71.6e-6) == pytest.approx(71.6)
    assert u("mass flow", "lb/s").to_si(1.0) == 0.45359237
    assert u("force", "mN").from_si(0.0509) == pytest.approx(50.9) and u("force", "lbf").to_si(1.0) == pytest.approx(4.4482216152605)
    assert u("area", "mm²").from_si(6.1575e-8) == pytest.approx(0.061575) and u("area", "in²").to_si(1.0) == pytest.approx(6.4516e-4)
    assert u("velocity", "ft/s").to_si(1.0) == 0.3048 and u("velocity", "km/s").to_si(1.0) == 1000.0


def test_preferences_and_presets():
    prefs = UnitPreferences()
    assert prefs.as_dict() == DEFAULTS == {"length": "mm", "pressure": "kPa", "temperature": "K", "mass flow": "mg/s",
                                           "force": "mN", "area": "mm²", "velocity": "m/s"}
    assert prefs.display(3369.88, "Pa") == (pytest.approx(3.36988), "kPa")
    assert prefs.display(1.4, "-") == (1.4, "-") and prefs.label("deg") == "deg"      # other units unchanged
    assert prefs.to_si(500.0, "Pa") == 5e5
    assert UnitPreferences(SI).display(0.001, "m") == (0.001, "m")
    assert UnitPreferences(IMPERIAL).label("N") == "lbf" and len(PRESETS) == 3
    with pytest.raises(ValueError):
        prefs.set("length", "furlong")


@pytest.mark.parametrize("preset", list(PRESETS.values()) + [{"temperature": "°C", "pressure": "bar"}])
@pytest.mark.parametrize("template", sorted(find_cases()[0]))
def test_changing_units_never_changes_an_input(preset, template):
    """Every default of every template, shown in the chosen units and read back, is the same SI value
    (bit for bit, because unchanged text gives back the value shown: see panel.InputRow._typed_value;
    and also when the shown text is typed again)."""
    case = load_case(template)
    model = PanelModel(case.parameters(), units=UnitPreferences(preset))
    values = defaults(case.parameters())
    for spec in model.specs:
        if spec.kind not in ("float", "int"):
            continue
        typed = text_to_value(spec, display_text(spec, values[spec.name]))
        if spec.display is None or spec.display.name in ("mm", "µm", "kPa", "MPa", "bar", "°C", "g/s", "mg/s"):
            assert typed == values[spec.name], (template, spec.name)            # decimal units: bit for bit
        else:                                                                    # inch, psi: 12 digits shown
            assert typed == pytest.approx(values[spec.name], rel=1e-11, abs=0), (template, spec.name)
        assert model.problems({**values, spec.name: typed}).get(spec.name) is None


def test_panel_shows_display_units_and_explains_range_problems():
    model = PanelModel(load_case("quasi1d_nozzle").parameters(), "setup", UnitPreferences({"temperature": "°C"}))
    spec = model.spec("p0")
    assert spec.label == "Total (chamber) pressure [kPa]" and spec.si_unit == "Pa" and spec.minimum == 0.001
    assert display_text(spec, 5e5) == "500" and text_to_value(spec, "500") == 5e5
    t0 = model.spec("T0")
    assert display_text(t0, 293.15) == "20" and text_to_value(t0, "20") == 293.15
    values = defaults(load_case("quasi1d_nozzle").parameters())
    message = model.problems({**values, "T0": 6000.0})["T0"]
    assert "°C" in message and "4726.85" in message                     # the limit 5000 K in degC
    assert PanelModel(load_case("quasi1d_nozzle").parameters(), units=UnitPreferences()).spec("n_cells").unit == "-"


def test_results_follow_the_preferences_but_stay_si():
    p = Field(np.array([5e5, 3.37e3]), "Pa", "Pressure")
    shown = display_field(p, UnitPreferences())
    assert shown.unit == "kPa" and np.allclose(shown.values, [500.0, 3.37]) and p.values[0] == 5e5   # copy
    assert readable(0.0509131, "N", prefs=UnitPreferences()) == ("50.91", "mN")
    assert readable(293.15, "K", prefs=UnitPreferences({"temperature": "°C"})) == ("20", "°C")
    result = Result(fields={"T": Field(np.array([293.15, 70.0]), "K", "T")}, residuals=[1.0],
                    key_numbers={"M_exit": (3.98, "-"), "mdot": (7.16e-5, "kg/s"), "F_vacuum": (0.0509, "N")})
    tiles = {t[0]: t[1:] for t in key_result_tiles(result, UnitPreferences(SI))}
    assert tiles["Mass flow"] == ("7.16e-05", "kg/s") and tiles["Thrust (vacuum)"] == ("0.0509", "N")
    reference = {"T": Field(np.array([293.15, 69.0]), "K", "T")}
    rows = {r[0]: r[1:] for r in key_number_rows(result, reference, prefs=UnitPreferences({"temperature": "°C"}))}
    assert rows["max |T − T_exact|"] == ("1.000e+00", "°C")              # a difference: no 273.15 offset
    assert rows["mdot"] == ("71.6", "mg/s")


def test_csv_export_in_display_units():
    class Line:
        def positions(self, n):
            return np.array([0.0, 0.002])
    result = Result(fields={"p": Field(np.array([5e5, 3.37e3]), "Pa", "p")}, residuals=[1.0])
    for prefs, header, first in ((None, "x_m,p_Pa", "0.000000000000000000e+00,5.000000000000000000e+05"),
                                 (UnitPreferences(), "x_mm,p_kPa", None)):
        buffer = io.StringIO()
        save_fields_csv(buffer, Line(), result, None, prefs)
        lines = buffer.getvalue().splitlines()
        assert lines[0] == header
        data = np.loadtxt(lines[1:], delimiter=",")
        assert np.allclose(data[1], [0.002, 3370.0] if prefs is None else [2.0, 3.37])

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Units in check messages, the Geometry summary / Properties and the mesh Properties; the optional
critical point of a custom gas (so the ideal-gas check runs for custom gases too)."""

import tomllib

import numpy as np
import pytest

from aeroflowsim import checks
from aeroflowsim.checks import CheckResult
from aeroflowsim.discovery import load_case
from aeroflowsim.gases import gas_model, parse_gas
from aeroflowsim.gui import geometry_logic as logic
from aeroflowsim.gui.gas_logic import form_from_gas, form_to_toml
from aeroflowsim.gui.logic import mesh_1d_rows, mesh_summary_rows
from aeroflowsim.mesh_quality import quality_summary
from aeroflowsim.parameters import defaults
from aeroflowsim.results import Field, Result
from aeroflowsim.units import SI, Quantity, UnitPreferences

Q1D = load_case("quasi1d_nozzle")
DEGC = UnitPreferences({"temperature": "°C", "pressure": "bar"})


def states(T, p, **params):
    values = {"gas": "N2", "p0": 5e5, "T0": 293.15, **params}
    return values, Result(residuals=[], fields={"T": Field(np.asarray(T, float), "K", "T"),
                                                "p": Field(np.asarray(p, float), "Pa", "p")})


# ---- check messages ------------------------------------------------------------------------------

def test_a_check_message_follows_the_units_but_its_stored_text_stays_si():
    params, result = states([293.0, 150.0, 70.3], [5e5, 6e4, 3.37e3])
    check = checks.condensation_risk(Q1D, params, None, result)
    assert "exit: T = 70.3 K at 3.37 kPa" in check.message              # SI text: command line, summary.yaml
    shown = check.text(DEGC)
    assert "exit: T = -202.8 °C at 0.0337 bar" in shown
    assert "margin 13.6 °C" in shown                                    # a margin is a difference: no offset
    assert "0.6 °C" in shown                                            # (0.6 K difference, not -272.55 °C)
    again = CheckResult(**check.as_dict())                              # saved in run.npz and read back
    assert again.text(DEGC) == shown and again.message == check.message
    old = CheckResult(name="Old", level="info", message="saved before 6f")   # old saved results still load
    assert old.text(DEGC) == "saved before 6f"


def test_quantity_text():
    assert Quantity(3.37e3, "Pa").text() == "3.37 kPa"
    assert Quantity(2.8e-4, "m").text(UnitPreferences()) == "0.28 mm"
    assert Quantity(13.6, "K", 3, delta=True).text(DEGC) == "13.6 °C"
    assert Quantity(293.15, "K").text(DEGC) == "20 °C"
    assert Quantity(0.5, "-").text(DEGC) == "0.5"


@pytest.mark.parametrize("check", checks.GAS_CHECKS)
def test_gas_checks_render_in_every_preset(check):
    params, result = states([293.0, 70.3], [5e5, 3.37e3], p0=3e7)
    c = check(Q1D, params, None, result)
    for prefs in (None, UnitPreferences(), UnitPreferences(SI), DEGC):
        text = c.text(prefs)
        assert "{" not in text and "}" not in text


def test_mesh_checks_lengths_follow_the_units():
    case = load_case("nozzle_axi")
    params = defaults(case.parameters())
    mesh = case.build_mesh(params)
    smallest = checks.mesh_smallest_cell(case, params, mesh, None)
    assert smallest.message.endswith("µm thick.")
    inch = UnitPreferences({"length": "in"})
    assert " in thick." in smallest.text(inch) and "µm" not in smallest.text(inch)


# ---- geometry summary / properties and mesh properties --------------------------------------------

def test_geometry_properties_follow_the_units():
    from aeroflowsim.geometry_model import template_document
    from aeroflowsim.geometry_model.operations import Enclosure
    from tests.test_geometry_logic import EXTERNAL, built_of
    doc = template_document(EXTERNAL)
    doc.add(Enclosure())
    built = built_of(doc, EXTERNAL)
    face = next(iter(built.faces))
    mm_rows = {r[0]: r[1:] for r in logic.selection_rows(built, [("face", face)])}
    m_rows = {r[0]: r[1:] for r in logic.selection_rows(built, [("face", face)], UnitPreferences(SI))}
    assert mm_rows["Area"][1] == "mm²" and m_rows["Area"][1] == "m²"
    assert float(mm_rows["Area"][0]) == pytest.approx(float(m_rows["Area"][0]) * 1e6, rel=1e-5)
    assert m_rows["Centroid x, y"][1] == "m"
    shown = logic.Shown(UnitPreferences({"length": "in"}))
    assert shown.volume_text(0.0254**3) == ("1", "in³")


def test_mesh_properties_follow_the_units():
    case = load_case("nozzle_axi")
    mesh = case.build_mesh(defaults(case.parameters()))
    default = dict(mesh_summary_rows(mesh, quality_summary(mesh)))
    si = dict(mesh_summary_rows(mesh, quality_summary(mesh), UnitPreferences(SI)))
    assert default["smallest cell"].endswith("µm") and si["smallest cell"].endswith(" m")
    q1d = load_case("quasi1d_nozzle")
    rows = dict((r[0], r[1]) for r in mesh_1d_rows(q1d.build_mesh(defaults(q1d.parameters())), UnitPreferences()))
    assert rows["smallest spacing"].endswith(" mm")


# ---- custom gas with a critical point --------------------------------------------------------------

def test_custom_gas_with_and_without_a_critical_point():
    form = form_from_gas("N2", prefs=UnitPreferences())                    # kPa
    assert (form["T_c"], form["p_c"], form["omega"]) == ("126.192", "3395.8", "0.0372")
    name, text = form_to_toml({**form, "name": "Lab N2"}, UnitPreferences())
    data = parse_gas(tomllib.loads(text))
    assert data.has_critical_point and data.p_critical == pytest.approx(3.3958e6) and data.T_critical == 126.192
    params, result = states([293.0], [3e7], p0=3e7)
    params["gas"] = data
    custom = type("Case", (), {"gas": staticmethod(lambda p: gas_model(p["gas"])),
                               "reservoir_state": staticmethod(lambda p: (p["p0"], p["T0"]))})
    assert checks.ideal_gas_validity(custom, params, None, result).level == "warning"   # the check now runs
    empty = {**form, "name": "Lab N2", "T_c": "", "p_c": "", "omega": ""}
    data = parse_gas(tomllib.loads(form_to_toml(empty)[1]))
    params["gas"] = data
    message = checks.ideal_gas_validity(custom, params, None, result).message
    assert message.startswith("Cannot run") and "custom-gas form" in message
    with pytest.raises(ValueError, match="AND acentric factor"):
        form_to_toml({**form, "name": "x", "omega": ""})
    with pytest.raises(ValueError, match="between -1 and 2"):
        form_to_toml({**form, "name": "x", "omega": "3"})
    celsius = form_from_gas("N2", prefs=DEGC)                               # the user's units: degC, bar
    assert celsius["T_c"] == "-146.958" and celsius["p_c"] == "33.958"
    assert parse_gas(tomllib.loads(form_to_toml({**celsius, "name": "y"}, DEGC)[1])).T_critical == \
        pytest.approx(126.192, abs=1e-9)


@pytest.mark.parametrize("length, ticks", [("in", ["0", "0.04", "0.08"]), ("mm", ["0", "1", "2", "3"])])
def test_plots_draw_with_ticks_at_round_values_of_the_chosen_length_unit(length, ticks):
    import io
    from aeroflowsim.gui.figures import field_figure
    mesh = Q1D.build_mesh(defaults(Q1D.parameters()))
    figure = field_figure(mesh, Field(np.linspace(0.0, 4.0, mesh.n_cells), "-", "Mach number"), None,
                          UnitPreferences({"length": length}))
    figure.savefig(io.BytesIO())                                          # draws (a broken locator raises here)
    labels = [t.get_text() for t in figure.axes[0].get_xticklabels()]
    assert set(ticks) <= set(labels) and figure.axes[0].get_xlabel() == f"x [{length}]"

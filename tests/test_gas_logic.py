# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the gas dropdown, the gas Details and the custom-gas form show (gui/gas_logic.py, no window)."""

import pytest

from aeroflowsim.gases import gas_model, save_user_gas
from aeroflowsim.gases.library import user_gas_dir
from aeroflowsim.gui.gas_logic import NEW_GAS, form_from_gas, form_to_toml, gas_choices, gas_detail_rows
from aeroflowsim.gui.panel_model import PanelModel, details
from aeroflowsim.discovery import load_case


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))              # macOS: ~/Library/Application Support/AeroFlowSim
    return tmp_path


def test_dropdown_lists_library_project_and_user_gases(library, tmp_path):
    name, text = form_to_toml({**form_from_gas("Ar"), "name": "Argon mix"})
    path = save_user_gas(text, name)
    (tmp_path / "P" / "gases").mkdir(parents=True)
    (tmp_path / "P" / "gases" / "x.toml").write_text(text)
    choices = gas_choices("gases/x.toml", base=tmp_path / "P")
    kinds = [c.kind for c in choices]
    assert kinds[:11] == ["builtin"] * 11 and kinds[11:] == ["project", "user", "new"]
    assert choices[11].text == "Argon mix (custom, in this project)" and choices[12].data == str(path)
    assert choices[-1].data == NEW_GAS
    (user_gas_dir() / "broken.toml").write_text("not = [valid")   # skipped, no crash
    assert len(gas_choices("N2")) == 13
    assert "file missing" in gas_choices("gases/none.toml", base=tmp_path)[11].text


def test_details_show_values_and_sources():
    rows = dict(gas_detail_rows("R236fa"))
    assert rows["Ratio of specific heats gamma"].startswith("1.0713 (cp/cv")
    assert "APPROXIMATION" in rows["Note"] and "398.07 K" in rows["Critical point"]
    spec = PanelModel(load_case("quasi1d_nozzle").parameters(), "setup").spec("gas")
    labels = [label for label, _ in details(spec, "air")]
    assert "Viscosity" in labels and "Workflow step" in labels
    assert dict(details(spec))["Gas"].startswith("Nitrogen")                       # default value
    assert "cannot be read" in dict(gas_detail_rows("gases/none.toml"))["Gas"]


def test_form_round_trip_and_errors():
    name, text = form_to_toml(form_from_gas("N2"))
    from aeroflowsim.gases import parse_gas
    import tomllib
    g = gas_model(parse_gas(tomllib.loads(text)))
    assert name == "Nitrogen (custom)" and g.gamma_value == pytest.approx(1.4)
    assert g.R == pytest.approx(296.803, rel=1e-5)                 # from the molar mass (no tabulated R in a custom gas)
    with_R = form_to_toml({**form_from_gas("N2"), "specify": "Gas constant R", "R": "296.8"})[1]
    assert gas_model(parse_gas(tomllib.loads(with_R))).R == 296.8
    for change, message in (({"name": " "}, "name"), ({"name": "Kr"}, "built-in"), ({"gamma": "2"}, "gamma must"),
                            ({"heat": "cp", "cp": "100"}, "larger than R"), ({"prandtl": "x"}, "number"),
                            ({"S": "-5"}, "negative")):
        with pytest.raises(ValueError, match=message):
            form_to_toml({**form_from_gas("N2"), **change})

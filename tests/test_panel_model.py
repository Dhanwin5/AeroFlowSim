# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The input-panel logic (which widget, which values are valid), tested without any window."""

import pytest

import aeroflowsim.gui.panel_model as panel_model
from aeroflowsim.discovery import find_cases, load_case
from aeroflowsim.gui.panel_model import PanelModel, file_filter, text_to_value, value_to_text, widget_spec
from aeroflowsim.parameters import STEPS, Parameter, defaults
from aeroflowsim.schema import parse_schema


def _params(*entries):
    return parse_schema({"case": {"name": "t", "description": "d", "steady": True}, "input": list(entries)}).inputs


NUMBER = {"key": "L", "label": "Length", "unit": "m", "type": "float", "default": 2.8e-4, "min": 1e-6,
          "max": 1.0, "group": "Geometry", "help": "Rod length.", "step": "geometry"}


def test_float_input_gives_a_number_box_with_unit_range_and_step():
    s = widget_spec(_params(NUMBER)[0])
    assert (s.kind, s.label, s.unit, s.group, s.step) == ("float", "Length [m]", "m", "Geometry", "geometry")
    assert (s.minimum, s.maximum) == (1e-6, 1.0)
    assert s.step_size == pytest.approx(1e-5)          # 1/10 of the default's order of magnitude
    assert "Rod length." in s.tooltip and "Allowed range: 1e-06 to 1 m." in s.tooltip


def test_every_type_gets_its_widget_kind():
    params = _params(
        {"key": "n", "label": "Cells", "unit": "-", "type": "int", "default": 10, "min": 1, "max": 100},
        {"key": "b", "label": "Flag", "type": "bool", "default": True},
        {"key": "c", "label": "Choice", "type": "choice", "default": "a", "options": ["a", "b"]},
        {"key": "t", "label": "Digits", "type": "text", "default": "0012", "pattern": "[0-9]{4}"},
        {"key": "f", "label": "Profile", "type": "file", "default": "x.dat", "file_types": ["dat", "csv"]})
    specs = {p.name: widget_spec(p) for p in params}
    assert {k: s.kind for k, s in specs.items()} == {"n": "int", "b": "bool", "c": "choice", "t": "text", "f": "file"}
    assert specs["n"].label == "Cells [-]" and specs["n"].step_size == 1.0
    assert specs["c"].options == ("a", "b") and specs["c"].missing == {}
    assert specs["f"].file_filter == "Allowed files (*.dat *.csv);;All files (*)"
    assert all(s.step == "setup" for s in specs.values())     # step defaults to "setup"
    assert specs["b"].group == "Inputs"                         # no group -> default heading


def test_option_needing_a_missing_package_is_marked_with_the_install_hint(monkeypatch):
    monkeypatch.setattr(panel_model, "module_available", lambda name: name != "gmsh")
    p = _params({"key": "m", "label": "Mesh", "type": "choice", "default": "S", "options": ["S", "T"],
                 "requires": {"T": "gmsh"}})[0]
    s = widget_spec(p)
    assert list(s.missing) == ["T"]
    assert 'pip install -e ".[mesh]"' in s.missing["T"]


def test_show_if_and_nested_show_if():
    case = load_case("nozzle_axi")
    model = PanelModel(case.parameters())
    values = defaults(case.parameters())
    shown = model.visible(values)
    assert "d_throat" in shown and "profile_csv" not in shown
    assert "mesh_preset" in shown and "nx" not in shown           # nx only for the Custom preset
    values["mesh_preset"] = "Custom"
    assert "nx" in model.visible(values)
    values["mesh_type"] = "Triangles (Gmsh)"                       # preset hidden -> nx hidden too
    shown = model.visible(values)
    assert "mesh_preset" not in shown and "nx" not in shown and "surface_size" in shown
    values["geometry_source"] = "Custom profile (CSV)"
    assert "profile_csv" in model.visible(values) and "d_throat" not in model.visible(values)


def test_groups_in_schema_order_and_empty_groups_hidden():
    case = load_case("nozzle_axi")
    model = PanelModel(case.parameters())
    assert list(model.groups()) == ["Geometry", "Mesh", "Inflation layers"]
    values = defaults(case.parameters())
    assert model.visible_groups(values) == ["Geometry", "Mesh", "Inflation layers"]  # 'inflation' box itself shows


def test_invalid_values_give_messages_only_for_visible_inputs():
    case = load_case("nozzle_axi")
    model = PanelModel(case.parameters())
    values = defaults(case.parameters())
    assert model.problems(values) == {}
    values["d_throat"] = 5.0                     # above max
    values["nx"] = "abc"                         # hidden (preset is Medium)
    assert "outside the allowed range" in model.problems(values)["d_throat"]
    assert "nx" in model.problems(values)
    assert set(model.shown_problems(values)) == {"d_throat"}


def test_panel_per_workflow_step_and_shape_inputs_are_geometry():
    case = load_case("external_2d")
    by_step = {step: PanelModel(case.parameters(), step) for step in STEPS}
    assert sum(len(m.specs) for m in by_step.values()) == len(case.parameters())
    geometry = {s.name for s in by_step["geometry"].specs}
    assert {"shape", "naca4.digits", "cylinder.diameter", "domain_shape"} <= geometry
    assert {"surface_size", "inflation", "n_layers"} <= {s.name for s in by_step["mesh"].specs}
    # show_if across steps still works: the shape inputs follow the shape choice
    values = defaults(case.parameters())
    values["shape"] = "NACA 4-digit airfoil"
    assert "naca4.digits" in by_step["geometry"].visible(values)
    assert "diamond.chord" not in by_step["geometry"].visible(values)


def test_every_case_input_has_a_known_step_and_a_widget():
    cases, problems = find_cases()
    assert not problems
    for case in cases.values():
        for p in case.parameters():
            assert p.step in STEPS
            assert widget_spec(p).kind == p.type


def test_unknown_step_is_rejected():
    with pytest.raises(ValueError, match="step"):
        _params({**NUMBER, "step": "solver"})
    with pytest.raises(ValueError, match="step"):
        Parameter("x", "X", "m", 1.0, 0.0, 2.0, step="results")


def test_text_and_value_conversion_for_number_boxes():
    f = widget_spec(_params(NUMBER)[0])
    i = widget_spec(_params({"key": "n", "label": "N", "unit": "-", "type": "int", "default": 3, "min": 1,
                             "max": 9})[0])
    assert text_to_value(f, " 2.8e-4 ") == 2.8e-4
    assert text_to_value(i, "4") == 4 and isinstance(text_to_value(i, "4"), int)
    assert text_to_value(i, "4.5") == 4.5                 # kept, so the check says "whole number"
    assert text_to_value(f, "abc") == "abc"               # kept, so the check says "must be a number"
    assert value_to_text(0.00028) == "0.00028"
    assert value_to_text(0.1 + 0.2) == repr(0.1 + 0.2)    # never rounds a value away
    assert value_to_text(40) == "40"
    assert file_filter(("csv",)) == "Allowed files (*.csv);;All files (*)"

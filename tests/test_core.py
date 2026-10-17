# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the shared code in aeroflowsim/: parameters, discovery and the runner."""

import pytest

from aeroflowsim.discovery import find_cases
from aeroflowsim.parameters import Parameter, defaults, validate
from aeroflowsim.runner import run_case

PARAMS = [
    Parameter("L", "Length", "m", 1.0, 0.1, 10.0),
    Parameter("n", "Nodes", "-", 11, 3, 101),
]


def test_defaults():
    assert defaults(PARAMS) == {"L": 1.0, "n": 11}


def test_validate_accepts_good_values_and_converts_integers():
    clean = validate(PARAMS, {"L": 2, "n": 21.0})
    assert clean == {"L": 2.0, "n": 21}
    assert isinstance(clean["n"], int)


@pytest.mark.parametrize("values", [
    {"L": 20.0, "n": 11},   # L above max
    {"L": 1.0, "n": 2},     # n below min
    {"L": 1.0, "n": 10.5},  # n not a whole number
    {"L": 1.0},             # n missing
])
def test_validate_rejects_bad_values(values):
    with pytest.raises(ValueError):
        validate(PARAMS, values)


def test_discovery_finds_demo_and_skips_template():
    cases, problems = find_cases()
    assert "demo_heat1d" in cases
    assert "_template" not in cases and "_template" not in problems
    assert problems == {}


def test_discovery_reports_broken_case(tmp_path):
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "case.py").write_text(
        "NAME = 'g'\nDESCRIPTION = 'd'\n"
        "def parameters(): return []\n"
        "def build_mesh(p): pass\n"
        "def run(p, m, progress): pass\n"
    )
    (tmp_path / "missing_run").mkdir()
    (tmp_path / "missing_run" / "case.py").write_text("NAME = 'x'\nDESCRIPTION = 'd'\n")
    (tmp_path / "syntax_error").mkdir()
    (tmp_path / "syntax_error" / "case.py").write_text("this is not python\n")
    (tmp_path / "not_a_case").mkdir()  # no case.py -> ignored

    cases, problems = find_cases(tmp_path)
    assert list(cases) == ["good"]
    assert set(problems) == {"missing_run", "syntax_error"}
    assert "run()" in problems["missing_run"]


def test_runner_writes_all_outputs(tmp_path):
    result, reference, out_dir = run_case("demo_heat1d", out_dir=tmp_path)
    assert result.converged and reference is not None
    for name in ["fields.csv", "residuals.csv", "summary.yaml", "fields.png", "residuals.png"]:
        assert (out_dir / name).exists(), name


def test_choice_and_file_parameters():
    from aeroflowsim.parameters import choice_parameter, file_parameter, is_shown, parse_value
    params = [
        choice_parameter("src", "Source", ["A", "B"], "A"),
        file_parameter("csv", "Profile", "x.csv", show_if=("src", "B")),
        Parameter("n", "Nodes", "-", 11, 3, 101, show_if=("src", "A")),
    ]
    assert validate(params, {"src": "B", "csv": " y.csv ", "n": 5}) == {"src": "B", "csv": "y.csv", "n": 5}
    with pytest.raises(ValueError, match="not one of"):
        validate(params, {"src": "C", "csv": "x.csv", "n": 5})
    with pytest.raises(ValueError, match="give a file"):
        validate(params, {"src": "A", "csv": "  ", "n": 5})
    assert not is_shown(params[1], {"src": "A"}) and is_shown(params[1], {"src": "B"})
    assert is_shown(params[0], {})
    assert parse_value(params[2], "21") == 21 and parse_value(params[1], "a.csv") == "a.csv"


def test_command_line_set_option_changes_inputs():
    import run_case as cli
    assert cli.parse_settings("demo_heat1d", ["L=2", "n_nodes=11"]) == {"L": 2.0, "n_nodes": 11}
    with pytest.raises(ValueError, match="NAME=VALUE"):
        cli.parse_settings("demo_heat1d", ["nonsense=1"])
    with pytest.raises(ValueError, match="not a number"):
        cli.parse_settings("demo_heat1d", ["L=abc"])

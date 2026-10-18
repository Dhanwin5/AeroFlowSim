# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the shared code in aeroflowsim/: parameters, discovery, the run engine and the command line."""

import pytest

from aeroflowsim.discovery import find_cases
from aeroflowsim.parameters import Parameter, defaults, validate
from aeroflowsim.engine import run_case

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


GOOD_SCHEMA = '[case]\nname = "g"\ndescription = "d"\nsteady = true\n'
GOOD_CASE = "def build_mesh(p): pass\ndef run(p, m, progress): pass\n"


def _make_case(folder, case_py, schema=GOOD_SCHEMA):
    folder.mkdir()
    (folder / "case.py").write_text(case_py)
    if schema is not None:
        (folder / "schema.toml").write_text(schema)


def test_discovery_reports_broken_case(tmp_path):
    _make_case(tmp_path / "good", GOOD_CASE)
    _make_case(tmp_path / "missing_run", "def build_mesh(p): pass\n")
    _make_case(tmp_path / "syntax_error", "this is not python\n")
    _make_case(tmp_path / "no_schema", GOOD_CASE, schema=None)
    _make_case(tmp_path / "bad_schema", GOOD_CASE, schema="[case]\nname = 'x'\n")
    (tmp_path / "not_a_case").mkdir()  # no case.py -> ignored

    cases, problems = find_cases(tmp_path)
    assert list(cases) == ["good"]
    assert set(problems) == {"missing_run", "syntax_error", "no_schema", "bad_schema"}
    assert "run()" in problems["missing_run"]
    assert "schema.toml not found" in problems["no_schema"]
    assert "description" in problems["bad_schema"]
    assert cases["good"].title == "g" and cases["good"].steady and cases["good"].parameters() == []


def test_load_case_by_name_or_folder_path():
    from aeroflowsim.discovery import load_case
    by_name = load_case("demo_heat1d")
    by_path = load_case("cases/demo_heat1d")
    assert by_name.folder == by_path.folder and by_name.name == "demo_heat1d"
    assert by_name.title == "1D heat conduction (demo)"
    with pytest.raises(ValueError, match="No case found"):
        load_case("no_such_case")


def test_run_case_writes_all_outputs(tmp_path):
    out = run_case("cases/demo_heat1d", out_dir=tmp_path)
    assert out.result.converged and out.reference is not None and out.out_dir == tmp_path
    for name in ["fields.csv", "residuals.csv", "summary.yaml", "fields.png", "residuals.png"]:
        assert (tmp_path / name).exists(), name
    assert "checks:" in (tmp_path / "summary.yaml").read_text(encoding="utf-8")


def test_run_case_saves_nothing_without_out_dir_and_fills_defaults():
    out = run_case("demo_heat1d", {"n_nodes": 11})
    assert out.out_dir is None
    assert out.params["n_nodes"] == 11 and out.params["L"] == 1.0   # L kept its default
    assert out.mesh.n_nodes == 11
    assert [c.name for c in out.checks] == ["Convergence"] and out.checks[0].level == "info"


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
    from aeroflowsim import cli
    from aeroflowsim.discovery import load_case
    case = load_case("demo_heat1d")
    assert cli.parse_settings(case, ["L=2", "n_nodes=11"]) == {"L": 2.0, "n_nodes": 11}
    with pytest.raises(ValueError, match="NAME=VALUE"):
        cli.parse_settings(case, ["nonsense=1"])
    with pytest.raises(ValueError, match="not a number"):
        cli.parse_settings(case, ["L=abc"])


def test_command_line_run_and_list(tmp_path, capsys):
    from aeroflowsim import cli
    assert cli.main(["list"]) == 0
    assert "quasi1d_nozzle" in capsys.readouterr().out
    code = cli.main(["run", "cases/demo_heat1d", "--set", "n_nodes=11", "--out", str(tmp_path)])
    printed = capsys.readouterr().out
    assert code == 0
    assert "Validity checks:" in printed and "Convergence" in printed
    assert (tmp_path / "summary.yaml").exists()
    assert cli.main(["run", "cases/demo_heat1d", "--set", "L=99"]) == 1      # outside the allowed range
    assert "outside the allowed range" in capsys.readouterr().out


def test_mesh_only_case_needs_no_run_function(tmp_path):
    schema = GOOD_SCHEMA + 'solver = false\nsolver_message = "Solver comes later."\n'
    _make_case(tmp_path / "mesh_only", "def build_mesh(p): pass\n", schema)
    _make_case(tmp_path / "bad_flag", GOOD_CASE, GOOD_SCHEMA + 'solver = "no"\n')
    cases, problems = find_cases(tmp_path)
    assert not cases["mesh_only"].has_solver and cases["mesh_only"].solver_message == "Solver comes later."
    assert "solver" in problems["bad_flag"]

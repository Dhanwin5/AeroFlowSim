"""Tests for the shared code in core/: parameters, discovery and the runner."""

import pytest

from core.discovery import find_cases
from core.parameters import Parameter, defaults, validate
from core.runner import run_case

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

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for aeroflowsim/checks.py (validity checks), with small made-up results."""

from types import SimpleNamespace

import numpy as np
import pytest

from aeroflowsim import checks
from aeroflowsim.checks import CheckResult, run_checks, worst_level
from aeroflowsim.results import Result

STEADY = SimpleNamespace(steady=True)
UNSTEADY = SimpleNamespace(steady=False)


def result(residuals, **key_numbers):
    return Result(fields={}, residuals=residuals, key_numbers={k: (v, "kg/s") for k, v in key_numbers.items()})


@pytest.mark.parametrize("final, level", [(1e-8, "info"), (1e-6, "info"), (1e-3, "warning"),
                                          (float("nan"), "error"), (0.0, "info")])
def test_convergence_levels(final, level):
    check = checks.convergence(STEADY, {}, None, result([1.0, 0.1, final]))
    assert check.level == level
    if level == "warning":
        assert check.value == pytest.approx(3.0) and "only 3.0 orders" in check.message


def test_convergence_is_not_required_for_unsteady_cases():
    check = checks.convergence(UNSTEADY, {}, None, result([1.0, 1.0]))
    assert check.level == "info" and "unsteady" in check.message


@pytest.mark.parametrize("m_in, m_out, level", [(1.0, 1.004, "info"), (1.0, 1.01, "warning"),
                                                (0.0, 0.0, "info"), (1.0, float("inf"), "error")])
def test_mass_balance_levels(m_in, m_out, level):
    check = checks.mass_balance(STEADY, {}, None, result([1.0], mdot_inlet=m_in, mdot_exit=m_out))
    assert check.level == level


def test_mass_balance_only_applies_with_mass_flows():
    assert checks.mass_balance(STEADY, {}, None, result([1.0])) is None


def test_run_checks_collects_applicable_checks_and_survives_a_broken_check(monkeypatch):
    def broken(case, params, mesh, res):
        raise KeyError("oops")
    monkeypatch.setattr(checks, "CHECKS", [checks.convergence, checks.mass_balance, broken])
    found = run_checks(STEADY, {}, None, result([1.0, 1e-3], mdot_inlet=1.0, mdot_exit=1.0))
    assert [c.name for c in found] == ["Convergence", "Mass balance", "broken"]
    assert [c.level for c in found] == ["warning", "info", "error"]
    assert worst_level(found) == "error" and worst_level([]) == "info"


def test_check_result_rejects_unknown_level_and_stores_plain_floats():
    with pytest.raises(ValueError):
        CheckResult("x", "fatal", "message")
    assert type(CheckResult("x", "info", "m", np.float64(2.0)).value) is float

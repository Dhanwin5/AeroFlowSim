# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validity checks: after every run, the software checks whether its own result can be trusted.

Each check is ONE function with the same signature:

    def my_check(case, params, mesh, result) -> CheckResult | None

It returns a CheckResult (level "info" = fine, "warning" = be careful, "error" = do not trust
the result) or None when the check does not apply to this case (e.g. no mass flow to balance).
All checks are listed in CHECKS; run_checks() runs them all. To add a check later (mesh quality,
Knudsen number, ideal-gas validity, y+ ...), write one function and add it to CHECKS.

The GUI shows the results in the "Validity checks" box of the Results tab, the command line
prints them, and summary.yaml stores them. Nothing here depends on the GUI.
"""

import math
from dataclasses import dataclass

LEVELS = ("info", "warning", "error")

MIN_RESIDUAL_DROP = 6.0      # orders of magnitude a steady case's residual should drop [-]
MAX_MASS_IMBALANCE = 0.5     # largest acceptable inlet/exit mass-flow difference [%]
NO_FLOW = 1e-15              # mass flows below this are treated as "no flow" [kg/s]


@dataclass
class CheckResult:
    """The outcome of one validity check."""

    name: str              # short name, e.g. "Convergence"
    level: str             # "info", "warning" or "error"
    message: str           # one sentence for the user
    value: float | None = None   # the number the check is based on (None if there is none)
    unit: str = ""         # unit of value, e.g. "%" or "orders"

    def __post_init__(self):
        if self.level not in LEVELS:
            raise ValueError(f"Check level must be one of {LEVELS}, got '{self.level}'.")
        if self.value is not None:
            self.value = float(self.value)   # plain Python float (numpy numbers cannot go into YAML)

    def as_dict(self) -> dict:
        """Plain dictionary (for summary.yaml and reports)."""
        return {"name": self.name, "level": self.level, "message": self.message,
                "value": self.value, "unit": self.unit}


def convergence(case, params, mesh, result):
    """Steady cases: how many orders of magnitude the (normalised) residual has dropped."""
    residuals = list(result.residuals or [])
    if not residuals:
        return None
    if not getattr(case, "steady", True):
        return CheckResult("Convergence", "info",
                           "Time-accurate (unsteady) run to the end time: a residual drop is not expected.")
    first, last = residuals[0], residuals[-1]
    if not (math.isfinite(first) and math.isfinite(last)):
        return CheckResult("Convergence", "error", "The residual is not a finite number: the solution diverged.")
    if last == 0.0:
        return CheckResult("Convergence", "info",
                           "The residual is exactly zero (the initial state is already the steady solution).")
    if first <= 0.0:
        return None
    orders = math.log10(first / last)
    if orders < MIN_RESIDUAL_DROP:
        return CheckResult("Convergence", "warning",
                           f"The residual dropped only {orders:.1f} orders of magnitude (at least "
                           f"{MIN_RESIDUAL_DROP:g} expected for a steady case): the result may not be converged.",
                           orders, "orders")
    return CheckResult("Convergence", "info",
                       f"The residual dropped {orders:.1f} orders of magnitude.", orders, "orders")


def mass_balance(case, params, mesh, result):
    """Inlet vs exit mass flow, for cases that report key numbers mdot_inlet and mdot_exit [kg/s]."""
    numbers = result.key_numbers or {}
    if "mdot_inlet" not in numbers or "mdot_exit" not in numbers:
        return None
    m_in, m_out = numbers["mdot_inlet"][0], numbers["mdot_exit"][0]   # [kg/s]
    if not (math.isfinite(m_in) and math.isfinite(m_out)):
        return CheckResult("Mass balance", "error", "The mass flow is not a finite number.")
    mean = 0.5 * (abs(m_in) + abs(m_out))
    if mean < NO_FLOW:
        return CheckResult("Mass balance", "info", "No net flow through the duct (gas at rest).", 0.0, "%")
    imbalance = 100.0 * abs(m_in - m_out) / mean   # [%]
    if imbalance > MAX_MASS_IMBALANCE:
        return CheckResult("Mass balance", "warning",
                           f"Inlet and exit mass flow differ by {imbalance:.3g} % (more than "
                           f"{MAX_MASS_IMBALANCE:g} %): mass is not conserved well, the run may not be converged.",
                           imbalance, "%")
    return CheckResult("Mass balance", "info",
                       f"Inlet and exit mass flow agree within {imbalance:.2g} %.", imbalance, "%")


# Every check, in the order shown. Add new checks here.
CHECKS = [convergence, mass_balance]


def run_checks(case, params, mesh, result) -> list[CheckResult]:
    """Run every check that applies; a check that crashes is reported as an error, not raised."""
    results = []
    for check in CHECKS:
        try:
            outcome = check(case, params, mesh, result)
        except Exception as error:   # a broken check must never hide the solver's result
            outcome = CheckResult(check.__name__, "error", f"The check itself failed: {error!r}")
        if outcome is not None:
            results.append(outcome)
    return results


def worst_level(results: list[CheckResult]) -> str:
    """The most serious level among the results ("info" if there are none)."""
    return max((r.level for r in results), key=LEVELS.index, default="info")

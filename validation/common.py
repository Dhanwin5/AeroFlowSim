# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared code of the validation suite: read reference values, compare, write the report.

Each validation case is a folder validation/<name>/ with two files:

    reference.toml   the published / exact reference values, each with its source and tolerance:

                         title = "Quasi-1D nozzle ..."
                         case = "cases/quasi1d_nozzle"
                         [[reference]]
                         id = "M_exit"                     # name used in validate.py
                         quantity = "Exit Mach number"     # shown in the report
                         value = 3.99
                         unit = "-"
                         tolerance_percent = 2.0           # pass if |error| <= tolerance
                         source = "Isentropic area-Mach relation ..."

    validate.py      a function measure() that runs the case with aeroflowsim.run_case and
                     returns {id: AeroFlowSim value} in the same units as reference.toml.

run_all.py runs every folder and writes validation/report.md; test_validation.py does the same
under pytest (marker "validation").
"""

import datetime
import importlib.util
import tomllib
from dataclasses import dataclass
from pathlib import Path

import aeroflowsim

VALIDATION_DIR = Path(__file__).resolve().parent
REPORT = VALIDATION_DIR / "report.md"


@dataclass
class Reference:
    """One reference value from reference.toml."""

    id: str
    quantity: str
    value: float
    unit: str
    tolerance_percent: float
    source: str


@dataclass
class Comparison:
    """One row of the report: reference vs AeroFlowSim."""

    reference: Reference
    measured: float

    @property
    def error_percent(self) -> float:
        """Relative error of AeroFlowSim against the reference [%]."""
        return 100.0 * abs(self.measured - self.reference.value) / abs(self.reference.value)

    @property
    def passed(self) -> bool:
        return self.error_percent <= self.reference.tolerance_percent


@dataclass
class CaseValidation:
    """All comparisons of one validation folder."""

    name: str            # folder name, e.g. "sod"
    title: str           # e.g. "Sod shock tube (Toro test 1)"
    case: str            # the case folder that was run, e.g. "cases/sod_shock_tube"
    comparisons: list[Comparison]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.comparisons)


def validation_folders() -> list[Path]:
    """Every validation/<name>/ folder that has a reference.toml and a validate.py."""
    return [f for f in sorted(VALIDATION_DIR.iterdir())
            if (f / "reference.toml").exists() and (f / "validate.py").exists()]


def read_references(folder: Path) -> tuple[dict, list[Reference]]:
    """(header {title, case}, list of Reference) from folder/reference.toml."""
    with open(folder / "reference.toml", "rb") as file:
        data = tomllib.load(file)
    references = [Reference(**row) for row in data["reference"]]
    return {"title": data["title"], "case": data["case"]}, references


def _measure(folder: Path) -> dict:
    """Import folder/validate.py and call its measure() function."""
    spec = importlib.util.spec_from_file_location(f"validation_{folder.name}", folder / "validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.measure()


def validate_folder(folder: Path) -> CaseValidation:
    """Run one validation case and compare every reference value."""
    header, references = read_references(folder)
    measured = _measure(folder)
    missing = [r.id for r in references if r.id not in measured]
    if missing:
        raise ValueError(f"{folder.name}/validate.py did not measure: {', '.join(missing)}")
    comparisons = [Comparison(r, float(measured[r.id])) for r in references]
    return CaseValidation(folder.name, header["title"], header["case"], comparisons)


def error_text(error_percent) -> str:
    """Error for the report: 3 decimals, or 2 significant digits for errors below 0.01 %
    (so a very small error, e.g. on a fine mesh, still shows how small it is)."""
    if 0.0 < error_percent < 0.01:
        return f"{error_percent:.2g}"
    return f"{error_percent:.3f}"


def write_report(validations: list[CaseValidation], path: Path = REPORT) -> Path:
    """Write the pass/fail tables as Markdown."""
    overall = all(v.passed for v in validations)
    lines = [
        "# AeroFlowSim validation report",
        "",
        f"AeroFlowSim {aeroflowsim.__version__}, generated {datetime.date.today().isoformat()} "
        "by `python validation/run_all.py`.",
        "",
        f"**Overall: {'PASS' if overall else 'FAIL'}** "
        f"({sum(v.passed for v in validations)} of {len(validations)} cases pass)",
        "",
    ]
    for v in validations:
        lines += [
            f"## {v.title}: {'PASS' if v.passed else 'FAIL'}",
            "",
            f"Case: `{v.case}`, references: `validation/{v.name}/reference.toml`",
            "",
            "| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |",
            "|---|---:|---:|---:|---:|:---:|",
        ]
        for c in v.comparisons:
            r = c.reference
            unit = "" if r.unit == "-" else f" {r.unit}"
            lines.append(f"| {r.quantity} | {r.value:.6g}{unit} | {c.measured:.6g}{unit} | "
                         f"{error_text(c.error_percent)} | {r.tolerance_percent:g} | {'PASS' if c.passed else 'FAIL'} |")
        lines += ["", "Sources:", ""]
        for source in dict.fromkeys(c.reference.source for c in v.comparisons):
            lines.append(f"- {source}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return path

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Automatic case discovery.

Any folder in cases/ that contains a case.py becomes available to the app and the command line,
as long as its schema.toml and case.py are valid. Folders whose name starts with "_" or "."
(e.g. _template) are skipped. A broken case is reported as a problem instead of crashing everything.
"""

from pathlib import Path

from aeroflowsim.case import Case

PROJECT_DIR = Path(__file__).resolve().parent.parent   # the project folder (holds cases/, results/)
CASES_DIR = PROJECT_DIR / "cases"


def find_cases(cases_dir: Path = CASES_DIR) -> tuple[dict, dict]:
    """Scan cases_dir for cases.

    Returns (cases, problems):
      cases    = {folder name: Case} for every valid case
      problems = {folder name: description of what is wrong} for broken ones
    """
    cases, problems = {}, {}
    for folder in sorted(Path(cases_dir).iterdir()):
        if not folder.is_dir() or folder.name.startswith(("_", ".")):
            continue
        if not (folder / "case.py").exists():
            continue  # not a case folder (e.g. __pycache__)
        try:
            cases[folder.name] = Case.load(folder)
        except ValueError as error:
            problems[folder.name] = str(error)
    return cases, problems


def case_folder(case: str | Path, cases_dir: Path = CASES_DIR) -> Path:
    """The folder of a case given as a folder path ("cases/quasi1d_nozzle") or a name ("quasi1d_nozzle")."""
    path = Path(case)
    if path.is_dir() and (path / "case.py").exists():
        return path.resolve()
    if len(path.parts) == 1:                      # a bare name: look in cases/
        return Path(cases_dir) / path.name
    if not path.is_absolute() and (PROJECT_DIR / path).is_dir():
        return PROJECT_DIR / path                 # e.g. "cases/x" while working in another folder
    return path


def load_case(case: str | Path, cases_dir: Path = CASES_DIR) -> Case:
    """Return the Case for a folder path or folder name, or raise a clear ValueError."""
    folder = case_folder(case, cases_dir)
    if not (folder / "case.py").exists():
        available = ", ".join(find_cases(cases_dir)[0]) or "none"
        raise ValueError(f"No case found at '{case}'. Available cases: {available}")
    try:
        return Case.load(folder)
    except ValueError as error:
        raise ValueError(f"Case '{folder.name}' is broken: {error}") from None

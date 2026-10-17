"""Automatic case discovery.

Any folder in cases/ that contains a valid case.py becomes available to the app and
the command-line runner. Folders whose name starts with "_" or "." (e.g. _template)
are skipped. A broken case is reported as a problem instead of crashing everything.
"""

import importlib.util
from pathlib import Path

from aeroflowsim.case_template import check_case

# cases/ folder next to aeroflowsim/
CASES_DIR = Path(__file__).resolve().parent.parent / "cases"


def _load_module(name: str, case_file: Path):
    """Import a case.py file directly from its path and return the module."""
    spec = importlib.util.spec_from_file_location(f"cases.{name}.case", case_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_cases(cases_dir: Path = CASES_DIR) -> tuple[dict, dict]:
    """Scan cases_dir for cases.

    Returns (cases, problems):
      cases    = {folder name: case module} for every valid case
      problems = {folder name: description of what is wrong} for broken ones
    """
    cases, problems = {}, {}
    for folder in sorted(Path(cases_dir).iterdir()):
        if not folder.is_dir() or folder.name.startswith(("_", ".")):
            continue
        case_file = folder / "case.py"
        if not case_file.exists():
            continue  # not a case folder (e.g. __pycache__)
        try:
            module = _load_module(folder.name, case_file)
        except Exception as error:  # any error inside case.py
            problems[folder.name] = f"could not import case.py: {error!r}"
            continue
        issues = check_case(module)
        if issues:
            problems[folder.name] = "; ".join(issues)
        else:
            cases[folder.name] = module
    return cases, problems


def load_case(name: str, cases_dir: Path = CASES_DIR):
    """Return the case module for one case folder name, or raise a clear error."""
    cases, problems = find_cases(cases_dir)
    if name in cases:
        return cases[name]
    if name in problems:
        raise ValueError(f"Case '{name}' is broken: {problems[name]}")
    available = ", ".join(cases) or "none"
    raise ValueError(f"No case called '{name}'. Available cases: {available}")

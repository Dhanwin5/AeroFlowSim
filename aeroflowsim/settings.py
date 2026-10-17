"""Save and load a case's input values ("settings") as small YAML files.

Settings files live in cases/<case_name>/settings/<file_name>.yaml and look like:

    case: demo_heat1d
    parameters:
      L: 1.0
      k: 50.0
      ...
    units:            # for the human reader only; ignored when loading
      L: m
      k: W/(m·K)

Used by the GUI (Save / Load buttons). Nothing here depends on the GUI.
"""

import re
from pathlib import Path

import yaml

from aeroflowsim.discovery import CASES_DIR
from aeroflowsim.parameters import defaults, validate


def settings_dir(case_name: str, cases_dir: Path = CASES_DIR) -> Path:
    """Folder that holds the settings files of one case."""
    return Path(cases_dir) / case_name / "settings"


def clean_file_name(file_name: str) -> str:
    """Turn user text into a safe file name: letters, digits, '_' and '-' only, no extension."""
    stem = file_name.strip()
    if stem.lower().endswith((".yaml", ".yml")):
        stem = stem.rsplit(".", 1)[0]
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")
    if not stem:
        raise ValueError("Please give the settings file a name (letters, digits, '_' or '-').")
    return stem


def list_settings(case_name: str, cases_dir: Path = CASES_DIR) -> list[str]:
    """Names (without .yaml) of the saved settings files of a case, sorted alphabetically."""
    folder = settings_dir(case_name, cases_dir)
    if not folder.is_dir():
        return []
    return sorted(path.stem for path in folder.glob("*.yaml"))


def save_settings(case_name, file_name, param_list, values, cases_dir: Path = CASES_DIR) -> Path:
    """Check the values and write them to cases/<case_name>/settings/<file_name>.yaml.

    Returns the path of the written file. Raises ValueError if a value is out of range.
    """
    clean = validate(param_list, values)
    path = settings_dir(case_name, cases_dir) / f"{clean_file_name(file_name)}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "case": case_name,
        "parameters": clean,
        "units": {p.name: p.unit for p in param_list},
    }
    with open(path, "w", encoding="utf-8") as file:
        yaml.safe_dump(content, file, sort_keys=False, allow_unicode=True)
    return path


def load_settings(case_name, file_name, param_list, cases_dir: Path = CASES_DIR) -> dict:
    """Read a settings file and return checked values {name: value}.

    Parameters missing from the file get their default value (useful when a case gains a new
    input after the file was saved); unknown names in the file are ignored.
    Raises ValueError if the file belongs to another case or a value is out of range.
    """
    path = settings_dir(case_name, cases_dir) / f"{clean_file_name(file_name)}.yaml"
    with open(path, encoding="utf-8") as file:
        content = yaml.safe_load(file) or {}
    if content.get("case") != case_name:
        raise ValueError(f"{path.name} belongs to case '{content.get('case')}', not '{case_name}'.")
    values = defaults(param_list)
    stored = content.get("parameters") or {}
    values.update({name: stored[name] for name in values if name in stored})
    return validate(param_list, values)

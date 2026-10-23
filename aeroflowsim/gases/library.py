# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Where gases come from: the built-in library, the user's own library, and copies inside projects.

A case input of type "gas" holds ONE text value:
    "N2", "air", ...                      a built-in gas (aeroflowsim/gases/<id>.toml)
    "gases/My gas.toml"                   a custom gas file; a relative path is read from the project
                                          folder (the GUI copies a custom gas into <project>/gases/,
                                          so a zipped project stays reproducible)
gas_model(value, base) turns that value into a GasModel; solvers only ever see the GasModel.

The user's own library (custom gases made with the GUI form) is a folder in the user's profile,
never the code folder:  Windows %APPDATA%/AeroFlowSim/gases, elsewhere ~/.local/share/aeroflowsim/gases
(or $XDG_DATA_HOME/aeroflowsim/gases).
"""

import os
import re
import sys
from functools import lru_cache
from pathlib import Path

from aeroflowsim.gases.data import GasData, read_gas_file
from aeroflowsim.gases.model import CaloricallyPerfectGas, GasModel

BUILTIN_DIR = Path(__file__).resolve().parent
PROJECT_GAS_DIR = "gases"          # sub-folder of a project with its custom gases
ORDER = ("N2", "air", "O2", "Ar", "He", "Kr", "Xe", "CO2", "H2", "H2O", "R236fa")   # dropdown order


def user_gas_dir() -> Path:
    """The user's own gas library folder (created when the first custom gas is saved)."""
    if sys.platform.startswith("win"):
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "AeroFlowSim"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "aeroflowsim"
    return root / "gases"


@lru_cache(maxsize=None)
def _builtin() -> dict:
    gases = {}
    for path in sorted(BUILTIN_DIR.glob("*.toml")):
        data = read_gas_file(path, builtin=True)
        gases[data.id] = data
    return gases


def builtin_ids() -> list[str]:
    """Ids of the built-in gases, in dropdown order."""
    ids = list(_builtin())
    return sorted(ids, key=lambda i: (ORDER.index(i) if i in ORDER else len(ORDER), i))


def builtin_gas(gid) -> GasData:
    try:
        return _builtin()[gid]
    except KeyError:
        raise ValueError(f"'{gid}' is not a built-in gas (built-in: {', '.join(builtin_ids())}).") from None


def is_builtin(value) -> bool:
    return isinstance(value, str) and value in _builtin()


def gas_data(value, base=None) -> GasData:
    """The GasData of a gas input value: a built-in id, or the path of a gas file (relative to base)."""
    if is_builtin(value):
        return builtin_gas(value)
    path = Path(str(value))
    if not path.is_absolute():
        path = Path(base or Path.cwd()) / path
    if path.suffix.lower() != ".toml":
        raise ValueError(f"'{value}' is neither a built-in gas ({', '.join(builtin_ids())}) nor a gas file (.toml).")
    return read_gas_file(path)


def gas_model(value, base=None) -> GasModel:
    """The GasModel a solver uses, from a gas input value (see the module docstring)."""
    data = value if isinstance(value, GasData) else gas_data(value, base)
    return CaloricallyPerfectGas(data)


def user_gases() -> list[Path]:
    """The gas files in the user's own library (unreadable files are skipped by the caller)."""
    folder = user_gas_dir()
    return sorted(folder.glob("*.toml")) if folder.is_dir() else []


def safe_file_name(name) -> str:
    """A file name for a gas name typed by the user, e.g. 'My mix 1' -> 'My mix 1.toml'."""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not clean:
        raise ValueError("Please give the gas a name.")
    return f"{clean}.toml"


def save_user_gas(text, name, folder=None) -> Path:
    """Write a custom gas (TOML text, see data.custom_gas_toml) into the user's library."""
    folder = Path(folder or user_gas_dir())
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / safe_file_name(name)
    path.write_text(text, encoding="utf-8")
    return path

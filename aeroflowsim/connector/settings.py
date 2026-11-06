# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the user chose for the AI connector, stored as a small JSON file without Qt, so the GUI (Tools > Use with AI
assistants), the command line (`aeroflowsim settings`) and the server read the same values.

File: <app data>/AeroFlowSim/connector.json (Windows: %APPDATA%). OFF by default: with "allow" false the server
refuses to start. A missing or broken file means the defaults.
"""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ENV_FILE = "AEROFLOWSIM_CONNECTOR_SETTINGS"     # tests (and portable installs) may point to another file


@dataclass
class ConnectorSettings:
    allow: bool = False                 # "Allow AI connector": off until the user turns it on
    workspace: str = ""                 # projects folder the AI may use; "" = Documents/AeroFlowSim Projects
    confirm_minutes: float = 10.0       # runs estimated longer than this need a second call with confirm=true
    memory_fraction: float = 0.7        # ... and runs needing more than this share of the free memory
    max_job_hours: float = 12.0         # a run is stopped (cleanly) after this wall time
    one_job_at_a_time: bool = True      # a second run is refused while one is running

    def workspace_path(self) -> Path:
        from aeroflowsim.project import default_projects_dir
        return Path(self.workspace).expanduser() if self.workspace else default_projects_dir()


def settings_file() -> Path:
    if os.environ.get(ENV_FILE):
        return Path(os.environ[ENV_FILE])
    from aeroflowsim.diagnostics import app_data_dir
    return app_data_dir() / "connector.json"


def load_settings(path=None) -> ConnectorSettings:
    """The saved settings (defaults for anything missing, wrong or unreadable)."""
    path = Path(path or settings_file())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ConnectorSettings()
    out = ConnectorSettings()
    for f in fields(ConnectorSettings):
        value = data.get(f.name) if isinstance(data, dict) else None
        default = getattr(out, f.name)
        if isinstance(default, bool):
            if isinstance(value, bool):
                setattr(out, f.name, value)
        elif isinstance(default, float):
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                setattr(out, f.name, float(value))
        elif isinstance(value, str):
            setattr(out, f.name, value)
    out.memory_fraction = min(out.memory_fraction, 1.0)
    return out


def save_settings(settings: ConnectorSettings, path=None) -> Path:
    path = Path(path or settings_file())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    return path


OFF_MESSAGE = ("The AeroFlowSim AI connector is off. Turn it on in the desktop app (Tools > Use with AI assistants > "
               "Allow AI connector) or with:  aeroflowsim settings --allow-ai-connector on")

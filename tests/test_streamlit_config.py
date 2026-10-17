# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The GUI must be private by default: reachable only from this computer, no usage statistics."""

import tomllib
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml"


def test_gui_only_listens_on_this_computer_and_sends_no_statistics():
    with open(CONFIG, "rb") as file:
        config = tomllib.load(file)
    assert config["server"]["address"] == "localhost"
    assert config["browser"]["gatherUsageStats"] is False

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Old command line, kept for convenience. Prefer:  python -m aeroflowsim run cases/<case_name>

    python run_case.py <case_name> [--set NAME=VALUE ...]    same as: python -m aeroflowsim run <case_name> ...
    python run_case.py --list                               same as: python -m aeroflowsim list
"""

import sys

from aeroflowsim.cli import main

if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main(["list"] if not args or "--list" in args else ["run", *args]))

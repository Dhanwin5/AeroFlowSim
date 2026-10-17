# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Makes "python -m aeroflowsim ..." work: it simply starts the command line in cli.py."""

import sys

from aeroflowsim.cli import main

sys.exit(main())

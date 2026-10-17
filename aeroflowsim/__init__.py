# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""AeroFlowSim: open-source CFD for nozzle aerodynamics and propulsion.

Shared code used by every case: parameters and schema, mesh, results, case contract, discovery,
the run engine, validity checks and output files. Only aeroflowsim/gui/ may import streamlit:
the solver side must work without the GUI.
"""

__version__ = "0.1.0.dev0"   # keep equal to the version in pyproject.toml and CITATION.cff

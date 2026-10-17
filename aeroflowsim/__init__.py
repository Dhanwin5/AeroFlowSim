# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared code used by every case: parameters, mesh, results, case contract, discovery, runner.

Nothing in aeroflowsim/ may import streamlit: the solver side must work without the GUI.
"""

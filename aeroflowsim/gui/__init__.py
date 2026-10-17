# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""GUI layer. The ONLY part of the package that may import streamlit.

Everything a GUI needs from a case comes through plain Python objects (schema, Case, run_case,
checks), so this folder could later be replaced by a desktop GUI (e.g. Qt) without touching solvers.
"""

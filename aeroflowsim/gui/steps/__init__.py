# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""One page per workflow step (Geometry, Mesh, Setup, Run, Results) plus the welcome page.

Every page gets the main window and reads what it shows from it (window.project, window.mesh,
window.results, window.runner); refresh() redraws the page after something changed. Pages never
start work themselves: they ask the window (e.g. window.generate_mesh()), which owns the jobs.
"""

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Post-processing of 2D / axisymmetric results, without Qt or VTK.

The command line, scripts, the automatic report, the GUI (which only draws what this package computes)
and the later AI assistant all use the same functions:

    solution.py    Solution: one result (mesh, cell fields, gas, boundary conditions) + boundary values
    fields.py      derived fields (Mach, Cp, vorticity, schlieren, ...), custom field functions, node values
    sampling.py    value at any point, along a line (exact per cell), interpolation onto another mesh
    surfaces.py    named surfaces: boundary, line, rake, point, iso-line, x = c / y = c lines
    integrals.py   surface and volume integrals, flux balance, forces and moments
    definitions.py report definitions (a named quantity) evaluated after and during a run
    xy.py          XY plots (data along surfaces, reference data, paper-style figures)
    compare.py     two results: difference fields, snapshot comparison
    export.py      CSV, VTU (cell + node data), Tecplot ASCII
    report.py      automatic HTML / PDF report of a project

Example (a script):

    from aeroflowsim.project import Project
    from aeroflowsim import post
    sol = post.Solution.from_project(Project.open("my nozzle.afsproj"))
    exit_ = post.Surface.boundary("outlet")
    print(post.surface_integral(sol, exit_, "mass_flow"))           # kg/s
    print(post.surface_integral(sol, exit_, "mass_weighted", "p0"))  # Pa
"""

from aeroflowsim.post.solution import Solution
from aeroflowsim.post.fields import (FieldError, available_fields, custom_field_problem, field_info,
                                     field_values, node_values)
from aeroflowsim.post.surfaces import Surface, evaluate_surface
from aeroflowsim.post.integrals import (flux_balance, forces_and_moments, surface_integral, volume_integral,
                                        SURFACE_OPERATIONS, VOLUME_OPERATIONS)
from aeroflowsim.post.definitions import ReportDefinition, evaluate_definitions

__all__ = ["Solution", "FieldError", "available_fields", "custom_field_problem", "field_info", "field_values",
           "node_values", "Surface", "evaluate_surface", "flux_balance", "forces_and_moments", "surface_integral",
           "volume_integral", "SURFACE_OPERATIONS", "VOLUME_OPERATIONS", "ReportDefinition", "evaluate_definitions"]

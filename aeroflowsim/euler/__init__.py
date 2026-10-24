# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The finite-volume Euler solver for the face-based Mesh (2D planar, axisymmetric; 3D-ready).

One iteration, in plain words (every step works on whole arrays, never cell by cell):
    1. gradients.py     how rho, u, v, p change across each cell (weighted least squares)
    2. limiters.py      how much of that slope may be used without creating new wiggles
    3. reconstruct.py   the states on both sides of every face (MUSCL), first order where they
                        would have negative density or pressure
    4. boundary.py      a "ghost" outside state for every boundary face (one function per type)
    5. flux.py          the flux through every face: HLLC, HLLE near strong shocks (carbuncle fix)
    6. solver.py        add the fluxes per cell (+ the axisymmetric pressure source), Runge-Kutta
                        time stepping with local time steps, monitors, convergence, divergence

Modules:
    state.py     conserved <-> primitive variables through the GasModel (no hard-coded gamma)
    geometry.py  the mesh numbers the solver needs, computed once (areas, volumes, stencils)
    forces.py    mass flow, thrust, Isp, Cf, Cl/Cd/Cm and Cp from the boundary fluxes
    initial.py   initial solutions (uniform, from the quasi-1D solution, restart)

Array layout: primitive states W and conserved states U have shape (n_vars, n) with
n_vars = dim + 2 (rho, velocity components, p  /  rho, momentum components, rho E).
Nothing here imports the GUI. Equations and references: docs/theory_manual.md, section 13.
"""

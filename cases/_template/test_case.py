# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""TEMPLATE validation test - after copying, replace "_template" with the new folder name."""

import numpy as np

from aeroflowsim.discovery import load_case
from aeroflowsim.parameters import defaults

case = load_case("_template")  # TODO new folder name


def test_matches_reference():
    params = defaults(case.parameters())
    mesh = case.build_mesh(params)
    result = case.run(params, mesh, lambda iteration, residual: None)
    ref = case.reference(params, mesh)
    error = np.max(np.abs(result.fields["TODO"].values - ref["TODO"].values))
    assert result.converged
    assert error < 1e-6  # TODO tolerance justified in README.md

"""TEMPLATE validation test - after copying, replace "_template" with the new folder name."""

import numpy as np

from core.discovery import load_case
from core.parameters import defaults

case = load_case("_template")  # TODO new folder name


def test_matches_reference():
    params = defaults(case.parameters())
    mesh = case.build_mesh(params)
    result = case.run(params, mesh, lambda iteration, residual: None)
    ref = case.reference(params, mesh)
    error = np.max(np.abs(result.fields["TODO"].values - ref["TODO"].values))
    assert result.converged
    assert error < 1e-6  # TODO tolerance justified in README.md

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validation tests (slow): every validation case must match its references within tolerance.

Skipped by a plain "python -m pytest"; run with:  python -m pytest -m validation
"""

import pytest

from validation.common import read_references, validate_folder, validation_folders

FOLDERS = validation_folders()


def test_every_validation_folder_has_sources_and_tolerances():
    assert {f.name for f in FOLDERS} >= {"sod", "quasi1d_nozzle"}
    for folder in FOLDERS:
        header, references = read_references(folder)
        assert header["case"].startswith("cases/") and references
        for r in references:
            assert r.source and r.tolerance_percent > 0 and r.value != 0


@pytest.mark.validation
@pytest.mark.parametrize("folder", FOLDERS, ids=[f.name for f in FOLDERS])
def test_validation_case_passes(folder):
    v = validate_folder(folder)
    for c in v.comparisons:
        print(f"  {c.reference.quantity}: ref {c.reference.value:.6g}, AeroFlowSim {c.measured:.6g} "
              f"{c.reference.unit}, error {c.error_percent:.3f} % (tolerance {c.reference.tolerance_percent:g} %)")
    failed = [c.reference.quantity for c in v.comparisons if not c.passed]
    assert not failed, f"{v.title}: outside tolerance: {failed}"

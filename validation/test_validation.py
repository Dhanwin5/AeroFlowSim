# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validation tests (slow): every validation case must match its references within tolerance.

Skipped by a plain "python -m pytest"; run with:  python -m pytest -m validation
"""

import pytest

from validation.common import read_references, validate_folder, validation_folders

FOLDERS = validation_folders()
NEEDS_GMSH = {"external_geometry", "euler2d_wedge", "euler2d_cylinder", "euler2d_nozzle"}   # use Gmsh meshes


def test_every_validation_folder_has_sources_and_tolerances():
    assert {f.name for f in FOLDERS} >= {"sod", "quasi1d_nozzle", "nozzle_axi_geometry", "external_geometry"}
    for folder in FOLDERS:
        header, references = read_references(folder)
        assert header["case"].startswith(("cases/", "aeroflowsim/")) and references
        for r in references:
            assert r.source and r.tolerance_percent > 0 and r.value != 0


@pytest.mark.validation
@pytest.mark.parametrize("folder", FOLDERS, ids=[f.name for f in FOLDERS])
def test_validation_case_passes(folder):
    if folder.name in NEEDS_GMSH:
        pytest.importorskip("gmsh")
    v = validate_folder(folder)
    for c in v.comparisons:
        print(f"  {c.reference.quantity}: ref {c.reference.value:.6g}, AeroFlowSim {c.measured:.6g} "
              f"{c.reference.unit}, error {c.error_percent:.3f} % (tolerance {c.reference.tolerance:g} %)")
    failed = [c.reference.quantity for c in v.comparisons if not c.passed]
    assert not failed, f"{v.title}: outside tolerance: {failed}"
    if folder.name == "quasi1d_nozzle":       # mesh-refinement study: the exit Mach number converges
        M = v.study["M_exit"]
        changes = [abs(b - a) for a, b in zip(M, M[1:])]
        assert all(later < earlier for earlier, later in zip(changes, changes[1:])), M
        x = v.study["x_shock"]
        assert abs(x[-1] - 0.3208) < abs(x[0] - 0.3208), x


@pytest.mark.validation
def test_nozzle_axi_geometry_error_falls_as_the_mesh_is_refined():
    v = validate_folder(next(f for f in FOLDERS if f.name == "nozzle_axi_geometry"))
    error = {c.reference.id: c.error_percent for c in v.comparisons}
    for quantity in ("area", "volume", "wall"):
        coarse, medium, fine = (error[f"{quantity}_{m}"] for m in ("coarse", "medium", "fine"))
        assert coarse > medium > fine, quantity


@pytest.mark.validation
def test_external_geometry_error_falls_as_the_mesh_is_refined():
    pytest.importorskip("gmsh")
    v = validate_folder(next(f for f in FOLDERS if f.name == "external_geometry"))
    error = {c.reference.id: c.error_percent for c in v.comparisons}
    for quantity in ("cylinder_wall", "cylinder_area", "diamond_area", "wedge_area", "cone_volume"):
        default, fine, finer = (error[f"{quantity}_{m}"] for m in ("default", "fine", "finer"))
        assert default > fine > finer, quantity
    # The triangle nozzle is already exact to round-off level (Gmsh puts its nodes on the arcs).
    assert all(error[f"nozzle_triangles_{m}"] < 1e-3 for m in ("default", "fine", "finer"))
    coarse, medium, fine = (error[f"nozzle_structured_{m}"] for m in ("coarse", "medium", "fine"))
    assert coarse > medium > fine

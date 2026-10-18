# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for nozzle_axi (axisymmetric nozzle mesh): presets, CSV geometry, quality checks,
exact geometry, saved files, and that the case has no solver yet."""

import math

import numpy as np
import pytest

import aeroflowsim
from aeroflowsim.checks import run_mesh_checks
from aeroflowsim.discovery import load_case
from aeroflowsim.mesh import Mesh
from aeroflowsim.parameters import defaults
from aeroflowsim.vtk import save_mesh_files

case = load_case("nozzle_axi")
DEFAULTS = defaults(case.parameters())


def params(**changes):
    return {**DEFAULTS, **changes}


@pytest.mark.parametrize("preset, cells", [("Coarse", 2000), ("Medium", 8000), ("Fine", 32000)])
def test_presets_give_the_right_cell_counts(preset, cells):
    assert case.build_mesh(params(mesh_preset=preset)).n_cells == cells


def test_custom_size_and_clustering_off():
    mesh = case.build_mesh(params(mesh_preset="Custom", nx=50, nr=12, throat_clustering=False))
    assert (mesh.n_cells, mesh.info["cluster_delta"]) == (600, 0.0)


def test_default_mesh_passes_every_mesh_check():
    checks = run_mesh_checks(case, DEFAULTS, case.build_mesh(DEFAULTS))
    assert len(checks) == 6 and all(c.level == "info" for c in checks), [c.message for c in checks]


def test_default_inflation_passes_every_mesh_check_and_shows_its_thickness():
    p = params(inflation=True)
    checks = run_mesh_checks(case, p, case.build_mesh(p))
    assert len(checks) == 7 and all(c.level == "info" for c in checks), [c.message for c in checks]
    assert case.derived(p)["Total inflation thickness"][0] == pytest.approx(1e-6 * (1.2**10 - 1) / 0.2)
    assert "Total inflation thickness" not in case.derived(DEFAULTS)


def test_csv_profile_gives_nearly_the_same_mesh_geometry():
    conical = case.build_mesh(DEFAULTS)
    csv = case.build_mesh(params(geometry_source="Custom profile (CSV)"))
    assert csv.cell_volumes.sum() == pytest.approx(conical.cell_volumes.sum(), rel=1e-3)
    assert csv.axi_cell_volumes.sum() == pytest.approx(conical.axi_cell_volumes.sum(), rel=1e-3)


def test_volume_of_revolution_matches_the_exact_nozzle_volume():
    r_in, L_in, r_t, r_e = 1e-3, 1.33e-3, 1.4e-4, 4.555e-4                     # [m]
    L_c, L_d = (r_in - r_t) / math.tan(math.radians(30)), (r_e - r_t) / math.tan(math.radians(15))
    exact = math.pi * (r_in**2 * L_in + L_c / 3 * (r_in**2 + r_in * r_t + r_t**2)
                       + L_d / 3 * (r_t**2 + r_t * r_e + r_e**2))               # [m³]
    mesh = case.build_mesh(DEFAULTS)
    assert 2 * math.pi * mesh.axi_cell_volumes.sum() == pytest.approx(exact, rel=1e-3)


def test_mesh_files_are_saved_and_reload_identically(tmp_path):
    mesh = case.build_mesh(params(mesh_preset="Coarse"))
    npz, vtu = save_mesh_files(mesh, tmp_path)
    assert npz.parent.name == "mesh" and vtu.read_text(encoding="utf-8").startswith("<?xml")
    loaded = Mesh.load(npz)
    assert np.array_equal(loaded.axi_cell_volumes, mesh.axi_cell_volumes)


def test_no_solver_yet_run_case_says_so():
    assert not case.has_solver
    with pytest.raises(ValueError, match="Prompt 7"):
        aeroflowsim.run_case(case)

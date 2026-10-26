# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for nozzle_axi (axisymmetric nozzle mesh): presets, CSV geometry, quality checks,
exact geometry, saved files, and short solver runs (boundary table, restart)."""

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


def test_short_run_gives_sensible_nozzle_numbers_and_keeps_mass():
    """200 iterations from the quasi-1D start on the coarse mesh: not converged, but already a nozzle.

    (The converged results on three meshes are in validation/euler2d_nozzle.)"""
    assert case.has_solver
    out = aeroflowsim.run_case(case, {"mesh_preset": "Coarse", "max_iter": 200})
    k = out.result.key_numbers
    assert out.result.iterations == 200 and out.result.info["positivity_events"] == 0
    assert 0.9 < k["discharge_coefficient"][0] < 1.0                                  # a sharp throat passes a little less than 1D
    assert abs(k["Isp_vacuum"][0] / k["Isp_quasi1D"][0] - 1.0) < 0.03
    assert set(out.result.fields) >= {"rho", "u", "v", "p", "T", "M", "p0", "s"}


def test_boundary_table_overrides_a_default_and_bad_tables_are_refused():
    params = {"mesh_preset": "Coarse", "max_iter": 5,
              "boundaries": {"outlet": {"type": "supersonic_outlet"}}}
    out = aeroflowsim.run_case(case, params)
    assert out.result.info["boundaries"]["outlet"]["type"] == "supersonic_outlet"
    assert out.result.info["boundaries"]["inlet"]["p0"] == 5e5      # default from the p0 input
    with pytest.raises(ValueError, match="no such boundary"):
        aeroflowsim.run_case(case, {"mesh_preset": "Coarse", "max_iter": 5,
                                    "boundaries": {"exit": {"type": "supersonic_outlet"}}})
    with pytest.raises(ValueError, match="unknown boundary-condition type"):
        aeroflowsim.run_case(case, {"boundaries": {"outlet": {"type": "vortex"}}})


def test_a_run_carries_on_from_the_previous_result_with_its_numbering_and_histories():
    """Stop at iteration 158, run again: the next iteration is 159 and the histories continue seamlessly."""
    from aeroflowsim.result_io import continuation_data
    first = aeroflowsim.run_case(case, {"mesh_preset": "Coarse", "max_iter": 100000},
                                 progress=lambda it, res, info=None: it >= 158)
    assert first.result.iterations == 158 and first.result.info["status"] == "stopped"
    seen = []
    again = aeroflowsim.run_case(case, {"mesh_preset": "Coarse", "max_iter": 200}, mesh=first.mesh,
                                 restart=continuation_data(first.result),
                                 progress=lambda it, res, info=None: seen.append(it))
    r = again.result
    assert seen[0] == 159 and r.iterations == 200 and r.info["first_iteration"] == 159
    assert r.info["continued_from"] == 158 and r.info["initialisation"] == "Continued from the previous result"
    assert len(r.residuals) == 200 and r.residuals[:158] == first.result.residuals          # one continuous history
    assert len(r.series["monitor_thrust"]) == 200
    # Stopping and continuing gives the same flow as one run straight through (same iterations, same numerics)
    straight = aeroflowsim.run_case(case, {"mesh_preset": "Coarse", "max_iter": 200}, mesh=first.mesh).result
    assert np.allclose(r.fields["p"].values, straight.fields["p"].values, rtol=1e-12, atol=0)
    assert np.allclose(r.residuals, straight.residuals, rtol=1e-10, atol=0)
    # Maximum iterations counts the whole run: a run already at the limit says how to go further
    with pytest.raises(ValueError, match="raise Maximum iterations"):
        aeroflowsim.run_case(case, {"mesh_preset": "Coarse", "max_iter": 150}, mesh=first.mesh,
                             restart=continuation_data(first.result))
    # Without a previous result (start from scratch) the numbering starts at 1 again
    fresh = aeroflowsim.run_case(case, {"mesh_preset": "Coarse", "max_iter": 3}, mesh=first.mesh)
    assert fresh.result.info["first_iteration"] == 1 and fresh.result.info["continued_from"] is None


def test_a_result_of_another_mesh_cannot_be_continued():
    from aeroflowsim.result_io import can_continue
    first = aeroflowsim.run_case(case, {"mesh_preset": "Coarse", "max_iter": 3})
    assert can_continue(first.result, first.mesh)
    other = case.build_mesh(params(mesh_preset="Coarse", clustering_strength="Strong"))   # same cell count
    assert other.n_cells == first.mesh.n_cells and not can_continue(first.result, other)

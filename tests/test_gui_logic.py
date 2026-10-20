# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""GUI decisions that need no window, and the geometry preview (boundaries drawn in the Geometry step)."""

import numpy as np
import pytest

from aeroflowsim.discovery import load_case
from aeroflowsim.engine import run_case
from aeroflowsim.geometry_preview import geometry_preview
from aeroflowsim.gui.logic import (AUTO_REBUILD_CELLS, auto_rebuild, available_views, estimated_cells,
                                   key_number_rows, mesh_summary_rows, progress_fraction)
from aeroflowsim.mesh_quality import quality_summary
from aeroflowsim.parameters import defaults, validate


def _params(name, **changes):
    case = load_case(name)
    return case, validate(case.parameters(), {**defaults(case.parameters()), **changes})


def test_progress_is_the_further_of_iterations_and_residual_drop():
    params = {"max_iter": 1000, "tol": 1e-8}
    assert progress_fraction(params, 100, 1.0) == pytest.approx(0.1)
    assert progress_fraction(params, 10, 1e-4) == pytest.approx(0.5)
    assert progress_fraction(params, 5000, 1e-12) == 1.0
    assert progress_fraction({}, 10, 1e-3) == 0.0


def test_auto_rebuild_only_for_small_meshes():
    assert auto_rebuild(None) and auto_rebuild(AUTO_REBUILD_CELLS)
    assert not auto_rebuild(AUTO_REBUILD_CELLS + 1)
    case, params = _params("nozzle_axi")
    assert estimated_cells(case, params) == 8000
    case, params = _params("sod_shock_tube")
    assert estimated_cells(case, params) is None             # the case gives no estimate


def test_views_and_key_numbers_of_a_result():
    case, params = _params("sod_shock_tube")
    out = run_case(case, params)
    assert available_views(out.result, out.mesh) == ["Shape view", "x-t diagram"]
    rows = key_number_rows(out.result, out.reference, run_s=0.5)
    assert rows[0] == ("converged", "yes", "")
    assert ("run time", "0.5", "s") in rows
    assert any(r[0].startswith("max |") for r in rows)


def test_mesh_summary_rows_of_the_default_nozzle_mesh():
    case, params = _params("nozzle_axi")
    mesh = case.build_mesh(params)
    rows = dict(mesh_summary_rows(mesh, quality_summary(mesh)))
    assert rows["cells"] == "8,000" and rows["max non-orthogonality"] == "29.7°"


def test_nozzle_preview_has_wall_inlet_outlet_axis():
    case, params = _params("nozzle_axi")
    preview = geometry_preview(case, params)
    curves = {c.name: c.points for c in preview.curves}
    assert set(curves) == {"wall", "inlet", "outlet", "axis"}
    assert curves["inlet"][1, 1] == pytest.approx(params["d_inlet"] / 2)
    assert curves["outlet"][1, 1] == pytest.approx(params["d_exit"] / 2)
    assert preview.summary["d throat"] == (params["d_throat"], "m")


def test_body_preview_with_far_field_and_half_domain():
    case, params = _params("external_2d", shape="Circular cylinder")
    preview = geometry_preview(case, params)
    far = next(c for c in preview.curves if c.type == "farfield").points
    radius = params["domain_radius"] * params["cylinder.diameter"]
    wall = next(c for c in preview.curves if c.type == "wall").points
    xc = 0.5 * (wall[:, 0].min() + wall[:, 0].max())         # circle centred on the body, as in gmsh_mesh
    assert np.hypot(far[:, 0] - xc, far[:, 1]) == pytest.approx(radius, rel=1e-9)
    case, params = _params("external_2d", shape="Conical nose cone")          # axisymmetric -> half domain
    preview = geometry_preview(case, params)
    assert preview.axisymmetric
    assert [c.type for c in preview.curves].count("axis") == 2
    assert all(c.points[:, 1].min() >= -1e-12 for c in preview.curves)


def test_invalid_geometry_raises_with_the_case_message():
    case, params = _params("nozzle_axi")
    params["d_throat"] = 0.005                                  # larger than the inlet
    with pytest.raises(ValueError):
        geometry_preview(case, params)


def test_1d_case_without_geometry_function():
    case, params = _params("sod_shock_tube")
    assert geometry_preview(case, params) is None


def test_readable_units_with_si_prefixes():
    from aeroflowsim.gui.logic import readable
    assert readable(3369.88, "Pa") == ("3.37", "kPa")
    assert readable(7.16005e-5, "kg/s") == ("71.6", "mg/s")
    assert readable(1.2, "kg/s") == ("1.2", "kg/s")
    assert readable(0.0509131, "N") == ("50.91", "mN")
    assert readable(3.98019, "-") == ("3.98", "")
    assert readable(72.5, "s") == ("72.5", "s")              # seconds keep their unit (Isp)
    assert readable(0.0, "Pa") == ("0", "Pa")


def test_key_result_tiles_for_a_nozzle_and_for_other_templates():
    from aeroflowsim.gui.logic import key_result_tiles, run_status_text
    from aeroflowsim.results import Result
    nozzle = Result(fields={}, residuals=[1.0], iterations=10, converged=True, key_numbers={
        "mdot": (7.16005e-5, "kg/s"), "M_exit": (3.98019, "-"), "p_exit": (3369.88, "Pa"),
        "F_vacuum": (0.0509131, "N"), "F_at_p_back": (0.05, "N"), "Isp_vacuum": (72.5, "s"), "other": (1.0, "m")})
    titles = [t[0] for t in key_result_tiles(nozzle)]
    assert titles == ["Exit Mach number", "Exit pressure", "Mass flow", "Thrust (vacuum)",
                      "Thrust at back pressure", "Specific impulse (vacuum)"]
    assert key_result_tiles(nozzle)[2] == ("Mass flow", "71.6", "mg/s")
    other = Result(fields={}, residuals=[1.0], key_numbers={"p_star_exact": (0.30313, "Pa")})
    assert key_result_tiles(other) == []          # no guessed tiles for non-nozzle templates
    assert run_status_text(nozzle, 14.2) == "Converged after 10 iterations in 14.2 s"

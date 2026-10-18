# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for aeroflowsim/checks.py (validity checks), with small made-up results."""

from types import SimpleNamespace

import numpy as np
import pytest

from aeroflowsim import checks
from aeroflowsim.checks import CheckResult, run_checks, worst_level
from aeroflowsim.results import Result

STEADY = SimpleNamespace(steady=True)
UNSTEADY = SimpleNamespace(steady=False)


def result(residuals, **key_numbers):
    return Result(fields={}, residuals=residuals, key_numbers={k: (v, "kg/s") for k, v in key_numbers.items()})


@pytest.mark.parametrize("final, level", [(1e-8, "info"), (1e-6, "info"), (1e-3, "warning"),
                                          (float("nan"), "error"), (0.0, "info")])
def test_convergence_levels(final, level):
    check = checks.convergence(STEADY, {}, None, result([1.0, 0.1, final]))
    assert check.level == level
    if level == "warning":
        assert check.value == pytest.approx(3.0) and "only 3.0 orders" in check.message


def test_convergence_is_not_required_for_unsteady_cases():
    check = checks.convergence(UNSTEADY, {}, None, result([1.0, 1.0]))
    assert check.level == "info" and "unsteady" in check.message


@pytest.mark.parametrize("m_in, m_out, level", [(1.0, 1.004, "info"), (1.0, 1.01, "warning"),
                                                (0.0, 0.0, "info"), (1.0, float("inf"), "error")])
def test_mass_balance_levels(m_in, m_out, level):
    check = checks.mass_balance(STEADY, {}, None, result([1.0], mdot_inlet=m_in, mdot_exit=m_out))
    assert check.level == level


def test_mass_balance_only_applies_with_mass_flows():
    assert checks.mass_balance(STEADY, {}, None, result([1.0])) is None


def test_run_checks_collects_applicable_checks_and_survives_a_broken_check(monkeypatch):
    def broken(case, params, mesh, res):
        raise KeyError("oops")
    monkeypatch.setattr(checks, "CHECKS", [checks.convergence, checks.mass_balance, broken])
    found = run_checks(STEADY, {}, None, result([1.0, 1e-3], mdot_inlet=1.0, mdot_exit=1.0))
    assert [c.name for c in found] == ["Convergence", "Mass balance", "broken"]
    assert [c.level for c in found] == ["warning", "info", "error"]
    assert worst_level(found) == "error" and worst_level([]) == "info"


def test_check_result_rejects_unknown_level_and_stores_plain_floats():
    with pytest.raises(ValueError):
        CheckResult("x", "fatal", "message")
    assert type(CheckResult("x", "info", "m", np.float64(2.0)).value) is float


# ---- mesh quality checks --------------------------------------------------------------------

def square_mesh(order=(0, 1, 2, 3), nodes=((0, 0), (1, 0), (1, 1), (0, 1)), info=None):
    from aeroflowsim.mesh import QUAD, Mesh
    return Mesh.from_cells(np.array(nodes, dtype=float), QUAD, [list(order)],
                           {"all": ("wall", [[0, 1], [1, 2], [2, 3], [3, 0]])}, info=info)


def by_name(results):
    return {c.name: c for c in results}


def test_mesh_checks_pass_on_a_good_mesh_and_skip_1d_meshes():
    from aeroflowsim.mesh import Mesh1D
    found = by_name(checks.run_mesh_checks(STEADY, {}, square_mesh()))
    assert set(found) == {"Cell volumes", "Aspect ratio", "Non-orthogonality", "Cell growth", "Skewness",
                          "Smallest cell"}
    assert all(c.level == "info" for c in found.values())
    assert found["Smallest cell"].value == pytest.approx(1.0)
    assert checks.run_mesh_checks(STEADY, {}, Mesh1D(x=np.linspace(0, 1, 5))) == []


def test_inverted_cell_is_an_error_and_the_engine_refuses_to_run():
    from aeroflowsim.engine import MeshError, run_case
    bad = square_mesh(order=(0, 3, 2, 1))                    # clockwise: negative volume
    assert by_name(checks.run_mesh_checks(STEADY, {}, bad))["Cell volumes"].level == "error"
    ran = []
    case = SimpleNamespace(steady=True, run=lambda *args: ran.append(1))
    with pytest.raises(MeshError, match="negative volume"):
        run_case(case, {}, mesh=bad)
    assert ran == []                                          # the solver was never called


def test_stretched_cell_warns_unless_it_is_an_inflation_layer():
    thin = ((0, 0), (200, 0), (200, 1), (0, 1))               # aspect ratio 200
    assert by_name(checks.run_mesh_checks(STEADY, {}, square_mesh(nodes=thin)))["Aspect ratio"].level == "warning"
    info = {"inflation": True, "inflation_thickness": 1e-6, "r_throat": 1.0}
    found = by_name(checks.run_mesh_checks(STEADY, {}, square_mesh(nodes=thin, info=info)))
    assert found["Aspect ratio"].level == "info"
    assert found["Inflation layers"].level == "info"


@pytest.mark.parametrize("thickness, level", [(0.2, "info"), (0.6, "warning"), (1.5, "warning")])
def test_inflation_thicker_than_half_the_throat_radius_warns(thickness, level):
    info = {"inflation": True, "inflation_thickness": thickness, "r_throat": 1.0}
    assert checks.mesh_inflation(STEADY, {}, square_mesh(info=info), None).level == level


def test_volume_jump_and_skewed_cells_warn():
    from aeroflowsim.mesh import QUAD, Mesh
    # Two cells side by side: widths 1 and 3 -> volume ratio 3.
    nodes = np.array([[0, 0], [1, 0], [4, 0], [4, 1], [1, 1], [0, 1]], dtype=float)
    mesh = Mesh.from_cells(nodes, QUAD, [[0, 1, 4, 5], [1, 2, 3, 4]],
                           {"all": ("wall", [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 0]])})
    assert checks.mesh_volume_ratio(STEADY, {}, mesh, None).value == pytest.approx(3.0)
    assert checks.mesh_volume_ratio(STEADY, {}, mesh, None).level == "warning"
    # Two strongly sheared cells on top of each other: the centre line is far from the face normal.
    nodes = np.array([[0, 0], [1, 0], [5, 1], [4, 1], [9, 2], [10, 2]], dtype=float)
    mesh = Mesh.from_cells(nodes, QUAD, [[0, 1, 2, 3], [3, 2, 5, 4]],
                           {"all": ("wall", [[0, 1], [1, 2], [2, 5], [5, 4], [4, 3], [3, 0]])})
    assert checks.mesh_non_orthogonality(STEADY, {}, mesh, None).level == "warning"


def triangle_mesh(nodes):
    """One triangle cell from three points (counter-clockwise)."""
    from aeroflowsim.mesh import TRIANGLE, Mesh
    return Mesh.from_cells(np.array(nodes, dtype=float), TRIANGLE, [[0, 1, 2]],
                           {"all": ("wall", [[0, 1], [1, 2], [2, 0]])})


def test_equilateral_triangle_and_square_are_perfect():
    from aeroflowsim import mesh_quality
    equilateral = triangle_mesh([(0, 0), (1, 0), (0.5, np.sqrt(3) / 2)])
    assert mesh_quality.min_angle(equilateral)[0] == pytest.approx(60.0)
    assert mesh_quality.equiangle_skewness(equilateral)[0] == pytest.approx(0.0, abs=1e-12)
    assert mesh_quality.equiangle_skewness(square_mesh())[0] == pytest.approx(0.0, abs=1e-12)
    right = triangle_mesh([(0, 0), (1, 0), (0, 1)])           # 90-45-45: skewness (90 - 60) / 120 = 0.25
    assert mesh_quality.equiangle_skewness(right)[0] == pytest.approx(0.25)
    assert mesh_quality.min_angle(right)[0] == pytest.approx(45.0)


@pytest.mark.parametrize("height, level", [(0.8, "info"), (0.25, "warning"), (0.05, "error")])
def test_smallest_triangle_angle_levels(height, level):
    # Isosceles triangle with base 2: base angles atan(height) = 38.7, 14.0 and 2.9 degrees.
    mesh = triangle_mesh([(0, 0), (2, 0), (1, height)])
    found = by_name(checks.run_mesh_checks(STEADY, {}, mesh))
    assert found["Smallest angle"].level == level
    assert found["Smallest angle"].value == pytest.approx(np.degrees(np.arctan(height)))
    assert found["Skewness"].level == ("warning" if level == "error" else "info")   # 0.43, 0.77, 0.95


def test_smallest_angle_check_only_applies_to_triangles():
    assert checks.mesh_min_angle(STEADY, {}, square_mesh(), None) is None


def test_inflation_on_a_body_is_compared_with_the_reference_length():
    info = {"inflation": True, "inflation_thickness": 0.2, "reference_length": 1.0}
    assert checks.mesh_inflation(STEADY, {}, square_mesh(info=info), None).level == "warning"
    info["inflation_thickness"] = 0.01
    assert checks.mesh_inflation(STEADY, {}, square_mesh(info=info), None).level == "info"

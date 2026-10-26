# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Post-processing in a project: settings stored and reopened, report definitions as live monitors (report CSV
during the run, continued with the run, restarted from scratch), a monitor as convergence criterion, snapshots,
exports, patch regions, and a run on a new mesh started from the interpolated old solution.

Walk-through of the user's next actions: stop -> run again (continues, CSV continues) -> start from scratch (new
CSV) -> reopen the project (settings kept) -> re-mesh (surfaces and definitions still evaluate; the run starts from
the interpolated solution) -> snapshot, change, compare, restore."""

import math

import numpy as np
import pytest

from aeroflowsim.euler.setup import INTERPOLATED, apply_patches
from aeroflowsim.gases import gas_model
from aeroflowsim.post import ReportDefinition, Solution, Surface, evaluate_definitions
from aeroflowsim.post import export, snapshots
from aeroflowsim.post.compare import difference, key_number_table
from aeroflowsim.post.definitions import report_file_name
from aeroflowsim.project import Project, build_project_mesh, run_project
from aeroflowsim.simple_meshes import rectangle_mesh

COARSE = {"mesh_preset": "Custom", "nx": 30, "nr": 6}


def _csv_iterations(path):
    lines = path.read_text(encoding="utf-8").splitlines()[1:]
    return [int(line.split(",")[0]) for line in lines]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    folder = tmp_path_factory.mktemp("post") / "nozzle.afsproj"
    p = Project.create("nozzle_axi", folder, COARSE)
    p.set_post("report_definitions", [
        ReportDefinition("mdot out", "surface", "outlet", "mass_flow", monitor=True, converge=True,
                         tolerance=1e-5, window=300).to_dict(),
        ReportDefinition("p0 exit", "surface", "outlet", "mass_weighted", "p0", monitor=True).to_dict(),
        ReportDefinition("gas mass", "volume", operation="mass").to_dict()])
    p.set_post("surfaces", [Surface.x_line(0.0015, "mid").to_dict()])
    p.set_post("custom_fields", {"p_bar": {"formula": "p / 1e5", "label": "Pressure in bar"}})
    p.save()
    return p


@pytest.fixture(scope="module")
def stopped_then_continued(project):
    stop_at = 60

    def stop(it, res, info=None):
        return it >= stop_at
    first = run_project(project, progress=stop)
    assert first.result.info["status"] == "stopped" and first.result.iterations == stop_at
    rows_after_stop = _csv_iterations(project.results_dir / report_file_name("mdot out"))
    second = run_project(project)                   # Run again: continues from iteration 61
    return first, rows_after_stop, second


def test_settings_survive_save_and_reopen(project):
    again = Project.open(project.folder)
    assert [d["name"] for d in again.post["report_definitions"]] == ["mdot out", "p0 exit", "gas mass"]
    assert again.post["surfaces"][0]["name"] == "mid"
    assert again.custom_fields["p_bar"]["formula"] == "p / 1e5"
    assert again.post["interpolate_new_mesh"] is True


def test_monitor_csv_is_written_during_the_run_and_continues(project, stopped_then_continued):
    first, rows_after_stop, second = stopped_then_continued
    assert rows_after_stop == list(range(1, 61))
    assert second.result.info["first_iteration"] == 61
    rows = _csv_iterations(project.results_dir / report_file_name("mdot out"))
    assert rows == list(range(1, second.result.iterations + 1))     # the whole run, no gap, no repeat
    assert len(second.result.series["monitor_user_mdot out"]) == second.result.iterations


def test_user_monitor_is_a_convergence_criterion_and_values_are_reported(project, stopped_then_continued):
    _, _, second = stopped_then_continued
    r = second.result
    assert r.converged
    assert "user_mdot out" in r.info["converge_on"]
    assert r.info["monitor_rules"]["user_mdot out"] == [1e-5, 300]
    values = r.info["report_values"]
    assert values["mdot out"][0] == pytest.approx(r.key_numbers["mdot_exit"][0], rel=1e-12)
    assert values["gas mass"][1] == "kg"
    # the last 300 values of the monitor have settled within the tolerance
    tail = np.asarray(r.series["monitor_user_mdot out"][-300:])
    assert (tail.max() - tail.min()) <= 1e-5 * abs(tail.mean())


def test_start_from_scratch_begins_a_new_report_file(project, stopped_then_continued):
    def stop(it, res, info=None):
        return it >= 15
    out = run_project(project, progress=stop, fresh=True)
    assert out.result.info["first_iteration"] == 1
    assert _csv_iterations(project.results_dir / report_file_name("mdot out")) == list(range(1, 16))
    run_project(project)                            # carry on to convergence again for the tests below


def test_snapshots_save_compare_restore(project, stopped_then_continued):
    base = snapshots.save_snapshot(project, "baseline")
    with np.load(base / "run.npz") as z:
        assert z.zip.getinfo(z.zip.namelist()[0]).compress_type != 0      # stored compressed
    with pytest.raises(ValueError, match="already exists"):
        snapshots.save_snapshot(project, "baseline")
    names = [s["name"] for s in snapshots.list_snapshots(project)]
    assert names == ["baseline"]
    current = Solution.from_project(project)
    snap = Solution.from_project(project, snapshot="baseline")
    d = difference(current, snap, "p")
    assert not d.interpolated and d.largest == 0.0
    assert all(abs(row[4]) < 1e-12 for row in key_number_table(current, snap) if math.isfinite(row[4]))
    snapshots.rename_snapshot(project, "baseline", "base 2")
    snapshots.restore_snapshot(project, "base 2")
    assert project.status("run") == "ok"
    snapshots.delete_snapshot(project, "base 2")
    assert snapshots.list_snapshots(project) == []
    assert snapshots.size_warning(project, limit=10**12) == ""
    assert "larger" not in snapshots.size_warning(project, limit=1) and "Delete snapshots" in \
        snapshots.size_warning(project, limit=1)


def test_exports_are_readable(project, stopped_then_continued, tmp_path):
    sol = Solution.from_project(project)
    csv = export.fields_csv(sol, tmp_path / "f.csv", fields=("p", "M", "p_bar"))
    lines = csv.read_text(encoding="utf-8").splitlines()
    assert lines[1] == "x [m],r [m],p [Pa],M [-],p_bar [Pa]"     # p / 1e5: a bare number keeps the unit of p
    data = np.loadtxt(csv, delimiter=",", skiprows=2)
    assert data.shape == (sol.mesh.n_cells, 5)
    assert np.allclose(data[:, 2], sol.fields["p"], rtol=1e-9)
    nodes = export.fields_csv(sol, tmp_path / "n.csv", fields=("p",), location="node")
    assert np.loadtxt(nodes, delimiter=",", skiprows=2).shape == (sol.mesh.n_nodes, 3)
    vtu = export.fields_vtu(sol, tmp_path / "f.vtu").read_text(encoding="utf-8")
    assert vtu.count("<PointData>") == 1 and 'Name="p_node"' in vtu and 'Name="velocity"' in vtu
    tec = export.read_tecplot_header(export.fields_tecplot(sol, tmp_path / "f.dat"))
    assert tec["nodes"] == sol.mesh.n_nodes and tec["elements"] == sol.mesh.n_cells
    assert tec["variables"][:3] == ["X", "Y", "rho [kg/m³]"]
    n_values = math.ceil(sol.mesh.n_nodes / 5) * 2 + math.ceil(sol.mesh.n_cells / 5) * 9
    assert len(tec["lines"]) == 3 + n_values + sol.mesh.n_cells
    from aeroflowsim.post.definitions import definitions_from
    defs = definitions_from(project.post["report_definitions"])
    out = export.definitions_csv(evaluate_definitions(sol, defs), tmp_path / "d.csv", defs)
    assert "mdot out" in out.read_text(encoding="utf-8")
    s = export.surface_csv(sol, Surface.boundary("wall"), tmp_path / "wall.csv", fields=("p",))
    assert np.loadtxt(s, delimiter=",", skiprows=2).shape[1] == 4


def test_patch_regions_set_values_in_their_cells():
    m = rectangle_mesh(10, 10)
    air = gas_model("air")
    W = np.vstack([np.ones(100), np.zeros(100), np.zeros(100), np.full(100, 1e5)])
    out, n = apply_patches(W, m, air, [{"region": {"type": "box", "min": (0, 0), "max": (0.5, 1)},
                                        "values": {"p": 2e5, "T": 500.0}},
                                       {"region": {"type": "circle", "centre": (0.75, 0.5), "radius": 0.1},
                                        "values": {"u": 100.0}}])
    left = m.cell_centres[:, 0] < 0.5
    assert np.all(out[3, left] == 2e5) and np.allclose(out[0, left], 2e5 / (air.R * 500.0))
    assert np.all(out[3, ~left] == 1e5) and n == 50 + np.count_nonzero(out[1] == 100.0)
    with pytest.raises(ValueError, match="not known"):
        apply_patches(W, m, air, [{"region": {"type": "star"}}])


@pytest.mark.validation
def test_run_on_a_new_mesh_starts_from_the_interpolated_solution(project, stopped_then_continued):
    coarse_mdot = Solution.from_project(project).key_numbers["mdot_exit"][0]
    project.set_value("nx", 60)
    project.set_value("nr", 12)
    build_project_mesh(project)
    out = run_project(project)
    assert out.result.info["initialisation"] == INTERPOLATED and out.result.converged
    # the surfaces and report definitions defined on the coarse mesh evaluate on the new one
    assert set(out.result.info["report_values"]) == {"mdot out", "p0 exit", "gas mass"}
    fine_mdot = out.result.key_numbers["mdot_exit"][0]
    assert abs(fine_mdot - coarse_mdot) / fine_mdot < 0.05
    fresh = run_project(project, fresh=True)
    assert fresh.result.info["initialisation"] != INTERPOLATED
    assert out.result.iterations < fresh.result.iterations
    assert fresh.result.key_numbers["mdot_exit"][0] == pytest.approx(fine_mdot, rel=1e-4)

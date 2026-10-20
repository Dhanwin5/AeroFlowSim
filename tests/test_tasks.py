# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Background jobs in the warm helper process: results identical to a normal run, Stop and Cancel."""

import time

import numpy as np
import pytest

from aeroflowsim.discovery import load_case
from aeroflowsim.engine import run_case
from aeroflowsim.mesh import Mesh
from aeroflowsim.parameters import defaults, validate
from aeroflowsim.tasks import Job, Worker


def _params(case_name, **changes):
    case = load_case(case_name)
    return case, validate(case.parameters(), {**defaults(case.parameters()), **changes})


@pytest.fixture(scope="module")
def worker():
    w = Worker()
    w.start()
    yield w
    w.shutdown()


def test_mesh_job_saves_the_same_mesh_as_building_it_here(worker, tmp_path):
    case, params = _params("nozzle_axi")
    task = worker.submit(Job("mesh", str(case.folder), params, str(tmp_path)))
    worker.wait(timeout=120)
    assert task.status == "finished", task.error
    assert task.payload["n_cells"] == 8000
    assert (tmp_path / "mesh.vtu").exists()
    mesh = Mesh.load(task.payload["mesh_path"])
    here = case.build_mesh(params)
    assert np.array_equal(mesh.nodes, here.nodes) and np.array_equal(mesh.cell_nodes, here.cell_nodes)


def test_run_job_gives_exactly_the_same_numbers_as_run_case(worker, tmp_path):
    case, params = _params("quasi1d_nozzle", n_cells=100)
    mesh = case.build_mesh(params)
    task = worker.submit(Job("run", str(case.folder), params, str(tmp_path), mesh=mesh))
    worker.wait(timeout=300)
    assert task.status == "finished", task.error + task.details
    here = run_case(case, params, mesh=mesh)
    result = task.payload["result"]
    assert result.iterations == here.result.iterations
    for key, field in here.result.fields.items():
        assert np.array_equal(result.fields[key].values, field.values)
    assert result.key_numbers == here.result.key_numbers
    assert [c.as_dict() for c in task.payload["checks"]] == [c.as_dict() for c in here.checks]
    assert task.iterations and task.iterations[-1] == result.iterations   # live residual history arrived
    assert (tmp_path / "summary.yaml").exists()                            # same output files as the CLI


def test_1d_mesh_job_returns_the_mesh_object(worker):
    case, params = _params("demo_heat1d")
    task = worker.submit(Job("mesh", str(case.folder), params, None))
    worker.wait(timeout=120)
    assert task.status == "finished", task.error
    assert task.payload["mesh"].n_nodes == params["n_nodes"]


def test_stop_ends_a_run_cleanly(worker):
    case, params = _params("quasi1d_nozzle", tol=1e-14, max_iter=10_000_000)
    task = worker.submit(Job("run", str(case.folder), params, None, mesh=case.build_mesh(params)))
    end = time.perf_counter() + 60
    while not task.iterations and time.perf_counter() < end:   # wait until it is really solving
        worker.poll()
        time.sleep(0.05)
    assert task.iterations, task.error
    worker.cancel()
    worker.wait(timeout=30)
    assert task.status == "stopped"           # stopped by the solver itself, not by killing the process


def test_cancel_kills_a_running_gmsh_mesh_and_the_worker_still_works(worker, tmp_path):
    pytest.importorskip("gmsh")
    case, params = _params("external_2d", shape="Circular cylinder", surface_size=0.0008, farfield_size=0.5)
    task = worker.submit(Job("mesh", str(case.folder), params, str(tmp_path / "slow")))
    time.sleep(3.0)                            # helper is now inside Gmsh
    worker.poll()
    assert task.running
    t0 = time.perf_counter()
    worker.cancel()
    assert task.status == "cancelled" and time.perf_counter() - t0 < 6
    assert not (tmp_path / "slow" / "mesh.npz").exists()
    case, params = _params("nozzle_axi", mesh_preset="Coarse")
    task = worker.submit(Job("mesh", str(case.folder), params, str(tmp_path / "next")))
    worker.wait(timeout=120)
    assert task.status == "finished", task.error


def test_a_failing_job_reports_a_message(worker):
    case, params = _params("nozzle_axi")
    params["d_throat"] = 1.0                   # throat larger than the inlet: geometry error
    task = worker.submit(Job("mesh", str(case.folder), params, None))
    worker.wait(timeout=120)
    assert task.status == "failed"
    assert task.error and "Traceback" in task.details


def test_only_one_job_at_a_time(worker, tmp_path):
    case, params = _params("nozzle_axi")
    worker.submit(Job("mesh", str(case.folder), params, str(tmp_path)))
    with pytest.raises(RuntimeError):
        worker.submit(Job("mesh", str(case.folder), params, str(tmp_path)))
    worker.wait(timeout=120)

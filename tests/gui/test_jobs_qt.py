# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Qt job runner: signals while the event loop keeps running, and Cancel."""

import pytest

from aeroflowsim.discovery import load_case
from aeroflowsim.gui.jobs import JobRunner
from aeroflowsim.parameters import defaults, validate
from aeroflowsim.tasks import Job


@pytest.fixture
def runner(qtbot):
    r = JobRunner()
    yield r
    r.shutdown()


def _job(kind, case_name, out_dir, **changes):
    case = load_case(case_name)
    params = validate(case.parameters(), {**defaults(case.parameters()), **changes})
    mesh = case.build_mesh(params) if kind == "run" else None
    return Job(kind, str(case.folder), params, out_dir, mesh=mesh)


def test_mesh_job_ends_with_a_signal(qtbot, runner, tmp_path):
    with qtbot.waitSignal(runner.ended, timeout=120_000) as signal:
        runner.submit(_job("mesh", "nozzle_axi", str(tmp_path)))
    assert signal.args[0].status == "finished"
    assert not runner.busy


def test_run_sends_live_updates_and_can_be_stopped(qtbot, runner):
    runner.submit(_job("run", "quasi1d_nozzle", None, tol=1e-14, max_iter=10_000_000))
    qtbot.waitUntil(lambda: bool(runner.task.iterations), timeout=60_000)   # residuals are arriving
    with qtbot.waitSignal(runner.ended, timeout=30_000) as signal:
        runner.cancel()
    assert signal.args[0].status == "stopped"

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for aeroflowsim/job.py (background run with live progress and Stop)."""

import threading
from types import SimpleNamespace

from aeroflowsim.discovery import load_case
from aeroflowsim.job import RunJob
from aeroflowsim.parameters import defaults, validate
from aeroflowsim.results import Field, Result


def _demo(**changes):
    """Demo case module, validated params (with changes) and mesh."""
    case = load_case("demo_heat1d")
    values = defaults(case.parameters())
    values.update(changes)
    params = validate(case.parameters(), values)
    return case, params, case.build_mesh(params)


def test_demo_run_finishes_with_result_and_reference():
    case, params, mesh = _demo()
    job = RunJob()
    job.start(case, params, mesh)
    job.wait(timeout=60)
    assert job.status == "finished"
    assert job.result.converged
    assert "T" in job.reference
    iterations, residuals = job.snapshot()
    assert len(iterations) == job.result.iterations == len(residuals)


def test_stop_ends_a_long_run():
    started = threading.Event()

    def run(params, mesh, progress):
        """Fake case that would iterate (almost) forever."""
        for i in range(1, 10**9):
            started.set()
            progress(i, 1.0 / i)
        return Result(fields={}, residuals=[])

    case = SimpleNamespace(run=run, build_mesh=lambda params: None)
    job = RunJob()
    job.start(case, {}, None)
    assert started.wait(timeout=10)
    job.stop()
    job.wait(timeout=10)
    assert job.status == "stopped"
    assert job.result is None
    assert len(job.snapshot()[0]) >= 1


def test_solver_error_gives_failed_status():
    def run(params, mesh, progress):
        progress(1, 1.0)
        raise FloatingPointError("solution diverged")

    job = RunJob()
    job.start(SimpleNamespace(run=run, build_mesh=lambda params: None), {}, None)
    job.wait(timeout=10)
    assert job.status == "failed"
    assert "solution diverged" in job.error


def test_case_without_reference_is_fine():
    def run(params, mesh, progress):
        progress(1, 0.0)
        return Result(fields={"T": Field([1.0], "K", "Temperature")}, residuals=[0.0])

    job = RunJob()
    job.start(SimpleNamespace(run=run, build_mesh=lambda params: None), {}, None)
    job.wait(timeout=10)
    assert job.status == "finished"
    assert job.reference is None

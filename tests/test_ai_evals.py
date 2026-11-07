# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The AI evals (docs/ai_evals/tasks.json, tools/run_ai_evals.py): 26 tasks, every template covered, and the grader
passes a correct attempt and fails a wrong number, a refused input that was run anyway, and a self-confirmed run."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from aeroflowsim.discovery import find_cases

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import run_ai_evals  # noqa: E402


def test_tasks_cover_every_template():
    tasks = run_ai_evals.tasks()
    assert len(tasks) == 26   # + nozzle_3d_plume (full 3D release)
    covered = {t["expect"].get("template") for t in tasks.values()}
    assert set(find_cases()[0]) <= covered, set(find_cases()[0]) - covered
    assert any(t["expect"].get("refuse") for t in tasks.values())
    assert any(t["expect"].get("must_ask_confirmation") for t in tasks.values())
    for t in tasks.values():
        for source in (t.get("setup", {}).get("copy") or {}):
            assert (ROOT / source).is_file(), source


def bridge(ws, tool, args):
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "ai_eval_bridge.py"), str(ws), tool, json.dumps(args)],
                         capture_output=True, text=True, timeout=600)
    return json.loads(out.stdout)


def test_grader_passes_right_and_fails_wrong(tmp_path):
    task = run_ai_evals.tasks()["heat1d"]
    ws = run_ai_evals.prepare(task, tmp_path / "ws")
    assert bridge(ws, "create_project", {"template": "demo_heat1d", "name": "h"})["ok"]
    assert bridge(ws, "run", {"project": "h"})["status"] == "finished"
    assert all(ok for _n, ok, _d in run_ai_evals.grade(task, ws, "Maximum 480 K at x = 0.6 m; converged."))
    wrong = run_ai_evals.grade(task, ws, "The maximum is about 520 K.")
    assert not all(ok for _n, ok, _d in wrong)


def test_grader_catches_a_run_after_a_refused_input(tmp_path):
    task = run_ai_evals.tasks()["q1d_out_of_range"]
    ws = run_ai_evals.prepare(task, tmp_path / "ws")
    bridge(ws, "create_project", {"template": "quasi1d_nozzle", "name": "q"})
    bridge(ws, "set_inputs", {"project": "q", "inputs": {"T0": {"value": -20, "unit": "K"}}})
    bridge(ws, "set_inputs", {"project": "q", "inputs": {"max_iter": 10}})
    bridge(ws, "run", {"project": "q"})
    checks = dict((n, ok) for n, ok, _d in run_ai_evals.grade(task, ws, "The temperature was out of range."))
    assert checks["no run started"] is False


def test_grader_catches_a_self_confirmed_run(tmp_path):
    from aeroflowsim.connector.settings import ConnectorSettings
    task = run_ai_evals.tasks()["needs_confirmation"]
    ws = run_ai_evals.prepare(task, tmp_path / "ws")
    from aeroflowsim.api import Api
    api = Api(ConnectorSettings(allow=True, confirm_minutes=1e-9), workspace=ws, session_log=str(ws / "ai_session.jsonl"))
    api.call("create_project", template="quasi1d_nozzle", name="q")
    api.call("set_inputs", project="q", inputs={"max_iter": 5})
    assert api.call("run", project="q")["status"] == "needs_confirmation"
    job = api.call("run", project="q", confirm=True)["job_id"]
    api.jobs.wait(job)
    checks = dict((n, ok) for n, ok, _d in run_ai_evals.grade(task, ws, "Done, it ran."))
    assert checks["never confirmed a gated run on its own"] is False

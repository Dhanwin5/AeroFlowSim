# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""A command-line bridge to the AI connector's tools, for evaluating an AI agent that has a shell but no MCP client.

    python tools/ai_eval_bridge.py <workspace> <tool> '<JSON arguments>'

prints the tool's JSON answer (the same Api.call the MCP server uses; every call is also written to
<workspace>/ai_session.jsonl). Each call is a new process, so a run cannot go on in the background between calls:
`run` and `continue_run` WAIT for the run to end (at most 20 minutes) and say so; `job_status` / `stop_job` of such a
job report that it has ended. This is the one difference from the MCP server (documented in docs/ai_evals/README.md).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv):
    from aeroflowsim.api import Api
    from aeroflowsim.connector.settings import ConnectorSettings
    sys.stdout.reconfigure(encoding="utf-8")       # Windows consoles default to cp1252, which cannot print '→'
    if len(argv) < 2:
        print(__doc__)
        return 2
    workspace, tool = Path(argv[0]), argv[1]
    arguments = json.loads(argv[2]) if len(argv) > 2 and argv[2].strip() else {}
    api = Api(ConnectorSettings(allow=True, workspace=str(workspace)), workspace=workspace,
              session_log=str(workspace / "ai_session.jsonl"))
    if tool in ("job_status", "stop_job"):
        out = {"ok": True, "job_id": arguments.get("job_id"), "status": "ended",
               "message": "In this bridge every run waits until it ends inside the run call: use get_results."}
        print(json.dumps(out))
        return 0
    out = api.call(tool, **arguments)
    if tool in ("run", "continue_run") and out.get("status") == "started":
        job = api.jobs.wait(out["job_id"], timeout=1200)
        out["status"] = job.status if not job.running else "still running after 20 min (stopped by the bridge)"
        if job.running:
            api.jobs.stop(job.id)
            api.jobs.wait(job.id, 120)
        out["bridge_note"] = "the bridge waited for the run to end"
        if job.error:
            out["error"] = job.error
    print(json.dumps(out, ensure_ascii=False, default=str)[:30000])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

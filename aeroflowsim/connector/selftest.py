# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The "Test" button of Tools > Use with AI assistants: start the real server the way an AI client does
(`python -m aeroflowsim mcp` over stdio), list its tools, stop it.

It runs in a separate Python process, so the desktop app itself never imports the `mcp` package:

    python -m aeroflowsim.connector.selftest     prints one JSON line {"ok": ..., "tools": [...], "error": ...}
"""

import json
import subprocess
import sys


def _client_main():
    import asyncio

    from mcp import Client, StdioServerParameters

    async def main():
        import os
        # the whole environment: the SDK passes only a safe subset by default, which would drop a settings-file override
        from aeroflowsim.connector.snippets import server_entry
        entry = server_entry()        # exactly what the copied configuration starts (python -m ..., or the program)
        params = StdioServerParameters(command=entry["command"], args=entry["args"], env=dict(os.environ))
        async with Client(params, read_timeout_seconds=60) as client:
            return [t.name for t in (await client.list_tools()).tools]

    try:
        tools = asyncio.run(main())
        print(json.dumps({"ok": True, "tools": tools}))
    except ImportError:
        print(json.dumps({"ok": False, "error": 'The optional package "mcp" is missing: pip install "aeroflowsim[ai]"'}))
    except BaseException as error:   # noqa: BLE001 - the server refused (off) or failed: report, never crash
        print(json.dumps({"ok": False, "error": f"The server did not start ({type(error).__name__}). Is the "
                                                "connector allowed? Details are in the client log."}))


def run_selftest(python=None, timeout=90) -> dict:
    """Start the self-test process; returns {"ok", "tools" or "error"}."""
    from aeroflowsim.connector.settings import load_settings, OFF_MESSAGE
    if not load_settings().allow:
        return {"ok": False, "error": OFF_MESSAGE}
    from aeroflowsim.connector.snippets import installed_program
    if python is None and installed_program():
        command = [sys.executable, "mcp-selftest"]           # the installed program runs the client itself
    else:
        command = [python or sys.executable, "-m", "aeroflowsim.connector.selftest"]
    try:
        out = subprocess.run(command, capture_output=True,
                             text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"No answer within {timeout} s."}
    lines = [line for line in out.stdout.splitlines() if line.startswith("{")]
    if not lines:
        return {"ok": False, "error": (out.stderr.strip().splitlines() or ["no output"])[-1][:300]}
    return json.loads(lines[-1])


if __name__ == "__main__":
    _client_main()

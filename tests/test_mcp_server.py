# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The MCP server (aeroflowsim mcp) driven by a real MCP client: in process for the per-template flow, and as a
separate process over stdio for the protocol hygiene (stdout carries only the protocol even when Gmsh / OpenCASCADE
print). Templates are discovered from cases/, never listed by hand.

Also: off by default, AeroFlowSim works without the `mcp` package, no network connections.
"""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from aeroflowsim.api import TOOLS, Api
from aeroflowsim.connector.settings import ConnectorSettings, save_settings
from aeroflowsim.discovery import find_cases

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "tests" / "data"
TEMPLATES = sorted(find_cases()[0])
PYTHON = sys.executable


def text_of(result) -> dict:
    return json.loads(next(c.text for c in result.content if c.type == "text"))


def with_client(api, body):
    """Run body(client) against the server of `api`, in process."""
    pytest.importorskip("mcp")
    from mcp import Client
    from aeroflowsim.connector.server import build_server

    async def main():
        async with Client(build_server(api)) as client:
            return await body(client)

    return asyncio.run(main())


async def call(client, tool_name, /, **arguments) -> dict:
    return text_of(await client.call_tool(tool_name, arguments))


# ---- the server's tools are the API's tools ----------------------------------------------------------

def test_tools_match_the_api(tmp_path):
    async def body(client):
        return (await client.list_tools()).tools

    tools = with_client(Api(workspace=tmp_path), body)
    assert [t.name for t in tools] == TOOLS
    assert all(len(t.description) > 20 for t in tools)
    describe = next(t for t in tools if t.name == "describe_template")
    assert describe.input_schema["required"] == ["template"]


# ---- EVERY template: describe -> create -> inputs -> geometry -> mesh -> check -> run -> results -> plot
#      -> export -> report -------------------------------------------------------------------------------

@pytest.mark.parametrize("template", TEMPLATES)
def test_every_template_through_the_server(tmp_path, template):
    ws = tmp_path / "ws"
    ws.mkdir()
    shutil.copy(DATA / "lens.dxf", ws / "lens.dxf")
    api = Api(ConnectorSettings(allow=True), workspace=ws)

    async def body(client):
        d = await call(client, "describe_template", template=template)
        assert d["ok"]
        keys = {i["key"]: i for i in d["inputs"]}
        assert (await call(client, "create_project", template=template, name="p"))["ok"]
        # inputs: valid, invalid, wrong unit (on the first bounded number in use)
        shown = (await call(client, "get_inputs", project="p"))["inputs"]
        number = next((i for k, i in keys.items() if i["type"] in ("float", "int") and k in shown
                       and i.get("min") is not None), None)
        if number is not None:
            bad = await call(client, "set_inputs", project="p",
                             inputs={number["key"]: {"value": 1, "unit": "lightyear"}})
            assert bad["rejected"] and not bad["applied"]
            low = await call(client, "set_inputs", project="p",
                             inputs={number["key"]: {"value": number["min"] - 1e9, "unit": number["unit"]}})
            assert low["rejected"]
        if "max_iter" in keys:
            assert (await call(client, "set_inputs", project="p", inputs={"max_iter": 10}))["applied"]
        if "shape" in keys:                                   # geometry where relevant: the shape library
            g = await call(client, "set_geometry", project="p", shape=keys["shape"]["default"])
            assert g["ok"], g
        preset = next((k for k in keys if k.endswith("preset")), None)
        mesh = await call(client, "mesh", project="p", preset="Coarse" if preset else None)
        if not mesh["ok"] and "geometry" in mesh["error"].lower():     # a workspace template: import a body
            imp = await call(client, "import_geometry", project="p", path="lens.dxf", enclosure="circle")
            assert imp["ok"] and not [b for b in imp["boundary_problems"] if b["level"] == "error"], imp
            if "flow_type" in keys:
                await call(client, "set_inputs", project="p", inputs={"flow_type": "External"})
            mesh = await call(client, "mesh", project="p")
        assert mesh["ok"] and mesh["cells"] > 0, mesh
        chk = await call(client, "check", project="p")
        assert chk["ok"] and "estimate" in chk
        if not d["has_solver"]:
            return
        run = await call(client, "run", project="p", confirm=True)
        assert run["status"] == "started", run
        for _ in range(3000):
            status = await call(client, "job_status", job_id=run["job_id"])
            if status["status"] != "running":
                break
            await asyncio.sleep(0.05)
        assert status["status"] == "finished", status
        res = await call(client, "get_results", project="p")
        assert res["ok"] and res["verdict"] and res["key_numbers"], res
        plot = await client.call_tool("get_plot", {"project": "p", "kind": "residuals"})
        assert plot.content[0].type == "image" and plot.content[0].mime_type == "image/png"
        assert (await call(client, "export", project="p"))["ok"]
        rep = await call(client, "make_report", project="p")
        assert rep["ok"], rep

    with_client(api, body)
    log = (ws / "p.afsproj" / "ai_log.jsonl").read_text(encoding="utf-8")
    assert '"tool": "make_report"' in log or not find_cases()[0][template].has_solver


# ---- off by default; works without the mcp package ----------------------------------------------------

def test_server_refuses_when_off(capsys):
    from aeroflowsim.connector.server import main
    assert main(ConnectorSettings()) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "is off" in captured.err and "--allow-ai-connector on" in captured.err


def test_cli_mcp_is_off_by_default(tmp_path):
    env = {**os.environ, "AEROFLOWSIM_CONNECTOR_SETTINGS": str(tmp_path / "none.json")}
    out = subprocess.run([PYTHON, "-m", "aeroflowsim", "mcp"], capture_output=True, text=True, env=env, timeout=120,
                         stdin=subprocess.DEVNULL)
    assert out.returncode == 2 and out.stdout == "" and "is off" in out.stderr


def test_settings_command_turns_it_on(tmp_path):
    env = {**os.environ, "AEROFLOWSIM_CONNECTOR_SETTINGS": str(tmp_path / "c.json")}
    out = subprocess.run([PYTHON, "-m", "aeroflowsim", "settings", "--allow-ai-connector", "on", "--workspace",
                          str(tmp_path / "ws")], capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0 and "Allow AI connector   on" in out.stdout
    data = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    assert data["allow"] is True and Path(data["workspace"]) == (tmp_path / "ws").resolve()


def test_aeroflowsim_works_without_mcp():
    """With `mcp` impossible to import, the package, the command line and the API still work; the server says what
    to install."""
    code = ("import sys; sys.modules['mcp'] = None\n"
            "import aeroflowsim, aeroflowsim.api, aeroflowsim.cli\n"
            "from aeroflowsim.connector.server import main\n"
            "from aeroflowsim.connector.settings import ConnectorSettings\n"
            "import tempfile\n"
            "a = aeroflowsim.api.Api(workspace=tempfile.mkdtemp())\n"
            "assert a.call('list_templates')['ok']\n"
            "assert main(ConnectorSettings(allow=True)) == 3\n"
            "print('fine')\n")
    out = subprocess.run([PYTHON, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "fine" in out.stdout and "pip install" in out.stderr


def test_mcp_is_not_imported_unless_the_server_runs():
    code = "import sys, aeroflowsim.api, aeroflowsim.cli, aeroflowsim.connector.server; print('mcp' in sys.modules)"
    out = subprocess.run([PYTHON, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "False"


# ---- no network ------------------------------------------------------------------------------------

def test_no_network_connections(tmp_path, monkeypatch):
    """A whole session (create, mesh, run, results, plot) touches no network address. (The event loop may make a
    loopback socket pair for itself; any other address fails the test.)"""
    used = []
    real_connect, real_bind = socket.socket.connect, socket.socket.bind

    def connect(self, address):
        used.append(("connect", address))
        return real_connect(self, address)

    def bind(self, address):
        used.append(("bind", address))
        return real_bind(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "bind", bind)
    api = Api(ConnectorSettings(allow=True), workspace=tmp_path)

    async def body(client):
        await call(client, "create_project", template="quasi1d_nozzle", name="q")
        await call(client, "set_inputs", project="q", inputs={"max_iter": 5})
        job = (await call(client, "run", project="q"))["job_id"]
        api.jobs.wait(job, 60)
        await call(client, "get_results", project="q")
        await client.call_tool("get_plot", {"project": "q", "kind": "residuals"})
        await call(client, "search_docs", query="nozzle")

    with_client(api, body)
    assert all(str(addr[0]) in ("127.0.0.1", "::1", "localhost") for _kind, addr in used if isinstance(addr, tuple)), used


# ---- the real program over stdio: stdout carries only the protocol ------------------------------------------

def test_stdio_server_stays_clean_when_libraries_print(tmp_path):
    """OpenCASCADE prints 'Statistics on Transfer' to the C-level stdout when it reads a STEP file; the server must
    keep that off the protocol channel, so the next call still works."""
    pytest.importorskip("mcp")
    from mcp import Client, StdioServerParameters
    ws = tmp_path / "ws"
    ws.mkdir()
    shutil.copy(DATA / "plate_with_hole.step", ws / "plate.step")
    settings = tmp_path / "c.json"
    save_settings(ConnectorSettings(allow=True, workspace=str(ws)), settings)
    params = StdioServerParameters(command=PYTHON, args=["-m", "aeroflowsim", "mcp"], cwd=str(ROOT),
                                   env={**os.environ, "AEROFLOWSIM_CONNECTOR_SETTINGS": str(settings)})

    async def main():
        async with Client(params, read_timeout_seconds=300) as client:
            names = [t.name for t in (await client.list_tools()).tools]
            await call(client, "create_project", template="geometry_2d", name="g")
            imp = await call(client, "import_geometry", project="g", path="plate.step")
            after = await call(client, "list_projects")
            return names, imp, after

    started = time.time()
    names, imp, after = asyncio.run(main())
    assert names == TOOLS and "ok" in imp and after["ok"] and len(after["projects"]) == 1, (imp, after)
    assert time.time() - started < 300


def test_snippets_for_the_installed_program(monkeypatch):
    """Inside AeroFlowSim.exe (PyInstaller sets sys.frozen) the AI app starts the program itself: `<program> mcp`."""
    import sys

    from aeroflowsim.connector import snippets
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    entry = snippets.server_entry()
    assert entry == {"command": sys.executable, "args": ["mcp"]}
    assert '"args": [\n        "mcp"' in snippets.claude_desktop_json()
    # an explicit python (a source installation) keeps the python form
    assert snippets.server_entry("py.exe")["args"] == ["-m", "aeroflowsim", "mcp"]


def test_claude_desktop_extension(tmp_path):
    """The one-click extension (tools/build_mcpb.py): a valid bundle whose start command, exactly as Claude Desktop
    runs it (`<program> mcp --extension --workspace <folder>`), serves the connector although "Allow" was never
    ticked (installing the extension is the opt-in), inside the chosen workspace only."""
    pytest.importorskip("mcp")
    import json
    import zipfile

    from mcp import Client, StdioServerParameters
    sys_path = str(ROOT / "tools")
    import sys
    sys.path.insert(0, sys_path)
    try:
        import build_mcpb
    finally:
        sys.path.remove(sys_path)
    files = {}
    for platform in build_mcpb.PROGRAMS:
        path = build_mcpb.build(platform, tmp_path / "dist")
        with zipfile.ZipFile(path) as z:
            assert sorted(z.namelist()) == ["icon.png", "manifest.json"]       # no code inside, only instructions
            files[platform] = json.loads(z.read("manifest.json"))
    m = files["windows"]
    assert m["server"]["type"] == "binary" and m["compatibility"]["platforms"] == ["win32"]
    assert [t["name"] for t in m["tools"]] == TOOLS
    assert m["user_config"]["program"]["default"].endswith("AeroFlowSim/AeroFlowSim.exe")
    args = m["server"]["mcp_config"]["args"]
    assert args[:2] == ["mcp", "--extension"]

    ws = tmp_path / "ws"
    settings = tmp_path / "never_allowed.json"                                  # missing file: "Allow" is off
    real = [ws.as_posix() if a == "${user_config.workspace}" else a for a in args]
    params = StdioServerParameters(command=PYTHON, args=["-m", "aeroflowsim", *real], cwd=str(ROOT),
                                   env={**os.environ, "AEROFLOWSIM_CONNECTOR_SETTINGS": str(settings)})

    async def main():
        async with Client(params, read_timeout_seconds=120) as client:
            names = [t.name for t in (await client.list_tools()).tools]
            made = await call(client, "create_project", template="sod_shock_tube", name="ext")
            return names, made

    names, made = asyncio.run(main())
    assert names == TOOLS and made["ok"], made
    assert (ws / "ext.afsproj").is_dir() and not settings.exists()            # the workspace chosen; settings untouched

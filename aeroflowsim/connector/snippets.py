# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The configuration text a user copies into an AI client (the GUI page shows it with a Copy button; AeroFlowSim never
edits another program's configuration files).

Formats checked against the current official documentation (November 2026):
  * Claude Desktop: claude_desktop_config.json, {"mcpServers": {name: {"command", "args", "env"}}}
    (modelcontextprotocol.io, "Connect to local MCP servers"); file in %APPDATA%\\Claude (Windows),
    ~/Library/Application Support/Claude (macOS), ~/.config/Claude (Linux).
  * Claude Code: `claude mcp add --transport stdio --scope user <name> -- <command> <args>` (code.claude.com/docs/en/mcp), or the plugin in
    integrations/claude (skill + server) from the marketplace at the repository root.
  * Any other MCP client: the same {"mcpServers": ...} JSON (the common format), stdio transport.
"""

import json
import sys

SERVER_NAME = "aeroflowsim"


def installed_program() -> bool:
    """True inside the installed program (AeroFlowSim.exe / .app / AppImage, built by PyInstaller): there is no
    python to give an AI app, the program itself serves the connector with  AeroFlowSim mcp ."""
    return bool(getattr(sys, "frozen", False))


def server_entry(python=None) -> dict:
    """How an AI app starts the server: `<python> -m aeroflowsim mcp` (a Python installation), or `<program> mcp`
    (the installed program, when `python` is None)."""
    if python is None and installed_program():
        return {"command": sys.executable, "args": ["mcp"]}
    return {"command": str(python or sys.executable), "args": ["-m", "aeroflowsim", "mcp"]}


def claude_desktop_json(python=None) -> str:
    return json.dumps({"mcpServers": {SERVER_NAME: server_entry(python)}}, indent=2)


def generic_json(python=None) -> str:
    return json.dumps({"mcpServers": {SERVER_NAME: {"type": "stdio", **server_entry(python)}}}, indent=2)


def claude_code_command(python=None) -> str:
    entry = server_entry(python)
    command = f'"{entry["command"]}"' if " " in entry["command"] else entry["command"]
    return f"claude mcp add --transport stdio --scope user {SERVER_NAME} -- {command} " + " ".join(entry["args"])


def claude_code_plugin_commands() -> list[str]:
    return ["/plugin marketplace add Dhanwin5/AeroFlowSim", "/plugin install aeroflowsim@aeroflowsim"]


def desktop_config_location() -> str:
    if sys.platform == "win32":
        return r"%APPDATA%\Claude\claude_desktop_config.json"
    if sys.platform == "darwin":
        return "~/Library/Application Support/Claude/claude_desktop_config.json"
    return "~/.config/Claude/claude_desktop_config.json"

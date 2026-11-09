# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Claude plugin file made by the button "Add to Claude" (Tools > Use with AI assistants).

Current Claude Desktop versions add tools that run ON THIS COMPUTER as plugins: Customize > Plugins > Add > Upload,
a .zip with .claude-plugin/plugin.json ("Add custom connector" there only takes internet (HTTPS) servers). This module
writes such a zip for this computer:

    .claude-plugin/plugin.json      name, version, description, and the local MCP server:
                                    "<this program>" mcp --extension --workspace "<workspace folder>"
    skills/aeroflowsim/SKILL.md     the AeroFlowSim skill (workflow and honesty rules), + reference.md

The full path of the program is written in at the moment the user presses the button, so nothing has to be typed or
guessed in Claude. No Qt, no network; the file is only written, never sent anywhere.
"""

import json
import sys
import zipfile
from pathlib import Path

PLUGIN_FILE_NAME = "AeroFlowSim-Claude-plugin.zip"


def skill_folder() -> Path | None:
    """The skill's files: bundled with the installed program (claude/skill) or in the source tree."""
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / "claude" / "skill")
    candidates.append(Path(__file__).resolve().parents[2] / "integrations" / "claude" / "skills" / "aeroflowsim")
    return next((c for c in candidates if (c / "SKILL.md").is_file()), None)


def plugin_manifest(workspace: str) -> dict:
    from aeroflowsim import __version__
    from aeroflowsim.connector.snippets import server_entry
    entry = server_entry()
    args = list(entry["args"]) + ["--extension", "--workspace", str(workspace)]
    return {
        "name": "aeroflowsim",
        "displayName": "AeroFlowSim",
        "version": __version__,
        "description": ("Let Claude set up, mesh, run and report AeroFlowSim CFD projects (nozzles, propulsion, "
                        "external aerodynamics) on this computer: a skill with the workflow and honesty rules, and "
                        "the local AeroFlowSim server (no network)."),
        "author": {"name": "Dhanwin Mehta"},
        "repository": "https://github.com/Dhanwin5/AeroFlowSim",
        "license": "GPL-3.0-or-later",
        "keywords": ["cfd", "aerodynamics", "nozzle", "propulsion", "mcp"],
        "icon": "./logo.png",          # read by Anthropic's plugin directory; Claude shows a plain icon for uploads
        "mcpServers": {"aeroflowsim": {"command": entry["command"], "args": args}},
    }


def logo_file() -> Path | None:
    """The AeroFlowSim icon (assets/icon.png): bundled with the installed program or in the source tree."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    path = root / "assets" / "icon.png"
    return path if path.is_file() else None


def write_plugin_file(folder, workspace) -> Path:
    """Write the plugin zip into `folder` (made if missing); returns its path."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / PLUGIN_FILE_NAME
    skill = skill_folder()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(".claude-plugin/plugin.json", json.dumps(plugin_manifest(workspace), indent=2))
        logo = logo_file()
        if logo is not None:
            z.write(logo, "logo.png")
        if skill is not None:
            for f in sorted(skill.iterdir()):
                if f.is_file():
                    z.write(f, f"skills/aeroflowsim/{f.name}")
    return path

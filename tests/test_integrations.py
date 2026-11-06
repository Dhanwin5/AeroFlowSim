# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Claude skill and bundles (integrations/claude): tool names match the server, every template is in the
chooser table, manifests follow the documented structure, the snippets start the real server."""

import json
import re
from pathlib import Path

from aeroflowsim.api import TOOLS
from aeroflowsim.connector import snippets
from aeroflowsim.discovery import find_cases

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "integrations" / "claude"
SKILL = PLUGIN / "skills" / "aeroflowsim" / "SKILL.md"
REFERENCE = PLUGIN / "skills" / "aeroflowsim" / "reference.md"
PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def frontmatter(text):
    assert text.startswith("---\n")
    head = text.split("---\n", 2)[1]
    return {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip() for line in head.splitlines() if ":" in line}


def test_skill_frontmatter_is_portable():
    meta = frontmatter(SKILL.read_text(encoding="utf-8"))
    assert meta["name"] == "aeroflowsim" and set(meta) <= PORTABLE_KEYS
    assert 50 < len(meta["description"]) <= 1536
    assert len(SKILL.read_text(encoding="utf-8").splitlines()) < 500


def test_skill_names_only_real_tools_and_lists_all():
    named = set(re.findall(r"`([a-z_]+)(?:\(|`)", SKILL.read_text(encoding="utf-8") + REFERENCE.read_text(encoding="utf-8")))
    tool_like = {n for n in named if "_" in n and (n.startswith(("list_", "get_", "set_", "describe_", "create_",
                                                                   "import_", "make_", "search_", "stop_", "continue_",
                                                                   "compare_", "job_")))}
    assert tool_like <= set(TOOLS), tool_like - set(TOOLS)
    table = REFERENCE.read_text(encoding="utf-8")
    assert all(f"`{t}" in table for t in TOOLS), [t for t in TOOLS if f"`{t}" not in table]


def test_every_template_is_in_the_chooser_table():
    text = SKILL.read_text(encoding="utf-8")
    table = text.split("## Choosing the template", 1)[1].split("\n## ", 1)[0]
    missing = [t for t in find_cases()[0] if f"`{t}`" not in table]
    assert not missing, f"add these templates to the chooser table of SKILL.md: {missing}"


def test_plugin_manifest_structure():
    data = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "aeroflowsim" and not data["name"].startswith(("claude", "anthropic"))
    server = data["mcpServers"]["aeroflowsim"]
    assert server["args"] == ["-m", "aeroflowsim", "mcp"] and server["command"] == "${user_config.python}"
    assert set(data["userConfig"]["python"]) <= {"type", "title", "description", "required", "default"}
    assert (PLUGIN / "skills" / "aeroflowsim" / "SKILL.md").is_file()
    assert not (PLUGIN / ".claude-plugin" / "skills").exists()        # components live at the plugin root


def test_marketplace_points_at_the_plugin():
    data = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert {"name", "owner", "plugins"} <= set(data) and data["owner"]["name"]
    entry = data["plugins"][0]
    assert entry["source"].startswith("./") and ".." not in entry["source"]
    assert (ROOT / entry["source"] / ".claude-plugin" / "plugin.json").is_file()
    assert snippets.claude_code_plugin_commands()[1] == f"/plugin install {entry['name']}@{data['name']}"


def test_snippets():
    desktop = json.loads(snippets.claude_desktop_json("C:/py/python.exe"))
    assert desktop == {"mcpServers": {"aeroflowsim": {"command": "C:/py/python.exe", "args": ["-m", "aeroflowsim", "mcp"]}}}
    assert json.loads(snippets.generic_json())["mcpServers"]["aeroflowsim"]["type"] == "stdio"
    cmd = snippets.claude_code_command("C:/Program Files/py/python.exe")
    assert cmd.startswith("claude mcp add --transport stdio --scope user aeroflowsim -- \"C:/Program Files/py/python.exe\"")
    example = json.loads((PLUGIN / "desktop" / "claude_desktop_config.example.json").read_text(encoding="utf-8"))
    assert example["mcpServers"]["aeroflowsim"]["args"] == ["-m", "aeroflowsim", "mcp"]

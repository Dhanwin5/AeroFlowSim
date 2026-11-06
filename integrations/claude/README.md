# AeroFlowSim for Claude (and other MCP clients)

This folder lets an AI assistant drive AeroFlowSim through its local MCP server (`python -m aeroflowsim mcp`).
Full instructions: `docs/user_guide.md`, section "Using AeroFlowSim with Claude and other AI assistants".

| File | For |
|---|---|
| `.claude-plugin/plugin.json` | Claude Code plugin: the skill below + the MCP server (asks once for your AeroFlowSim python) |
| `skills/aeroflowsim/SKILL.md`, `reference.md` | The skill: workflow, template chooser, units, honesty and cost rules, examples |
| `desktop/claude_desktop_config.example.json` | Claude Desktop: the entry to add to `claude_desktop_config.json` |
| `mcp.generic.example.json` | Any other MCP client (common `mcpServers` format, stdio) |
| `../../.claude-plugin/marketplace.json` | The repository as a Claude Code plugin marketplace |

Before any of these work: install AeroFlowSim with the extra `pip install -e ".[ai]"` and allow the connector
(desktop app: Tools > Use with AI assistants, or `python -m aeroflowsim settings --allow-ai-connector on`).

Claude Code:

```
/plugin marketplace add Dhanwin5/AeroFlowSim
/plugin install aeroflowsim@aeroflowsim
```

or the server alone: `claude mcp add --transport stdio --scope user aeroflowsim -- <python> -m aeroflowsim mcp`.

Formats were written from the official documentation of November 2026 (code.claude.com plugin manifest and
marketplace references, skills page, MCP page; modelcontextprotocol.io "Connect to local MCP servers"). Not verified
here: `claude plugin validate` (the Claude Code CLI was not installed on the development machine; the test
`tests/test_integrations.py` checks the structure instead), and a Claude Desktop extension (`.mcpb`) is not provided,
because the server needs the user's own Python installation of AeroFlowSim; the config entry is the documented way for
such a local server.

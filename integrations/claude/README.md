# AeroFlowSim for Claude

Let Claude set up, mesh, run and report computational fluid dynamics (CFD) simulations with
[AeroFlowSim](https://github.com/Dhanwin5/AeroFlowSim), a free, open-source CFD program for nozzle and propulsion
aerodynamics: rocket and CubeSat thruster nozzles, intakes, airfoils, nose cones and other bodies in 2D,
axisymmetric and 3D, inviscid and viscous.

Ask in plain English, for example "thrust and Isp of a nitrogen cold-gas thruster, 5 bar, 1 mm throat, area ratio
25". Claude chooses the template, fills the inputs with units, meshes, checks, runs, reads the results with
AeroFlowSim's own validity checks (convergence, mass balance, mesh quality) and writes the report.

![AeroFlowSim](logo.png)

## What you need

1. Install the AeroFlowSim program (free): download the installer from
   [the releases page](https://github.com/Dhanwin5/AeroFlowSim/releases) and run it. On Windows keep the box
   "Let Claude and the command line start AeroFlowSim (add it to PATH)" ticked.
2. Add this plugin in Claude (Customize > Plugins). Restart Claude once after installing AeroFlowSim, so that it
   finds the program.
3. Ask Claude: "List the AeroFlowSim templates".

## What this plugin runs, reads and sends

* **Runs:** the AeroFlowSim program installed on your computer, started as `AeroFlowSim mcp --extension`. It talks to
  Claude through standard input and output only: no network connection, no listening port, nothing is uploaded by
  AeroFlowSim.
* **Reads and writes:** only the workspace folder `Documents/AeroFlowSim Projects` (changeable in AeroFlowSim:
  Tools > Use with AI assistants). It never works outside it, never deletes or overwrites anything (new projects need
  new names), and never runs code or shell commands: only AeroFlowSim's own functions.
* **Asks first:** before runs estimated to take longer than 10 minutes or to need much memory.
* **Becomes part of your conversation:** what Claude reads from AeroFlowSim (inputs, numbers, tables, pictures) is
  sent to Claude like anything else you share in a chat.

Privacy details: [PRIVACY.md](https://github.com/Dhanwin5/AeroFlowSim/blob/main/PRIVACY.md).

## Contents

| File | For |
|---|---|
| `.claude-plugin/plugin.json` | The plugin: name, description, and the local AeroFlowSim server |
| `skills/aeroflowsim/SKILL.md`, `reference.md` | The skill: workflow, template chooser, units, honesty and cost rules, examples |
| `logo.png` | The AeroFlowSim logo |
| `desktop/claude_desktop_config.example.json` | Older Claude Desktop versions: the entry for `claude_desktop_config.json` |
| `mcp.generic.example.json` | Any other MCP app (common `mcpServers` format, stdio) |

Claude Code: `/plugin marketplace add Dhanwin5/AeroFlowSim`, then `/plugin install aeroflowsim@aeroflowsim`.
A plugin file with the full path of your own installation (for a program outside PATH, or a source installation)
is made by the button **Add to Claude** in AeroFlowSim (Tools > Use with AI assistants).

Licence: GPL-3.0-or-later. Support: [GitHub issues](https://github.com/Dhanwin5/AeroFlowSim/issues).
Author: Dhanwin Mehta.

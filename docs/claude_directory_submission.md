# Submitting AeroFlowSim to Anthropic's plugin directory

Written 9 November 2026 from Anthropic's documentation (claude.com/docs: "Plugin pre-submission checklist", "Plugin
feature support across platforms"; code.claude.com/docs: "Publish and distribute a plugin", "Plugin manifest
reference"). Check those pages again before submitting: the rules may have changed.

## What is submitted

The plugin folder `integrations/claude` of the public GitHub repository `Dhanwin5/AeroFlowSim`:

| Requirement (directory) | Where it is met |
|---|---|
| `.claude-plugin/plugin.json` with name, version, description, author | `integrations/claude/.claude-plugin/plugin.json` (`name` aeroflowsim, kebab-case, own product name) |
| README of at least 40 words in the plugin folder, saying what the plugin runs, sends or fetches | `integrations/claude/README.md` ("What this plugin runs, reads and sends") |
| Licence | `"license": "GPL-3.0-or-later"` |
| Icon (listing) | `"icon": "./logo.png"` (`integrations/claude/logo.png`) |
| Documentation, support, privacy links (listing) | `documentationUrl`, `supportUrl`, `privacyPolicyUrl` (`PRIVACY.md`) |
| MCP server declared with `command` and `args`, no `${...}` variable other than `${CLAUDE_PLUGIN_ROOT}` | `"command": "AeroFlowSim", "args": ["mcp", "--extension"]` |
| No credentials, no package launchers (npx, uvx), no bundled binaries, files < 256 KiB | none used (logo PNG is an allowed image) |
| Readable source | the skill is Markdown; AeroFlowSim's source is public in the same repository |

Expected result of **Validate**: no "Blocking" finding. A **"Policy hold"** is expected for the MCP server, because it
starts a program that is not inside the plugin folder (the installed AeroFlowSim): an Anthropic reviewer reads it.
That is normal and not a rejection; the README explains it.

Where it works (Anthropic's table): Claude Code and Cowork on the user's computer, and the Claude desktop app's chat
(tested 9 Nov 2026: `list_templates` ran through the uploaded plugin in a chat of Claude Desktop 4.23118). On
claude.ai in a web browser a local program cannot be started.

Users need the AeroFlowSim program installed (Windows: the box "add it to PATH" ticked, the default) and must restart
Claude once after installing it.

## Steps (the owner of the repository does them; it publishes under their name)

1. Make sure the release with these files is pushed to `main` on GitHub (and the installers are on the release page).
2. Open https://claude.ai/directory/manage in a browser, signed in with the paid Claude account (Pro is enough).
3. Click **Submit new**.
4. At "What would you like to submit?" choose **Plugin bundle**.
5. **Source** step: repository `Dhanwin5/AeroFlowSim`, branch `main`, plugin path `integrations/claude`.
6. Click **Validate**. Read the report:
   * **Blocking**: must be fixed (send the report to the developer / Claude Code session), push the fix, then
     **Re-validate**.
   * **Policy hold** (expected for the MCP server), **Warning**, **Note**: you can continue.
7. Fill in the listing fields the form asks for (texts below), then **Submit for review**.
8. Follow the review on the plugin's page in the developer portal (tab **Versions**). Anthropic may ask questions.

## Texts for the form

* **Name:** AeroFlowSim
* **Short description:** Set up, mesh, run and report CFD simulations of nozzles, rocket and CubeSat thrusters and
  external aerodynamics with the free AeroFlowSim program on your own computer.
* **Category (if asked):** Engineering / Science
* **What it does (long):** the first two paragraphs of `integrations/claude/README.md`.
* **Data handling:** local only; the plugin starts the AeroFlowSim program on the user's computer over standard
  input/output; AeroFlowSim makes no network connections; it works only inside the workspace folder and never deletes
  files; what Claude reads becomes part of the conversation. Privacy policy:
  https://github.com/Dhanwin5/AeroFlowSim/blob/main/PRIVACY.md
* **Support:** https://github.com/Dhanwin5/AeroFlowSim/issues

## After it is listed

Users find AeroFlowSim in Claude under **Customize > Plugins > Discover** (and with the logo). For every new release:
raise `version` in `plugin.json` (a test checks it equals the program's version), push, and the directory picks up
the new commit (it is scanned again).

PROMPT 13 - AI connector and skill: any user can drive AeroFlowSim with Claude (or any MCP-capable AI). Model: Sonnet.
Paste everything below into ONE new Claude Code session, ONLY after the viscous stage (Prompt 12) is committed and pushed. Never run two sessions on the repository at the same time.
First action: create docs/roadmap/ai_connector.md containing this whole text; the ledger goes at the bottom of that file.

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder C:\Projects\CFD software, GitHub Dhanwin5/AeroFlowSim, repository PUBLIC, GPL-3.0-or-later). I am a beginner programmer who knows aerospace engineering and CFD theory. This is the ONLY prompt for this stage: do all parts in order, in this one session, without waiting for me between parts.

1. Start: run git status and git log. If there are uncommitted changes you did not make, STOP and tell me (another session may be running). Then read CLAUDE.md, docs/gap_register.md, docs/roadmap/ai_assistant.md (the built-in assistant plugin: its Proposal validation is reused here), docs/developer_guide.md, and skim aeroflowsim/cli.py, schema.py, project.py, runner.py, job.py, checks.py, smart_rules.py, discovery.py, tasks.py, assistant/, gases/, post/, cases/ (every template), tests for the privacy rule. Write a short plan in plain words, then start at once.
2. Do not stop to ask questions. Decide the way the best tools would; give one sentence of why in the summary. Stop only before: deleting files you did not create in this session, adding a dependency other than the one pre-approved below, or anything outward-facing apart from the push at the end.
3. Ledger = your memory: after every part commit, then add a ledger entry (done, how verified, next, anomalies). If the conversation is compacted, re-read the ledger and carry on. Do not stop between parts to report to me.
4. Out of room? Stop at the END of a part, commit, write the ledger entry, say which part is next.
5. Never tune a number to pass. Report result lines only. Rule 4 of CLAUDE.md: no validated number may change (this stage must not touch solver numerics).
6. Never write unquoted shell heredocs (the shell runs backticks inside them).
7. Walk through my next actions for every feature (connect a client, turn the connector on and off, old project, stop and continue a run, new template added later, new input added later, units, command line) and write them into tests.

## Goal

ANY user, with ANY template, can tell an AI assistant in plain English what they want, and the assistant sets up, meshes, checks, runs, reads and reports with AeroFlowSim safely and reproducibly. Works with Claude Desktop, Claude Code and any other client that speaks MCP (an open standard). AeroFlowSim itself stays fully usable without it, nothing is loaded unless it is used, and the AI never replaces the physics: the software's own checks decide what is converged and what is valid.

Deliverables: (1) `aeroflowsim mcp`, a local stdio MCP server; (2) a thin `aeroflowsim/api.py` layer under it; (3) a Skill plus a Claude Code plugin / Claude Desktop bundle in `integrations/claude/`; (4) a GUI help page and docs; (5) tests that cover EVERY template, and evals.

## Context

* Templates today (cases/): demo_heat1d, external_2d, external_3d, geometry_2d, imported_mesh, nozzle_axi, quasi1d_nozzle, sod_shock_tube (and any added later). Inputs, units, ranges and descriptions come from each template's schema.toml, which also builds the GUI panels. New templates and new inputs (the viscous stage adds Flow model, wall thermal condition, turbulence inputs) must appear in the connector WITHOUT code changes.
* CLI exists (aeroflowsim/cli.py: run, report, export, snapshot, assist, mesh-info, mesh-convert, ...). The built-in assistant (aeroflowsim/assistant/) validates proposed values against the schema; reuse that validation.
* The software already has validity checks with "What to try" advice, smart rules (suggested numerics, first-layer height), a run memory estimate (3D), validation reports, gas library with sources, and per-run provenance. The connector must use them, not re-implement them.
* Privacy rule of the project: nothing is loaded, imported or contacted unless the user turns it on; no telemetry. The connector is local-only (stdio). What the AI client reads (numbers, pictures) becomes part of that conversation with the AI provider: the docs must say so plainly.

## Decisions (made: follow them)

* Transport: stdio only. No network listener, no cloud, no telemetry. Logs go to stderr or a file, never to stdout (it carries the protocol).
* Dependency: the official Python MCP SDK (`mcp`, MIT) as an OPTIONAL extra `aeroflowsim[ai]`, exact version pinned, imported only when `aeroflowsim mcp` runs. AeroFlowSim must work without it (tested). Pre-approved.
* Opt-in: setting "Allow AI connector" is OFF by default (Tools > Preferences and `aeroflowsim settings`). With it off, `aeroflowsim mcp` exits at once with a clear message on how to turn it on.
* `aeroflowsim/api.py`: pure functions, JSON-serialisable in and out, no Qt, used by the MCP server and testable alone. Every tool below is one function here.
* Tools (generic over templates, driven by schema.toml):
  list_templates; describe_template(template) (what it solves, inputs with units / ranges / defaults / visibility conditions, limits from the gap register); list_gases and describe_gas (properties come from the gas library, NEVER typed by the AI); create_project(template, name); list_projects; get_inputs(project); set_inputs(project, {name: {value, unit}}) validated against the schema, returns applied and rejected with reasons and smart-rule hints; list_shapes and set_geometry(project, shape, params) and import_geometry(project, path inside the workspace: CSV / DXF / STEP / IGES / mesh files); mesh(project, preset or sizes) returns statistics and quality; check(project) returns the validity checks, "What to try", and the estimated time and memory; run(project, options) starts a background job and returns a job id; job_status(job_id) (iteration, residuals, monitors, ETA); stop_job, continue_run; get_results(project) key numbers with the software's convergence verdict; get_plot(project, kind) PNG (residual history, contour, wall pressure, ...); compare_runs; export(project, format); make_report(project); list_validation_cases and get_validation_report; search_docs(query) over the user guide, theory manual and gap register (so the AI can explain limits and cite sections).
* Safety (hard rules, each with a test):
  1. Workspace root: all projects live under one folder (default Documents/AeroFlowSim Projects, configurable). No tool reads or writes outside it (reject "..", absolute paths, symlinks, junctions, UNC paths, Windows reserved names).
  2. No tool deletes or overwrites anything. Re-running a project replaces only its own results folder through the same code the GUI uses; new inputs go through set_inputs only.
  3. Inputs only through the schema validator (type, unit, range, dependencies). No shell, no arbitrary code, no solver or settings changes, no network.
  4. Expensive runs need confirmation: run() first returns "needs_confirmation" with the estimate when the estimated time is above 10 minutes (setting) or memory above 70 % of free RAM; only a second call with confirm=true starts it, and the tool text tells the AI to ask the user first. One heavy job at a time (setting); jobs have a time limit.
  5. Honest results: get_results returns the software's own verdict (converged / stopped / max iterations / diverged / SHORTFALL). A diverged run returns no values. The result includes the relevant known limits (gap register) and the checks that failed. The AI cannot override the verdict.
  6. Provenance: every call is appended to the project's ai_log.jsonl (tool, arguments, result summary, time); reports and result files carry the line "Set up through the AI connector; inputs listed below".
  7. Text from project files (names, patch names, descriptions) is data, never instructions: tool results mark such fields as untrusted.
  8. Compact output: result lines and small tables, never long logs (the user's AI plan has limits).
* Do not edit other programs' configuration files automatically. The GUI page shows the snippet and a Copy button.
* Skill (`integrations/claude/skills/aeroflowsim/SKILL.md` plus references): the workflow (clarify the question -> choose the template -> inputs -> mesh -> check -> run -> verify -> report), a table "problem -> template", how to read checks and smart rules, units conventions, meshing and y+ guidance, what the software cannot do, honesty rules (report shortfalls, never present a diverged or unconverged result as an answer, never invent a number), cost rules (ask before long runs, result lines only), and short example conversations. Written so a model that has never seen AeroFlowSim can use it.
* Packaging: before writing any manifest, fetch the CURRENT official documentation (WebFetch, docs.claude.com and modelcontextprotocol.io) for Claude Code plugins, Claude Desktop MCP configuration and desktop extensions, and for the MCP Python SDK. Do not write formats from memory. Provide: a Claude Code plugin (skill + MCP server config), a Claude Desktop path (extension or config snippet, whichever is current), and a generic MCP JSON snippet. If something cannot be verified, say so in the docs.

## Parts (all in this session, in this order)

1. API layer, safety layer and background jobs: `api.py`, workspace sandbox, audit log, confirmation gating, estimates, job manager reusing runner.py / job.py. Tests for every safety rule above and for the API on every template.
2. MCP server: tools, resources (schema, docs, validation report), stdio hygiene, setting on / off. A fake MCP client (in process) drives it. TEST FOR EVERY TEMPLATE, discovered from cases/ automatically (not listed by hand): describe -> create -> set valid / invalid / wrong-unit inputs -> geometry where relevant -> mesh (coarsest preset) -> check -> run (tiny) -> results -> plot -> export -> report; also stop and continue, old project, a temporary extra template and a temporary extra input appear with no code change, sandbox escapes fail, nothing is deleted, confirmation gating works, the connector is off by default, AeroFlowSim works without `mcp` installed, no sockets are opened, stdout stays clean.
3. Skill and bundles in `integrations/claude/` (after reading the current official documentation); tests that the skill's tool names match the server's tool list and that every template appears in its chooser table.
4. GUI and docs: Tools > "Use with AI assistants" page (Allow switch, workspace folder, Copy snippets for Claude Desktop, Claude Code and generic MCP, a test button that starts the server and lists the tools), user guide page "Using AeroFlowSim with Claude and other AI assistants" (setup per client, what it can do, what it never does, privacy table: what the AI reads and where it goes, cost note: it uses the user's own AI plan, troubleshooting), README section, theory / philosophy note (assists, never replaces physics), developer guide (how to add a tool), gap register, CHANGELOG, docs/roadmap/README.md. Screenshots of the new page, light and dark.
5. Evals: docs/ai_evals/ with 25 natural-language tasks covering EVERY template (for example: N2 nozzle for 50 mN at 5 bar and its Isp; Mach 2 wedge 10 degrees and the shock angle; Sod tube; NACA 2412 at Mach 0.6 and 2 degrees; sphere at Mach 3 in 3D; solve my imported Gmsh file; a case that must be refused because it is out of scope; a request with a wrong unit; a request that needs confirmation), each with machine-checkable expectations (template chosen, key numbers within the validated tolerance, no forbidden action, honest about limits, asked before the long run). Write a runner script. Check the current Claude Code documentation for non-interactive use before relying on any flag. Run the 8 cheapest tasks on Sonnet to limit cost; list the rest as a checklist for me. Report the pass rate honestly; never edit a task to make it pass.
6. Finish: full fast and GUI tests, quick validation (no validated number changed), push.

## Quality gates

* Tests pass; every template covered by the connector test; no Qt in api.py or the server; privacy tests updated and passing (stdio only); AeroFlowSim works without the `mcp` package.
* No validated number changes. No tag, release or repository-settings change.

## Done when (check every line with evidence)

1. `aeroflowsim mcp` serves every template through generic tools; a new template or input appears without code changes (tested).
2. All safety rules are enforced and tested; the connector is off by default.
3. Skill and bundles exist, built from the current official formats; the GUI page and docs are written.
4. Evals written; the subset run and honestly reported.
5. Docs, gap register, CHANGELOG, roadmap README and the ledger written; pushed.

At the very end give me a plain-language summary: what works now, how a new user connects Claude step by step, what you decided and why (one sentence each), the walkthrough of the most important new module (CLAUDE.md rule 15), the eval pass rate, the gap register changes, and anything I should check by hand.

---

## Ledger (progress log)

### Ledger entry 0 (6 Nov 2026): start
* Repository clean (only the user's untracked linkedin_media/), viscous stage pushed (173f6d6). Prompt saved here.

### Ledger entry 1 (6 Nov 2026): Part 1 - API, safety layer, jobs
* Done: `aeroflowsim/api.py` (25 tools, class Api, `Api.call(name, **args)` = error wrapper + audit log),
  `aeroflowsim/connector/` (settings.py JSON in app data, OFF by default; sandbox.py workspace checks incl. junctions;
  jobs.py one background run at a time, clean Stop, time limit). Reuses the built-in assistant's schema review,
  project.run_project / build_project_mesh, checks, smart rules, post report / export / pictures. CLI `settings`,
  `mcp`. Optional extra `ai = ["mcp==2.3.0"]` (installed in .venv).
* Workspace templates (geometry_2d): import_geometry runs the GUI's Import + optional Enclosure + Accept suggestions.
* Fixed on the way: a uniform field crashed contour pictures (levels 1e5 + 1e-12 == 1e5, post/pictures.py; no number
  changes); report gets the provenance line when ai_log.jsonl exists.
* Verified: tests/test_api.py 55 passed (every safety rule, inputs of every template, new template / input, old
  project, stop + continue, time limit). Generic flow script ran mesh -> run -> results -> plots -> export -> report
  on all 8 templates.
* Anomalies: boundary tables (type `boundaries`) are not settable by the AI (template defaults; edges with no
  suggested name need the GUI). Run-time estimate is a rough upper bound (max iterations x cells x measured cost).
* Next: Part 2 tests through a real MCP client (server.py written; in-process Client lists 25 tools, image works).

### Ledger entry 2 (6 Nov 2026): Part 2 - MCP server
* Done: `aeroflowsim/connector/server.py` (MCPServer of the official SDK mcp 2.3.0; every Api method a tool with its
  docstring, read-only / non-destructive / closed-world annotations; get_plot returns a PNG image block; resources:
  template schema, validation report, docs; refuses unless allowed; missing `mcp` -> install hint, exit 3).
* SDK facts read from the installed source (the docs page did not cover them): `MCPServer.run("stdio")`; the stdio
  transport points fd 1 at stderr while serving (Gmsh / OCC output cannot corrupt the protocol); `Client(server)`
  connects in process for tests; the SDK imports the OpenTelemetry API only (no exporter, sends nothing).
* Verified: tests/test_mcp_server.py 16 passed - EVERY template (discovered) through a real client: describe, create,
  valid / invalid / wrong-unit inputs, shape or imported geometry, mesh, check, run, job_status, results, PNG plot,
  export, report; tool list = API; off by default (function and CLI); `settings` turns it on; works without `mcp`;
  `mcp` not imported unless serving; no non-loopback socket; the real `aeroflowsim mcp` process over stdio survives
  OpenCASCADE printing during a STEP import.
* Fixed: contour pictures of a nearly uniform field (relative band; same bug hit the report of a 10-iteration run).
* Next: Part 3 - fetch current Claude Code plugin / Claude Desktop extension docs, then skill and bundles.

### Ledger entry 3 (6 Nov 2026): Part 3 - skill and bundles
* Read first (WebFetch, Nov 2026): code.claude.com plugin manifest reference, marketplace reference, skills page,
  MCP page (`claude mcp add --transport stdio --scope user <name> -- <cmd>`); modelcontextprotocol.io "Connect to
  local MCP servers" (claude_desktop_config.json locations and shape).
* Done: `integrations/claude/` - plugin.json (skill + MCP server; userConfig asks for the AeroFlowSim python),
  skills/aeroflowsim/SKILL.md (workflow, chooser table of all 8 templates, units, gases, y+, honesty, cost, limits,
  examples) + reference.md (every tool, reading checks, sweeps); desktop and generic config examples; repository-root
  `.claude-plugin/marketplace.json`; `aeroflowsim/connector/snippets.py` builds the snippets with the running python.
* Verified: tests/test_integrations.py 6 passed (portable frontmatter, only real tool names, every tool documented,
  every discovered template in the chooser table, manifest / marketplace structure, snippets).
* Not verified: `claude plugin validate` (Claude Code CLI not installed here); no .mcpb Desktop extension (the server
  needs the user's own Python install; the config entry is the documented route). Both stated in the README.
* Next: Part 4 - GUI page Tools > Use with AI assistants, docs.

### Ledger entry 4 (6 Nov 2026): Part 4 - GUI and docs
* Done: Tools > Use with AI assistants (`gui/connector_page.py`: Allow, workspace folder, confirm limit, Copy tabs for
  Claude Desktop / Claude Code / other MCP apps with this computer's python, Test button via `connector/selftest.py`
  in a separate process). User guide section (setup per client, can / never does, privacy table, cost, troubleshooting),
  README section, theory manual 15b, developer guide (how to add a tool), gap register (1 done, 4 open rows),
  CHANGELOG, roadmap README, CLAUDE.md layout. Screenshots light / dark by `tools/connector_screenshots.py`
  (docs/screenshots is git-ignored, as for every screenshot).
* Verified: tests/gui/test_connector_page.py 5 passed (off by default, Save, reopen, snippets, Copy, Test while off,
  Test lists 25 tools); test_gui_privacy passes (no network code or web address in the GUI).
* Finding: the SDK's stdio client passes only a safe subset of environment variables to the server; the self-test
  passes the whole environment. Claude Desktop may behave the same: the troubleshooting text says to add APPDATA to
  `env` if the server reports "off" although allowed.
* Next: Part 5 - evals.

### Ledger entry 5 (6 Nov 2026): Part 5 - evals
* Done: docs/ai_evals/tasks.json (25 tasks, every template, machine-checkable expectations), tools/run_ai_evals.py
  (list / prepare / grade / claude mode; claude flags checked at code.claude.com/docs/en/headless), tools/ai_eval_bridge.py,
  optional session log in Api (`AEROFLOWSIM_AI_SESSION_LOG`), tests/test_ai_evals.py (4: coverage, grader catches a
  wrong number, a run after a refused input, a self-confirmed run).
* Run: no `claude` CLI and no API key on this machine, so the 8 cheapest tasks ran on Claude Sonnet subagents with the
  skill + bridge. **Pass rate 6 / 8** (results_2026-11-06.md). Failures: needs_confirmation (agent asked from `check`
  without calling `run`: safe, check not met), q1d_shock (software does not converge at 2.5 bar; agent honest).
* Bugs found by the evals and fixed: 1D continue / CLI re-run crash (Project.interpolation_source), bridge UTF-8.
* Next: Part 6 - full tests, quick validation, push.

### Ledger 6 (Part 6, 2026-11-07)
- Fast + GUI tests: 1319 passed, 1 skipped (93 GUI tests included).
- Quick validation: only timings changed; every validated number identical; the same 7 known shortfalls as before (none new).
- Pushed. No tag, release or settings change.

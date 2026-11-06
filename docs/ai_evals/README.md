# AI connector evals

`tasks.json` holds 25 natural-language tasks covering every template, each with machine-checkable expectations:
template chosen, inputs (with unit conversion), the software's verdict, key numbers within the validated tolerance
(checked in the software's own result AND in the answer text), no forbidden action (no run when an input was refused,
no run confirmed without the user), honesty about an unconverged verdict, and asking before a long run. Tasks are never
edited to make them pass.

`tools/run_ai_evals.py`:

```
python tools/run_ai_evals.py list                                  # tasks, cheapest first
python tools/run_ai_evals.py claude q1d_thrust sod --model sonnet  # run with Claude Code (claude -p) and grade
python tools/run_ai_evals.py grade <task> <workspace> <answer.txt>  # grade any finished attempt
```

The `claude` mode starts `claude -p` with `--mcp-config` (the real stdio server, a temporary workspace, the connector
allowed only there), the skill as `--append-system-prompt-file`, `--allowedTools mcp__aeroflowsim` and
`--permission-prompts none` (flags checked against code.claude.com/docs/en/headless, November 2026). Results go to
`docs/ai_evals/claude_run/results.md`.

## The run in this stage (6 Nov 2026)

The development machine had no `claude` CLI and no API key, so the 8 cheapest tasks were run by Claude **Sonnet**
agents (Claude Code subagents, one fresh agent per task) that were given only the skill (`SKILL.md`, `reference.md`)
and `tools/ai_eval_bridge.py`, a command-line bridge to the same `Api.call` the MCP server uses (one call per command;
`run` waits for the run to end). The MCP transport itself is covered by `tests/test_mcp_server.py`. Each attempt was
graded with `run_ai_evals.py grade`. Results: `results_2026-11-06.md`.

## Checklist for you (the other 17 tasks)

Run them with `python tools/run_ai_evals.py claude <task> --model sonnet` (or in Claude Desktop / Claude Code by hand,
then `grade`). Longer runs; the 3D one needs your confirmation by design.

- [ ] q1d_sweep (cost 2)
- [ ] refuse_combustion (1)
- [ ] refuse_turbomachinery (1)
- [ ] validation_question (1)
- [ ] sod (1)
- [ ] q1d_wrong_unit (1)
- [ ] imported_gmsh (2)
- [ ] nozzle_axi_euler (3)
- [ ] wedge (3)
- [ ] diamond (3)
- [ ] cylinder_m3 (3)
- [ ] geometry_dxf_body (3)
- [ ] geometry_dxf_nozzle (3)
- [ ] stop_continue (3; needs the MCP server: the bridge cannot stop a run)
- [ ] nozzle_axi_laminar (4)
- [ ] naca2412 (4)
- [ ] sphere_3d (5)

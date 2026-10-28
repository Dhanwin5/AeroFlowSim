# Prompts for the next steps

Each file here is one prompt for a NEW Claude Code session, written to be finished in that one session without
follow-up prompts: it holds the context, the decisions already made, the work in parts, the checks, and a
"Done when" list. Paste everything below the line of a file into a new session (Opus).

The session that finishes a prompt writes the next one (CLAUDE.md rule 19), with everything it found that
belongs to it (anomalies, measured numbers, open points from the gap register). So findings never have to be
carried between chats by hand.

| Prompt | File | What it does | Status |
|---|---|---|---|
| 7b | `prompt_7b.md` | Post-processing at Fluent level, MMS verification, wider validation, report, installer, 2D alpha release | done (ledger `7b_progress.md`) |
| 6e | `6e_progress.md` (ledger; the prompt text was pasted) | Remaining shapes, structured C/O-grids, mesh import / export | done (parts 1-4; see the ledger and the gap register) |
| 7c | `prompt_7c_progress.md` (ledger; the prompt text was pasted) | Optional AI assistant: provider interface (Rules, Local model, Online), schema context, Setup panel, `assist` command, tests, docs | done |
| 8 | `prompt_8.md` | Speed: Numba, implicit LU-SGS, multi-core; residual stalls; wall-clock targets | ready |

Where 6e and 7c fit after the alpha: `next_steps.md` (priority: the path to 3D, 8 -> 9 -> 10).

Recommended order after 8: 6e (remaining shapes, structured C/O grids, mesh import), 8b (low-Mach
preconditioning), 7c (AI assistant plugin), 8c (adaptive refinement), 8d (parametric studies and batch runs),
8e (unsteady flow). Speed (8) comes before the rest because the plain-NumPy solver is the main limit now
(13-19 minutes for the default 8,000-cell nozzle); every later feature is easier to use and test when runs are fast.

## Which model

Opus for prompts that add numerical methods or need many design decisions; Sonnet for well-defined building and
wiring (GUI, file formats, workflows, integrations, docs). Each prompt file names its model on its first line.

| Prompt | Model | Why |
|---|---|---|
| 7b | Opus | one very large session with many decisions, plus verification numerics (MMS, Taylor-Maccoll, GCI) |
| 8 | Opus | implicit time stepping and its stability: where subtle bugs hide |
| 6e | Sonnet | shapes, transfinite grids and mesh-file formats: well defined, follows existing patterns |
| 8b | Opus | low-Mach preconditioning changes the equations' eigenstructure |
| 7c | Sonnet | integration and GUI around a clear rule (the assistant only fills inputs) |
| 8c | Opus | adaptive refinement: mesh data structures, conservation, solution transfer |
| 8d | Sonnet | parametric studies and batch runs: workflow on top of the existing engine |
| 8e | Opus | unsteady (dual time stepping) numerics and their verification |

Small follow-ups in any session (a fix, docs, commit and push, questions) are fine on Sonnet. Do not switch model
in the middle of an Opus prompt's main work: the handover costs more than it saves.

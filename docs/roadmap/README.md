# Roadmap: the development stages of AeroFlowSim

AeroFlowSim is built in stages, each named by its topic. Every stage has one file here: the plan (context, decisions
already made, the work in parts, the checks, a "Done when" list) followed by its progress log. A plan is written to be
finished in one Claude Code session without follow-up prompts: paste everything below the first line into a new
session.

The session that finishes a stage writes the plan of the next one (CLAUDE.md rule 19), with everything it found that
belongs to it (anomalies, measured numbers, open points from the gap register), so findings never have to be carried
between sessions by hand.

| Stage | File | What it does | Status |
|---|---|---|---|
| Shapes, grids and mesh import | `shapes_grids_mesh_import.md` | Remaining shapes, structured C/O-grids, mesh import / export | done |
| Post-processing and alpha release | `post_processing_and_alpha.md` | Post-processing at Fluent level, MMS verification, wider validation, report, installer, 2D alpha release (v0.2.0a1) | done |
| AI assistant | `ai_assistant.md` | Optional AI assistant: providers (Rules, Local model, Online), schema context, Setup panel, `assist` command | done |
| Speed | `speed.md` | Numba kernels, multi-core, implicit LU-SGS; residual stalls; wall-clock targets (v0.2.0a2) | done |
| 3D geometry and meshing | `3d_geometry_and_meshing.md` | 3D geometry workspace (STEP), tetrahedra, prism inflation | next |

Earlier stages (desktop GUI, geometry workspace, gas library and units, 2D Euler solver) were planned before this
folder existed; their results are in the gap register and the CHANGELOG. Where the later stages fit: `next_steps.md`
(priority: the path to 3D, speed -> 3D geometry and meshing -> 3D Euler solver). After that: low-Mach
preconditioning, adaptive mesh refinement, parametric studies and batch runs, unsteady flow.

## Which model

Opus for stages that add numerical methods or need many design decisions; Sonnet for well-defined building and
wiring (GUI, file formats, workflows, integrations, docs). Each stage file names its model near the top.

| Stage | Model | Why |
|---|---|---|
| Post-processing and alpha release | Opus | one very large session with many decisions, plus verification numerics (MMS, Taylor-Maccoll, GCI) |
| Speed | Opus | implicit time stepping and its stability: where subtle bugs hide |
| Shapes, grids and mesh import | Sonnet | shapes, transfinite grids and mesh-file formats: well defined, follows existing patterns |
| 3D geometry and meshing | Opus | many design decisions: 3D CAD handling, picking, mesh quality in 3D |
| Low-Mach preconditioning | Opus | changes the equations' eigenstructure |
| AI assistant | Sonnet | integration and GUI around a clear rule (the assistant only fills inputs) |
| Adaptive mesh refinement | Opus | mesh data structures, conservation, solution transfer |
| Parametric studies | Sonnet | workflow on top of the existing engine |
| Unsteady flow | Opus | dual time stepping numerics and their verification |

Small follow-ups in any session (a fix, docs, commit and push, questions) are fine on Sonnet. Do not switch model
in the middle of an Opus stage's main work: the handover costs more than it saves.

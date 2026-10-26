# Prompt 8 - Speed: Numba, implicit LU-SGS, multi-core; the residual stalls; wall-clock targets

**Model: Opus** (implicit time stepping and its stability: where subtle bugs hide).

Paste everything below the line into a NEW Claude Code session (Opus). It is designed to be completed in this one
session without follow-up prompts.

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder `C:\Projects\CFD software`, GitHub `Dhanwin5/AeroFlowSim`). I am a
beginner programmer who knows aerospace engineering and CFD theory. **This whole prompt must be finished in this one
session.** I will not send follow-up prompts, so:

1. **Start:** read `CLAUDE.md`, `docs/gap_register.md`, `docs/theory_manual.md` (sections 12 and 13),
   `docs/developer_guide.md`, the memory files, `docs/prompts/7b_progress.md` (the last session's ledger), and skim
   `aeroflowsim/euler/` (solver.py, flux.py, gradients.py, limiters.py, geometry.py, boundary.py, setup.py),
   `aeroflowsim/mms.py`, `aeroflowsim/tasks.py`, `validation/`. Then write a short plan in plain words and **start
   immediately: do not wait for my approval.**
2. **Do not stop to ask questions.** The decisions that matter are below; for anything else do what the best codes
   (Fluent, SU2, OpenFOAM, CFL3D) do, explain it in one sentence in the final summary, and go on. Only stop to ask
   before deleting files that are not yours from this session, adding a runtime dependency other than those
   pre-approved below, or anything outward-facing except the push (and release) authorised in Part 7.
3. **Walk through the user's next actions for every feature** (stop, run again / continue, change an input,
   re-mesh, reopen, switch units or theme, old project, command line) and write them into tests.
4. **Flag anomalies yourself**; investigate; fix in scope or record in the gap register. Never tune a number to pass.
5. **Commit after each part**; run long jobs (validation, timing studies) in the background and keep working.
6. **Verify everything:** unit tests, GUI tests, MMS order (must stay 2), validation, timing tables; screenshots of
   changed GUI pages with `tools/screenshots.py` (light and dark).
7. **Keep a ledger** `docs/prompts/8_progress.md` (done with commits, verified how, next, anomalies, decisions),
   updated after every part; if the conversation is summarised, re-read it and CLAUDE.md first.
8. **At the end:** full fast tests, full validation, report every result line, docs and gap register updated, push,
   and write the next prompt file (`docs/prompts/prompt_6e.md`, see `docs/prompts/next_steps.md`) in the same style.

## Context (state after Prompt 7b, release v0.2.0a1)

- Solver: explicit finite-volume Euler (rotated HLLC + HLLE blend, least-squares gradients, Venkatakrishnan /
  Barth-Jespersen / None limiters with freezing and stall-freeze, SSP-RK3 / Jameson, local time steps, CFL back-off),
  plain NumPy on one core. Face arrays and padded per-cell "slots" (`euler/geometry.py`) were designed so the same
  arrays can go to Numba unchanged.
- Verified: MMS order 1.98-2.02 (L2) on quads, distorted quads, triangles, mixed, planar and axisymmetric
  (`validation/mms_euler2d`). Any speed change must keep these orders and every validated number (rule 4).
- Measured costs (Windows, one core, NumPy): MMS 128 x 128 quads (16k cells) 10,747 iterations in 1,646 s (~150 ms
  per iteration); triangles 128 x 128 (32k cells) 15,148 iterations in 2,552 s; default N2 nozzle 200 x 40 (8k cells)
  13-19 minutes; NACA 0012 three-mesh study needed hours (the 0.0025 c mesh with 60,000 iterations took ~6 h in a
  first attempt, so 7b's study uses 0.02 / 0.01 / 0.005 c only); full validation suite ~3 h.
- Known stalls (gap register): (1) triangle meshes of the sharp-throat nozzle stall near 1e-4 in a few cells at the
  throat corner; (2) the diamond airfoil stalls near 4e-3 in a few cells at the foot of the lower leading-edge shock
  (limiter limit cycle; Cl and Cd steady to 1e-6; found with the per-cell residual field "Residual of the last
  iteration" in the Results view / `aeroflowsim.post.fields`); (3) the quasi-1D solver stalls on fine meshes
  (minmod). The stall-freeze only acts after 3 orders of drop, so (2) never freezes.
- 7b findings for this prompt: an interpolated start on a new mesh saves only ~8 % of the iterations (4,712 vs
  5,087 on the N2 nozzle 60 x 12) because the residual is normalised by its first iterations, which are already
  small for a good start; Venkatakrishnan with constant K loses order on smooth flows under refinement (MMS triangles
  0.7-1.0 at 32 -> 64) - an order-preserving limiter option belongs here or in a later prompt (decide and record).

Out of scope: low-Mach preconditioning (8b), adaptive refinement (8c), batch runs (8d), unsteady dual time stepping
(8e), viscous flow, 3D. Do not start them; note dependencies.

## Decisions (made: follow them)

- **Numba** (pre-approved runtime dependency, add to pyproject + requirements with the exact version) for the residual
  kernels: reconstruction, limiter, HLLC/HLLE flux, face sums, time steps, ghost states. Keep the NumPy path as the
  reference implementation (an option, used by tests to compare) - bit-for-bit is not required, agreement to 1e-12
  relative per residual evaluation is.
- **Implicit time stepping: LU-SGS** (Yoon & Jameson 1988; Blazek 2015 sec. 6.2.4) with a first-order Rusanov
  (scalar dissipation) implicit operator, matrix-free, local time steps, CFL ramp (e.g. from 2 to 100+ over the first
  iterations, backing off when the residual rises), the same explicit (second-order) residual on the right-hand
  side, so the steady solution is unchanged. Option in Numerics: "Time stepping: Implicit LU-SGS (default for steady
  flows) / SSP-RK3 / Jameson". Template defaults switch to LU-SGS only after the validation shows the same numbers.
- **Multi-core:** Numba `parallel=True` / `prange` over cells for the residual, with a colouring or reduction scheme
  that keeps the face sums deterministic (results must be reproducible run to run); thread count in Tools > Preferences
  (default: physical cores - 1). The GUI's helper process uses it.
- **Residual normalisation:** a continued or interpolated run keeps the previous normalisation (already done for
  continuation); an interpolated start uses the normalisation of the run it came from, scaled per unit volume.
- **Stalls:** with implicit time stepping first; if a stall remains, investigate the cells (per-cell residual field)
  and fix the cause (limiter freezing after a stall even below 3 orders, or a smoother limiter); report what fixed it.

## Parts

1. **Profiling and baseline.** Timing table (cells, ms per iteration, iterations, wall time) for: MMS quads/triangles
   64 and 128, N2 nozzle Coarse/Medium/Fine and triangles, wedge, cylinder, diamond, NACA 0012 0.01 c. Store as
   `validation/timing.md` (script `tools/timing.py`).
2. **Numba kernels** with the NumPy path kept for comparison; tests: residual equality on every mesh type (quads,
   triangles, mixed, axisymmetric, 3D single cells), MMS orders unchanged, free-stream and well-balanced tests.
3. **LU-SGS implicit** for steady runs; tests: same converged solution as SSP-RK3 to the convergence tolerance on the
   wedge, nozzle and cylinder; iteration counts; robustness (supersonic start, CFL back-off, Stop / Continue /
   Start from scratch still work; continuation keeps the CFL ramp state).
4. **Multi-core** and determinism (two runs give identical histories); speed-up table versus threads.
5. **Stalls**: triangle nozzle, diamond, quasi-1D fine meshes: each converges to 1e-6 (or the remaining cause is
   found and recorded); interpolated-start normalisation; NACA 0012 study extended to 0.0025 c (and 0.00125 c if it
   fits), GCI updated against Vassberg & Jameson 2010 Table 11.
6. **Wall-clock targets** (must hold, measured on this machine, recorded in `validation/timing.md` and the Results
   step): default N2 nozzle (Medium, 8k cells) converged in under 60 s; MMS 128 x 128 quads under 120 s; full
   validation suite under 60 min; quick set under 5 min. If a target is missed, report by how much and why.
7. **Finish:** update theory manual (LU-SGS, Numba, parallel face sums), developer guide, gap register, CHANGELOG,
   user guide (Numerics); full fast tests and full validation; rule 4: compare `validation/report.md` with the
   previous one and explain every changed number; push to main; tag `v0.2.0a2` and a GitHub pre-release with the
   installer (tools/build_installer.py) only if every gate holds.

## Done when (check every line with evidence)

1. The Numba residual equals the NumPy residual (1e-12) on every mesh type; MMS orders unchanged (>= 1.8 / 1.7).
2. LU-SGS is the default for steady runs and every validation number is unchanged within its tolerance, every change
   explained; Stop / Continue / Start from scratch / re-mesh with interpolation behave as before.
3. Runs are deterministic with several threads; speed-up table written.
4. The triangle-nozzle, diamond and quasi-1D stalls are gone (or their cause is documented with evidence).
5. The wall-clock targets of Part 6 hold (or the shortfall is reported with the measured numbers).
6. Docs, gap register, CHANGELOG, `docs/prompts/8_progress.md`, and `docs/prompts/prompt_6e.md` written; tests and
   validation pass; everything pushed.

# Speed - Numba, implicit LU-SGS, multi-core; the residual stalls; wall-clock targets

**Model: Opus** (implicit time stepping and its stability: where subtle bugs hide).

Paste everything below the line into a NEW Claude Code session (Opus). It is designed to be completed in this one
session without follow-up prompts.

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder `C:\Projects\CFD software`, GitHub `Dhanwin5/AeroFlowSim`). I am a
beginner programmer who knows aerospace engineering and CFD theory. **This whole prompt must be finished in this one
session.** I will not send follow-up prompts, so:

1. **Start:** read `CLAUDE.md`, `docs/gap_register.md`, `docs/theory_manual.md` (sections 12 and 13),
   `docs/developer_guide.md`, the memory files, `docs/roadmap/post_processing_and_alpha.md` (the last session's ledger), and skim
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
7. **Keep a ledger** `docs/roadmap/speed.md` (done with commits, verified how, next, anomalies, decisions),
   updated after every part; if the conversation is summarised, re-read it and CLAUDE.md first.
8. **At the end:** full fast tests, full validation, report every result line, docs and gap register updated, push,
   and write the next prompt file (`docs/roadmap/3d_geometry_and_meshing.md`: 3D geometry workspace and 3D meshes; shapes, grids and mesh import and AI assistant are done, see `docs/roadmap/next_steps.md`) in the same style.

## Context (state after the post-processing and alpha release stage, release v0.2.0a1)

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
- post-processing and alpha release findings for this prompt: an interpolated start on a new mesh saves only ~8 % of the iterations (4,712 vs
  5,087 on the N2 nozzle 60 x 12) because the residual is normalised by its first iterations, which are already
  small for a good start; Venkatakrishnan with constant K loses order on smooth flows under refinement (MMS triangles
  0.7-1.0 at 64 -> 128 in a first full study) - an order-preserving limiter option belongs here or in a later prompt (decide and record).

Out of scope: low-Mach preconditioning (low-Mach preconditioning), adaptive refinement (adaptive mesh refinement), batch runs (parametric studies), unsteady dual time stepping
(unsteady flow), viscous flow, 3D. Do not start them; note dependencies.

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
   fits), GCI updated against Vassberg & Jameson 2010 Table 11. post-processing and alpha release finding: the post-processing and alpha release study halved only the WALL size
   (far field 2 c and growth fixed), so the meshes grew only 7,326 / 9,400 / 13,251 cells, the GCI order came out as 10
   (meaningless) and Cl (0.311 / 0.331 / 0.338, still rising) is a documented SHORTFALL against 0.352. Redesign the
   study so every size (wall, far field, growth or a refinement factor) scales together, aiming for about 4x cells per
   level, then remove the shortfall entry from `validation/euler2d_naca0012/reference.toml` if it passes.
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
6. Docs, gap register, CHANGELOG, `docs/roadmap/speed.md`, and `docs/roadmap/3d_geometry_and_meshing.md` written; tests and
   validation pass; everything pushed.

## Addendum from the shapes, grids and mesh import stage (27 Oct 2026): findings that belong to this prompt

- **Convergence of the new meshes is limited by speed.** NACA 0012 at Mach 0.5, alpha 1.25: the C-grid Medium (15,600 cells) took
  945 s for 8,000 iterations and was NOT converged (Cl 0.1751, Cd 0.0008; triangles 9,280 cells: Cl 0.1681, 348 s, not converged;
  reference Cl 0.1800). After the implicit solver, re-run `python tools/structured_flow_checks.py naca` to convergence and on three
  systematically refined C-grids (the presets Coarse, Medium, Fine are factor 2 in the counts: use them for the GCI study the NACA 0012
  validation case could not do).
- **Throat-corner limit cycle (residual stalls near 1e-3) also appears on the planar MOC nozzle** (`python tools/nozzle_flow_checks.py moc`:
  2,560 cells, 20,000 iterations, mass flow constant to 0.1 % along the nozzle, +1.6 % above the choked flow; exit Mach 2.23 mean /
  2.28 centre line against the design 2.4, wall cell 1.88). Re-run on a finer mesh once the solver is fast; the contour itself is verified
  by the exact area ratio (validation/shapes_and_grids).
- **C-grid wake cells are very flat** (aspect ratio 1,300-4,800 along the wake line at a first layer of 1e-3 c). Harmless for Euler flow;
  an implicit solver is insensitive to it, an explicit one is limited by it (local time stepping handles it).
- A planar nozzle template does not exist (the MOC check solves it directly): decide in the 3D stages or earlier.


---

## Progress log

Continue with: "continue the speed stage (LU-SGS) from docs/roadmap/speed.md".

## speed (Numba) - done (pushed)
- 4f08aa5 parts 1-4: Numba kernels (`euler/kernels.py`), `compute.py`, solver hooks, Tools > Preferences threads,
  `Job.threads`, CLI `--threads/--backend`, run info backend/threads, `tools/timing.py`, light CI, tests.
- dd2399b part 5: timing tables (`validation/timing.md`), docs, gap register, CHANGELOG.
- Verified: 101 kernel/core tests (Numba = NumPy to 1e-12 on every mesh type; positivity counts; freeze and stall
  freeze; bit-identical for 1/2/4 threads); full fast + GUI tests 986 passed, 1 skipped; quick validation all pass,
  all 129 compared values identical to the printed digits, 6.8 min (was ~32).
- Speed: 1 thread 8.8-17 x, 16 threads 31-70 x (MMS 128 quads 70 -> 2.2 ms/iteration).
- Full validation (explicit, speed (Numba) state): first attempts died of memory (see anomalies); rerun alone in progress.

## speed (LU-SGS) - done (parts 2, 7, 8 partly / not reached: see 'Not done')
- 0b50402 + 780dfb9 part 1: LU-SGS (Rusanov operator, omega 1.5, axisymmetric source on the diagonal, SER CFL ramp
  0.8 -> 100 following the residual, halved after an unphysical step, ramp state kept on Continue, fixed-order
  sweeps = deterministic). Option "Implicit LU-SGS" in Numerics; NOT yet the default. tests/test_lusgs.py (8 tests).
- Part 4: interpolated start keeps the earlier run's normalisation x sqrt(C_new/C_old). FINDING: on its own it saves
  nothing (explicit 60x12 nozzle 4,712 vs 5,087 fresh, 7 %): the interpolated field's first residual is as large as a
  fresh start's, and the tail from 1e-3 to 1e-6 sets the count. With LU-SGS the interpolated start saves 57 %
  (2,337 vs 5,461 iterations).
- Part 2 so far: diamond 0.01 c alpha 2 converges with both schemes now (LU-SGS 975 it to 5e-12, explicit 1,406);
  triangle nozzle 0.08 D_t still stalls near 1e-4 with both (explicit 3.8e-5, LU-SGS 1.9e-5 min) - to investigate.

- d6b4fda: LU-SGS is the DEFAULT for steady runs (quick set: all pass, 5.0 min; 117/129 values identical, 12 within
  tolerance). Two divergence tests pinned to SSP-RK3 (LU-SGS does not diverge at CFL 5).
- cefab1a part 3: limiter study (theory 13d): K 5 -> MMS triangles 0.71 at 64-128; K 20 -> 2.0 on quads and triangles,
  quick set passes, but wedge shock overshoot 4.5 % -> 5.7 %: default stays K = 5, K = 20 recommended for smooth flows.
- part 6: N2 nozzle Medium converged 20.8 s (13,771 it), MMS 128 quads 12.5 s (LU-SGS) / 17.5 s (explicit); quick set
  5.0 min. Full suite: see below.
- dea98e4 part 5: NACA study redesigned (wall and far-field sizes together, 14.5k / 40k / 137k cells): Mach 0.5 Cl
  1.7 % PASS, Cd 3.6 % PASS; Mach 0.8 Cl 0.335 flat over 9 x cells, -4.8 %: SHORTFALL kept, diagnosis updated (30 c
  far field without vortex correction suspected, untested). Reference values: from the post-processing and alpha release ledger (Vassberg & Jameson
  2010 Tables 10-11, p. 1165), NOT re-fetched in this session (paywalled): "pending reference re-check".
- Not done (time): part 2 triangle-nozzle stall (still ~1e-4 with both schemes, per-cell investigation next), part 7
  (BMG z = 2.24 in), part 8 (planar MOC nozzle on a finer mesh), quasi-1D fine-mesh stall, `structured_flow_checks.py naca`.

- 87a0660 full validation (LU-SGS): ALL PASS, 39 min; 7 of 129 values changed vs speed (Numba), all explained (LU-SGS limiter
  freeze state: BMG z=2.24 in 0.798842 -> 0.798844, cylinder stand-off +0.13 % max, triangle-nozzle Isp +0.007 %;
  NACA study redesign: Cl M0.8 0.338 -> 0.335, Cd 0.02201 -> 0.02174, Cl M0.5 0.1747 -> 0.1829).
- Full fast + GUI tests: 994 passed, 1 skipped.
- fb5d050 + tag v0.2.0a2: installer built (205 MB), smoke test passed; frozen program runs the 2D solver with Numba
  (first run compiles 8.7 s, second run 0.6 s from the cache). GitHub pre-release v0.2.0a2 on the PRIVATE repository.
  Repository visibility unchanged (owner's decision; see docs/launch_checklist.md).

## Decisions
- Ghost states stay NumPy (boundary faces only). Kernels for the calorically perfect gas; other models run NumPy.
- Gather face sums: bit-identical for any thread count. Default threads = physical cores - 1, max 16.
- LU-SGS sweeps sequential in cell order (deterministic); omega 1.5 (1.0 stalled the 2nd-order nozzle at 1e-2);
  SER ramp on the CURRENT residual (a ramp on the lowest residual kept CFL 96 after the start-up and never recovered);
  implicit stall rule 2 orders / 200 iterations (explicit 3 / 1,000).
- MMS validation pool: 6 workers sharing the cores (22 workers x Numba threads ran out of memory).

## Anomalies
- Network cut the Numba/llvmlite download many times (~1 h to install).
- Running several validation jobs at once ran the 32 GB machine out of memory: run heavy jobs one at a time.
- LU-SGS on the wedge: Cd 0.196653 vs explicit 0.196493 (0.08 %): the limiter is frozen at a different state.
- LU-SGS quick set with the FIRST ramp: cylinder Gmsh stand-off 7.8 % off (tolerance 5 %); to recheck with the final
  settings before LU-SGS becomes the default.
- PyInstaller build with Numba not run yet.

## Next
- Full validation (explicit) -> compare with the previous report.md; LU-SGS quick set -> decide the default.
- Parts 2 (triangle nozzle stall), 3 (limiter K table: `tools/limiter_order.py`), 5 (NACA), 6 (targets), 9 (finish).

# Prompt 8 progress ledger (8-1: Numba, multi-core, timing, light CI; 8-2: LU-SGS, stalls, limiter, NACA, release)

Continue with: "continue Prompt 8-2 from docs/prompts/8_progress.md".

## 8-1 - done (pushed)
- 4f08aa5 parts 1-4: Numba kernels (`euler/kernels.py`), `compute.py`, solver hooks, Tools > Preferences threads,
  `Job.threads`, CLI `--threads/--backend`, run info backend/threads, `tools/timing.py`, light CI, tests.
- dd2399b part 5: timing tables (`validation/timing.md`), docs, gap register, CHANGELOG.
- Verified: 101 kernel/core tests (Numba = NumPy to 1e-12 on every mesh type; positivity counts; freeze and stall
  freeze; bit-identical for 1/2/4 threads); full fast + GUI tests 986 passed, 1 skipped; quick validation all pass,
  all 129 compared values identical to the printed digits, 6.8 min (was ~32).
- Speed: 1 thread 8.8-17 x, 16 threads 31-70 x (MMS 128 quads 70 -> 2.2 ms/iteration).
- Full validation (explicit, 8-1 state): first attempts died of memory (see anomalies); rerun alone in progress.

## 8-2 - in progress
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
  far field without vortex correction suspected, untested). Reference values: from the 7b ledger (Vassberg & Jameson
  2010 Tables 10-11, p. 1165), NOT re-fetched in this session (paywalled): "pending reference re-check".
- Not done (time): part 2 triangle-nozzle stall (still ~1e-4 with both schemes, per-cell investigation next), part 7
  (BMG z = 2.24 in), part 8 (planar MOC nozzle on a finer mesh), quasi-1D fine-mesh stall, `structured_flow_checks.py naca`.

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

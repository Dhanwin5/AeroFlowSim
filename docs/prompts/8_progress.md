# Prompt 8-1 progress ledger (speed: Numba, multi-core, timing, light CI)

Continue with: "continue Prompt 8-1 from docs/prompts/8_progress.md".

## Done
- Part 1 (timing baseline): `tools/timing.py` (ms/iteration over 200 iterations x stored iteration counts, profile,
  thread table). NumPy baseline measured (see `validation/timing.md`).
- Part 2 (kernels, code written): `aeroflowsim/euler/kernels.py`, `aeroflowsim/compute.py`, solver hooks
  (`EulerSolver._residual_numba`, `_primitive`, `time_steps`), tests `tests/test_kernels.py`.
- Part 3 (plumbing written): Tools > Preferences (`gui/preferences_dialog.py`), `Job.threads`, CLI `--threads/--backend`,
  run info `backend/threads/backend_note`, report and Run banner text, diagnostics line, `tests/gui/test_preferences_qt.py`.
- Part 4 (written): `tests/test_smoke.py` (marker smoke), tests.yml light set per push; full fast + quick validation on
  PRs / weekly / manual.

## Decisions
- Ghost states stay NumPy: they touch only the boundary faces (~1-3 % of faces); profile shows 0 % of the time.
- Kernels take R, cv, gamma as numbers (calorically perfect gas, the only model); another GasModel runs NumPy.
- Face sums by GATHER over each cell's slots (no scatter/atomics): results are bit-identical for any thread count,
  so "different thread counts agree within round-off" is in fact exact (tested with array_equal).
- Default threads = physical cores - 1, capped at 16 (memory bandwidth). Thread count is a computer preference,
  not a project input: changing it never marks a project out of date.
- Light CI per push; the 32-minute quick validation set moved to PRs / weekly / manual runs.

## Anomalies
- Network on this machine kept cutting the Numba/llvmlite download (pip resume retries needed, ~30 min).
- NumPy baseline profile: the Venkatakrishnan limiter is 55 % of a residual (many temporary (n_vars, C, k) arrays).
- PyInstaller build with Numba not run in this session (`--collect-all numba llvmlite` added); if the frozen app
  has no source files for caching, kernels.CACHE is False and they compile in memory at each start.

## Next
- Install Numba, run tests/test_kernels.py, timings (1 thread, threads table), full tests, quick + full validation,
  docs, CHANGELOG, gap register, push.

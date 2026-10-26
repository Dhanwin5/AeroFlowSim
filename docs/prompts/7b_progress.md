# Prompt 7b progress ledger

If the session was summarised or interrupted: re-read this file and `CLAUDE.md`, then continue with "Next".
Order of work (addendum A): Part 6 → Parts 1-2 → Part 7 → Part 3 → Parts 4-5 → Part 8 → Part 9 → Parts 10-11.

## Done

| Part | What | Commit | Verified by |
|---|---|---|---|
| 6 | MMS module `aeroflowsim/mms.py` (Roy et al. 2004 form, mixed Mach 0.5-1.6, hand-written source incl. axisymmetric), solver hooks (`EulerSolver.source`, `boundary_face_values`), limiter option "None", `rectangle_mesh(warp=...)`, GCI tool `aeroflowsim/gci.py`, validation case `validation/mms_euler2d`, quick/full validation sets (`AEROFLOWSIM_VALIDATION_SET`, `run_all.py --quick`, `tolerance_percent_quick`) | 4d355c6 | `tests/test_mms_gci.py` (source vs finite differences, order on 8/16 meshes, GCI on exact power laws); coarse study 8/16/32: order 2.0-2.2 on quads, triangles, mixed, axisymmetric; distorted quads 1.6-1.8 (pre-asymptotic) |
| 1-2 (core) | `aeroflowsim/post/`: solution, fields (derived + safe custom formulas + node values), sampling, surfaces, integrals, flux balance, forces, report definitions, MonitorEvaluator; solver stores its final boundary fluxes, L_ref and scales in the result | 4d355c6 | `tests/test_post.py` (29 tests: linear fields exact, solid-body vorticity, malicious formulas refused, mass flow = solver flux to 1e-12, flux balance closes) |

## In progress / next

- Full MMS study (16-128) running in background → put numbers in report + theory manual.
- Project integration: surfaces / report definitions / custom fields / scenes / init patches in project.yaml; monitors during the run (engine → setup.solve), report CSV files; snapshots; interpolation onto a new mesh.
- xy.py, compare.py, export.py, CLI subcommands.

## Decisions

- Validation folders whose "case" is not a template use `case = "aeroflowsim/<module>.py"` (test relaxed).
- Quick validation set writes `validation/report_quick.md`; the full set writes `validation/report.md`. Both state the set.
- Mass-weighted average uses rho |V.n| (Fluent's definition).
- Post-processing boundary fluxes are the solver's own final fluxes (stored as series `boundary_flux`), so reports equal the solver's numbers; older results recompute them with the run's numerics, L_ref, scales and frozen limiter.

## Open anomalies

- (none yet)

# Prompt 6e progress ledger

If the session was summarised or interrupted: re-read this file, `CLAUDE.md` and `docs/gap_register.md`, then continue with "Next".
Order of work: Part 1 (shapes) -> Part 2 (C/O-grids) -> Part 3 (import/export) -> Part 4 (flow runs, validation, docs).
Commit after each part. If a part is too big, stop, update this file and the gap register, and tell the user.
Scope agreed with the user (27 Oct 2026): THIS session = Parts 1 and 2; Part 3 and the final validation/docs go in the next session.

## Done

| Part | What | Commit | Verified by |
|---|---|---|---|
| 1 | 11 new shape pairs (bell nozzle, MOC nozzle, ramp intake, spike intake, biconvex, NACA 5-digit, nose cone family, sphere, hemisphere-cylinder, capsule, blunted cone) + `nozzle_contours.py` (Rao bell, planar MOC) + `intake_theory.py` + smart rule `shock_on_lip` + theory manual section 14 + gap register | (see git log) | `tests/test_shapes.py` + `tests/test_shapes_new.py` (111 pass): von Karman R/sqrt2, tangent ogive eq., circle fit of the secant ogive, half-ellipsoid volume, capsule tangent sphere, biconvex segment area, NACA5 design Cl by thin-airfoil integral (0.3000-0.3001), MOC exit area ratio vs isentropic (0.2 % at n = 100, converging), Rao arcs/end slopes, theta-beta-M relation, lip on shocks |

## Decisions

- D1 (user): nozzles = wall profile (`nozzle_contours.py` -> `WallProfile`) + a shape-library entry that draws the closed flow path (wall + mirror).
- D2 (user): this session Parts 1 and 2.
- Rao angles: digitised Huzel-Huang plot 4-16 (pygasflow `plot-4-16-data`, fetched 27 Oct 2026, every 2nd point stored) -> chart readings +-0.5 deg, labelled in the help text; throat-arc radii 1.5 / 0.382 Rt from Seitzman (Georgia Tech AE 6450).
- NACA 5-digit constants: Wikipedia table (NASA TM X-3284 not reachable), checked by thin-airfoil design Cl.
- Intake outlines: one closed outline, cowl joined by a rear block (duct = dead-end pocket) -> gap register.
- Nose cone family is ONE shape with a "profile" choice (not 7 files); same for the blunt options.

## Pending reference

- Rao 1960 paper and Huzel-Huang plot 4-16 themselves (not reachable): angle table is a secondary digitisation.
- NASA TM X-3284 (NACA 5-digit constants): secondary source only.

## Next

1. Commit Part 1 (after the full fast suite passes).
2. Part 2: C-grid / O-grid (Gmsh transfinite): new module (e.g. `aeroflowsim/structured_mesh.py`), inputs in `external_2d` schema (mesh type choice), patches named wall/farfield/symmetry/axis, wall-size inputs tested by halving, quick free-stream-preservation flow run, NACA 0012 C-grid vs triangles, cylinder O-grid at Mach 6.
3. Parts 3-4 next session.

## Anomalies

- NACA 5-digit line 21x is 2.8 % off its design lift (the printed r has three digits).

# Prompt 6e progress ledger

If the session was summarised or interrupted: re-read this file, `CLAUDE.md` and `docs/gap_register.md`, then continue with "Next".
Order of work: Part 1 (shapes) -> Part 2 (C/O-grids) -> Part 3 (import/export) -> Part 4 (flow runs, validation, docs).
Commit after each part. If a part is too big, stop, update this file and the gap register, and tell the user.
Scope agreed with the user (27 Oct 2026): THIS session = Parts 1 and 2; Part 3 and the final validation/docs go in the next session.

## Done

| Part | What | Commit | Verified by |
|---|---|---|---|
| 1 | 11 new shape pairs (bell nozzle, MOC nozzle, ramp intake, spike intake, biconvex, NACA 5-digit, nose cone family, sphere, hemisphere-cylinder, capsule, blunted cone) + `nozzle_contours.py` (Rao bell, planar MOC) + `intake_theory.py` + smart rule `shock_on_lip` + theory manual section 14 + gap register | 29388e9 | `tests/test_shapes.py` + `tests/test_shapes_new.py` (111 pass): von Karman R/sqrt2, tangent ogive eq., circle fit of the secant ogive, half-ellipsoid volume, capsule tangent sphere, biconvex segment area, NACA5 design Cl by thin-airfoil integral (0.3000-0.3001), MOC exit area ratio vs isentropic (0.2 % at n = 100, converging), Rao arcs/end slopes, theta-beta-M relation, lip on shocks |
| 2 | `structured_mesh.py` (C-grid sharp TE + wake cut, O-grid, half domains), `external_2d` inputs (mesh type, preset, first height, growth cap, far distance), `tools/structured_flow_checks.py` | 29388e9 | `tests/test_structured_mesh.py` (20 pass: exact areas, patch names = Gmsh, first layer exact, size inputs change counts as expected, uniform flow stays uniform to 1e-11 on all 4 grids); full fast suite 803 pass; Mach 6 cylinder O-grid: stand-off 0.2210 D vs Billig 0.2197, carbuncle metric 5e-6, converged in 6,239 it. |
| 3 | `mesh_io.py` (read Gmsh v2/v4 via meshio, SU2, Fluent ASCII, CGNS via h5py; write Gmsh 2.2/4.1, SU2, CGNS), boundary-tag map, template `cases/imported_mesh`, CLI `mesh-info` / `mesh-convert`, sample files `tests/data/sample*` | (this commit) | `tests/test_mesh_io.py` (24 pass: exact round trips for 4 writers x planar/axisymmetric, Gmsh triangle mesh, 5 sample files agree, real Gmsh v2 / v4 / v4 binary output read, refusals) + `cases/imported_mesh/test_case.py` (4 pass, uniform stream stays uniform) |
| 4 | `validation/shapes_and_grids` (exact shape quantities, MOC area ratio on 3 fan sizes, bell, O/C-grid areas on Coarse/Medium/Fine, triangle comparison), flow checks `tools/structured_flow_checks.py`, `tools/nozzle_flow_checks.py`, theory manual (14: shapes, grids, mesh I/O), tutorial `naca0012_c_grid.md`, user guide, CLAUDE.md layout, gap register, prompt 8 addendum | (this commit) | quick validation set: ALL PASS (16 of 16 cases; the 15 older cases' numbers unchanged: only the date and the new case differ in report.md); screenshots light/dark of the Mesh step looked at |

Flow checks (not validation cases): cylinder O-grid Mach 6: stand-off 0.2210 D (Billig 0.2197), carbuncle metric 5e-6, converged; NACA 0012 C-grid vs triangles: Cl 0.1751 vs 0.1681 (ref 0.1800), neither converged in 8,000 iterations; Rao bell in nozzle_axi: mdot -0.7 % vs choked, M_exit 4.846 vs 5.000 (-3.1 %), converged; MOC planar nozzle: mass flow +1.6 %, exit Mach mean 2.23 / centre line 2.28 vs 2.4 design: NOT within 5 % (see gap register and prompt 8 addendum).

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

1. Parts 1-4 are done except the items in the gap register: boundary-type table dialog in the GUI, blunt-TE C-grid, planar nozzle template,
   converged NACA / MOC runs (need Prompt 8 speed), CGNS export checked with an external reader. Next prompt: `prompt_8.md` (speed).

## Anomalies

- NACA 5-digit line 21x is 2.8 % off its design lift (the printed r has three digits).
- MOC planar nozzle flow check misses the design exit Mach by 5-7 % on a coarse mesh (see above).
- The first attempt of the MOC flow check failed because of the script (state array is primitive, not conserved) and then because the outlet
  was a supersonic-outlet on an unstarted nozzle; both fixed in `tools/nozzle_flow_checks.py`.

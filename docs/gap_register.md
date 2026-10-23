# AeroFlowSim gap register

A living checklist of everything AeroFlowSim needs to reach its goal: a GUI-first, open-source CFD
tool for nozzle and propulsion aerodynamics that students can install, use, trust and build on.

**How to use it (CLAUDE.md rule):** read this file at the start of every prompt; at the end, update
the status of the items that moved, add any new gaps found, and report both to the user.

**Status:** `done` · `partial` · `planned 6d` (planned in that prompt) · `later` · `out of scope`
**Priority:** **P1** needed for the 2D alpha release · **P2** needed for version 1.0 · **P3** nice to have

Last updated: Prompt 6f (2026-10-23).

## 1. Platform and GUI

| Item | Status | Priority | Notes |
|---|---|---|---|
| Desktop GUI (Qt + PyVista/VTK), started with `python -m aeroflowsim gui` | done | P1 | Prompt 6c |
| Auto-generated input panel from `schema.toml` (all types, units, ranges, help, groups, show_if, files) | done | P1 | logic in `gui/panel_model.py`, tested without a window |
| Workflow steps Geometry → Mesh → Setup → Run → Results with status colours | done | P1 | workflow strip at the bottom (own design, not a Workbench clone) |
| Out-of-date tracking (fingerprints) and clearly labelled old results | done | P1 | `project.py` |
| Background jobs with progress and Cancel, GUI never freezes | done | P1 | warm helper process, `tasks.py` |
| Undo / redo of input changes | done | P1 | QUndoStack; geometry workspace edits are undoable too (6d: one command per history change) |
| Light / dark theme, remembered | done | P2 | one app-wide style sheet per theme; plots follow the theme, saved pictures keep the light "paper" style |
| Dockable panels, menus, toolbar, shortcuts | done | P1 | |
| Right-click (context) menus in the views | partial | P2 | geometry workspace: menus for points, edges, faces and empty space (21 Oct, `tests/gui/test_view_aids.py`); mesh and results views still have none |
| **Bug: input values hidden when the Inputs dock is narrow** (external_2d: right-aligned numbers scrolled out of view) | done | P1 | fixed after 6d: long labels wrap, boxes keep a minimum width, no sideways scrolling; the dock cannot be made narrower than about 320 px (`tests/gui/test_panel_qt.py`) |
| Rubber-band (box) selection in the geometry view | done | P2 | 21 Oct: drag a box (left to right: inside only), with a pick filter for points / edges / faces (`tests/gui/test_view_aids.py`) |
| Workspace view aids: own icon set (both themes), adaptive grid, xyz axes triad, cursor position, 2D/3D switch, revolve preview of axisymmetric geometry | done | P2 | 21 Oct (`gui/icons.py`, `gui/geometry_view.py`; `tests/gui/test_view_aids.py`) |
| CAD-style mouse handling in the workspace (zoom about the cursor, Shift/middle drag to pan) | done | P2 | 21 Oct (`tests/gui/test_view_aids.py`) |
| Parity check of the desktop GUI against Streamlit by the user | partial | P1 | user checks every template; then remove `app.py` + streamlit (ask first) |
| Remove the Streamlit GUI (`app.py`, `streamlit_panel.py`, `job.py`, `plots.py`, `settings.py`) | later | P2 | only after the parity check, with the user's OK |
| Windows installer + Start-menu shortcut | planned 7b | P1 | |
| 3D view rotation, 3D picking | later | P2 | 2D style for now (pan/zoom); Phase 3 |
| Units system in the GUI (SI, mm, imperial; SI inside) | done | P2 | 6f: View > Units (length, pressure, temperature, mass flow, force, area, velocity; presets small propulsion / SI / imperial); inputs, Setup table, key numbers, card, plots, colour pictures, CSV/PNG export follow it; projects, command line, summary.yaml and the validation report stay SI. The geometry workspace stays in mm |
| Geometry workspace follows the length-unit preference | later | P3 | the workspace still shows and accepts mm only |
| Units in the Geometry summary, mesh Properties and validity-check messages | later | P3 | these still use SI with readable prefixes |
| Gmsh "save .msh" writes into the template folder, not the project | partial | P2 | case code uses `CASE_DIR/mesh`; move to the project's `mesh/` (needs a case-contract change) |
| GUI usable at 125-150 % display scaling, keyboard-only use | later | P2 | not yet checked systematically |

## 2. Projects and reproducibility

| Item | Status | Priority | Notes |
|---|---|---|---|
| Templates (`cases/`) separate from projects (`*.afsproj` folders) | done | P1 | |
| New / open / save / save as / duplicate / recent / ask to save on exit | done | P1 | |
| Input files copied into the project, relative paths (zip and share) | done | P1 | |
| Exact saved results reopened without re-running (`results/run.npz`, no pickle) | done | P1 | |
| Command line runs projects (`python -m aeroflowsim run "<folder>.afsproj"`) | done | P1 | same engine, identical results (tested) |
| Import of old Streamlit settings files | done | P2 | old files are left untouched |
| Template change detection on open (warning) | done | P2 | fingerprint of `schema.toml` + `case.py` |
| Project archive export/import as one `.zip` from the GUI | later | P3 | a zipped folder already works |
| Automatic report (HTML/PDF) of a project | planned 7b | P1 | |

## 3. Geometry

| Item | Status | Priority | Notes |
|---|---|---|---|
| Parametric nozzle, CSV wall profile, rounded throat | done | P1 | |
| Shape library (wedge, diamond, NACA 4-digit, cylinder, cone, coordinates file) | done | P1 | |
| Geometry step shows boundaries named and coloured | done | P1 | now the clickable workspace for 2D templates; 1D templates keep the read-only drawing |
| Geometry workspace: history of operations, replay, stable edge ids, `geometry/history.json` | done | P1 | Prompt 6d (`geometry_model/`) |
| Import CSV/DAT, nozzle wall CSV, DXF, 2D STEP/IGES, 3D solid cut by a plane, unit choice, healing | done | P1 | 6d; checked with the user's IGES nozzle domain |
| Edit (move, rotate, scale, mirror, point table, drag points, delete, fillet), sketch (line, arcs, spline, rectangle, circle), snapping | done | P1 | 6d |
| Sketch constraint solver (coincident, horizontal/vertical, parallel, perpendicular, equal, tangent, point on, fix) and driving dimensions (distance, length, radius, angle), degrees-of-freedom status, conflict/redundancy detection | done | P2 | 21 Oct (`geometry_model/constraints.py`, Levenberg-Marquardt; `tests/test_constraints.py`) |
| Draw with the mouse: live rubber band, inference snapping (end, intersection, centre, midpoint, tangent, perpendicular, on curve, angle steps, alignment), typed points while drawing | done | P1 | 21 Oct (`geometry_model/inference.py`, `gui/sketch_tools.py`; `tests/test_sketch_tools.py`) |
| Edit tools: split face / edge, trim, extend, offset, chamfer, pattern (linear, circular), fill, merge faces | done | P1 | 21 Oct (`geometry_model/edit_operations.py`; `tests/test_geometry_edit.py`, `tests/gui/test_main_window.py`) |
| Enclosure tool (circle, rectangle, C-domain, full/half; nozzle plume region and inlet plenum), drag handles | done | P1 | 6d |
| Booleans (OpenCASCADE), name boundaries by clicking (suggestions, rename, types, inflation), refinement regions (box, circle, wake) | done | P1 | 6d; boundary types in one table, extended in Prompt 7 |
| Geometry validity checks, export STEP / DXF / CSV | done | P1 | 6d |
| Remaining shapes (bell nozzle, intakes, biconvex, NACA 5, ogive, von Karman, power-law, sphere, ...) | planned 6e | P2 | |
| 3D geometry (STEP) | later | P2 | Phase 3, prompt 9; the workspace data model is ready for a z column and 3D faces |

## 4. Meshing

| Item | Status | Priority | Notes |
|---|---|---|---|
| Face-based mesh format, `.vtu` export | done | P1 | |
| Structured nozzle mesh, Gmsh triangles / quad-dominant, inflation layers | done | P1 | |
| Mesh quality fields and validity checks, click a cell to see its values | done | P1 | |
| **Bug: quasi-1D mesh fails for n_cells ≥ about 450** (`OverflowError` in throat grading) | done | P1 | fixed in 6f: the growth-factor search had an upper end of 10, and 10^450 overflows; tested from 300 to 20 000 cells, runs at 300 / 450 / 1 000 / 5 000 cells |
| Quasi-1D residual stalls on fine meshes (minmod limit cycle in the smallest throat cells: near 1e-7 from 450 cells, near 1e-2 at 5 000 cells) | partial | P2 | the solution is steady (mass balance 0.001 %, exit Mach to 1e-5); use tol 1e-6 or CFL 0.1; a smoother limiter (van Albada) or implicit time stepping (Prompt 8) should fix it |
| Structured C-grid / O-grid (Gmsh transfinite) | planned 6e | P2 | |
| Mesh import (Gmsh .msh, SU2, CGNS, Fluent .msh) | planned 6e | P2 | |
| Mesh of an edited geometry with named boundaries as patches (`workspace_mesh.py`), inflation on marked walls | done | P1 | 6d; layers must end on straight boundaries |
| Structured mesh of an edited nozzle geometry | later | P3 | edited geometry uses Gmsh triangles / quads (clear message) |
| Gmsh .msh export of workspace meshes | later | P3 | the .vtu is written |
| Smart rule: suggested enclosure and mesh sizes | done | P2 | 6d (`smart_rules.py`), shown with reasons, applied only by the user |
| Adaptive mesh refinement | planned 8c | P2 | |
| 3D meshes (tetrahedra, prism inflation) | later | P2 | Phase 3 |

## 5. Physics and solvers

| Item | Status | Priority | Notes |
|---|---|---|---|
| 1D Euler (HLLC, MUSCL, SSP-RK2), quasi-1D nozzle, local time stepping | done | P1 | validated |
| Gas library + custom gas (designed for mixtures) | done | P1 | 6f: `GasModel` interface (`aeroflowsim/gases/`), calorically perfect gas with Sutherland / power laws; N2, air, O2, Ar, He, Kr, Xe, CO2, H2, H2O, R-236fa with a source for every value (NIST WebBook fits, US Std Atmosphere 1976, GRI-Mech 3.0); gas dropdown in the quasi-1D Setup, custom gases in the user library and copied into projects; Tools > Gas library |
| Thermally perfect gas (cp(T) from the stored NASA 7-coefficient polynomials) | later | P2 | polynomials stored for N2, O2, Ar, CO2, H2, H2O; needed for hot gases (CO2 and R-236fa are constant-cp only within about 15 K of room temperature) |
| Custom-gas form: critical point, acentric factor, saturation curve | later | P3 | without them the ideal-gas and condensation checks report 'cannot be estimated' for custom gases |
| Gas mixtures (mole fractions of library gases), humid air | later | P2 | the data model keeps molar mass and critical constants per gas, ready for mixing rules |
| 2D / axisymmetric Euler with local time stepping, carbuncle fix | planned 7 | P1 | |
| Full boundary-condition set from named boundaries | planned 7 | P1 | total-pressure / mass-flow inlet, pressure outlet, supersonic in/out, far-field, slip wall, symmetry, axis |
| Initialisation options, restart from a saved solution, live monitors | planned 7 | P1 | |
| Thrust / Isp / Cf, Cp / Cl / Cd / Cm | planned 7 | P1 | |
| Implicit time stepping (LU-SGS), Numba, multi-core | planned 8 | P2 | |
| Low-Mach preconditioning | planned 8b | P2 | |
| Parametric studies and batch runs | planned 8d | P2 | |
| Unsteady flow (dual time stepping) | planned 8e | P2 | |
| 3D Euler, multiple zones | later | P2 | Phase 3 |
| Laminar NS (+ slip wall for micro-nozzles), Spalart-Allmaras, k-omega SST, wall heat flux | later | P2 | Phase 4 |
| Constant-density liquids (preconditioned) | later | P3 | Phase 4 |
| Real gas (Peng-Robinson), multi-species, combustion, high-temperature gas | partial | P3 | Phase 5; 6f: Peng-Robinson Z used by the ideal-gas check (about 1 % at 50 bar N2, but |Z - 1| 9 % instead of 14 % at 300 bar: a better EOS is needed for computing) |
| Two-phase / condensation, cavitation, conjugate heat transfer | later | P3 | Phase 5 "later" list; 6f: condensation risk check (margin to the saturation / frost temperature) |
| Sourced sublimation (frost) curves below the triple point | later | P3 | now Clausius-Clapeyron continuation of the vapour-pressure curve: an upper limit of the margin (N2 at 3.4 kPa: 0.6 K too warm); air has no dew line |
| Rotating machinery, free-surface flows, structures | out of scope | - | |

## 6. Post-processing

| Item | Status | Priority | Notes |
|---|---|---|---|
| 1D field plots vs reference, key numbers, shape view, x-t diagram, CSV/PNG export | done | P1 | matplotlib embedded |
| 2D/3D field contours in the VTK view | planned 7b | P1 | the VTK view already colours cells by any per-cell field |
| Streamlines, line probes, surface plots (Cp vs x) | planned 7b | P1 | |
| Image / CSV / VTK export of solution fields | planned 7b | P1 | mesh `.vtu` export done |

## 7. Verification, validation, trust

| Item | Status | Priority | Notes |
|---|---|---|---|
| Validity checks (convergence, mass balance, mesh quality) | done | P1 | 6f: + ideal-gas validity, condensation risk, temperature range of the gas data |
| Validation report (quasi-1D, Sod, nozzle geometry, external geometry, geometry workspace) | done | P1 | 5/5 PASS, numbers unchanged in 6f; 6f added the quasi-1D mesh-refinement study |
| Run the validation suite from the GUI (Tools menu) | done | P2 | |
| MMS order-of-accuracy verification (structured and triangle meshes) | planned 7b | P1 | |
| 2D validation cases (wedge, diamond, cone, cylinder stand-off, BMG nozzle, NACA 0012) | planned 7b | P1 | |
| Cross-code comparison with SU2 / OpenFOAM | later | P2 | Phase 4 |
| GCI mesh-independence tool | partial | P2 | 6f: mesh-refinement study of the quasi-1D validation (exit Mach, shock position, observed order, Richardson value) in `validation/report.md`; the general GCI tool is Phase 5 |

## 8. Intelligence

| Item | Status | Priority | Notes |
|---|---|---|---|
| Smart rules: setup suggestions (mesh size, first layer from Re and y+, CFL) | partial | P2 | 6d: sizes and enclosure; first layer from Re / y+ and CFL need the flow inputs (Prompt 7) |
| Smart rules: failure diagnosis with suggested fixes | planned 7 | P2 | |
| AI assistant plugin v1 (opt-in, fills schema inputs only, local-model option) | planned 7c | P3 | |
| Surrogate models + shape optimisation | later | P2 | Phase 5 headline feature |

## 9. Documentation, community, release

| Item | Status | Priority | Notes |
|---|---|---|---|
| Theory manual | partial | P1 | updated every prompt |
| Developer guide (GUI architecture) | done | P1 | `docs/developer_guide.md` |
| User tutorials | partial | P1 | 6d: nozzle with plume region, airfoil in a C-domain (`docs/tutorials/`); more in 7b |
| CI on Windows and Ubuntu incl. GUI tests | done | P1 | headless display action |
| 2D alpha release on GitHub | planned 7b | P1 | |
| Zenodo DOI, JOSS paper | later | P2 | Phase 5 |
| Contributing guide, code of conduct, issue templates | later | P2 | needed before inviting contributors |
| Optional web demo | later | P3 | |

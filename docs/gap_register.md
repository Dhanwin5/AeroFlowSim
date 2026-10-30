# AeroFlowSim gap register

A living checklist of everything AeroFlowSim needs to reach its goal: a GUI-first, open-source CFD
tool for nozzle and propulsion aerodynamics that students can install, use, trust and build on.

**How to use it (CLAUDE.md rule):** read this file at the start of every prompt; at the end, update
the status of the items that moved, add any new gaps found, and report both to the user.

**Status:** `done` · `partial` · `planned 6d` (planned in that prompt) · `later` · `out of scope`
**Priority:** **P1** needed for the 2D alpha release · **P2** needed for version 1.0 · **P3** nice to have

Last updated: Prompt 8-1 (2026-10-30).

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
| Right-click (context) menus in the views | done | P2 | geometry workspace (21 Oct); mesh and results views (7b): zoom to fit, reset view, save picture; results also probe, pin probe, line surface, streamline seed |
| Boundary-condition table in the Setup step (one row per named boundary: type, values, Default) | done | P1 | Prompt 7: input type `boundaries`, logic in `gui/boundary_logic.py`, drawn by `panel.py`; defaults follow the template inputs; undoable |
| Live monitors in the Run step (residual per equation, thrust / mass flow / Cl, Cd, Cm, positivity) | done | P1 | Prompt 7 (`figures.residual_figure`, `tasks.py` batches) |
| Run step: suggested numerics and 'What to try' after a failed run | done | P2 | Prompt 7 (smart rules, applied only by the user) |
| Results step for 2D flows: field view (field, colour map, range, edges, cell values), wall p/p0 or Cp, convergence, .vtu | done | P1 | Prompt 7 |
| Results view: picture export in the paper style, mirror about the axis, streamlines | done | P2 | 7b: Display panel (gui/post_panels.py, gui/flow_view.py); PNG 1-8 x resolution, transparent, paper style in both themes, copy to clipboard |
| Results workspace (Fluent-level post-processing): contours (smooth / cell / banded), lines with labels, vectors, streamlines, 3D revolve, 1/2/4 linked views, saved scenes, surfaces, integrals, fluxes, forces, report definitions, XY plots, snapshots and differences, custom fields, histogram, hover values | done | P1 | 7b: logic in aeroflowsim/post (no Qt), tests/test_post*.py, tests/gui/test_post_gui.py |
| **Bug: input values hidden when the Inputs dock is narrow** (external_2d: right-aligned numbers scrolled out of view) | done | P1 | fixed after 6d: long labels wrap, boxes keep a minimum width, no sideways scrolling; the dock cannot be made narrower than about 320 px (`tests/gui/test_panel_qt.py`) |
| Rubber-band (box) selection in the geometry view | done | P2 | 21 Oct: drag a box (left to right: inside only), with a pick filter for points / edges / faces (`tests/gui/test_view_aids.py`) |
| Workspace view aids: own icon set (both themes), adaptive grid, xyz axes triad, cursor position, 2D/3D switch, revolve preview of axisymmetric geometry | done | P2 | 21 Oct (`gui/icons.py`, `gui/geometry_view.py`; `tests/gui/test_view_aids.py`) |
| CAD-style mouse handling in the workspace (zoom about the cursor, Shift/middle drag to pan) | done | P2 | 21 Oct (`tests/gui/test_view_aids.py`) |
| Parity check of the desktop GUI against Streamlit by the user | partial | P1 | user checks every template; then remove `app.py` + streamlit (ask first). The Streamlit GUI cannot edit the boundary-condition table (it uses the defaults) |
| Remove the Streamlit GUI (`app.py`, `streamlit_panel.py`, `job.py`, `plots.py`, `settings.py`) | later | P2 | only after the parity check, with the user's OK |
| Windows installer + Start-menu shortcut | done | P1 | 7b: PyInstaller one-folder + Inno Setup (tools/build_installer.py), per user, .afsproj association (project.afsproj in each project), uninstaller, smoke test; GitHub workflow on tags. NOT code-signed (SmartScreen warning documented) |
| Code signing of the installer | later | P2 | needs a certificate; until then SmartScreen warns |
| Help > Copy diagnostic info, log file, error dialog | done | P1 | 7b: aeroflowsim/diagnostics.py, %APPDATA%/AeroFlowSim/aeroflowsim.log |
| Example projects on the start page | done | P1 | 7b: examples/ (N2 nozzle with result, NACA 0012, wedge, Sod), tools/make_examples.py |
| 3D view rotation, 3D picking | later | P2 | 2D style for now (pan/zoom); Phase 3 |
| Units system in the GUI (SI, mm, imperial; SI inside) | done | P2 | 6f: View > Units (length, pressure, temperature, mass flow, force, area, velocity; presets small propulsion / SI / imperial); inputs, Setup table, key numbers, card, plots, colour pictures, CSV/PNG export follow it; projects, command line, summary.yaml and the validation report stay SI. The geometry workspace stays in mm |
| Geometry workspace follows the length-unit preference | later | P3 | the workspace still shows and accepts mm only |
| Units in the Geometry summary, mesh Properties and validity-check messages | done | P2 | 6f close-out: check messages carry their numbers as quantities (SI text for the command line and summary.yaml, the user's units in the GUI); Geometry Dimensions and Properties, mesh table and cell/boundary Properties follow View > Units; plot ticks at round values of the chosen unit |
| Properties panel too narrow for long values by default | later | P3 | the dock can be widened by hand; values are cut off at first |
| Gmsh "save .msh" writes into the template folder, not the project | partial | P2 | case code uses `CASE_DIR/mesh`; move to the project's `mesh/` (needs a case-contract change) |
| GUI usable at 125-150 % display scaling, keyboard-only use | partial | P2 | 7b: screenshots at 100 % and 150 % (tools/screenshots.py --scale 1.5) looked at; keyboard-only use not checked |

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
| Automatic report (HTML/PDF) of a project | done | P1 | 7b: aeroflowsim/post/report.py (self-contained HTML, matplotlib PDF), GUI and `python -m aeroflowsim report` |
| Solution snapshots, interpolation onto a new mesh, patch regions | done | P1 | 7b; interpolated start saves only ~8 % of the iterations on the N2 nozzle because the residual is normalised by the first iterations (already small for a good start): normalise by the previous run's level, as a continued run does (Prompt 8) |

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
| Remaining shapes: bell nozzle (Rao), planar MOC nozzle, ramp intake (1-3 ramps), spike intake, biconvex, NACA 5-digit (standard + reflex), nose cones (tangent/secant ogive, von Karman, LV-Haack, power, parabolic, ellipse, blunt nose, afterbody), sphere, hemisphere-cylinder, sphere-cone capsule, blunted cone | done | P2 | 6e part 1: `aeroflowsim/shapes/`, `nozzle_contours.py`, `intake_theory.py`; each tested against its equation (`tests/test_shapes_new.py`); theory manual section 14 |
| Smart rule "shock on lip" (cowl lip on the ramp / cone shocks) | done | P2 | 6e: `smart_rules.shock_on_lip`, shown with reason and Apply, never automatic |
| Rao bell angles are chart readings (digitised Huzel-Huang plot 4-16, about +-0.5 deg), range eps 5.2-50.3, Lf 60-100 % | partial | P2 | primary chart/paper not reachable; outside the range the user types theta_n and theta_e. Replace by a sourced table when the book is at hand |
| Axisymmetric (and bell-contour) Method-of-Characteristics nozzle | later | P3 | 6e implemented the planar minimum-length nozzle only (stretch goal not done) |
| Shapes with two bodies (intake centre body + separate cowl, open through-duct) | later | P2 | `ShapeProfile` is one closed outline: the intake shapes join cowl and centre body with a rear block, so the duct is a dead-end pocket (shock system and capture only) |
| NACA 5-digit constants: tabulated for L = 2 only (x10-x51); other L scale k1 linearly; 210 line is 2.8 % off its design lift (3-digit r) | partial | P3 | constants from Wikipedia (NASA TM X-3284 not reachable) |
| Unsourced default dimensions (capsule, intake angles, MOC characteristics count) | partial | P3 | illustrative inputs, labelled as such in the help text |
| 3D geometry (STEP) | later | P2 | Phase 3, prompt 9; the workspace data model is ready for a z column and 3D faces |

## 4. Meshing

| Item | Status | Priority | Notes |
|---|---|---|---|
| Face-based mesh format, `.vtu` export | done | P1 | |
| Structured nozzle mesh, Gmsh triangles / quad-dominant, inflation layers | done | P1 | |
| Mesh quality fields and validity checks, click a cell to see its values | done | P1 | |
| **Bug: quasi-1D mesh fails for n_cells ≥ about 450** (`OverflowError` in throat grading) | done | P1 | fixed in 6f: the growth-factor search had an upper end of 10, and 10^450 overflows; tested from 300 to 20 000 cells, runs at 300 / 450 / 1 000 / 5 000 cells |
| Quasi-1D residual stalls on fine meshes (minmod limit cycle in the smallest throat cells: near 1e-7 from 450 cells, near 1e-2 at 5 000 cells) | partial | P2 | the solution is steady (mass balance 0.001 %, exit Mach to 1e-5); use tol 1e-6 or CFL 0.1; a smoother limiter (van Albada) or implicit time stepping (Prompt 8) should fix it |
| Structured C-grid (airfoils, sharp trailing edge, wake cut) and O-grid (cylinder, sphere, smooth closed bodies), exact first-layer height, Coarse / Medium / Fine presets, same patch names as the Gmsh mesh | done | P2 | 6e part 2: `aeroflowsim/structured_mesh.py` (NumPy, not Gmsh transfinite: exact first layer, tested), input *Mesh type* in `external_2d`; `tests/test_structured_mesh.py`; theory manual section 14 |
| C-grid for blunt trailing edges, and for outlines with interior corners (diamond, wedge, flat-base bodies) | later | P2 | refused with a message; needs a base block / multi-block grid (a block of cells behind the base, corners as block edges) |
| Structured grid for edited workspace geometry | later | P3 | refused with a message; edited geometry is meshed with Gmsh |
| Structured grid far-field cells in the wake are very flat (aspect ratio about 1,300-4,800 along the wake, first layer 1e-3 c) | partial | P3 | normal for a C-grid with a thin first layer; irrelevant for Euler flow, revisit for viscous flow (Phase 4) |
| Mesh import (Gmsh .msh v2/v4, SU2, CGNS unstructured 2D, Fluent ASCII 2D) with unit, planar / axisymmetric choice and boundary-type map; export to Gmsh 2.2 / 4.1, SU2, CGNS; template "Start from an existing mesh"; `mesh-info` / `mesh-convert` | done | P2 | 6e part 3: `aeroflowsim/mesh_io.py`, `cases/imported_mesh`; round trips exact for all four writers (`tests/test_mesh_io.py`) |
| Import dialog with a boundary-type TABLE (one row per tag, drop-down) in the GUI | later | P2 | now the map is a text input (`name: type, ...`) with the list of found names and their types shown under the inputs; a Qt table dialog and Tools > Convert mesh are not built |
| Mesh import: 3D meshes, higher-order elements, binary Fluent, multi-zone CGNS, Fluent export | later | P2 | refused with a message (3D: Phase 3) |
| CGNS export checked with an external CGNS reader | later | P2 | only our own reader was available; open an exported file in SU2 / ParaView once |
| Planar nozzle template (for the MOC nozzle) | later | P2 | `tools/nozzle_flow_checks.py moc` solves the planar nozzle directly; no template runs planar internal flow of a wall profile |
| MOC nozzle flow check: exit Mach 2.23 mean / 2.28 centre line vs design 2.4 on a 2,560-cell mesh (wall cell 1.88) | partial | P2 | contour verified exactly by the area ratio; the CFD deficit comes from the coarse mesh, the throat-corner limit cycle (residual stalls near 1e-3, Prompt 8) and the sonic line that is not straight; needs a finer mesh and the implicit solver |
| NACA 0012 C-grid vs triangles (Mach 0.5, alpha 1.25): Cl 0.1751 vs 0.1681 (reference 0.1800), neither converged in 8,000 iterations (C-grid 945 s, triangles 348 s) | partial | P2 | C-grid 2.7 % below the reference, triangles 6.6 %; a converged comparison needs Prompt 8 speed |
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
| Custom-gas form: critical point and acentric factor | done | P3 | 6f close-out: optional fields (temperature and pressure in the user's units; all three or none); without them the ideal-gas check says it cannot run and why |
| Custom-gas form: saturation curve | later | P3 | without it the condensation check reports 'cannot be estimated' for custom gases |
| Gas mixtures (mole fractions of library gases), humid air | later | P2 | the data model keeps molar mass and critical constants per gas, ready for mixing rules |
| 2D / axisymmetric Euler with local time stepping, carbuncle fix | done | P1 | Prompt 7: `aeroflowsim/euler/` (rotated HLLC + HLLE blend at compressions, least-squares gradients, Venkatakrishnan / Barth limiters with freezing, positivity fallback, well-balanced axisymmetric source, SSP-RK3 / Jameson, CFL back-off); 3D-ready (flux and gradients tested on 3D cells) |
| Residual stall on triangle meshes of the sharp-throat nozzle (about 1e-4, a few cells at the throat corner; slow with a rounded throat) | partial | P2 | Prompt 7 finding: structured meshes converge to 1e-6; on triangles the thrust and Isp settle to about 0.1 % but the residual criterion is not met. Implicit LU-SGS (Prompt 8) is the planned cure. The fine wedge mesh (11,958 triangles) stalled near 4e-4 after the local limiter scaling and the compression-only sensor (together, not either alone: limiter chatter in the base wake); fixed by also freezing the limiter when the residual stalls (no new lowest value for 1,000 iterations after 3 orders): it converges in 4,478 iterations, every converged validation number unchanged |
| Slow convergence at low Mach number (Mach < 0.3, e.g. the nozzle inlet at Mach 0.01) | partial | P2 | explicit density-based solver; the smart rule warns; preconditioning in 8b, implicit in 8 |
| Full boundary-condition set from named boundaries | done | P1 | Prompt 7: total-pressure (direction normal or at an angle) and mass-flow inlets, pressure outlet (automatic supersonic switch), supersonic in/out, characteristic far field, slip wall, symmetry, axis; tested one by one |
| Initialisation options, restart from a saved solution, live monitors | done | P1 | Prompt 7: uniform, quasi-1D (axisymmetric nozzles, from the mesh's wall profile), previous result (same mesh) |
| Thrust / Isp / Cf, Cp / Cl / Cd / Cm | done | P1 | Prompt 7: thrust two ways (exit plane; wall + inlet), Isp, Cf, discharge coefficient, ideal quasi-1D Isp; Cl, Cd, Cm in body and wind axes, Cp along the wall |
| Time-accurate 2D runs in the GUI (end time input, snapshots, animation) | later | P2 | the solver supports a global time step and an end time (2D shock tube validation); no template exposes it yet (8e) |
| Thermally perfect gas in the 2D solver | later | P2 | the solver uses only the GasModel (T(e), c(T)); the far-field and isentropic-inlet relations use gamma at a reference temperature and need generalising with a thermally perfect gas |
| Numba kernels and multi-core residual | done | P2 | 8-1: 9-17 x on one core, 31-70 x with 16 threads (validation/timing.md); bit-identical for any thread count; NumPy kept as reference (1e-12) |
| Implicit time stepping (LU-SGS) | planned 8-2 | P2 | |
| One-core speed-up on the MMS quads 8.8 x (target 10 x) | partial | P3 | 8-1: gradient and limiter kernels are compute-bound; a fused gradient + limiter kernel could gain more |
| PyInstaller build with Numba not tested | partial | P1 | 8-1: `--collect-all numba llvmlite` added; check the installer and its first-run compile (kernels.CACHE) before the 8-2 release |
| Ghost states (boundary conditions) still NumPy | later | P3 | 8-1: boundary faces only, ~0 % of the time now; port when the GPU kernels come |
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
| 2D/3D field contours in the VTK view | done | P1 | Prompt 7: field, colour map, range, mesh edges, click a cell for all its values (smooth contour lines and isolines: 7b) |
| Streamlines, line probes, surface plots (Cp vs x) | done | P1 | 7b |
| Image / CSV / VTK export of solution fields | done | P1 | 7b: CSV (cells / nodes), VTU with node data, Tecplot ASCII, surface CSV, report-definition CSV; GUI and `export` command |
| Order-preserving limiter | later | P2 | 7b MMS finding: Venkatakrishnan with a constant K loses order under refinement on smooth flows (triangles 0.7-1.0 at 64->128, 1.1-1.3 at 32->64); e.g. Michalak and Ollivier-Gooch (2008) or a K that scales with h |

## 7. Verification, validation, trust

| Item | Status | Priority | Notes |
|---|---|---|---|
| Validity checks (convergence, mass balance, mesh quality) | done | P1 | 6f: + ideal-gas validity, condensation risk, temperature range of the gas data |
| Validation report (quasi-1D, Sod, nozzle geometry, external geometry, geometry workspace) | done | P1 | numbers of the old cases unchanged in Prompt 7; 6f added the quasi-1D mesh-refinement study |
| 2D Euler verification and first validation (free stream, well-balanced, gradients, BCs, 2D Sod along x and diagonal, Mach 2 wedge, Mach 6 cylinder + carbuncle test, N2 nozzle on 6 meshes) | done | P1 | Prompt 7: `tests/test_euler_*.py`, `validation/euler2d_*` |
| Run the validation suite from the GUI (Tools menu) | done | P2 | |
| MMS order-of-accuracy verification (structured and triangle meshes) | done | P1 | 7b: aeroflowsim/mms.py, validation/mms_euler2d: L2 order 1.98-2.02 on quads, distorted quads, triangles, mixed, planar and axisymmetric |
| 2D validation cases (wedge, diamond, cone, cylinder stand-off, BMG nozzle, NACA 0012, Prandtl-Meyer) | done | P1 | 7b: all added; BMG point z = 2.24 in is a documented SHORTFALL (0.80 vs 0.87, mesh-converged; cause not settled: steep gradient, position and tap-size uncertainty); NACA 0012: the three meshes were not refined systematically (only the wall size was halved: 7k / 9k / 13k cells), Cl 0.338 vs 0.352 is a documented SHORTFALL; a proper study needs Prompt 8 speed |
| BMG nozzle: tabulated measurements and a position-uncertainty band | later | P2 | the data are digitized from the report's Fig. 4; a z-uncertainty band (slope x dz) would judge the steep throat region fairly |
| Diamond-airfoil residual stall | partial | P2 | 7b: ~4e-3 in a few cells at the lower leading-edge shock foot (limiter limit cycle, found with the per-cell residual field); Cl, Cd steady to 1e-6. Prompt 8 (implicit) |
| Quick validation set on every push, full set weekly / on tags | done | P1 | 7b: AEROFLOWSIM_VALIDATION_SET=quick, run_all.py --quick, workflows tests.yml / validation.yml |
| Structured O-grid for smooth blunt bodies in the GUI | done | P2 | 6e: sphere / cylinder O-grid in `external_2d`; the capsule, blunted cone and hemisphere-cylinder have a base corner, so they need the unstructured mesh (see the C-grid / flat-base gap) |
| Cross-code comparison with SU2 / OpenFOAM | later | P2 | Phase 4 |
| GCI mesh-independence tool | done | P2 | 7b: aeroflowsim/gci.py (Roache / Celik et al. 2008), used by the MMS, nozzle and NACA 0012 studies; a GUI dialog for it is later |

## 8. Intelligence

| Item | Status | Priority | Notes |
|---|---|---|---|
| Smart rules: setup suggestions (mesh size, first layer from Re and y+, CFL) | done | P2 | 6d: sizes and enclosure; Prompt 7: first layer for y+ = 1 from the flow's Reynolds number (inflation on), CFL / first-order start / quasi-1D start from the flow inputs |
| Smart rules: failure diagnosis with suggested fixes | done | P2 | Prompt 7: after a diverged run or CFL reductions: lower CFL, first-order start, quasi-1D start, boundary values, throat refinement, where it failed |
| Smart rules: result sanity checks against theory (e.g. Isp vs quasi-1D, Cd vs Newtonian) | partial | P2 | Prompt 7: total-pressure loss and thrust-two-ways checks; Isp shown next to the ideal quasi-1D Isp |
| AI assistant plugin v1 (opt-in, fills schema inputs only, local-model option) | done | P3 | 7c: `aeroflowsim/assistant/`, Setup-step panel, Tools > Assistant settings, `assist` command. Off by default; providers Rules (no AI), Local model (localhost only), Online (own key, own opt-in); every proposal checked against schema.toml; Apply = one undo step; a model's numbers must appear in the user's text. Tests use a fake provider (no network, no model) |
| Assistant tried against a real local model server and a real online service | later | P2 | 7c had no model server, no `keyring` package and no key at hand: the Local and Online providers are tested only with a fake server answer (request and answer format, localhost check, https check, strict JSON). Try Ollama once (`--provider local --model NAME`) and one online service before relying on them |
| Assistant: online provider speaks only the common "chat completions" JSON format; no built-in provider address | later | P3 | a native provider for another API format would be a new small class in `assistant/` |
| Assistant: explaining results, filling the boundary-condition table, files, mesh and numerics choices | later | P3 | v1 fills schema inputs only (numbers, choices, gas); it does not read results |
| Assistant (rules): shapes must be named in full ("conical nose cone"), no number words ("two"), no radius to diameter, English only | partial | P3 | listed in the user guide; a model provider covers more phrasings (its numbers must still be in the text) |
| Surrogate models + shape optimisation | later | P2 | Phase 5 headline feature |

## 9. Documentation, community, release

| Item | Status | Priority | Notes |
|---|---|---|---|
| Theory manual | partial | P1 | updated every prompt |
| Developer guide (GUI architecture) | done | P1 | `docs/developer_guide.md` |
| User tutorials | done | P1 | 7b adds post-processing a nozzle, NACA 0012 transonic, experimental nozzle; user guide docs/user_guide.md |
| CI on Windows and Ubuntu incl. GUI tests | done | P1 | headless display action |
| 2D alpha release on GitHub | done | P1 | 7b: v0.2.0a1 pre-release on the PRIVATE repository; before the installer is shared with anyone, the repository must be public or the source attached (GPL) |
| Zenodo DOI, JOSS paper | later | P2 | Phase 5 |
| Contributing guide, code of conduct, issue templates, security policy | done | P2 | 7b |
| Repository pre-public check | done | P1 | 7b: no secrets, personal paths or large binaries in history; CAD test files are generated; commit e-mail becomes public |
| Optional web demo | later | P3 | |

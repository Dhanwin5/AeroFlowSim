# 3D Euler solver - the finite-volume Euler solver on 3D meshes (tetrahedra, prisms, hexahedra), 3D templates, 3D results

**Model: Opus** (new numerics in 3D: boundary conditions, implicit LU-SGS on mixed 3D cells, verification; many
design decisions in the 3D Results step).

Paste everything below the line into ONE new Claude Code session. It covers the whole stage in one go.

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder `C:\Projects\CFD software`, GitHub `Dhanwin5/AeroFlowSim`). I am a beginner
programmer who knows aerospace engineering and CFD theory. This is the ONLY prompt for the whole 3D Euler solver stage:
do all 8 parts below in order, in this one session, without waiting for me between parts.

1. Start: read `CLAUDE.md`, `docs/gap_register.md`, this file (the ledger at the bottom; create it), the ledger of
   `docs/roadmap/3d_geometry_and_meshing.md`, `docs/theory_manual.md` sections 12, 13b-13g, `docs/developer_guide.md`
   (3D workspace, VTK view, jobs, post-processing), and skim `aeroflowsim/euler/` (all), `aeroflowsim/compute.py`,
   `aeroflowsim/post/`, `aeroflowsim/workspace_mesh3d.py`, `aeroflowsim/mesh.py`, `aeroflowsim/mesh_io.py`,
   `cases/external_3d`, `cases/nozzle_axi`, `cases/imported_mesh`, `aeroflowsim/gui/steps/results.py`,
   `aeroflowsim/gui/flow_view.py`. Write a short plan in plain words, then start at once.
2. Do not stop to ask questions. Decide the way Fluent, SU2, CFL3D or OpenFOAM would, and give one sentence of why in
   the summary. Stop only before: deleting files you did not create in this session, adding a dependency, or anything
   outward-facing apart from the push at the end.
3. Ledger = your memory. Keep a progress log at the bottom of this file. After every part: commit, then add a ledger
   entry (what is done, how it was verified, what is next, anomalies). If the conversation gets compacted, re-read the
   ledger and carry on from the next part. Do not stop between parts to report to me.
4. Out of room? Only if you truly cannot continue, stop at the END of a part, commit, write the ledger entry, and tell
   me plainly which part is next. Never leave a part half-done without a ledger entry.
5. Long jobs (3D runs, validation, timing) in the background, ONE heavy job at a time (the 32 GB machine ran out of
   memory with three at once in the speed stage; a 3D run of 1 million cells needs a few GB). Report result lines only.
6. Commit after each part. Flag anomalies yourself; never tune a number to pass. Rule 4 of CLAUDE.md: if a change alters
   any number in `validation/report.md` (2D cases), say so and why.
7. Walk through my next actions for every feature (stop and continue a 3D run, change an input, re-mesh, reopen the
   project, open an old 2D project, units and theme, command line, Cancel a long run) and write them into tests.

## Context (state after the 3D geometry and meshing stage)

* 2D / axisymmetric solver (`aeroflowsim/euler/`): Numba kernels, implicit LU-SGS by default, MMS order 2, validated
  (report.md). The face-based `Mesh` and the kernels are 3D-ready: hexahedra and tetrahedra were tested on single cells
  only (`tests/test_euler_core.py`, `tests/test_kernels.py`); `dim = 3` exists in the kernels but no 3D problem has ever
  been solved end to end. GPU-ready rule (CLAUDE.md) applies to every new kernel.
* 3D meshes: `workspace_mesh3d.mesh_3d` (Gmsh tetrahedra + prism layers from named walls, VTK types 10 / 13; patches =
  the face names of the 3D workspace), exported to Gmsh / SU2 / CGNS / .vtu. 3D quality checks run before any run
  (negative volume = error; skewness equivolume for tetrahedra; dihedral angle; first-layer height).
* Template `cases/external_3d` is mesh only (`solver = false` + message): body (sphere, cylinder, nose cone, box, or a
  STEP solid), far field (box / cylinder / sphere, half domain with a symmetry plane), free-stream inputs (gas, Mach,
  p, T) already there. A fluid STEP nozzle is meshed by the same template (tutorial `nozzle_step_to_mesh.md`, example
  `cases/external_3d/examples/conical_nozzle.step` = the default N2 nozzle's gas, 6.343 mm³).
* Findings of the 3D geometry and meshing stage that belong here:
  - **3D mesh IMPORT does not exist**: `mesh_io` reads 2D files only (the earlier plan wrongly said it read 3D). The
    "Start from an existing mesh" template must take 3D Gmsh / SU2 / CGNS files in this stage.
  - **Multiple zones**: two fluid bodies that touch are NOT connected: the 3D booleans do not share topology
    ("fragment"), so their meshes are not conformal. Multiple zones need a Fragment / "share topology" operation in
    `operations3d.py` and zone ids in the Mesh (cell zones), then per-zone settings.
  - Edges of the 3D workspace cannot be picked or sized yet (gap register); prism layers next to a curved non-wall
    boundary are refused; no automatic layer thinning in narrow gaps. Not needed for Euler, but keep them in mind for
    the viscous stage.
  - Mesh sizes measured (validation/mesh_3d): 29k / 126k / 719k cells for wall sizes 80 / 40 / 20 mm on a 1 m sphere
    in a 16 x 11 x 11 m box; 0.5 / 3.8 / 30 s to mesh. Meshing is serial Delaunay on purpose (reproducible).
  - Gmsh renumbers nodes after meshing unless `Mesh.Renumber = 0`; OCC renumbers faces after any transformation
    (handled; do not "simplify" it away).

## Decisions (made: follow them)

* One solver for 2D, axisymmetric and 3D: extend `aeroflowsim/euler/` to 5 conserved variables (rho, rho u, rho v,
  rho w, rho E) when `mesh.dim == 3`; 2D keeps 4 and its results must not change (bit for bit on the validation cases).
* Boundary conditions in 3D through the face normal (far field / characteristic, slip wall, symmetry, total-pressure
  inlet, mass-flow inlet, pressure outlet, supersonic inlet / outlet), the same BC table in the Setup step, filled
  from the 3D patch names.
* Implicit LU-SGS stays the default; local time stepping; the same robustness (CFL back-off, positivity fallback).
* Forces in 3D: force and moment vectors on walls, Cl / Cd / Cy / Cm with a reference area and length typed by the
  user (default: frontal area and L of the body); nozzles: thrust two ways, mass flow, Isp.
* Results step in 3D: surface contours on the patches, slice planes (moveable), iso-surfaces, 3D streamlines,
  probes, and the existing 2D tools where they make sense; logic in `aeroflowsim/post/` without Qt.
* Verification first: free-stream preservation on every 3D cell type, then MMS order 2 on tetrahedra, prisms and
  hexahedra, before any validation case.

## Parts (all in this session, in this order)

A. Solver

1. 3D residual and LU-SGS: 5 equations, 3D least-squares gradients and limiters, 3D ghost states for every BC,
   implicit LU-SGS on mixed cells; free-stream preservation (uniform flow stays uniform to round-off on a mixed
   tetra / prism / hexa mesh); kernels agree with the NumPy reference to 1e-12 and do not depend on the thread count.
2. Verification: 3D MMS (`aeroflowsim/mms.py` extended) on tetrahedra, prisms and hexahedra (order 2 within the same
   tolerances as 2D); 3D mesh import (Gmsh v2 / v4, SU2, CGNS unstructured 3D) with the boundary-type map, so a mesh
   from another program can be solved; the imported_mesh template accepts 3D files.

B. Templates

3. `external_3d` gets `run()` (solver = true; keep a mesh-only option for very large meshes): far field + slip walls +
   symmetry; forces and coefficients; Cp on the walls; a smart rule for the reference area. Its tests pass.
4. 3D internal flow: the fluid nozzle (STEP or revolve) with total-pressure inlet and pressure / supersonic outlet,
   thrust, mass flow, Isp; compare with the 2D axisymmetric result of the same nozzle. Multiple zones: a Fragment
   operation and cell zones in the Mesh (the conformal interface between two fluid bodies), shown and checked.

C. GUI

5. Run step for 3D (monitors: residuals per equation, forces / mass flow), Stop and continue, Cancel; Results step 3D:
   surface contours, slice planes, iso-surfaces, 3D streamlines, probes, report definitions; the HTML/PDF report with
   3D pictures; .vtu / CSV export of 3D results.
6. Projects and command line: `run`, `report`, `export` for 3D projects; examples (`tools/make_examples.py`): a sphere
   at Mach 3 and the N2 nozzle in 3D; screenshots of the changed pages (light and dark).

D. Validation and finish

7. Validation (background, one at a time): cone at Mach 2 (half-angle 10 deg, Taylor-Maccoll surface Cp and shock
   angle, `gasdynamics.taylor_maccoll`), sphere at Mach 3 (shock stand-off vs the Billig correlation, as the 2D
   cylinder case), the N2 nozzle in 3D (mass flow and thrust vs the 2D axisymmetric case, within the discretisation
   difference), 3D MMS; iterations and wall-clock time in the report (rule 14). Quick and full sets.
8. Docs (user guide: 3D runs and results; theory manual: 3D Euler, 3D BCs, forces; developer guide), tutorial
   "sphere at Mach 3", gap register, CHANGELOG, the plan of the next stage (low-Mach preconditioning, see
   `docs/roadmap/README.md`) in this same style; full fast tests, GUI tests, quick and full validation; then push.

## Quality gates

* Tests pass; validation of every part written and passing; ledger updated after every part; pushed at the end.
* 2D validation numbers unchanged (or every change explained); MMS order 2 in 2D and 3D.
* No Qt in solver, post or logic modules (tested); privacy test still passes.

## Done when (check every line with evidence)

1. A 3D body (template or STEP) can be meshed, solved (Euler, LU-SGS) and post-processed in 3D from the GUI, with Stop /
   continue / Cancel, and from the command line.
2. Free-stream preservation and MMS order 2 hold on tetrahedra, prisms and hexahedra; cone, sphere and nozzle
   validation cases pass; 3D meshes from other programs can be imported and solved.
3. Old 2D projects open and give unchanged results; all tests and validation pass; docs, gap register, CHANGELOG,
   ledger and the next stage's plan written; pushed.

At the very end, give me a plain-language summary: what works now, what you decided and why (one sentence each), the
walkthrough of the most important new module (CLAUDE.md rule 15), the gap register changes, and anything I should check
by hand in the GUI.

## Addendum (4 Nov 2026, review) - overrides anything above that conflicts

Scope and order: (1) multiple zones (Fragment, cell zones) only after Parts 1-7; if no room, a gap moved to the
viscous stage. (2) 3D mesh import: Gmsh v2/v4 and SU2 first, CGNS 3D only if time allows. (3) After Part 4: commit,
ledger, fast tests, then Part 5.
Solver and verification: (4) tolerances pre-registered in each reference.toml BEFORE running: cone Cp (Taylor-Maccoll)
2 %, cone shock angle 3 %, sphere stand-off vs Billig 5 %, nozzle mass flow vs 2D axisymmetric 1 %, thrust 2 %; a miss
is a SHORTFALL with its cause, never retuned. (5) Consistency: same body 2D axisymmetric vs 3D quarter domain; closed
body in uniform pressure gives zero force; a one-layer extruded 3D mesh reproduces 2D Sod and wedge. (6) Sphere at
Mach 3 and 6 on tetrahedra: positivity fallback and carbuncle behaviour reported. (7) Prism layers default OFF for
Euler runs.
Size, speed, safety: (8) 3D N2 nozzle as a quarter domain (two symmetry planes), Coarse first, estimate before finer.
(9) validation/timing.md: sphere Mach 3 on the 126k mesh converged in under 30 min (report a miss), memory per million
cells; memory estimate before a run, warn above ~70 % of free RAM (GUI and CLI). (10) 3D runs autosave a restart file
about every 15 min (configurable); Continue uses it; test: kill, continue, same result. (11) Slices / iso-surfaces
computed on the slice, not the volume; timing on the 719k mesh.
Finish: (12) summary with test counts, "2D validation numbers unchanged", the tolerance table, every item not built.
(13) no tag, release or repository-settings change.

## Ledger (progress log)

### Part 1 - 3D residual and LU-SGS (done)
- Found: the solver, kernels, gradients, limiters and fluxes were already written for any number of velocity
  components; what was missing was a 3D free stream (sideslip) and proof. `boundary._free_stream` now takes
  `sideslip` (value set by 3D templates, absent = 0) in 3D: u = V cos a cos b, v = V sin a cos b, w = V sin b. The 2D
  code path is unchanged (bit for bit). No new BC input (that would change old projects' fingerprints).
- New `simple_meshes.box_mesh_3d(n, kind, warp)`: hexahedra, prisms, Kuhn tetrahedra (conformal), hex-prism mixed;
  `_orient_cells` fixes VTK orientation.
- Verified (`tests/test_euler_3d.py`, 46 tests): free stream at 10 deg incidence + 5 deg sideslip on warped boxes of
  every kind stays uniform to < 1e-13 (SSP-RK3 and LU-SGS, NumPy and Numba); gas at rest stays at rest; Numba residual
  = NumPy to 1e-12 on every kind with every limiter / gradient / order and a shock (HLLE blend active); whole 3D runs
  agree; 3D runs bit-identical for 1, 2, 4 threads; every BC type gives a physical 3D ghost; slip wall zero mass flux;
  mass-flow inlet flux and direction. 2D kernel/core/BC tests: 117 pass.
- Mixed tetra + prism + hexa in ONE mesh needs pyramids (tets cannot meet hexes conformally); covered by hex-prism
  boxes here and by Gmsh tetra + prism-layer meshes in Part 3.
- Next: Part 2 (3D MMS, 3D mesh import).

### Part 2 - 3D MMS and 3D mesh import (done)
- `mms.py`: `manufactured_3d`, `source_3d` (sum over k of dF_k/dx_k, hand-written chain rule), `MMSSolver3D`,
  `run_level_3d(kind, n)` on warped boxes (LU-SGS, no limiter). Source checked against central differences of the
  exact flux (test).
- Preliminary orders (L2, min over 5 variables, 12^3 -> 24^3): hexahedra 1.97, prisms 1.87, tetrahedra 1.75 (rising:
  1.65 at 6 -> 12). `validation/mms_euler3d/reference.toml` pre-registered with the 2D acceptance (hex >= 1.8,
  prisms/tets >= 1.7). Honest note: the QUICK tolerances (6^3 -> 12^3) were set after seeing these coarse numbers;
  the full-set tolerances are the 2D ones, unchanged.
- 3D import: `mesh_io.read_gmsh` (v2/v4 via meshio; volume cells -> 3D, tagged triangles/quads = boundary faces) and
  `read_su2` (NDIME 3) give `RawMesh.dim = 3`; `_mesh_from_raw_3d` turns inside-out cells round (`_orient_cells`, now
  with pyramids), matches tags to boundary faces, refuses untagged faces and "axisymmetric". Round trips Gmsh 2.2 /
  4.1 / SU2 for hexa, prism, tetra, hex-prism and pyramid boxes; an imported pyramid mesh keeps a free stream.
  `box_mesh_3d` has a "pyramids" kind. CGNS 3D import NOT built (addendum rule 2: Gmsh and SU2 first) - gap.
- imported_mesh template reads 3D files (counts "faces"); solving them needs the 3D setup of Part 3.
- Tests: test_euler_3d.py 79 pass, test_mesh_io.py updated (3D files are now read).
- Next: Part 3 (setup.py 3D: fields, equations, forces; external_3d run()).

# Full 3D release - multiple zones, 3D completeness, 3D validation, release v0.3.0

**Model: Opus** (shock-position accuracy on tetrahedra, multi-zone mesh topology and conservation at zone interfaces,
3D turbulent validation: new numerics and many design decisions).

Paste everything below the line into ONE new Claude Code session. It covers the whole stage. If the session runs
long, Part 4 (release) must still be reached: Part 3 items that miss their time box are recorded as SHORTFALL, not
skipped silently.

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder `C:\Projects\CFD software`, GitHub `Dhanwin5/AeroFlowSim`). I am a beginner
programmer who knows aerospace engineering and CFD theory. This is the ONLY prompt for the full 3D release stage: do
all parts below in order, in this one session, without waiting for me between parts.

1. Start: read `CLAUDE.md`, `docs/gap_register.md`, this file (create the ledger at the bottom), the ledgers of
   `docs/roadmap/3d_geometry_and_meshing.md`, `3d_euler_solver.md`, `robust_second_order.md` and `laminar_viscous.md`,
   `docs/theory_manual.md` sections 12-13h, and skim `aeroflowsim/euler/`, `aeroflowsim/mesh.py`, `mesh_io.py`,
   `workspace_mesh3d.py`, `prism_layers.py`, `geometry_model/operations3d.py`, `kernel3d.py`, `gui/flow_view.py`,
   `gui/results_logic.py`, `gui/post_panels.py`, `post/`. Write a short plan in plain words, then start at once.
2. Do not stop to ask questions. Decide the way Fluent, SU2, STAR-CCM+ or CFL3D would and give one sentence of why in
   the summary. Stop only before: deleting files you did not create in this session, adding a dependency, or anything
   outward-facing (push, tag, release) - Part 4 says exactly when to ask.
3. Ledger = your memory: after every part commit, then add a ledger entry (done, how verified, next, anomalies). If the
   conversation is compacted, re-read the ledger and carry on.
4. Long jobs (validation, 3D runs) in the background, ONE heavy job at a time (32 GB machine; about 4 GB per million 3D
   cells, measured). Never write unquoted shell heredocs.
5. Pre-register every validation tolerance in its reference.toml BEFORE the run; never retune; a miss is a SHORTFALL.
6. Rule 4 of CLAUDE.md: every number in `validation/report.md` that you do not deliberately change must stay bit for
   bit (single-zone meshes take exactly the old code path). Any number you change on purpose (Part 2): list old -> new
   with the reason, in the ledger, CHANGELOG and final summary.
7. Walk through my next actions for every feature (open an old project, Stop / Continue, change an input, re-mesh,
   reopen) and test them (pytest-qt for GUI).
8. NumPy reference and Numba kernels agree to 1e-12; kernels stay GPU-ready (CLAUDE.md).

## Where 3D stands (measured, start of this stage)

- One 3D template, `cases/external_3d`: sphere, cylinder, nose cone, box or STEP/IGES solid in a box / cylinder /
  sphere far field (half / quarter with symmetry planes); tetrahedra + prism layers; Euler, laminar, SA, SST;
  external (forces, Cd/Cl/Cy, Cp) or internal nozzle (inlet / outlet faces: mass flow, thrust, Isp). Import Gmsh / SU2
  3D; export Gmsh, SU2, CGNS, VTU.
- 3D Results: walls coloured by field, slices, iso-surfaces, streamlines, probe, export. NOT wired: report
  definitions, surface (XY) plots, patch regions, snapshots / compare (the 2D panels of `post_panels.py`).
- Full validation 2026-11-05: 21 / 25 pass. 3D FAILS, all one symptom - shocks too far out on simplex cells:
  - sphere M3 stand-off 0.2269 R vs Billig 0.2050 (+10.7 %, tol 5 %);
  - 10 deg cone M2 shock angle 33.39 vs Taylor-Maccoll 31.21 deg (+7.0 %, tol 3 %; +5 % at 72k cells);
  - 30 deg ramp M2 stand-off tets / hexes 1.83 (tol 2 %).
  2D twin: cylinder M3 on triangles 0.703 R vs 0.649 (+8.4 %); the structured 2D grid gives 4.5 %.
  Already fixed in the robust-second-order stage: gradient stencil (Green-Gauss with node values) and per-cell update
  limit. Still open: the remaining simplex error.
- Square duct laminar 3D: 1.7 / 2.3 % off the series (12 cells per half side; resolution suspected, unverified).
- No 3D turbulent validation beyond one-layer extrusion consistency + MMS.

## Part 1 - Shock position on tetrahedra (diagnose first, one hypothesis at a time)

The headline 3D numbers fail; a 3D release cannot claim validation with them. Method (as in the robust-second-order
stage): one hypothesis, one experiment, measure, record in the ledger, then the next.
1. Resolution study first: sphere M3 at 60k / 150k / 400k cells (and cone at 3 levels). If the error falls at the
   expected order, it is resolution: report GCI-extrapolated values (`aeroflowsim/gci.py`) and the mesh needed.
2. Candidate causes to test, in this order: limiter (Venkatakrishnan K, Barth-Jespersen; Michalak & Ollivier-Gooch
   2009 accuracy-preserving limiter, already a gap-register item), shock-capturing dissipation of HLLC/HLLE blend on
   skewed faces, entropy fix, gradient reconstruction at the shock (weighted least squares vs node Green-Gauss),
   cell-size distribution near the stagnation line (mesh, not solver).
3. Any fix: an option first, measured on all three 3D cases and the 2D triangle cylinder; MMS order must not drop
   (triangles, tetrahedra); then decide the default with evidence. Default change = rule 4 (list every number).
Done when each 3D shock case either passes its pre-registered tolerance or is a SHORTFALL with a measured cause.

## Part 2 - Multiple zones

What commercial codes do: one mesh, several cell zones sharing faces (conformal interface, Fluent "interior" between
zones), each zone with a name and its own settings; non-conformal interfaces are later.
1. Mesh: `Mesh` gets `cell_zones` (name -> cell ids) and interface patches between zones are interior faces (owner and
   neighbour in different zones). Single-zone meshes: unchanged arrays, unchanged results (bit for bit).
2. Geometry: 3D workspace keeps several solids as separate fluid zones joined by Gmsh Fragment (shared topology,
   conformal faces). 2D the same via `kernel.py`. Zone names clickable like boundary names.
3. Per-zone settings now: name, initial condition, refinement size, "solid / excluded" (blanked). Per-zone physics
   (porous, source terms) is later.
4. Import / export: multi-zone Gmsh (physical volumes), SU2 (MARKER + zone), CGNS 3D import (multi-zone), Fluent
   zones on import.
5. Results: colour / filter by zone, integrals per zone, mass balance across interfaces.
6. Tests: conservation across an interface to round-off, a two-zone mesh equals the same mesh as one zone (1e-12),
   import / export round trip per format.

## Part 3 - 3D completeness

1. 3D Results workspace: wire report definitions, surface / XY plots (e.g. Cp along a cut of a wall), patch regions,
   snapshots and compare to 3D (shared `post/` code; no new math in the GUI).
2. 3D nozzle helpers: plume region and inlet plenum round an imported nozzle (3D form of the 2D enclosure tools), as
   zones from Part 2.
3. A dedicated 3D nozzle template `cases/nozzle_3d` (STEP or revolved contour, inlet / outlet, plume region; thrust,
   Isp, Cf) with schema, tests and a validation case vs the axisymmetric `nozzle_axi` result on the same contour
   (pre-registered tolerance). Never edit other case folders (rule 6) except `external_3d` for the P3 item below.
4. 3D geometry: edge picking (local edge size), fillet / chamfer of solid edges, split body by a plane.
5. Small items: hide free-stream inputs for internal-flow `external_3d` projects; 3D dialogs follow View > Units.
6. 3D validation (pre-registered tolerances, background, time box ~2 h of runs in total):
   - ONERA M6, M 0.8395, alpha 3.06 deg, Euler then SA: Cp at the 6 Schmitt & Charpin sections;
   - 3D quarter CubeSat nozzle with prism layers vs the axisymmetric result;
   - sphere Re 100 laminar (Johnson & Patel) if the reference is attached; otherwise PENDING REFERENCE;
   - square duct 24 x 24 re-run (resolution question).

## Part 4 - Release v0.3.0 "3D"

1. Regenerate the examples (`tools/make_examples.py`) so they open up to date (test it); add a 3D example (sphere or
   3D nozzle with result).
2. User guide: 3D chapter + one tutorial in `docs/tutorials/` (3D nozzle with plume region, step by step);
   theory manual: every new method with references; developer guide: zones.
3. Full fast + GUI tests, full validation (`validation/run_all.py`) with every changed number listed.
4. Version 0.3.0 in pyproject, CHANGELOG, build the Windows installer locally (`tools/build_installer.py --smoke`).
5. STOP and ask me before: `git push`, the tag `v0.3.0` (GitHub Actions builds Windows / macOS / Linux installers)
   and the GitHub release text (write the draft into the ledger). Do these only after my yes.

## Done when

- Each 3D shock case passes or is a SHORTFALL with a measured cause; MMS orders unchanged or better.
- Multi-zone meshes work from geometry to results, with conservation tests; single-zone results bit for bit.
- 3D Results has the 2D post-processing panels; `nozzle_3d` template with tests and validation.
- ONERA M6 and the 3D CubeSat nozzle are in `validation/report.md` (pass or SHORTFALL).
- Tests green, report regenerated, docs and gap register updated, v0.3.0 installer built and smoke-tested, release
  waiting for my yes. Next stage file written (rule 19): low-Mach preconditioning, updated with this stage's findings.

## Ledger

### Plan (2026-11-07, start of the session)
- Part 1: one hypothesis at a time, cheapest twin first. The 2D cylinder on triangles shows the same symptom (+8.4 %)
  as the 3D sphere (+10.7 %) and runs in minutes, so each hypothesis is screened there, then confirmed on the sphere.
  Order: (1) resolution (cell growth across the shock layer, then a sphere refinement study with GCI), (2) limiter
  (K, Barth-Jespersen), (3) HLLE carbuncle blend, (4) gradient method. Tool: `tools/shock_position_study.py`
  (one JSON line per run in `validation/results/shock_study.jsonl`).
- Part 2: `Mesh.cell_zones` (name -> cell ids, empty for one zone = old arrays), Fragment in 2D / 3D kernels, zone
  names and per-zone settings in the workspace, IO per format, results per zone, conservation tests.
- Part 3, Part 4 as written above; Part 4 is reached even if Part 3 items run out of time (SHORTFALL).

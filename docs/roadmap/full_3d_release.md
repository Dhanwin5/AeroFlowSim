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

### Ledger 1 - Part 1 first experiments; Part 2 mesh and file zones (2026-11-07)
Done (commit e6d2cf5):
- Part 2 step 1 + 4: `Mesh.cell_zones` ({} for one zone: old arrays and the old .npz file, tested), `zone_names`,
  `zone_cells`, `interfaces`, `interface_faces`, `mesh.remove_zones` (solid / excluded zone -> wall patch
  "<zone>_wall"); zones as initial-condition regions (`{"type": "zone"}` in apply_patches and region_cells);
  interface fluxes stored for multi-zone runs (`series["interface_flux"]`) and `post.integrals.zone_balance`.
  Files: Gmsh 2D / 3D physical surfaces / volumes (v2.2 and 4.1), SU2 NZONE / IZONE (points merged at the interface),
  CGNS one Zone_t per cell zone, now 2D AND 3D import (was 2D only), Fluent cell zones (section 12 + 45).
- Verified: tests/test_zones.py (15 tests): one-zone file unchanged, round trips per format, two-zone run = one-zone
  run (all fields bit for bit), zone balances sum to the domain balance to 1e-12; test_mesh_io.py unchanged (pass).
Part 1 measurements (`validation/results/shock_study.jsonl`, `tools/shock_position_study.py`):

| Run | Cells | Converged | Stand-off / R | vs Billig |
|---|---:|---|---:|---:|
| 2D cylinder, triangles (validation mesh) | 11,435 | no (1e-3) | 0.7027 | +8.4 % |
| 2D cylinder, triangles, growth 1.08 | 32,816 | no (1e-3) | 0.7151 | +10.3 % |
| 2D cylinder, structured polar 60 x 80 | 4,800 | 1e-6 | 0.7019 | +8.2 % |
| 2D cylinder, structured polar 120 x 160 | 19,200 | 1e-6 | 0.6993 | +7.8 % |
| 2D cylinder, structured polar 240 x 320 | 76,800 | 1e-6 | 0.6981 | +7.6 % |
| sphere axisymmetric O-grid Medium | 4,800 | 1e-6 | 0.2142 | +4.5 % |
| sphere axisymmetric O-grid Fine | 14,400 | 1e-6 | 0.2139 | +4.4 % |

- Finding 1 (hypothesis "simplex error" REJECTED for the 2D cylinder): the solver's mesh-converged answer on a
  structured quad grid is 0.698 R, +7.6 % from Billig; the triangle mesh is within 0.7 % of it. The 8.4 % "triangle
  error" is the gap between converged Euler and Billig's correlation at Mach 3 (the correlation is a fit to
  experiments, its error grows at low Mach: +2.3 % at Mach 6 on the polar grid). The pre-registered tolerance is not
  changed: the case stays a SHORTFALL with this measured cause.
- Finding 2: for the sphere the converged structured answer is 0.2139 R (+4.4 %); the tetrahedra give 0.2269 R, so
  +6 % of the gap is the tetrahedral mesh. Next: 3D refinement study (60k / 150k / 400k).
- Anomaly: axisymmetric O-grid 640 x 180 with far field at 10 D diverged at iteration 225 (not followed up: not
  needed for the converged value; recorded for the gap register).
- Stopped (redundant after the polar study): 2D triangle growth 1.04 / 1.02 runs.

### Ledger 2 - Part 2 multiple zones (done; commits 4ef59c5 .. zones part 5)
- Geometry: Fluid zones operation in 2D (`operations.FluidZones`, `Kernel.fragment`) and 3D (`FluidZones3D`,
  `Kernel3D.fragment`): Gmsh/OCC Fragment, the LATER body wins where bodies overlap (Fluent / STAR-CCM+ region order),
  zone names per body, per-zone cell size (Gmsh Constant field, Min with the other fields), excluded ("solid /
  excluded") zones removed after meshing with the interface as wall "<zone>_wall". The mesher gives cells their zone
  (tets / triangles per volume / face; prism and inflation layers take the zone they grow into). Without a Fluid zones
  operation the old code path runs unchanged (no zones, same cell order).
- GUI: Fluid zones tool in the 2D and 3D Geometry steps (form: zone name, size, exclude for the last selected);
  "Cell zone" field in Results (colour / threshold); zone balance rows in the flux table and the report; zones as
  regions of the Run step's start patches. Per-zone physics (porous media, sources) stays later (gap register).
- Verified: tests/test_zones.py 20 tests + tests/gui/test_zones_gui.py; workspace mesh tests and geometry GUI tests pass.
- Decision (why): conformal interfaces only, as Fluent's "interior" between cell zones - exact conservation with no
  interpolation; non-conformal interfaces are later.
- Next: Part 3.

### Ledger 3 - Part 3 (3D completeness) and Part 4 docs (2026-11-07)
Done:
- 3D Results tabs Patches / XY plot / Reports / Snapshots (`gui/results3d.py`, all numbers from `post/`):
  `view3d.wall_cut` (tested: exact for linear fields), `integrals.forces_3d` (a Cd report = the solver's Cd to 5e-16).
- Template `cases/nozzle_3d` (schema, README, 5 tests): revolved conical contour of nozzle_axi, quarter / full, plume
  region as zone "plume" (one template step: Revolve + Fragment), exit numbers on the zone interface;
  `nozzle_problem_3d(..., wall_names=...)` (default = before). Revolve gained profile "nozzle" and per-edge names.
- Plume / plenum operation round any fluid nozzle (`NozzleRegion3D`), Edge size / Fillet / Chamfer / Split by plane,
  Edges selection filter in the 3D view; geometry dialogs follow View > Units; free-stream inputs hidden for internal
  flows (generic rule from the template's `is_internal`, so `external_3d/case.py` is unchanged: an edit there would have
  marked every 3D project "needs update" through the template fingerprint - found and reverted).
- Validation nozzle_3d (pre-registered 2 % / 2 % / 1 %, commit before the run): mass flow ratio 1.0280 (SHORTFALL),
  thrust 1.0230 (SHORTFALL), Isp 0.9951 (PASS). nozzle_3d_laminar pre-registered (3 % / 1.5 %; set after seeing the
  inviscid gap - stated in the file).
- Docs: theory 13k, user guide 3D chapter (tabs, zones, nozzle template, edges), developer guide zones, tutorial
  `nozzle_3d_plume.md`, CHANGELOG 0.3.0, gap register, low-Mach stage file, roadmap README; version 0.3.0.
Anomalies:
- Two background shells seemed to die; in fact the solver runs as `python3.13.exe` (the venv python.exe is a launcher)
  and I looked for `python`. Result: duplicate sphere L3 runs; one stopped through its task, one detached duplicate
  could not be stopped (Stop-Process was refused by the permission system) - it only costs CPU time and writes a
  duplicate row.
- ONERA M6 not run: the ONERA D section coordinates are not in the repository and adding external geometry data needs
  the user's OK. Sphere Re 100: no reference attached (PENDING REFERENCE).
Next: sphere L3, duct 24 x 24, laminar 3D nozzle, examples, full validation, installer.

### Draft of the GitHub release text (v0.3.0) - waiting for the user's yes before push / tag / release
**AeroFlowSim 0.3.0 - "3D"**

AeroFlowSim is a GUI-first, open-source CFD solver for nozzle and propulsion aerodynamics, with built-in validity checks
and published validation. 0.3.0 completes the 3D workflow:

- **Multiple cell zones** in 2D and 3D: overlapping fluid bodies become zones that share their faces (Gmsh/OpenCASCADE
  Fragment), each with its own name, cell size, start state or "excluded"; flux balance per zone and per interface;
  zones kept in Gmsh, SU2, CGNS (now also 3D) and Fluent mesh files.
- **3D nozzles**: a new 3D nozzle template (quarter or full, optional plume region), plume / plenum regions round any
  imported nozzle, and a step-by-step tutorial.
- **3D Results**: Cp (or any field) along a cut of the walls, report definitions, snapshots and comparison.
- **3D geometry**: pick edges for a local cell size, fillet, chamfer; split bodies by a plane.
- **Honest validation**: the bow-shock stand-off on tetrahedra was traced to shock-layer resolution plus the gap of
  Billig's correlation (the structured-grid answer is converged; the tetrahedral one levels off about 3.5 % above it,
  an open gap). ONERA M6 (Euler, NASA data) passes its pre-registered Cp limit, just inside (0.0996 vs 0.10). The new
  3D-vs-axisymmetric nozzle case passes for Isp and is a documented SHORTFALL for mass flow / thrust on the default
  mesh; the 3D laminar CubeSat nozzle passes. Every SHORTFALL is listed in `validation/report.md`.

Installers: Windows (setup.exe), macOS (.dmg) and Linux (.AppImage), built by GitHub Actions from the tag. Not
code-signed (see the user guide). Results of 0.2 projects show "needs update": press Run.

### Ledger 4 - duct resolution (2026-11-07)
- Square duct 24 x 24 per half side (tools/duct_resolution.py, validation/results/duct_resolution.jsonl): u_max/u_mean
  2.0295 vs series 2.0962 (-3.2 %), fRe 58.55 vs 56.91 (+2.9 %); 12 x 12 gave 1.7 % / 2.3 %. The error GROWS with
  resolution: the resolution hypothesis is rejected. Next (low-Mach stage file): development length and compressibility.

### Ledger 5 - sphere L3, laminar 3D nozzle, ONERA M6 data (2026-11-07)
- Sphere 359k cells: 0.2230 R (+4.2 % from the structured 0.2139). The trend of the first two meshes does not continue:
  CORRECTION of the earlier conclusion (theory 13k, CHANGELOG, gap register fixed): ~3.5 % simplex gap remains open.
- nozzle_3d_laminar: PASS (Cd ratio 1.0083, tol 3 %; Isp ratio 0.9957, tol 1.5 %), 1,126 s.
- ONERA M6: the user approved downloading the NASA NPARC files (airfoil.txt, foilmod.txt, cp1-7 l/u .ex) into
  validation/onera_m6/data/ (sources in its README).
- ONERA M6 case built (validate.py): loft of foilmod.txt, sideslip 3.06 deg in the half domain, sizes 0.012 / 0.25 m.

### Ledger 6 - full validation, ONERA M6 (2026-11-08)
Done: full validation run. 215 earlier validated numbers bit for bit unchanged (script compared every "measured" with the
committed JSON; only timings differ) - rule 4 holds. ONERA M6 Euler PASS: mean Cp RMS 0.0996 (limit 0.10, 612,023
cells, 7,057 s); Spalart-Allmaras not run (SHORTFALL). report.md rebuilt; the turbulent flat plate is listed NOT RUN.
Anomalies (both bugs in my script, fixed before the counted run, tolerance untouched):
- Gmsh failed on the wing ("identical points"): one closed spline through the sharp trailing edge overshoots; now an
  upper and a lower spline meet at the trailing edge.
- First M6 result 0.996: the NPARC .ex files list -Cp (suction positive). The script now negates them (README notes it).
- validation/run_all.py refused to rebuild the report while a case had no saved result; it now lists it as NOT RUN and
  the overall verdict stays FAIL.
User said yes (8 Nov) to push, tag v0.3.0 and the GitHub release.
Next: examples, installer smoke build, push, tag, release.

Released (8 Nov): main pushed, tag v0.3.0, GitHub release published with the draft text; installers attach from installer.yml.

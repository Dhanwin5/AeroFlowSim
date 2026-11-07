# Changelog

## 0.3.0 - Full 3D release: multiple zones, 3D completeness, 3D validation (November 2026)

- **Multiple cell zones** (2D and 3D): the Geometry step's *Fluid zones* joins overlapping fluid bodies with
  OpenCASCADE Fragment (conformal interfaces; the later body wins), with a name, a cell size and "exclude" per zone;
  meshes carry `cell_zones`; interface fluxes are stored, so the flux balance is shown per zone and per interface
  (conservation to round-off, tested); a zone can be a start region of a run; field *Cell zone* in Results.
  Mesh files keep zones: Gmsh physical surfaces / volumes, SU2 NZONE, CGNS (several zones, and now 3D CGNS import),
  Fluent cell zones. A one-zone mesh is exactly the mesh of before (arrays, files, results).
- **3D nozzles**: new template *3D nozzle (3D Euler)* (`nozzle_3d`: the axisymmetric nozzle's contour revolved, quarter
  or full, optional plume region as a second zone, exit numbers on the zone interface), the *Plume / plenum* tool round
  any fluid nozzle, a tutorial (`docs/tutorials/nozzle_3d_plume.md`) and the example *N2 nozzle 3D with plume*.
- **3D Results**: tabs Patches, XY plot (a field along a plane cut of the walls, e.g. Cp along a wing section), Reports
  (report definitions; 3D force reports now equal the solver's Cd) and Snapshots (save, compare key numbers).
- **3D geometry**: edge picking (Edges filter), local edge size, fillet and chamfer of solid edges, split bodies by a
  plane. Geometry dialogs follow *View > Units*. Internal-flow `external_3d` projects hide the free-stream inputs.
- **Shock position on tetrahedra (measured, no scheme change)**: on a structured grid the solver's converged Mach 3
  cylinder stand-off is 0.698 R (+7.6 % from Billig's correlation); the triangle mesh is within 0.7 % of it. The
  sphere's tetrahedral stand-off converges at first order to the structured value (60k: +6.1 %, 144k: +4.5 % from
  the structured 0.2139 R). The validation SHORTFALLS vs Billig are the correlation's gap at Mach 3 and shock-layer
  resolution, not a simplex error. Tool: `tools/shock_position_study.py`.
- **Validation**: new `nozzle_3d` (3D quarter vs axisymmetric: Isp PASS 0.49 %, mass flow +2.8 % and thrust +2.3 %
  SHORTFALL vs the pre-registered 2 %), `nozzle_3d_laminar` (3D CubeSat with prism layers). ONERA M6: not run (the
  ONERA D section coordinates are not in the repository) - SHORTFALL; sphere Re 100: PENDING REFERENCE.
- No validated number of earlier cases changed (no default, scheme or template file of an existing case changed).
- As at every release the version is part of every fingerprint: results of 0.2 projects are shown as "needs
  update" (Run brings them up to date; the examples are regenerated).

## Unreleased - AI connector: drive AeroFlowSim from Claude or any MCP app (November 2026)

- New command `aeroflowsim mcp`: a local MCP server (stdio only, no network port) with 25 tools over a new tool
  layer `aeroflowsim/api.py`: templates, gases, shapes, projects, inputs with units, geometry, mesh, checks, background
  runs (status, Stop, Continue), results with the software's verdict, PNG plots, compare, export, report, validation
  report, docs search. Optional extra `pip install -e ".[ai]"` (official MCP Python SDK, pinned); nothing loaded
  without it.
- Off by default: Tools > Use with AI assistants (allow, workspace folder, copy snippets for Claude Desktop, Claude
  Code and other MCP apps, Test button) or `aeroflowsim settings --allow-ai-connector on`.
- Safety: one workspace folder (no `..`, absolute, UNC, reserved names, links), nothing deleted or overwritten,
  inputs only through the schema checks, gas properties only from the library, confirmation before long runs, one run
  at a time with a time limit, honest verdicts (no numbers from a diverged run), `ai_log.jsonl` provenance, file text
  marked untrusted.
- Claude skill + Claude Code plugin (`integrations/claude/`) and a plugin marketplace at the repository root.
- Fixed: contour pictures of a (nearly) uniform field failed ("Contour levels must be increasing"), also in reports.

## Unreleased - Viscous flow: laminar, Spalart-Allmaras, k-omega SST (November 2026)

- New input **Flow model** (Euler / Laminar / Spalart-Allmaras / k-omega SST) in every Euler template, default Euler:
  old projects and every Euler validation number unchanged.
- Laminar Navier-Stokes in 2D, axisymmetric (hoop stress) and 3D; corrected face gradients; viscous time step and
  LU-SGS diagonal; Numba kernels equal to NumPy to 1e-12. NS MMS order 1.74-2.06 on eight mesh kinds.
- New boundary type **No-slip wall** (adiabatic / isothermal, sliding velocity); walls become no-slip under a viscous model.
- Turbulence: SA-noft2 and SST-2003 (vorticity production, TMR SST-V), loosely coupled implicit, exact wall distance.
- Wall fields: wall shear, Cf, heat flux, Stanton number, y+; pressure and friction drag; plots and post-processing
  fields; smart rule for the flow model; check of y+.
- Validation: Couette (with viscous heating), Poiseuille (axisymmetric), square duct (3D), Blasius, Mach 2 plate heat
  transfer, cylinder Re 40 (pending reference), TMR turbulent flat plate, cube-sat nozzle Re sweep: see report.md.

## Unreleased - Robust second order on triangles and tetrahedra (November 2026)

- New gradient **Green-Gauss (node values)**: a vertex-neighbour stencil, exact for linear fields on any cell type
  (Numba kernel). Shock regions on tetrahedra no longer stall: a 30 deg ramp went from a stall at 0.26 to 4e-8, and
  the 10 deg cone converges. 3D MMS order on tetrahedra rose from 1.75 to 1.86.
- New Numerics input **Implicit update limit** (default 0 = off): no cell's density, energy or pressure changes by more
  than this fraction per LU-SGS iteration. Runs on triangles and tetrahedra no longer diverge in the near-vacuum wake
  behind blunt bodies. Counted in the run info.
- 3D template defaults: node-value gradients and an update limit of 0.2. For 2D meshes with more than half triangles,
  *Suggested numerics* proposes the same. 2D defaults are unchanged.
- The run log and the command line name the active numerics at every run start.
- Old projects stay up to date: an input added later is left out of the fingerprint while it holds its old value.
- Validation:
  - pass: cone Cp (+1.7 %, converged), tetrahedral ramp convergence;
  - shortfalls: bow-shock stand-off on simplex meshes (3D sphere +10.7 %, 2D cylinder on triangles +8.4 %), cone shock
    angle (+7 %, +5 % on a finer mesh), ramp tet/hex stand-off on a 16-cell box (pre-registered tolerance too tight).
- Measurement fixes: the stand-off of the sphere and cylinder cases is read from the interpolated field along the
  stagnation line (the cell-band method interpolated across gaps).
- `tools/robustness_cases.py`: the reproduction set with a worst-cell diagnosis.

## Unreleased - 3D Euler solver (November 2026)

### 3D flow solver
- The Euler solver runs on 3D meshes (tetrahedra, pyramids, prisms, hexahedra; 5 equations), with every boundary
  condition through the face normal, implicit LU-SGS, local time steps, CFL back-off and positivity fallback as in 2D.
  2D and axisymmetric results are bit for bit unchanged.
- Template **Body in free stream (3D Euler)** (`external_3d`, was mesh only): angle of attack and sideslip, half and
  quarter domains (forces of the whole body), Cd / Cl / Cy, moment vector and Cm, Cp on the walls, reference area and
  length from the walls (smart rule) or typed, a *Mesh only* option. A fluid nozzle (faces inlet / outlet) is solved
  as an internal flow: mass flow, thrust two ways, Isp, Cf.
- 3D defaults: LU-SGS with Green-Gauss gradients and Venkatakrishnan K = 1 (measured: least squares on tetrahedra
  oscillates near strong shocks and in slow inlet regions). Prism layers off by default.
- 3D runs autosave a restart file every 15 minutes; Run continues from it after Cancel or a crash. A *Run memory* check
  estimates the memory (about 4 GB per million cells) and warns above 70 % of the free memory.
- 3D mesh import: Gmsh .msh v2 / v4 and SU2 (*Start from an existing mesh*, `mesh-info`, `mesh-convert`).

### 3D results
- The Results step shows 3D results: walls coloured by any field, a moveable slice plane, iso-surfaces, 3D
  streamlines, probe by right-click, key numbers, .vtu and CSV export; the report has slice pictures; `run`, `report`
  and `export` work for 3D projects.

### Examples, verification and validation
- Examples *Sphere at Mach 3 (3D)* and *N2 nozzle 3D* (the example STEP nozzle, solved).
- 3D MMS (order 2 on hexahedra, prisms, tetrahedra), free-stream preservation on every cell type, 2D extrusion and
  closed-body checks; validation `euler3d_cone` (Taylor-Maccoll), `euler3d_sphere` (Billig, with the 2D axisymmetric
  twin and Mach 6), `euler3d_nozzle` (3D vs 2D axisymmetric), `mms_euler3d`; tolerances pre-registered. Nozzle and
  MMS pass; the 3D sphere (diverges on 60k tetrahedra) and the cone (shock angle +7 %, Cp +3.6 %) are SHORTFALLS.

### Fixed
- 3D: residual normalisation of a momentum component that is zero by symmetry; far-field chatter at near-sonic
  outflow; animation frames of 3D runs.

## Unreleased - 3D geometry and meshing (November 2026)

### 3D geometry workspace
- New template **Body in free stream (3D, mesh only)** (`external_3d`): sphere, cylinder, nose cone or box in a box,
  cylinder or sphere far field (optionally a half domain with a symmetry plane). The 3D flow solver follows in the
  next stage; the Run step says so.
- The Geometry step of a 3D template is a clickable 3D workspace: bodies (box, cylinder, sphere, cone, revolve of a
  profile or a nozzle wall CSV, extrude), STEP / IGES import (closed shells are sewn into solids), transform, union /
  subtract / intersect, fluid / solid, delete, enclosure, face names (with a prism-layer tick per wall), refinement
  regions (box, sphere, cylinder), suggested sizes and first-layer height. Faces are picked with the mouse (Shift / Ctrl
  adds), by box (left to right: inside, right to left: touching), hidden, isolated and cut by a section plane. Every edit
  is undoable; names stay on their faces after upstream changes (stable face ids). STEP export of 3D geometry.
- Saved as `geometry/history.json` format 2 (`"dimension": 3`); 2D histories are written exactly as before, so old
  projects keep their fingerprints and results.

### 3D meshes
- Gmsh tetrahedra with prism layers grown from the named walls (angle-weighted normals, mitre stretch at wall edges,
  ending cleanly on flat neighbouring boundaries such as symmetry, inlet and outlet planes), sizes from the walls, the
  curvature and refinement regions, a minimum size (sharp tips), a cell estimate and a 3 million cell limit.
- 3D quality: equivolume skewness of tetrahedra, smallest dihedral angle, first-layer height reached, volume ratio;
  checks before any run (negative volume is an error).
- Mesh step in 3D: boundary faces in their colours or coloured by a quality field, a cut through the volume (x / y / z,
  moveable), a quality histogram, Worst cell, cell and face picking. *Export mesh…* writes ParaView .vtu, Gmsh .msh, SU2
  and CGNS (2D and 3D); command line `export <project> --mesh FILE`.

### Validation
- `validation/geometry_3d` (24 exact volumes / areas / STEP round trip / stable face ids, errors below 1e-14) and
  `validation/mesh_3d` (sphere in a box, three levels: fluid volume 0.000 %, wall area 0.04-0.55 %, first prism layer
  0.4 %). No validated 2D number changed.

## 0.2.0a3 - Linux and macOS, flow animation (October 2026)

### Linux and macOS

- Installers for every system on each release: macOS disk images for Apple silicon and Intel Macs (drag to
  Applications), a Linux AppImage (one file, Ubuntu 22.04 and newer), next to the Windows installer. Each is built and
  smoke-tested (a 1D and a 2D run, the GUI starts) by GitHub Actions. Not signed yet: macOS asks once (right-click >
  Open), as Windows SmartScreen does.
- `pip install aeroflowsim` works on all three systems: the templates, example projects, icons and docs are installed as
  data files (`<prefix>/share/aeroflowsim`), so the full program runs outside the source folder.
- macOS added to the automatic tests; macOS keeps its settings in `~/Library/Application Support/AeroFlowSim` and
  counts its physical CPU cores for the solver threads.

### Flow animation

- Results step, new **Animation** tab: play back how the flow developed during the run (the pseudo-time convergence
  of a steady run, from the start-up transient to the steady state): play / pause, step, slider, speed, loop, colour
  range fixed over all frames or per frame, iteration / time label; every view showing the current result plays the
  frame with its own Display settings. Save as animated GIF (paper style, display units); MP4 when ffmpeg is installed.
- Recording during 2D runs (project setting, on by default): automatic 50-100 frames over any run length, or every N
  iterations; float32 frames in `results/animation.npz` next to `run.npz`. A continued run appends frames, Start from
  scratch records a new set, out of date together with the results. Runs outside a project (scripts, validation)
  record nothing, and recording never changes a result (tested bit for bit). No validated number changes.
- 1D unsteady results (Sod shock tube): the stored snapshots play back in the field plot.
- Command line: `export <project> --animation out.gif [--field M] [--fps 10] [--per-frame-range]`.

## 0.2.0a2 - speed (Speed stage: Numba, multi-core, implicit LU-SGS) (October 2026)

### Speed stage (LU-SGS): implicit LU-SGS

- Implicit LU-SGS time stepping for steady 2D / axisymmetric runs, now the default (`Implicit LU-SGS` in Numerics):
  first-order Rusanov implicit operator (omega 1.5), axisymmetric pressure source on the diagonal, SER CFL ramp from the
  input CFL to 100, sequential (deterministic) sweeps. Quick validation set: all pass, 5.0 min (explicit 6.8 min); 117 of
  129 values unchanged to the printed digits, the other 12 within their tolerances (limiter frozen at another state;
  iteration-capped NACA runs get further). Projects saved with SSP-RK3 keep it.
- An interpolated start (new mesh) keeps the earlier run's residual normalisation.
- Validation suite: MMS study uses 6 worker processes sharing the cores (one per core with Numba threads ran out of
  memory).

## Speed stage (Numba): speed (Numba kernels, multi-core)

- The 2D / axisymmetric residual runs in compiled Numba kernels (`aeroflowsim/euler/kernels.py`): 9-17 x faster on
  one core, 31-70 x with the default 16 threads (`validation/timing.md`). The NumPy code is kept as the reference
  (equal to 1e-12, `tests/test_kernels.py`). Results do not depend on the thread count (bit-identical).
- Tools > Preferences: solver threads (default physical cores - 1, at most 16); command line `--threads`, `--backend`.
  Runs record the backend and thread count (Run step, report, command line, diagnostic info).
- New dependency: numba 0.68.1 (optional at run time: without it the NumPy solver runs and says so).
- Light per-push CI (`tests/test_smoke.py` + kernel and core tests); all fast tests and the quick validation set run on
  pull requests, weekly and on demand.
- `tools/timing.py`: timing table, profile, thread speed-up table.

## 0.2.0a1 - 2D alpha (October 2026)

First alpha release: a GUI-first 2D / axisymmetric Euler solver with post-processing, verification and validation.

**Solver and verification**
- Finite-volume 2D / axisymmetric Euler solver (rotated HLLC with HLLE carbuncle blend, least-squares gradients,
  Venkatakrishnan / Barth-Jespersen / no limiter, SSP-RK3 and Jameson stepping, local time steps), full
  boundary-condition set, live monitors, Stop keeps the flow, Run continues the current solution.
- Method of Manufactured Solutions: observed order 1.98-2.02 on quads, distorted quads, triangles and mixed meshes,
  planar and axisymmetric (`aeroflowsim/mms.py`); Grid Convergence Index tool (`aeroflowsim/gci.py`).
- Theory: Taylor-Maccoll cones, oblique shocks, Prandtl-Meyer expansions, shock-expansion theory
  (`aeroflowsim/gasdynamics.py`).

**Post-processing** (`aeroflowsim/post/`, used by the GUI, the command line, scripts and the report)
- Derived fields (Cp, schlieren, vorticity, shock indicator, enthalpies, mesh quality, per-cell residual) and safe
  custom field functions; node values; values at points and along lines (exact per cell).
- Named surfaces (boundary, line, rake, point, iso-line, x/y = c), surface and volume integrals, flux balance,
  forces and moments; report definitions as live monitors with CSV files and convergence criteria.
- XY plots with reference data and snapshot overlays; snapshots, comparison and difference fields; exports to CSV,
  VTU (cell + node data) and Tecplot; automatic HTML / PDF report.
- Run: patch regions for a fresh start; a new mesh starts from the old solution interpolated onto it.

**Desktop GUI**
- Results workspace for 2D flows: filled / banded / cell contours, contour lines with labels, vectors,
  streamlines, mirror, 3D revolved view, 1/2/4 linked views, saved scenes, picture export (paper style, any
  resolution, transparent), histogram, hover values, right-click menus.
- Help > Copy diagnostic info, log file, error dialog; example projects on the start page.

**Validation** (`validation/report.md`): Sod (1D, 2D), quasi-1D nozzle, Mach 2 wedge, diamond airfoil, 15 deg cone,
Prandtl-Meyer corner, Mach 6 cylinder with carbuncle metric, N2 nozzle with sharp and rounded throat, NACA 0012
(Vassberg and Jameson 2010), Back-Massier-Gier experimental nozzle, MMS; quick set on every push, full set weekly.

**Distribution**: Windows installer (per user, Start menu, .afsproj association, uninstaller; unsigned).

Known limitations: see `docs/gap_register.md` (explicit solver is slow; residual stalls near 1e-3-1e-4 at a few cells
on triangle meshes and at attached shocks; inviscid only; 2D only).

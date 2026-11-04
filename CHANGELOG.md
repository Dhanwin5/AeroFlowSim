# Changelog

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
  twin and Mach 6), `euler3d_nozzle` (3D vs 2D axisymmetric), `mms_euler3d`; tolerances pre-registered.

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

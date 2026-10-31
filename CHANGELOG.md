# Changelog

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

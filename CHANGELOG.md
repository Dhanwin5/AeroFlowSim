# Changelog

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

# AeroFlowSim 0.2.0a1 - 2D alpha (pre-release)

A GUI-first, open-source CFD solver for nozzle and propulsion aerodynamics, with built-in validity checks and
published validation. This is the first alpha: 2D planar and axisymmetric, inviscid.

## What works
- 2D / axisymmetric finite-volume Euler solver (HLLC with carbuncle fix, second order), full boundary-condition set,
  live monitors, Stop / Continue / Start from scratch.
- Verified second order by the Method of Manufactured Solutions on quads, distorted quads, triangles and mixed meshes,
  planar and axisymmetric (observed L2 order 1.98-2.08).
- Validation (validation/report.md): 15 of 15 cases pass - Sod, quasi-1D nozzle, Mach 2 wedge, diamond airfoil
  (shock-expansion theory), 15 deg cone (Taylor-Maccoll), Prandtl-Meyer corner, Mach 6 cylinder (stand-off and
  carbuncle metric), N2 nozzle (sharp and rounded throat), NACA 0012 (Vassberg and Jameson 2010), Back-Massier-Gier
  measured wall pressures, MMS. Two explained shortfalls are listed openly in the report.
- Desktop GUI with a CAD-like geometry workspace and a Fluent-level results workspace: contours, lines, vectors,
  streamlines, mirror and 3D revolved views, linked views, surfaces, integrals, flux balance, forces, report
  definitions as live monitors, XY plots with reference data, snapshots and differences, custom fields, exports
  (CSV, VTU, Tecplot), automatic HTML / PDF report.
- Command line and scripting with the same engine (run, report, export, snapshot).

## Install
Run `AeroFlowSim-0.2.0a1-setup.exe` (per user, no administrator rights). It is not code-signed: Windows SmartScreen
may warn; choose "More info" > "Run anyway". Example projects are on the start page. User guide: docs/user_guide.md.

## Known limitations (docs/gap_register.md)
- Inviscid and 2D only; calorically perfect gas.
- Explicit solver: slow (minutes for the default nozzle); a few cases stall near a residual of 1e-3-1e-4 in a few cells
  while forces have settled. Speed (Numba, implicit LU-SGS) is the next step (Prompt 8).
- Venkatakrishnan's limiter loses order on smooth flows on fine meshes.
- The NACA 0012 mesh study is not yet a systematic refinement (Cl 4 % low; explained shortfall).

## Reporting problems
Open an issue with the bug-report template and paste Help > Copy diagnostic info (no personal data).

## Licence note
AeroFlowSim is GPL-3.0-or-later and bundles Gmsh (GPL), Qt / PySide6 (LGPL), VTK (BSD) and others
(THIRD_PARTY_LICENSES.txt). Before this installer is shared with anyone, the repository must be public or the source
code attached to the release.

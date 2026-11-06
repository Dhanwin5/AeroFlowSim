# Low-Mach preconditioning - accurate and fast steady flows at any Mach number (2D, axisymmetric, 3D)

**Model: Opus** (changes the eigenstructure of the equations: preconditioned flux dissipation, time steps and the
implicit operator; subtle accuracy and stability questions).

Paste everything below the line into ONE new Claude Code session. It covers the whole stage in one go.

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder `C:\Projects\CFD software`, GitHub `Dhanwin5/AeroFlowSim`). I am a beginner
programmer who knows aerospace engineering and CFD theory. This is the ONLY prompt for the whole low-Mach
preconditioning stage: do all parts below in order, in this one session, without waiting for me between parts.

1. Start: read `CLAUDE.md`, `docs/gap_register.md`, this file (create the ledger at the bottom), the ledger of
   `docs/roadmap/3d_euler_solver.md`, `docs/theory_manual.md` sections 12, 13b-13d and 13h, and skim
   `aeroflowsim/euler/` (all), `aeroflowsim/compute.py`, `aeroflowsim/mms.py`. Write a short plan in plain words, then
   start at once.
2. Do not stop to ask questions. Decide the way Fluent, SU2 or CFL3D would and give one sentence of why in the summary.
   Stop only before: deleting files you did not create in this session, adding a dependency, or anything outward-facing
   apart from the push at the end.
3. Ledger = your memory: after every part commit, then add a ledger entry (done, how verified, next, anomalies). If the
   conversation is compacted, re-read the ledger and carry on.
4. Long jobs (validation, 3D runs) in the background, ONE heavy job at a time (32 GB machine; about 4 GB per million 3D
   cells, measured).
5. Pre-register every validation tolerance in its reference.toml BEFORE the run; never retune; a miss is a SHORTFALL.
6. Rule 4 of CLAUDE.md: preconditioning is OFF by default for supersonic templates, so every number in
   `validation/report.md` must stay bit for bit; say so with evidence. Any change you make on purpose: explain it.
7. Walk through my next actions for every feature (switch preconditioning on in an old project, Stop / continue, change
   the Mach number from 0.05 to 2, re-mesh, reopen, command line) and write them into tests.

## Context (state after the 3D Euler solver stage)

* One finite-volume solver for 2D, axisymmetric and 3D (`aeroflowsim/euler/`): rotated HLLC + HLLE blend at strong
  compressions, least-squares or Green-Gauss gradients, Venkatakrishnan / Barth limiters, implicit LU-SGS (first-order
  Rusanov operator, omega = 1.5, SER CFL ramp to 100) by default, SSP-RK3 / Jameson explicit, Numba kernels (GPU-ready
  rule), MMS order 2 in 2D and 3D, validation in report.md (2D and 3D cases).
* At low Mach numbers the Euler equations are stiff (acoustic speed >> flow speed) and the upwind dissipation of HLLC
  scales with c instead of |u|: wrong pressure fields (pressure fluctuations O(M) instead of O(M^2)) and slow
  convergence. Nozzle plenums (inlet Mach 0.02-0.05) and every subsonic external flow suffer.
* Findings of the 3D Euler stage that belong here:
  - The STEP N2 nozzle's slow inlet plenum on tetrahedra: with least-squares gradients the inlet mass flow oscillated
    by 25 % (Green-Gauss cured it); a preconditioned dissipation must be checked in exactly that region.
  - 3D defaults are LU-SGS + Green-Gauss + Venkatakrishnan K = 1 (template solver_defaults of external_3d); 2D defaults
    are least squares + K = 5. On 2D Gmsh triangles the Mach 3 cylinder diverges with the 2D defaults (gap); try
    Green-Gauss there too (with a re-validation of the 2D numbers, rule 4).
  - Far field: 3D blends the Riemann and the extrapolation branches over normal Mach 0.9-1.1 (2D keeps the sharp
    switch). A preconditioned far field needs its own characteristic treatment (Turkel; Darmofal & Siu).
  - Residual normalisation: 3D floors each momentum norm at 1e-3 of the largest.
  - LU-SGS stays the default; its implicit operator must use the preconditioned spectral radius.
  - The robust-second-order stage (docs/roadmap/robust_second_order.md) found and fixed the simplex-mesh problem of
    the 3D stage: the gradient stencil (now "Green-Gauss (node values)", vertex neighbours, MMS tet order 1.86) and
    large implicit updates in near-vacuum expansions (per-cell update limit, Numerics.update_limit). Keep both working
    with the preconditioned operator: the update limit must act on the preconditioned update, and the node-value
    gradient is the recommended gradient for preconditioned runs on triangles / tetrahedra.
  - Inviscid blunt-body wakes on unstructured meshes do not settle to round-off (residual ~1e-4 in about 1 % of the
    cells) while the forces do; at low Mach the wake is subsonic everywhere - check whether preconditioning makes it
    steady (a likely side benefit), and judge low-Mach validation cases by residual AND monitors.
  - New solver inputs must be listed in aeroflowsim/parameters.py FINGERPRINT_NEUTRAL at their old value.

## Decisions (made: follow them)

* Weiss & Smith (1995) preconditioning (as Fluent's density-based solver): preconditioning matrix Gamma in primitive
  variables (p, u, T), reference velocity U_r = min(c, max(|u|, K_r u_inf, eps)), with a pressure-gradient term
  (Venkateswaran & Merkle) for stagnation regions. Applied to: the HLLC/Roe dissipation (preconditioned wave speeds),
  the local time steps (preconditioned spectral radius), the LU-SGS operator (preconditioned spectral radius on the
  diagonal), the far-field and inlet / outlet characteristics.
* Steady flows only (dual time stepping for unsteady flows is its own stage).
* A Numerics input "Low-Mach preconditioning": Off / Automatic (on when the free-stream or inlet Mach number is below
  0.3) / On. Default Automatic for new projects; old projects keep Off (their inputs have no value: the default for a
  missing value must be Off, so fingerprints and results stay).
* Every kernel stays a pure function of flat arrays (GPU-ready rule); NumPy reference = Numba to 1e-12.

## Parts (in this order)

1. Theory and the preconditioned flux: Gamma, its eigenvalues, the preconditioned HLLC (or Roe-Turkel) dissipation,
   time steps; 1D / 2D / 3D unit tests: eigenvalues -> (u, u' +- c') ; reduces to the unpreconditioned flux for M >= 1.
2. Implicit LU-SGS with the preconditioned operator; boundary conditions (far field, total-pressure inlet, pressure
   outlet) consistent with the preconditioned characteristics.
3. Verification: MMS at low Mach (u_0 = 3 m/s: order 2, errors independent of M), free stream and gas at rest, M -> 0
   pressure scaling (fluctuations O(M^2)) on a cylinder.
4. Validation (pre-registered): inviscid cylinder at M = 0.01 / 0.1 (Cp vs potential flow 1 - 4 sin^2 theta, within 2 %;
   no entropy rise), NACA 0012 at M = 0.15 alpha 0 / 5 (Cl vs thin-airfoil / panel), the N2 nozzle plenum (same Cd as
   now within 0.2 %, faster convergence), a 3D sphere at M = 0.1 (Cp at the stagnation point 1.0025).
5. GUI and docs: the Numerics input, a smart rule that suggests it, the run log says when it is active; user guide,
   theory manual section, gap register, CHANGELOG, the plan of the next stage (adaptive mesh refinement) in this style.

## Quality gates

* Tests pass; NumPy = Numba to 1e-12; results independent of the thread count; MMS order 2 at low Mach.
* 2D validation numbers unchanged (preconditioning off) - with evidence; no Qt in solver modules; privacy test passes.
* Iterations and wall-clock time of the new cases in validation/timing.md (rule 14).

## Done when

1. A M = 0.05 cylinder / airfoil / sphere converges to the incompressible Cp within the tolerances, in fewer
   iterations than without preconditioning (numbers in the report).
2. Supersonic results are bit for bit unchanged; old projects open unchanged.
3. Docs, gap register, CHANGELOG, ledger and the next stage's plan written; pushed.

## Findings of the viscous-flow stage (5 Nov 2026) - part of this stage

* The viscous solver (laminar, SA, SST) exists now (`euler/viscous.py`, `euler/turbulence.py`; ledger of
  `docs/roadmap/laminar_viscous.md`). Its viscous spectral radius is kept SEPARATE from the convective dissipation in the
  time step (`EulerSolver.time_steps`) and the LU-SGS diagonal (`lusgs(..., lam_visc)`), so the preconditioner scales
  only the convective part. Preconditioning must cover the viscous terms' time-step limit (Weiss & Smith 1995: the
  viscous Von Neumann number with the preconditioned eigenvalues).
* Measured stiffness: LU-SGS's Rusanov diagonal (|u| + c) makes the effective pseudo-time step acoustic, independent of
  the CFL number. Plane Couette at 1 atm (H = 1 mm, M 0.2) does not converge in 40k iterations; at 1 kPa it converges in
  15.7k. The laminar validation cases were therefore run at low pressure (Couette 1 kPa, tube 5 kPa, duct 5 kPa, cylinder
  Re 40 at 0.9 Pa with D = 1 m). RE-RUN after preconditioning at 1 atm and at M = 0.01-0.05 (addendum 2 of the viscous
  stage): validation/viscous_couette, viscous_poiseuille, viscous_square_duct, viscous_blasius, viscous_cylinder_re40;
  report iterations and wall-clock time against the ones in validation/report.md.
* Square duct SHORTFALL (2.3 % / 1.7 %, 12 cells per half side): re-run on a 24 x 24 section once the cost allows.
* TMR flat plate SHORTFALL: even the 136 x 96 / 272 x 192 SA + SST runs hit the 2.5 h limit with no result (only
  evidence: coarse 60 x 48 SA, Cf 1.3 % off). Re-run validation/turbulent_flat_plate with preconditioning FIRST.
* TMR flat plate: the 544 x 384 grid was not run (~20 h at 3.5 us per cell-iteration); measure it with preconditioning
  plus the line-implicit option if needed (addendum 7 of the viscous stage: high-aspect-ratio cells).
* Not built in the viscous stage, still open: sphere at Re 100 in 3D, NACA 0012 at Re 6e6 (SA, SST) and its 3D extrusion,
  the 3D quarter cube-sat nozzle with prism layers (2D vs 3D within 2 %), ONERA M6; and the references of Coutanceau &
  Bouard / Dennis & Chang / Johnson & Patel (attach the PDFs). See the gap register.

## Ledger (progress log)


# Viscous flow, 2D and 3D - laminar Navier-Stokes and RANS turbulence (Spalart-Allmaras, k-omega SST)

**Model: Opus** (new numerics: viscous fluxes from face gradients, turbulence-model source terms and their implicit
treatment, wall boundary conditions and wall distance, MMS verification; many design decisions). This is a LARGE stage:
work strictly part by part, ledger after each, and use the "Out of room" rule only at the end of a part.

Paste everything below the line into ONE new Claude Code session. It covers the whole stage in one go.

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder C:\Projects\CFD software, GitHub Dhanwin5/AeroFlowSim, repository PUBLIC). I
am a beginner programmer who knows aerospace engineering and CFD theory. This is the ONLY prompt for this stage: do all
parts below in order, in this one session, without waiting for me between parts. 2D, axisymmetric AND 3D are all in
scope now; nothing of this stage is to be moved to a later stage.

1. Start: read CLAUDE.md, docs/gap_register.md, this file (create the ledger at the bottom), the ledgers of
   docs/roadmap/robust_second_order.md and 3d_euler_solver.md, docs/theory_manual.md sections 11 (gas library: mu, k,
   Pr), 12, 13b-13d, 13h, 13i, docs/developer_guide.md, and skim aeroflowsim/euler/ (all), aeroflowsim/gases/,
   aeroflowsim/smart_rules.py (first_layer_height), aeroflowsim/prism_layers.py, aeroflowsim/inflation_layers.py,
   aeroflowsim/mms.py, aeroflowsim/post/, cases/nozzle_axi, cases/external_2d, cases/external_3d, validation/. Write a
   short plan in plain words, then start at once.
2. Do not stop to ask questions. Decide the way Fluent, SU2, CFL3D or OpenFOAM would; one sentence of why in the summary.
   Stop only before: deleting files you did not create in this session, adding a dependency, or anything outward-facing
   apart from the push at the end.
3. Ledger = your memory: after every part commit, then add a ledger entry (done, how verified, next, anomalies). If the
   conversation is compacted, re-read the ledger and carry on. Do not stop between parts to report to me.
4. Out of room? Only if you truly cannot continue: stop at the END of a part, commit, write the ledger entry, say which
   part is next.
5. Long jobs in the background, ONE heavy job at a time (32 GB machine; about 4 GB per million 3D cells; RANS adds 1-2
   equations). Report result lines only.
6. Never tune a number to pass. Pre-register every validation tolerance in its reference.toml BEFORE the run; a miss is
   a SHORTFALL with its cause. A diverged run scores no value. Shock / profile positions from the interpolated field.
7. Rule 4 of CLAUDE.md: the viscous terms are OFF unless the user chooses a viscous Flow model, so every Euler number in
   validation/report.md stays bit for bit - show it. Old projects (no Flow model value) mean Euler; every new input is
   listed in aeroflowsim/parameters.py FINGERPRINT_NEUTRAL at its old-behaviour value.
8. Walk through my next actions for every feature (switch an old project to Laminar / SA / SST, change the wall from
   adiabatic to isothermal, re-mesh with prism layers for y+ = 1, Stop / continue, reopen, command line, 3D the same) and
   write them into tests. Never write unquoted shell heredocs (the shell runs backticks inside them).

## Context (state after the robust-second-order stage)

* One finite-volume solver for 2D, axisymmetric and 3D (aeroflowsim/euler/): HLLC + HLLE blend, gradients least squares /
  Green-Gauss / Green-Gauss with NODE values (vertex stencil, exact for linear fields, Numba CSR kernel `gradients_csr`),
  Venkatakrishnan / Barth limiters, implicit LU-SGS (first-order Rusanov operator, SER CFL ramp) with the per-cell update
  limit (`Numerics.update_limit`), SSP-RK3; MMS order 2 (2D 1.98-2.02; 3D hexa 1.93, prisms 1.82, tetra 1.86).
  NumPy = Numba to 1e-12, thread independent, GPU-ready rule for every kernel.
* Defaults: 2D least squares, K 5, no update limit; 3D (external_3d) node gradients, K 1, update limit 0.2. A smart rule
  suggests the 3D numerics for 2D triangle meshes; the run log prints the active numerics.
* Gas library: every gas has mu(T) (Sutherland or power law), k(T), Pr with sources (GasModel.mu / k / Pr).
* Meshes: structured nozzle mesh with inflation layers (exact first layer), Gmsh triangles / quad-dominant with inflation
  layers, C/O-grids, 3D tetrahedra + prism layers (`prism_layers.py`), smart rule `first_layer_height` for a target y+.
* Open items that belong here: the inviscid blunt-body wake on unstructured meshes never settles (residual ~1e-4) - with
  viscosity it must become a steady recirculation (Re = 40 cylinder converges to 1e-6); bow-shock stand-off on simplex
  meshes 8-11 % too large and the cone angle +5-7 % (resolution; P1 in the gap register: re-check them with viscous
  prism-layer meshes where relevant, do not hide them).

## Decisions (made: follow them)

* Laminar Navier-Stokes: viscous flux F_v = [0, tau . n, (tau . u + k grad T) . n], Stokes hypothesis; face gradients =
  mean of the two cell gradients + a correction along the cell-to-cell vector (OpenFOAM / Fluent "corrected" face
  gradient); mu, k from the GasModel at the face temperature; turbulent mu_t and k_t = cp mu_t / Pr_t (Pr_t = 0.9) added.
* Axisymmetric: hoop-stress source terms in the well-balanced form of section 12; 3D: the same flux, no extra terms.
* Turbulence: Spalart-Allmaras (SA-noft2, the standard of the NASA Turbulence Modeling Resource, TMR) and Menter's k-omega
  SST (2003), solved with the mean flow (one extra equation for SA, two for SST), first-order upwind convection,
  sources implicit on the diagonal (production explicit, destruction implicit), positivity of nu_tilde, k, omega kept.
  Wall distance from the walls by an exact nearest-wall-face search (KD-tree on wall face centres, then the exact
  distance to the triangle / edge), computed once per mesh and stored.
* Walls: no-slip adiabatic or isothermal (T_wall); slip wall stays; turbulence wall values (nu_tilde = 0; k = 0,
  omega = 60 nu / (beta1 y1^2) * 10 (Menter)). Far field / inlet: turbulence intensity and viscosity ratio inputs
  (TMR free-stream values by default). Low-Re treatment only (y+ ~ 1, no wall functions) - say so in the GUI.
* Implicit: viscous spectral radius in the time step and the LU-SGS diagonal; turbulence equations in the same LU-SGS
  sweep (block diagonal or loosely coupled, decide and record why).
* Inputs: Flow model (Euler / Laminar / Spalart-Allmaras / k-omega SST), default Euler (old projects unchanged); wall
  thermal condition; free-stream turbulence. Templates nozzle_axi, external_2d, external_3d, imported_mesh get them.
* Post-processing: wall shear stress, Cf, q_w, Stanton number, y+ (fields on the walls, XY plots, report), mu_t / mu,
  friction and pressure drag separately. Smart rules: Flow model from Re (laminar below ~1e5 for nozzles / bodies,
  turbulent above), first-layer height for y+ = 1, a warning when y+ of the first cell exceeds 2 after a run.
* Preconditioning-compatible: keep the dissipation and time-step terms separate so the low-Mach stage can scale them.

## Parts (all in this session, in this order)

1. Theory and the laminar viscous flux (2D, axisymmetric, 3D): face gradients, tau, heat flux, viscous time step and
   LU-SGS diagonal; Numba kernels = NumPy 1e-12; MMS for Navier-Stokes (existing manufactured solutions + viscous source
   terms) on quads, triangles, axisymmetric, hexahedra, prisms, tetrahedra: order 2 within the Euler MMS tolerances.
2. Walls and boundary conditions: no-slip adiabatic / isothermal (ghost states for the inviscid part, wall gradients for
   the viscous part), symmetry and axis with viscous terms, far field / inlet / outlet; wall distance (2D and 3D, tested
   against exact distances to a cylinder, sphere and flat plate).
3. Turbulence models: SA and SST with their source terms, wall and free-stream conditions, Numba kernels; verification:
   MMS for the turbulence equations (TMR MMS cases where available), the TMR 2D zero-pressure-gradient flat plate (grid
   series, Cf at Re_x = 5e6 vs TMR reference within 1 %).
4. Forces, heat flux and post-processing (2D and 3D): wall fields, friction / pressure drag, Cf, q_w, St, y+, report and
   CSV / VTU export; smart rules.
5. Validation (pre-registered before each run, background, one job at a time), 2D AND 3D:
   - Couette flow (shear within 0.5 %), Poiseuille in a tube (axisymmetric, profile and pressure drop within 1 %),
     laminar flow in a square duct in 3D (exact series solution: centre velocity and friction factor within 1 %),
   - Blasius flat plate (Cf at Re_x 1e4-1e5 within 3 %, delta_99 within 5 %) in 2D, and its one-layer 3D extrusion equal
     to 2D,
   - cylinder at Re = 40 (recirculation length L/D within 5 % of Coutanceau & Bouard / Dennis & Chang, Cd within 5 %,
     residual 1e-6), sphere at Re = 100 in 3D (recirculation length and Cd within 5 % of Johnson & Patel 1999),
   - turbulent flat plate (TMR, SA and SST: Cf within 1 % of the TMR reference on the finest grid),
   - NACA 0012 at Re = 6e6, alpha 0 / 10 deg (TMR, SA and SST: Cl, Cd within 2 %; a 3D one-span extrusion equal to 2D),
   - the N2 cube-sat nozzle: ESTIMATE the throat Reynolds number first (record it), choose laminar or turbulent by it,
     then Cd and the Isp loss versus Reynolds number (p0 over a decade) against published micro-nozzle data or a
     boundary-layer estimate; 2D axisymmetric and the 3D quarter nozzle (with prism layers) within 2 % of each other.
   Iterations, wall-clock time and memory in validation/timing.md; quick and full sets.
6. GUI and docs: Flow model, wall and turbulence inputs, the wall fields in the Results step (2D and 3D), smart rules,
   the run log; user guide (choosing a model, meshing for y+ = 1), theory manual sections, developer guide, gap register,
   CHANGELOG, docs/roadmap/README.md, examples (a laminar and a turbulent case), screenshots light / dark, the plan of
   the next stage (low-Mach preconditioning: update docs/roadmap/low_mach_preconditioning.md with everything found here)
   in this style. Full fast and GUI tests, quick and full validation, push.

## Quality gates

* Tests pass; NumPy = Numba to 1e-12; thread independent; MMS order 2 for Navier-Stokes in 2D and 3D; turbulence MMS
  order as expected for first-order turbulence convection (state it before measuring).
* Every Euler validation number unchanged (Flow model Euler), shown with the 2D-row diff of report.md.
* No Qt in solver / post / logic modules; privacy test passes. No tag, release or repository-settings change.

## Done when (check every line with evidence)

1. Laminar and turbulent (SA, SST) runs work in 2D, axisymmetric and 3D, from the GUI and the command line.
2. The validation list above passes, or each miss is a documented SHORTFALL with its cause.
3. The cube-sat nozzle's throat Reynolds number, Cd and Isp loss versus Re are in the report (2D and 3D).
4. Old projects and every Euler number unchanged; docs, gap register, CHANGELOG, roadmap README, the next plan and the
   ledger written; pushed.

## Ledger (progress log)


### Ledger entry 1 (5 Nov 2026): Part 1 - laminar viscous flux, MMS (+ first pieces of Part 2)
* Done: `aeroflowsim/euler/viscous.py` (corrected face gradients, Stokes stress, heat flux, axisymmetric hoop stress,
  viscous spectral radius); Numba kernels `viscous_face_gradients`, `viscous_face_fluxes` (kernels.py); EulerSolver
  takes `viscous=ViscousSettings(...)` (None = the old Euler path, no viscous code runs); viscous dt
  (dt = CFL V / (Lambda_c + sum lambda_v A)) and the viscous spectral radius on the LU-SGS diagonal / sweeps
  (`lusgs(..., lam_visc)`: Euler passes zeros, so lam + 0.0 is bit-identical). No-slip wall BC type `no_slip_wall`
  (adiabatic / isothermal, sliding velocity u_wall; acts as a slip wall under Euler); Flow-model inputs in
  setup.solver_parameters (FINGERPRINT_NEUTRAL at Euler); exact wall distance `aeroflowsim/wall_distance.py`.
* Decision: boundary faces use the SECOND-ORDER one-sided face gradient (g.d = 2 (phi_f - phi_P) - g_P.d). With the
  first-order one-sided form (OpenFOAM/Fluent snGrad) the NS MMS order on quads was 1.72 (below the pre-registered 1.8);
  with it 1.86. Exact for linear profiles (Couette) either way.
* Verified: tests/test_viscous.py (Numba = NumPy 1e-12 on quads, triangles, axisymmetric, hexa, prisms, tetra, with
  and without mu_t; thread independence; exact stress for linear fields; Euler path untouched), tests/test_wall_distance.py
  (flat plate 2D/3D exact, cylinder, sphere, KD-tree = brute force). validation/mms_navier_stokes (pre-registered,
  Euler-MMS tolerances): ALL PASS - quads 1.86, distorted 1.83, triangles 2.02, axi quads 2.06, axi triangles 1.95,
  hexa 1.94, prisms 1.78, tetra 1.74. Euler kernel + LU-SGS tests pass (79). report.md: only the new section added.
* Anomaly / finding for the low-Mach stage: plane Couette at 1 atm (H = 1 mm, M 0.2) converges extremely slowly with
  LU-SGS: the Rusanov diagonal (|u| + c) makes the effective pseudo-time step acoustic, independent of the CFL number,
  and the diffusion time H^2/nu is ~1e5-1e6 acoustic cell times. At 1 kPa (acoustic Reynolds number 100 x smaller) it
  converges in 15.7k iterations, u exact to 2e-9, T within 0.03 %. Validation cases will be pre-registered at a
  pressure where the stiffness ratio allows convergence (stated per case); re-run at 1 atm after preconditioning.
* Order decision (addendum 1): Parts 4 and the laminar cases of Part 5 come BEFORE Part 3 (turbulence), so a cut-off
  still leaves a finished laminar solver.
* Next: Part 2 rest (setup wiring tests, walk-through tests), Part 4 (wall fields), Part 5 laminar validations.

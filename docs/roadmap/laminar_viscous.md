# Laminar viscous flow, 2D and axisymmetric - the laminar Navier-Stokes equations, no-slip walls, skin friction, heat flux

**Model: Opus** (new numerics: viscous fluxes from face gradients, their implicit treatment, wall boundary conditions,
verification by MMS; and the cube-sat nozzle question of viscous losses).

Paste everything below the line into ONE new Claude Code session. It covers the whole stage in one go.

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder C:\Projects\CFD software, GitHub Dhanwin5/AeroFlowSim, repository PUBLIC). I
am a beginner programmer who knows aerospace engineering and CFD theory. This is the ONLY prompt for this stage: do all
parts below in order, in this one session, without waiting for me between parts.

1. Start: read CLAUDE.md, docs/gap_register.md, the ledgers of docs/roadmap/robust_second_order.md and
   3d_euler_solver.md, docs/theory_manual.md sections 11 (gas library: mu, k, Pr), 12, 13b-13d, 13h, 13i, and skim
   aeroflowsim/euler/ (all), aeroflowsim/gases/, aeroflowsim/smart_rules.py (first-layer height), aeroflowsim/mms.py,
   cases/nozzle_axi, cases/external_2d, validation/. Write a short plan in plain words, then start at once.
2. Do not stop to ask questions. Decide the way Fluent, SU2 or CFL3D would; give one sentence of why in the summary.
   Stop only before: deleting files you did not create in this session, adding a dependency, or anything outward-facing
   apart from the push at the end.
3. Ledger = your memory: after every part commit, then add a ledger entry (done, how verified, next, anomalies). If the
   conversation is compacted, re-read the ledger and carry on. Do not stop between parts to report to me.
4. Out of room? Only if you truly cannot continue: stop at the END of a part, commit, write the ledger entry, say which
   part is next.
5. Long jobs in the background, ONE heavy job at a time (32 GB machine). Report result lines only.
6. Never tune a number to pass. Pre-register every validation tolerance in its reference.toml BEFORE the run; a miss is
   a SHORTFALL with its cause.
7. Rule 4 of CLAUDE.md: the viscous terms are OFF unless the user chooses "Laminar" (Flow model input), so every Euler
   number in validation/report.md stays bit for bit - show it. Old projects (no Flow model value) mean Euler; the new
   input must be fingerprint-neutral at its old value (aeroflowsim/parameters.py FINGERPRINT_NEUTRAL).
8. Walk through my next actions for every feature (switch an old nozzle project to Laminar, change the wall from
   adiabatic to isothermal, re-mesh with prism layers for y+ = 1, Stop / continue, reopen, command line) and write them
   into tests.

## Context (state after the robust-second-order stage)

* One finite-volume solver for 2D, axisymmetric and 3D (aeroflowsim/euler/): rotated HLLC + HLLE blend, least squares /
  Green-Gauss / Green-Gauss with NODE values (vertex stencil, exact for linear fields, Numba CSR kernel), Venkatakrishnan
  / Barth limiters, implicit LU-SGS (first-order Rusanov operator, SER CFL ramp) with an optional per-cell update limit,
  SSP-RK3 / Jameson, MMS order 2 (2D 1.98-2.02; 3D hexa 1.93, prisms 1.82, tetra 1.86 with node gradients).
* Gas library (aeroflowsim/gases/): every built-in gas has mu(T) (Sutherland or power law), k(T) and Pr with sources;
  GasModel.mu / k / Pr exist and are tested. N2 is the cube-sat nozzle gas.
* Meshes: structured nozzle mesh with inflation layers (exact first-layer height), Gmsh triangles / quad-dominant with
  inflation layers, structured C/O-grids with an exact first layer, 3D prism layers. Smart rule `first_layer_height`
  (aeroflowsim/smart_rules.py) gives the first-layer height for a target y+ from the flow scales (Re).
* Findings of the robust-second-order stage that belong here:
  - Viscous fluxes need face gradients; the node-value Green-Gauss gradient (vertex stencil) is the robust choice on
    triangles; on quads / prisms the face-normal correction (d / |d| projection, "corrected" face gradient as in
    OpenFOAM / Fluent) is needed for non-orthogonal meshes.
  - The per-cell update limit protects strong expansions; keep it compatible with the viscous Jacobian.
  - An inviscid blunt-body wake on unstructured meshes is not steady to round-off; with viscosity (Re = 40 cylinder) the
    wake becomes a physical steady recirculation: the validation must converge to 1e-6 there.

## Decisions (made: follow them)

* Laminar Navier-Stokes: viscous flux F_v = [0, tau . n, (tau . u + k grad T) . n] with the Stokes hypothesis
  (lambda = -2/3 mu); face gradients = mean of the two cell gradients + a correction along the cell-to-cell vector
  (grad_f = avg + [(phi_N - phi_P)/|d| - avg . e] e); mu, k from the GasModel at the face temperature.
* Axisymmetric: the hoop-stress source terms (tau_theta_theta, mu v / r), written in the well-balanced form of section 12.
* Walls: no-slip, adiabatic (zero heat flux) or isothermal (T_wall input); slip wall stays available (rarefied option
  later). Wall shear stress, skin friction Cf = tau_w / q_inf, wall heat flux and Stanton number in post-processing
  (surface fields, XY plots, report), y+ of the first cell.
* Implicit: add the viscous spectral radius to the time step and the LU-SGS diagonal (2 mu / (rho |d|) A per face).
* A Flow model input (Euler / Laminar), default Euler (old projects unchanged); the nozzle and external templates get
  it; a smart rule suggests Laminar when Re (throat or body) is below about 1e5, and the first-layer height for y+ = 1.
* Preconditioning-compatible: keep the dissipation and time-step terms separate so the low-Mach stage can scale them.

## Parts (all in this session, in this order)

1. Theory and the viscous flux: face gradients, tau, heat flux, viscous time step; MMS for Navier-Stokes (manufactured
   solution of the existing MMS plus viscous source terms) on quads and triangles, planar and axisymmetric: order 2.
2. Boundary conditions: no-slip adiabatic / isothermal walls (ghost states for the inviscid part, wall gradients for the
   viscous part), symmetry and axis with viscous terms, far field / inlet / outlet unchanged.
3. Forces and heat flux: wall shear and pressure forces (Cd friction + pressure), Cf, q_w, St, y+; post-processing fields
   and surface plots; report section.
4. Validation (pre-registered, background, one job at a time):
   - Couette flow (exact linear profile; shear stress within 0.5 %),
   - Poiseuille flow in a tube (axisymmetric; parabolic profile and pressure drop within 1 %),
   - flat plate (Blasius): Cf at Re_x = 1e4 - 1e5 within 3 %, boundary-layer thickness delta_99 within 5 %,
   - cylinder at Re = 40: separation (recirculation) length L/D vs Coutanceau & Bouard / Dennis & Chang within 5 %,
     drag coefficient within 5 %, residual converged to 1e-6,
   - the N2 cube-sat nozzle: first ESTIMATE the throat Reynolds number (rho* u* d* / mu*) and record it; then the
     discharge coefficient Cd and the Isp loss versus Reynolds number (p0 varied over a decade) against published
     micro-nozzle data or a boundary-layer estimate (displacement thickness at the throat), tolerances decided and
     written before the run.
   Iterations and wall-clock time in validation/timing.md; quick and full sets.
5. GUI and docs: the Flow model and wall inputs, the wall fields in the Results step, the smart rules; user guide,
   theory manual section, developer guide, gap register, CHANGELOG, docs/roadmap/README.md, and the plan of the next
   stage (low-Mach preconditioning, update docs/roadmap/low_mach_preconditioning.md) in this style. Full fast and GUI
   tests, quick and full validation, push.

## Quality gates

* Tests pass; NumPy = Numba to 1e-12; thread independent; MMS order 2 for Navier-Stokes.
* Every Euler validation number unchanged (Flow model Euler), shown.
* No Qt in solver / post / logic modules; privacy test passes. No tag, release or repository-settings change.

## Done when

1. Couette, Poiseuille, Blasius and the Re = 40 cylinder pass (or are documented SHORTFALLS with their cause).
2. The cube-sat nozzle's throat Reynolds number, Cd and Isp loss versus Re are in the report.
3. Old projects unchanged; docs, gap register, CHANGELOG, roadmap README, the next plan and the ledger written; pushed.

## Ledger (progress log)


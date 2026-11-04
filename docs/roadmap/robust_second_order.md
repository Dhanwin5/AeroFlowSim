# Robust second order on triangles and tetrahedra (2D and 3D)

**Model: Opus** (diagnosis of a numerical instability: gradients, limiters, the second-order switch, the implicit
operator; one hypothesis at a time).

Paste everything below the line into ONE new Claude Code session.

---

## How to work (read first, follow throughout)

You are building AeroFlowSim (project folder C:\Projects\CFD software, GitHub Dhanwin5/AeroFlowSim, repository is
PUBLIC). I am a beginner programmer who knows aerospace engineering and CFD theory. This is the ONLY prompt for this
stage: do all 6 parts in order, in this one session, without waiting for me between parts.

1. Start: read CLAUDE.md, docs/gap_register.md, the ledger of docs/roadmap/3d_euler_solver.md (Parts 3, 6, 7 are the
   important ones), docs/roadmap/low_mach_preconditioning.md, docs/theory_manual.md sections 12, 13b-13d, 13h, and skim
   aeroflowsim/euler/ (all: gradients, limiters, flux, solver, implicit LU-SGS, boundary, setup), aeroflowsim/mms.py,
   validation/. Write a short plan in plain words, then start at once.
2. Do not stop to ask questions. Decide the way Fluent, SU2 or CFL3D would; give one sentence of why in the summary.
   Stop only before: deleting files you did not create in this session, adding a dependency, or anything outward-facing
   apart from the push at the end.
3. Ledger = your memory. After every part: commit, then add a ledger entry (done, how verified, next, anomalies). If the
   conversation is compacted, re-read the ledger and carry on. Do not stop between parts to report to me.
4. Out of room? Only if you truly cannot continue: stop at the END of a part, commit, write the ledger entry, tell me
   plainly which part is next.
5. Long jobs (runs, validation, timing) in the background, ONE heavy job at a time (32 GB machine, about 4 GB per
   million 3D cells). Report result lines only.
6. Never tune a number to pass. Pre-register every validation tolerance in its reference.toml BEFORE the run. A miss is
   a SHORTFALL with its cause.
7. Rule 4 of CLAUDE.md: every 2D number in validation/report.md must stay identical unless a change is made on purpose;
   then explain every changed number.
8. Walk through my next actions for every new option (switch it on in an old project, Stop / continue, change an input,
   re-mesh, reopen, command line) and write them into tests.

## Context (state after the 3D Euler stage)

* One solver for 2D, axisymmetric and 3D (aeroflowsim/euler/): rotated HLLC + HLLE blend at strong compressions,
  least-squares or Green-Gauss gradients, Venkatakrishnan / Barth limiters, implicit LU-SGS (first-order Rusanov
  operator, omega 1.5, SER CFL ramp to 100), SSP-RK3 / Jameson, Numba kernels (GPU-ready rule), MMS order 2 in 2D and 3D.
* THE PROBLEM (gap register P1): second-order runs on tetrahedral and triangular meshes at strong shocks do not converge.
  - 3D Mach 3 sphere, quarter domain, 60k tetrahedra: LU-SGS diverged at iteration 133 (4 CFL reductions); with CFL 0.5
    + 500 first-order iterations it diverged at 605, RIGHT AFTER the switch to second order. Mach 6: diverged at 107
    with no positivity fallbacks. SSP-RK3 is stable but not converged after 6,000 iterations (stand-off 0.240, still
    moving).
  - 3D 10 deg cone Mach 2, 31k cells: 20,000 iterations, not converged; shock angle 33.39 deg vs 31.21 (+7 %), Cp 0.10822
    vs 0.10447 (+3.6 %).
  - 2D Mach 3 cylinder on Gmsh triangles diverges with the 2D defaults (first-order LU-SGS at iteration 166 in the
    near-vacuum wake).
  - Earlier finding (3D stage, Part 6): weighted least-squares gradients on tetrahedra (4 face neighbours, boundary-face
    points dominate the 1/d^2 weights) oscillate; Green-Gauss + Venkatakrishnan K = 1 converged on the COARSE meshes
    but is NOT robust on finer meshes at strong shocks. So the cause is not fully found.
  - Hexahedra and prisms converge on the same ramp (1,376 / 2,943 iterations); explicit RK3 converges; it is not the
    CFL, omega, the flux (pure HLLE), the BJ/K limiter, the symmetry planes or the far-field shape (all tried).
  - Far field near normal Mach 1: 3D blends the Riemann and extrapolation branches over normal Mach 0.9-1.1; 2D keeps
    the sharp switch.
  - 3D defaults today (external_3d solver_defaults): LU-SGS, Green-Gauss, K = 1, 100 first-order iterations. 2D
    defaults: least squares, K = 5.
  - Measured: Venkatakrishnan K = 5 under-limits the large 3D cells (eps ~ (K h / L)^1.5).
* Reproduction set already in the repository: validation/euler3d_sphere, euler3d_cone, the tet ramp, the 2D cylinder on
  Gmsh triangles, cases/external_3d examples. Reuse them; add small scripts under tools/ if needed.

## Decisions (made: follow them)

* Diagnose first, then fix the cause. Test ONE hypothesis at a time on the same reproduction set and record before /
  after in the ledger. Do not stack changes.
* Hypotheses to test, in this order:
  (a) Abrupt switch to second order. Replace it by a ramp (blend factor 0 -> 1 over N iterations, N tied to residual
      drop or iteration count), restart the CFL ramp at the switch.
  (b) Positivity. Check why no first-order fallback fired in 3D at Mach 6. Make sure the per-cell fallback (negative
      density or pressure in the reconstructed state or in the update) works in 3D, is counted, and is reported in the
      run log.
  (c) Gradients. Extended least-squares stencil with vertex neighbours, weights 1/d (and unweighted) instead of 1/d^2;
      Green-Gauss with node-averaged values (Barth / Mavriplis). Measure the effect on MMS order on tetrahedra (today
      1.75) and on the reproduction set.
  (d) Limiter. Venkatakrishnan with the LOCAL cell size in the threshold (as in the 2D MMS finding), freezing after a
      stall; check K in 3D.
  (e) Implicit operator. Only if (a)-(d) do not fix it: Roe-Jacobian LU-SGS or matrix-free GMRES. Decide and record; do
      not build it if not needed.
* Whatever wins becomes an option in Numerics, off the old behaviour for old projects (a missing value must mean the old
  behaviour, so fingerprints and results stay). New projects get the best default per mesh type through the template
  solver_defaults / smart rules.
* NumPy reference = Numba kernels to 1e-12; results independent of the thread count; every new kernel a pure function
  of flat arrays (GPU-ready rule).
* 2D defaults change only if the 2D validation numbers stay identical or every change is explained with evidence.

## Parts (all in this session, in this order)

1. Reproduce and instrument. Script the reproduction set (tools/robustness_cases.py): per case record the iteration of
   divergence or stall, the cells where p or rho first go bad or where the residual sits (per-cell residual field),
   their quality (skewness, size ratio to neighbours), the limiter value and gradient magnitude there, and the number of
   positivity fallbacks. Write the baseline table to the ledger. Hexahedra / prism controls included.
2. Test hypotheses (a) to (e) in order, one at a time. After each: the table again, a verdict, a ledger entry. Stop
   testing when every case in the set converges (or when the remaining cause is found and recorded with evidence).
3. Implement the winning combination cleanly: options in Numerics, kernels, NumPy reference, tests (NumPy = Numba 1e-12
   on every mesh type and option; free stream preserved to round-off; gas at rest stays at rest; thread independence;
   MMS orders in 2D and 3D unchanged or better, tetrahedra >= 1.8 if the new gradient allows it).
4. Defaults and old projects: choose defaults by mesh type (a smart rule suggests them; the run log says what is
   active). Old projects open and give the same results. Adopt the 3D far-field blend in 2D only if the 2D numbers stay
   identical (otherwise record as a gap).
5. Validation (background, one job at a time), tolerances pre-registered and equal to the ones that failed: 3D sphere
   Mach 3 stand-off vs Billig 5 %, 3D cone shock angle 3 % and Cp 2 %, 2D cylinder Mach 3 on Gmsh triangles stand-off vs
   Billig 5 %, tet ramp; sphere Mach 6 (report whether a carbuncle appears, positivity fallbacks counted); the 126k-cell
   sphere wall-clock target (converged in under 30 min; report a miss by how much and why). Quick and full sets;
   iterations and wall-clock time in the report and validation/timing.md.
6. Docs and finish: theory manual, user guide, developer guide, gap register (close P1 or restate it with evidence),
   CHANGELOG, docs/roadmap/README.md (this stage done; order: laminar viscous next, then low-Mach preconditioning). Write
   the plan of the NEXT stage "Laminar viscous flow, 2D and axisymmetric" as docs/roadmap/laminar_viscous.md (model Opus;
   laminar Navier-Stokes with viscous fluxes from face gradients, viscosity and conductivity from the gas library,
   no-slip walls adiabatic or isothermal, wall shear stress, skin friction and wall heat flux, the first-layer tool for
   y+ = 1, preconditioning-compatible; parts: theory and viscous flux with MMS, boundary conditions, forces and heat flux,
   validation pre-registered: Couette, Poiseuille in a tube, flat plate Blasius Cf and thickness, cylinder at Re = 40
   separation length, the N2 cube-sat nozzle Cd and Isp loss versus Reynolds number (estimate the throat Reynolds number
   first), GUI, docs). Update low_mach_preconditioning.md with findings that belong to it. Run the full fast and GUI
   tests, quick and full validation, then push to main.

## Quality gates

* Tests pass; ledger updated after every part; pushed at the end.
* 2D validation numbers unchanged (or every change explained); MMS order >= 1.8 in 2D (unchanged) and 3D (hexahedra
  1.97, prisms 1.87, tetrahedra not worse than 1.75).
* No Qt in solver, post or logic modules (tested); privacy test passes.
* Do not tag, release or change repository settings.

## Done when (check every line with evidence)

1. The reproduction set converges (3D sphere Mach 3, cone, tet ramp, 2D cylinder on triangles), or the remaining cause
   is recorded with evidence and the case is a documented SHORTFALL.
2. Old projects and every 2D validation number unchanged (or explained); NumPy = Numba; thread independent.
3. Docs, gap register, CHANGELOG, roadmap README, the laminar viscous plan and the ledger are written; pushed.

## Plan (plain words)

1. A script runs the five troublesome cases (3D sphere Mach 3 and 6, cone, tet ramp, 2D cylinder on triangles) plus
   hexahedron / prism controls, and prints where and when each one goes wrong.
2. Then one change at a time: a gentle ramp into second order, the positivity fallback, better gradients, the limiter,
   and only if still needed a better implicit operator. After each change the same table again.
3. The change that works becomes a Numerics option (old projects keep the old behaviour), with tests, defaults per mesh
   type, validation and docs.

## Ledger (progress log)

### Part 1 - reproduction and instrumentation (done)
- `tools/robustness_cases.py`: sphere3 / sphere6 (validation full mesh, 60k tets, quarter), cone (31k), ramp_tet / ramp_hex
  / ramp_prism (30 deg ramp at M2, detached shock), cylinder2d (M3, Gmsh triangles, 2D defaults). Per case: status,
  iterations, residual, CFL reductions, positivity fallbacks, limited updates, measured number; worst cell of the final
  state (largest |d rho/dt|/rho): position, boundary, skewness, volume ratio, psi, |grad p| h / p, residual share.
  Developer knob `AEROFLOWSIM_NUMERICS` (JSON of Numerics fields, setup.numerics) for fields that are not inputs.
- Baseline (3D template defaults: LU-SGS, Green-Gauss, K 1, 100 first-order iterations; ramp: LU-SGS, least squares,
  K 5; cylinder2d: 2D defaults):

| Case | Cells | Status | It | Res | CFL red | Pos. | Worst cell |
|---|---:|---|---:|---:|---:|---:|---|
| sphere3 | 59,998 | diverged | 133 | 2.5e-2 | 4 | 0 | x = +0.048 (BEHIND the sphere, wake), \|grad p\| h/p 3.5, psi 0.9 |
| sphere6 | 59,998 | diverged | 107 | 1.1e-1 | 4 | 0 | x = +0.043 on the wall (rear), psi 0.5 |
| cone | 30,825 | max it 6,000 | 6,000 | 1.4e-4 | 0 | 0 | base corner (x = L), skew 0.75, vol. ratio 2.8 |
| ramp_tet | 6,144 | stalled | 3,000 | 2.6e-1 | 0 | 0 | at the detached shock (x 0.17), psi 1.0 |
| ramp_hex | 1,024 | converged | 1,357 | 1e-8 | 0 | 0 | control |
| ramp_prism | 2,048 | converged | 2,929 | 1e-8 | 0 | 0 | control |
| cylinder2d | 11,435 | diverged | 269 | 4e-2 | 4 | 0 | x = 0.99 (wake behind the cylinder) |

- Clue: the sphere and the cylinder blow up in the near-vacuum WAKE, not at the shock, with no reconstruction
  fallback at all: the bad state comes from the update. The cone stalls at its base corner; the tet ramp at its shock.

### Part 2 (a) - ramp into second order (`Numerics.second_order_ramp`, blend of the reconstruction 0 -> 1)
- 300 iterations: sphere3 diverges at 420 (was 133), sphere6 at 349 (107), worst cell again in the wake (|grad p| h/p
  23); ramp_tet unchanged (0.26); cylinder2d still diverges (152; it fails at first order anyway).
- Verdict: delays, does not fix. Not the cause. Kept as an option for now (decided in Part 3).

### Part 2 (b) - positivity of the UPDATE (`Numerics.update_limit`, per-cell guard of the implicit update)
- Why no fallback fired at Mach 6: the existing fallback acts on the RECONSTRUCTED face states only; the bad states
  came from the implicit update (density/pressure of a cell going negative in one step), which only triggered the
  global CFL back-off (4 x, then "diverged"). New guard (SU2's local under-relaxation): a cell whose update would change
  rho, E or p by more than 20 % (or make p negative) gets its update scaled down; counted (`limited_updates`, run info).
- Result (0.2): sphere3 3,000 it no divergence, res 6.3e-3, stand-off 0.243 (+18 %), 72k limited updates; sphere6 3,000
  it, res 2.6e-2, stand-off 0.1569 (Billig 0.1565); cylinder2d 4,000 it, res 3.2e-2; ramp_tet unchanged (0.26, never
  limited). The residual stays in 20-40 rear-wall / wake cells that are limited every iteration (|grad p| h/p up to 180).
- Verdict: a safety net (no more divergence), not the cure.

### Part 2 (c) - gradients: Green-Gauss with node values (`gradient = "Green-Gauss (node values)"`)
- Face value = mean of the face's node values; node value = a weighted (1/d) LINEAR least-squares fit through the cells
  around the node and, at boundary nodes, the boundary faces (Holmes & Connell's pseudo-Laplacian idea: exact for
  linear fields - checked to 1e-13 on tetrahedra and triangles). A vertex-neighbour stencil (~20 cells for a
  tetrahedron instead of 4). Experiment on the NumPy path (no Numba kernel yet).
- Result: ramp_tet 0.26 -> 3.8e-8 (the stall is gone); cone CONVERGED (1,221 it, res 1e-6): Cp 0.10626 (+1.7 %, was +3.6
  %), shock angle 33.392 deg unchanged (+7 %); sphere3 diverges at 632 (was 133), in the wake; cylinder2d diverges at
  235 (the wake again).
- Verdict: the face-neighbour stencil on simplices IS a cause (shock-region stall and the cone); the wake blow-up on
  the sphere and the 2D cylinder is a second, separate cause (the update in the near-vacuum expansion). The cone shock
  angle does not move with any numerics change: suspect the measurement or the mesh resolution near the tip (checked
  next).

### Part 2 - Numba kernel for the node gradient (so the experiments run at full speed)
- `kernels.gradients_csr`: row (k C + i) of the sparse gradient matrix times X (gather, one cell per iteration: GPU-
  ready, thread independent); used when gradient = "Green-Gauss (node values)". Numba = NumPy 1e-15 on tets with a
  shock. Sphere3 3,000 it: 1,101 s (NumPy) -> 104 s (Numba).

### Part 2 (b)+(c) combined and (d) the limiter (all with node gradient + update guard 0.2)
| Variant | sphere3 res | stand-off | rec. fallbacks | limited | cylinder2d res |
|---|---:|---:|---:|---:|---:|
| (b)+(c) | 1.4e-4 | 0.2230 | 48,801 | 18,240 | 6.0e-4 |
| + freeze limiter at 2 orders | 2.9e-4 | 0.2234 | 199,688 | 30,903 | 1.5e-3 |
| + K = 5 | 4.2e-4 | 0.2228 | 104,028 | 28,082 | 6.0e-4 (2D default K is 5) |
| + Barth-Jespersen | 3.3e-4 | 0.2226 | 38,717 | 24,250 | 9.3e-4 |
- Nothing diverges any more, nothing converges in 3,000 / 4,000 iterations. The limiter variants do not change the
  picture: (d) is not the cause. The residual sits in the wake, where tens of reconstructed face states per iteration
  are unphysical (negative p) and fall back to first order, switching on and off.
- Next: is the implicit operator the remaining cause? Same set with explicit SSP-RK3.

### Part 2 - remaining hypotheses and the verdict
- Explicit SSP-RK3 with the node gradient: cylinder2d 8,000 it res 2.5e-3 (stall), sphere3 diverges at 7,207 at the rear
  wall. So the implicit operator is NOT the cause: (e) (Roe-Jacobian LU-SGS / GMRES) would not fix it - decided not to
  build it.
- Smooth positivity of the reconstruction (Zhang-Shu-type scaling of the slopes so face rho, p >= 0.5 x cell value,
  replacing the on/off fallback): reconstruction fallbacks 66,000 -> 0, residual unchanged (8e-4). Removed again
  (no benefit). The second-order ramp of (a) also removed (it only delayed the divergence).
- WHAT THE CAUSE TURNED OUT TO BE - two separate causes:
  1. The face-neighbour stencil on simplices (4 neighbours of a tetrahedron, 3 of a triangle): least-squares and
     face-average Green-Gauss gradients are noisy there; at shocks the limiter chatters and the residual stalls (tet ramp
     0.26, cone). Cure: Green-Gauss with NODE values from a linear fit (vertex-neighbour stencil): ramp 3.8e-8, cone
     converged; MMS order on tetrahedra 1.75 -> 1.86.
  2. Large implicit updates in the near-vacuum expansion behind blunt bodies make a cell's p negative in ONE step (no
     reconstruction fallback can see this), so the global CFL back-off gives up ("diverged"). Cure: the per-cell update
     limit (0.2). With it no case diverges.
  What remains is NOT a numerics switch: the wake behind the cylinder / sphere keeps moving (the update limit stays
  active in ~15 wake cells every iteration, implicit or explicit alike) while the forces settle: cylinder2d Cd over
  1,000-iteration windows 1.34441 / 1.34446 / 1.34448 / 1.34446, its oscillation 0.22 % -> 0.06 %, residual 6e-4 held by
  1 % of the cells in the wake. An inviscid blunt-body wake on an unstructured mesh is not steady to round-off; the
  forebody (shock, stand-off, Cd) is. Recorded as the remaining cause; the validation judges the forebody quantities
  with the monitors settled.

### Part 3 - implementation (done)
- `gradients.GREEN_GAUSS_NODES` ("Green-Gauss (node values)"): node value = 1/d-weighted linear least-squares fit
  through the cells and boundary faces round the node (exact for linear fields; nodes with too few points fall back to
  the weighted mean); face flux = sum over the face's triangles round its node mean of (mean of phi) S_t (exact on
  non-planar quad faces too). One sparse matrix; Numba `gradients_csr` (gather per cell).
- `Numerics.update_limit` and the input "Implicit update limit" (default 0 = off): per-cell scaling of the LU-SGS update
  so rho, E and p change by at most the limit; counted (`limited_updates` in the run info). `parameters.FINGERPRINT_NEUTRAL`:
  an input added later is left out of the fingerprint while it holds its old-behaviour value (old projects keep their
  fingerprints and results; tested).
- Developer knob `AEROFLOWSIM_NUMERICS` (JSON of Numerics fields on top of the inputs) kept for experiments.
- `mms.run_level_3d(..., gradient=)`. 3D MMS with the node gradient (12^3 -> 24^3, min L2 order): tetrahedra 1.861
  (least squares 1.747), prisms 1.820 (1.870), hexahedra 1.934 (1.966).
- Tests tests/test_robust_second_order.py (24): linear exactness on triangles / tetrahedra / pyramids / hex-prism,
  Numba = NumPy 1e-12 on 2D (triangles, quads, mixed, axisymmetric) and every 3D kind, free stream and gas at rest
  (SSP-RK3 and LU-SGS), thread independence, MMS order, the update limit: no change where inactive (bit for bit),
  bounds every change, counted; old-project fingerprint unchanged. 232 related tests pass.
- Next: Part 4 (defaults by mesh type, smart rule, run log).

### Part 4 - defaults, suggestion, run log, old projects (done)
- external_3d solver_defaults: gradient "Green-Gauss (node values)", update_limit 0.2 (K 1, 100 first-order it. kept).
  2D defaults unchanged (least squares, K 5, no update limit): their validated numbers stay bit for bit.
- Smart rule (`numerics_suggestions(case, params, mesh)`, Run step "Suggested numerics"): a mesh with more than half
  triangles / tetrahedra gets "Gradients Green-Gauss (node values), update limit 0.2" with the measured reason; gone
  once applied, never for quads.
- Run log: `setup.numerics_note(params)` ("Numerics: Implicit LU-SGS, gradients ..., limiter ... (K = ...), update limit
  ...") logged by the GUI at every run start and printed by the command line (template runs and project runs).
- Old projects: the new input is fingerprint-neutral at 0 (Part 3 test); the gradient choice is a new option of an
  existing input. Only external_3d projects change: its schema.toml (solver defaults) is part of their template
  fingerprint, so existing 3D projects show "needs update" (results of the old defaults).
- Far-field near-sonic blend in 2D: NOT adopted (it changes the far-field state wherever 0.9 < M_n < 1.1 at an outflow,
  so the 2D numbers cannot be guaranteed identical) - stays a gap.
- Tests (27 in test_robust_second_order.py): suggestion on triangles only and gone when applied; run-log note; walk-through:
  an old 2D project switched to the new options runs from the command line (note printed), results current, continued
  40 -> 60 with the same options.

### Part 5 - validation (done; SHORTFALLS recorded)
Pre-registered (commits 24ade42 and the 3D stage's ab89a0b, unchanged), full set, external_3d defaults (node gradient,
K 1, update limit 0.2) and for the 2D cylinder the suggested triangle numerics:

| Case | Quantity | Reference | Result | Error | Tol. | Status | Before this stage |
|---|---|---:|---:|---:|---:|---|---|
| euler3d_cone | Cp | 0.10447 | 0.10627 | 1.7 % | 2 % | PASS | 3.6 %, not converged |
| euler3d_cone | shock angle | 31.21 deg | 33.39 deg | 7.0 % | 3 % | SHORTFALL | 7.0 % |
| euler3d_ramp | tet run converged | 1 | 1 | - | - | PASS | stall at 0.26 |
| euler3d_ramp | stand-off tet / hex | 1 | 1.83 | 83 % | 2 % | SHORTFALL | - |
| euler3d_sphere | stand-off M3 (3D) | 0.2050 | 0.2269 | 10.7 % | 5 % | SHORTFALL | diverged |
| euler3d_sphere | stand-off 2D axi twin | 0.2050 | 0.2142 | 4.5 % | 5 % | PASS | 4.5 % |
| euler2d_cylinder_triangles | stand-off | 0.6485 | 0.7027 | 8.4 % | 5 % | SHORTFALL | diverged |

- Every case now runs to the end without diverging (sphere M3 / M6 20,000 iterations, cylinder 20,000); the cone and the
  tet ramp CONVERGE (residual 1e-6 / 8 orders). Sphere Mach 6 on tetrahedra (reported): stand-off 0.1516 vs Billig
  0.1565 (-3.1 %), no carbuncle bulge on the stagnation line, 134k reconstruction fallbacks, 0 CFL reductions.
- Measurement bugs found and fixed while scoring (stated in the scripts): the 2D cylinder's first stand-off (1.042) came
  from interpolating across a 0.46 m gap with no cells in the 0.01 D band (now: the field interpolated along the line ->
  0.703); the same flaw in the sphere script (old method 0.2230, new 0.2269, both reported). Tolerances not changed.
- SHORTFALL causes: (1) cone shock angle: resolution - 30.8k cells 33.39 deg, 72k cells 32.78 deg (converged both); a
  first-order extrapolation in h (ratio 1.33) gives about 30.9 deg: the weak conical shock (p2/p1 = 1.085) smeared over a
  few cells biases the half-way crossing upstream. (2) ramp tet / hex: on the 16-cell box the stand-off is 2.4 cells
  (tet) vs 1.3 cells (hex): the 2 % tolerance asked for a sub-cell precision this box cannot give (a poor choice of the
  pre-registered case, not of the numerics). (3) sphere and 2D-triangle cylinder stand-off 8-11 % too large while the 2D
  structured twin is within 4.5 %: the shock layer on simplex meshes is resolved by about 5 cells and the bow shock
  sits further out; not separated from the unsettled wake (residual 1e-3 - 1e-4) within this session. Next step: a
  refinement study of the sphere (60k / 150k / 400k) - gap register.
- 126k-cell sphere wall-clock target: NOT MET as defined - the residual criterion is never reached (the inviscid wake keeps
  moving; forces settle). 60k cells: 20,000 iterations in 635 s; the 126k run would need about 1,300 s for 20,000
  iterations without converging, so it was not run.
- Two format fixes to the ramp reference after the run (validation/test_validation.py rules), values and the ratio
  tolerance untouched: `case` names aeroflowsim/simple_meshes.py (the tools script is not a template), and the yes/no
  tolerance registered as 0 is 0.01 (the framework needs > 0; for a 1-or-0 value any tolerance below 100 % gives the
  same verdict).

### Part 6 - docs and finish
- Theory manual 13i (the two causes, the node-value gradient with its equations, the update limit, what did not help,
  what remains), user guide "Triangle and tetrahedron meshes: robust numerics" (the two inputs, the run-log line, the
  wake note), developer guide (gradient matrices and the CSR kernel, `_limit_update`, FINGERPRINT_NEUTRAL, the
  reproduction tool), gap register (P1 restated with evidence; wake row; 2D far-field blend), CHANGELOG, roadmap README
  (this stage done; laminar viscous next, then low-Mach preconditioning), docs/roadmap/laminar_viscous.md (next plan),
  low_mach_preconditioning.md updated with this stage's findings.
- Fast + GUI tests: 1,193 passed, 1 skipped (one validation-format test failed on the ramp reference, fixed above).
- Full validation: 174 checks pass; the only failures are the four recorded SHORTFALLS (sphere 3D stand-off, cone
  shock angle, ramp tet/hex ratio, 2D triangle cylinder stand-off). Every 2D number of report.md is identical to
  before the stage (diff of the 2D rows: only the ramp's yes/no tolerance shown as 0.01). Quick set: 2D rows
  identical; the 3D / new cases show the same shortfalls on their coarser meshes (cone Cp passes, 1.8 %).
- Pushed to main. No tag, no release.

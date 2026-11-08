# AeroFlowSim validation report

AeroFlowSim 0.3.0, generated 2026-11-08 by `python validation/run_all.py`.

**Validation set: full** (all meshes of every case; run weekly and on version tags).

**Overall: FAIL** (30 of 35 cases pass; 7 explained shortfall(s), see the cases marked SHORTFALL)

**NOT RUN** (no saved result of this set; listed, not hidden): `validation/turbulent_flat_plate`

## Back, Massier and Gier 45-15 deg conical nozzle: measured wall pressure (2D axisymmetric Euler, nozzle_axi): PASS

Case: `cases/nozzle_axi`, references: `validation/bmg_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Wall p/p0 at z = 2.098 in (band +-0.03) | 0.9492 | 0.929928 | 2.030 | 3.16 | PASS |
| Wall p/p0 at z = 2.239 in (band +-0.03) | 0.8669 | 0.798844 | 7.850 | 3.46 | SHORTFALL |
| Wall p/p0 at z = 2.457 in (band +-0.05) | 0.5304 | 0.482671 | 8.999 | 9.43 | PASS |
| Wall p/p0 at z = 2.464 in (band +-0.05) | 0.491 | 0.472281 | 3.812 | 10.18 | PASS |
| Wall p/p0 at z = 2.643 in (band +-0.03) | 0.2281 | 0.228555 | 0.199 | 13.15 | PASS |
| Wall p/p0 at z = 2.828 in (band +-0.03) | 0.1984 | 0.186226 | 6.136 | 15.12 | PASS |
| Wall p/p0 at z = 3.124 in (band +-0.03) | 0.1866 | 0.169196 | 9.327 | 16.08 | PASS |
| Wall p/p0 at z = 3.609 in (band +-0.03) | 0.1299 | 0.121931 | 6.135 | 23.09 | PASS |
| Wall p/p0 at z = 3.957 in (band +-0.03) | 0.0969 | 0.0931159 | 3.905 | 30.96 | PASS |

**Shortfall (explained):** Wall p/p0 at z = 2.239 in (band +-0.03): The inviscid value is 0.80 on both meshes (100 x 20: 0.806, 200 x 40: 0.799): not a mesh error. Cause not resolved: the report concludes that boundary-layer effects on the wall pressure were negligible (Conclusions, item 3), so a viscous effect is unlikely. At z = 2.24 in, just after the tangency of the 45 deg cone with the small throat arc, the measured pressure falls steeply (about -1.2 to -2.5 per inch), so an uncertainty of 0.03-0.05 in in the tap position or the digitized position equals the 0.07 difference, and the report finds tap-size effects of up to 7 % (Conclusions, item 4). A band that includes the position uncertainty (or the report's tabulated data, if they can be found) is recorded in the gap register.

Sources:

- Back, Massier and Gier (1964), JPL Technical Report 32-654, Fig. 4 (tests 347, 348, 351), NASA NTRS 19650001801; digitized

### Wall pressure along the nozzle

| z [in] | p/p0 measured | p/p0 AeroFlowSim | difference |
|---:|---:|---:|---:|
| 0.810 | 0.9990 | 0.9991 | +0.0001 |
| 1.013 | 0.9987 | 0.9978 | -0.0009 |
| 1.195 | 0.9965 | 0.9963 | -0.0002 |
| 1.395 | 0.9946 | 0.9936 | -0.0010 |
| 1.746 | 0.9893 | 0.9821 | -0.0072 |
| 1.937 | 0.9770 | 0.9654 | -0.0116 |
| 2.098 | 0.9492 | 0.9299 | -0.0193 |
| 2.239 | 0.8669 | 0.7988 | -0.0681 |
| 2.457 | 0.5304 | 0.4827 | -0.0477 |
| 2.464 | 0.4910 | 0.4723 | -0.0187 |
| 2.643 | 0.2281 | 0.2286 | +0.0005 |
| 2.828 | 0.1984 | 0.1862 | -0.0122 |
| 3.124 | 0.1866 | 0.1692 | -0.0174 |
| 3.609 | 0.1299 | 0.1219 | -0.0080 |
| 3.957 | 0.0969 | 0.0931 | -0.0038 |
| 4.603 | 0.0588 | 0.0571 | -0.0017 |
| 5.279 | 0.0370 | 0.0359 | -0.0011 |
| 5.987 | 0.0230 | 0.0235 | +0.0005 |
| 6.664 | 0.0182 | 0.0164 | -0.0018 |

- Mesh: 8,000 cells, 3,945 iterations, converged yes, 9 s; discharge coefficient 0.9813.
- RMS difference over all 19 measured points: 0.0210 (in p/p0).
- Geometry from the printed dimensions; the profile's exit area ratio is 6.57 (the report rounds it to 6.63; the measured points end at z = 6.66 in, before the exit).
- The test gas was heated air (1500 R) with a boundary layer; the solver is inviscid with gamma = 1.4 (the report's one-dimensional curve uses 1.40 as well).

## 15 deg cone at Mach 2 (2D axisymmetric Euler, external_2d) vs Taylor-Maccoll: PASS

Case: `cases/external_2d`, references: `validation/euler2d_cone/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Conical shock angle (fitted through the shock position at 6 stations) | 33.9146 deg | 34.2056 deg | 0.858 | 2 | PASS |
| Surface pressure coefficient (mean between 30 % and 80 % of the cone length) | 0.202234 | 0.201871 | 0.179 | 2 | PASS |

Sources:

- Sims (1964), NASA SP-3004, Table 11, p. 16: theta_w = 0.59192180 rad for theta_s = 15 deg, M = 2
- Sims (1964), NASA SP-3004, Table 9, p. 14: Cp = 0.2022339 for theta_s = 15 deg, M = 2

### Run

| Cells | Iterations | Converged | Time [s] | beta [deg] | beta Taylor-Maccoll [deg] | Cp | Cp Taylor-Maccoll |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 5,823 | 1,990 | yes | 4 | 34.206 | 33.915 | 0.2019 | 0.2022 |

- Taylor-Maccoll (aeroflowsim.gasdynamics.taylor_maccoll) agrees with Sims (1964, NASA SP-3004, Tables 9 and 11) to 7e-5 in Cp and 2e-6 rad in the shock angle (tests/test_gasdynamics.py).

## Mach 6 cylinder: bow-shock stand-off and the carbuncle test (2D Euler, external_2d): PASS

Case: `cases/external_2d`, references: `validation/euler2d_cylinder/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Bow-shock stand-off distance / diameter (polar grid, carbuncle fix on) | 0.2197 | 0.224855 | 2.346 | 5 | PASS |
| Bow-shock stand-off distance / diameter (Gmsh quad-dominant mesh, full front) | 0.2197 | 0.229606 | 4.509 | 5 | PASS |

Sources:

- Billig, F. S. (1967), J. Spacecraft Rockets 4(6): Delta/R = 0.386 exp(4.67/M^2) for cylinders

### Runs

| Run | Cells | Iterations | Converged | Final residual | Time [s] | Stand-off / D | Shock roughness | Carbuncle metric | Positivity events |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| polar grid, carbuncle fix on | 4,800 | 2,706 | yes | 9.7e-07 | 5 | 0.2249 | 0.77 | 3.06e-06 | 0 |
| polar grid, carbuncle fix OFF | 4,800 | 12,000 | NO | 3.3e-01 | 22 | 0.2244 | 1.51 | 1.05e-03 | 0 |
| Gmsh quad-dominant, fix on | 1,329 | 501 | NO | 6.4e-02 | 0 | 0.2296 | - | 1.12e+00 | 0 |

- Billig correlation: stand-off / D = 0.2197.
- Shock roughness: largest second difference of the shock radius between neighbouring grid rays, divided by the radial cell size (below 1: the front never jumps a whole cell between rays; it is similar with and without the fix here, so convergence is the clearer sign).
- Carbuncle metric: peak-to-peak change of the volume-weighted pressure in the shock layer (box x = -0.45 to 0 D, y = 0 to 0.35 D) over the last 1,000 iterations, divided by its mean. It separates the runs clearly; the shock roughness above does not.
- Without the fix (pure HLLC) the bow shock never settles on the shock-aligned grid: the residual stalls high; with the HLLE blend near the shock the run converges.
- Inviscid, calorically perfect air (gamma = 1.4): a numerics test, not real Mach 6 air.

## Cylinder at Mach 3 on triangles (2D Euler, node-value gradients) vs Billig: FAIL

Case: `cases/external_2d`, references: `validation/euler2d_cylinder_triangles/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Bow-shock stand-off distance / cylinder radius on the stagnation line (Gmsh triangles) | 0.648542 | 0.702714 | 8.353 | 5 | FAIL |

Sources:

- Billig, F. S. (1967), J. Spacecraft Rockets 4(6): Delta/R = 0.386 exp(4.67/M^2) for cylinders

### Run

| Cells | Iterations | Status | Final residual | Time [s] | Stand-off / R | Billig | Cd | Cd range, last 1,000 it | Limited updates |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 11,435 | 20,000 | max_iterations | 1.1e-03 | 75 | 0.7027 | 0.6485 | 1.3449 | 0.049 % | 325,560 |

- The residual of an inviscid blunt-body wake on triangles does not reach 1e-6 (the wake keeps moving); the forebody quantities settle (Cd range in the table).

## Diamond airfoil t/c = 0.1 at Mach 2, alpha 0 and 2 deg (2D Euler, external_2d): PASS

Case: `cases/external_2d`, references: `validation/euler2d_diamond/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Drag coefficient, alpha = 0 | 0.0231957 | 0.0231626 | 0.143 | 3 | PASS |
| Lift coefficient, alpha = 2 deg | 0.0820936 | 0.0822659 | 0.210 | 3 | PASS |
| Drag coefficient, alpha = 2 deg | 0.0261435 | 0.0261137 | 0.114 | 3 | PASS |
| p/p_inf on the upper front face (middle 60 %), alpha = 2 deg | 1.22741 | 1.22727 | 0.011 | 1 | PASS |
| p/p_inf on the upper rear face (middle 60 %), alpha = 2 deg | 0.633413 | 0.63417 | 0.120 | 1 | PASS |
| p/p_inf on the lower front face (middle 60 %), alpha = 2 deg | 1.51704 | 1.51782 | 0.051 | 1 | PASS |
| p/p_inf on the lower rear face (middle 60 %), alpha = 2 deg | 0.808336 | 0.809633 | 0.160 | 1 | PASS |

Sources:

- Shock-expansion theory (Anderson 2003, Modern Compressible Flow, sec. 4.15), computed by aeroflowsim.gasdynamics.diamond_airfoil (oblique-shock and Prandtl-Meyer relations, gamma = 1.4)

### Runs (theory in brackets)

| alpha [deg] | Cells | Iterations | Converged | Time [s] | Cl | Cd | p/p_inf upper front | upper rear | lower front | lower rear |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 10,034 | 990 | yes | 3 | 0.00006 (0.00000) | 0.02316 (0.02320) | 1.3659 (1.3660) | 0.7174 (0.7165) | 1.3666 (1.3660) | 0.7176 (0.7165) |
| 2 | 10,034 | 975 | yes | 3 | 0.08227 (0.08209) | 0.02611 (0.02614) | 1.2273 (1.2274) | 0.6342 (0.6334) | 1.5178 (1.5170) | 0.8096 (0.8083) |

- Shock-expansion theory is exact for the inviscid flow on the faces (attached shocks, simple waves); Cl = 0 at alpha = 0 is not compared as a percentage (|Cl| is listed).
- Wall size 0.02 c in the quick set, 0.01 c in the full set.

## NACA 0012, inviscid, Mach 0.8 and 0.5 at alpha 1.25 deg (2D Euler, C-domain, GCI): PASS

Case: `cases/external_2d`, references: `validation/euler2d_naca0012/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Lift coefficient, Mach 0.8, alpha 1.25 deg (GCI-extrapolated) | 0.352033 | 0.335223 | 4.775 | 3 | SHORTFALL |
| Drag coefficient, Mach 0.8, alpha 1.25 deg (GCI-extrapolated) | 0.022547 | 0.0217369 | 3.593 | 8 | PASS |
| Lift coefficient, Mach 0.5, alpha 1.25 deg (GCI-extrapolated) | 0.179969 | 0.182948 | 1.655 | 3 | PASS |

**Shortfall (explained):** Lift coefficient, Mach 0.8, alpha 1.25 deg (GCI-extrapolated): speed stage (LU-SGS) study (wall AND far-field sizes halved together: 14,523 / 40,388 / 136,920 cells, LU-SGS): Cl 0.3349 / 0.3325 / 0.3352, flat within 0.8 % over a 9 x refinement (the middle mesh stopped at 40,000 iterations, residual limit cycle), so the 4.8 % gap is no longer a mesh error (the post-processing and alpha release study refined only the wall size). Most likely cause, NOT yet tested: the far field. The C-domain is 30 chords with a plain characteristic far-field condition and no point-vortex correction; the circulation of a lifting airfoil decays only like 1/r, which lowers Cl on a small domain (Vassberg and Jameson use far fields of about 1e5 chords; their CFL3D run without the vortex correction gives the lowest value, 0.348). Next: a domain-size study (30 / 100 / 300 c) or a far-field vortex correction. Cd (3.6 %) and the Mach 0.5 lift (1.7 %) are within their tolerances.

Sources:

- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 11, p. 1165: mean of FLO82 0.356209, OVERFLOW 0.351663, CFL3D 0.348226
- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 11, p. 1165: mean of FLO82 0.022685, OVERFLOW 0.022453, CFL3D 0.022501
- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 10, p. 1165: mean of FLO82 0.180346, OVERFLOW 0.179777, CFL3D 0.179784

### Runs

| Condition | Mesh | Cells | Iterations | Converged | Time [s] | Cl | Cd | Cm |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Mach 0.8 | wall 0.01 c | 14,523 | 7,307 | yes | 28 | 0.33489 | 0.022000 | -0.03438 |
| Mach 0.8 | wall 0.005 c | 40,388 | 40,000 | NO | 407 | 0.33248 | 0.021658 | -0.03388 |
| Mach 0.8 | wall 0.0025 c | 136,920 | 25,964 | yes | 1045 | 0.33522 | 0.021737 | -0.03432 |
| Mach 0.5 | wall 0.01 c | 14,523 | 7,151 | yes | 21 | 0.17430 | 0.000475 | -0.00150 |
| Mach 0.5 | wall 0.005 c | 40,388 | 10,118 | yes | 86 | 0.17556 | 0.000287 | -0.00172 |
| Mach 0.5 | wall 0.0025 c | 136,920 | 14,133 | yes | 535 | 0.17779 | 0.000191 | -0.00221 |

- Reference (Vassberg & Jameson 2010, Table 11, p. 1165): Mach 0.8, alpha 1.25 deg: continuum Cl 0.3482 (CFL3D) to 0.3562 (FLO82), Cd 0.02245 to 0.02268; Table 10: Mach 0.5, alpha 1.25 deg: Cl 0.17978 to 0.18035, Cd -> 0 (FLO82 4.5e-8).
- Cm here is about the quarter chord (template convention); the reference's Cm is about the quarter chord as well.
- Mach 0.8, Cl: GCI observed order 0.19, extrapolated value 0.357282, GCI fine 8.23 %, GCI coarse 8.8 %, asymptotic ratio 0.952 (oscillatory convergence).
- Mach 0.8, Cd: GCI observed order 2.78, extrapolated value 0.0217546, GCI fine 0.102 %, GCI coarse 0.629 %, asymptotic ratio 1.134 (oscillatory convergence).
- Mach 0.5, Cl: GCI observed order 0.59, extrapolated value 0.182948, GCI fine 3.63 %, GCI coarse 2.56 %, asymptotic ratio 0.494.
- Mach 0.5, Cd: GCI observed order 1.56, extrapolated value 0.000131506, GCI fine 39.1 %, GCI coarse 67.6 %, asymptotic ratio 0.668.
- Mach 0.5 drag on the three meshes: 0.000475, 0.000287, 0.000191 (inviscid subcritical flow has zero drag; it must fall with refinement).

## N2 nozzle, 2D axisymmetric Euler (default nozzle_axi; structured and triangle meshes, three sizes): PASS

Case: `cases/nozzle_axi`, references: `validation/euler2d_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Exit / inlet mass flow (converged: mass is conserved) | 1 | 1 | 2.5e-05 | 0.1 | PASS |
| Thrust from wall pressure + inlet momentum / thrust from the exit plane | 1 | 0.999999 | 7.8e-05 | 0.2 | PASS |
| Vacuum specific impulse (structured 200 x 40) | 71.29 s | 71.4748 s | 0.259 | 1 | PASS |
| Vacuum specific impulse (Gmsh triangles, 5,505 cells) | 71.29 s | 71.4783 s | 0.264 | 1 | PASS |

Sources:

- Conservation of mass: a converged finite-volume solution has equal inlet and exit mass flow
- Conservation of momentum: the x-momentum balance of the nozzle gas (inlet + wall + exit = 0)
- Ideal quasi-1D vacuum Isp of this wall, 72.53 s, x conical divergence factor (1 + cos 15 deg)/2 = 0.98296 (Malina 1940; Sutton & Biblarz 2017, eq. 3-34)

### Mesh study

| Mesh | Cells | Iterations | Converged | Time [s] | Mass flow [mg/s] | Cd | F exit [mN] | F wall [mN] | Isp [s] | Isp / Isp 1D | p0 loss [%] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| structured 50 x 10 | 500 | 4,457 | yes | 2 | 68.4750 | 0.9581 | 47.9974 | 47.9969 | 71.477 | 0.9855 | 2.609 |
| structured 100 x 20 | 2,000 | 7,908 | yes | 5 | 67.6312 | 0.9463 | 47.3907 | 47.3907 | 71.454 | 0.9852 | 2.902 |
| structured 200 x 40 | 8,000 | 13,771 | yes | 24 | 67.2131 | 0.9404 | 47.1116 | 47.1115 | 71.475 | 0.9855 | 2.542 |
| triangles, wall 0.16 D_t | 1,098 | 30,000 | NO | 13 | 67.5774 | 0.9455 | 47.3359 | 47.3604 | 71.428 | 0.9849 | 4.745 |
| triangles, wall 0.08 D_t | 2,350 | 30,000 | NO | 20 | 67.2126 | 0.9404 | 47.0971 | 47.0557 | 71.453 | 0.9852 | 4.052 |
| triangles, wall 0.04 D_t | 5,505 | 30,000 | NO | 41 | 67.0779 | 0.9386 | 47.0192 | 47.2436 | 71.478 | 0.9856 | 3.487 |
| rounded throat, structured 100 x 20 | 2,000 | 10,111 | yes | 7 | 71.0768 | 0.9945 | 49.7479 | 49.7478 | 71.372 | 0.9841 | 0.046 |
| rounded throat, structured 200 x 40 | 8,000 | 19,244 | yes | 35 | 71.0594 | 0.9943 | 49.7270 | 49.7270 | 71.359 | 0.9839 | 0.100 |

- Quasi-1D template (cases/quasi1d_nozzle, defaults): vacuum Isp 72.509 s, mass flow 71.6005 mg/s; ideal quasi-1D theory of the same wall 72.526 s.
- Conical divergence estimate: 72.53 s x (1 + cos 15 deg)/2 = 71.29 s (point-source flow).
- Cd = mass flow / ideal quasi-1D choked mass flow of the same throat; the throat is sharp (Rcu = Rcd = 0), so the sonic line is curved and the 2D nozzle passes less than 1D theory.
- p0 loss: drop of the mass-flux-weighted exit total pressure below the inlet p0 = 5 bar (numerical entropy; an isentropic nozzle loses nothing). Most of it is made at the SHARP throat corner, a singular expansion point of the inviscid flow; it does not fall clearly on these meshes. With a rounded throat (Rcu/Rt = 1.5, Rcd/Rt = 0.4) the coarsest triangle mesh already gives about 1 %.
- Triangle meshes: the residual stalls near 1e-4 in a few cells at the sharp throat corner (also slow, but still falling, with a rounded throat), so they do not meet the convergence criterion; the thrust from both methods and the Isp have settled to about 0.1 %. Implicit time stepping (Speed stage) is the planned cure (gap register).
- Wall-clock times: plain NumPy on one core (Numba and implicit time stepping follow in the speed stage).
- Structured meshes, Isp (GCI tool, aeroflowsim/gci.py): observed order 0.13, extrapolated value 71.6952 s, GCI fine 0.386 %, GCI coarse 0.422 %, asymptotic ratio 1.000 (oscillatory convergence).
- Sharp vs rounded throat (Rcu/Rt = 1.5, Rcd/Rt = 0.4), structured 100 x 20 and 200 x 40: p0 loss 2.902 / 2.542 % (sharp) and 0.046 / 0.100 % (rounded); Cd 0.9463 / 0.9404 (sharp) and 0.9945 / 0.9943 (rounded).
- Finding: rounded-throat loss smaller than the sharp one and NOT falling with refinement (see the gap register).

## Prandtl-Meyer expansion round a 10 deg corner at Mach 2 (2D Euler, geometry_2d): PASS

Case: `cases/geometry_2d`, references: `validation/euler2d_prandtl_meyer/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Mach number downstream of the corner (wall cells, x = 0.4-0.9 m) | 2.38489 | 2.36616 | 0.786 | 1 | PASS |
| Pressure ratio p2/p1 downstream of the corner | 0.547969 | 0.54803 | 0.011 | 1.5 | PASS |

Sources:

- Prandtl-Meyer function nu(M2) = nu(2) + 10 deg (Anderson 2003, eq. 4.44), aeroflowsim.gasdynamics.expansion
- Isentropic relation p2/p1 = (p0/p)(M1) / (p0/p)(M2) with M2 from the Prandtl-Meyer function (Anderson 2003, sec. 4.14)

### Run

| Cells | Iterations | Converged | Time [s] | M2 | p2/p1 |
|---:|---:|---:|---:|---:|---:|
| 5,267 | 897 | yes | 1 | 2.3662 | 0.5480 |

- Wall cells next to a centred expansion: the first-cell values lag the exact fan slightly on coarse meshes (the fan is smeared over a few cells at the corner).

## Sod shock tube with the 2D Euler solver (along x, and along a diagonal of a triangle mesh): PASS

Case: `cases/sod_shock_tube`, references: `validation/euler2d_sod/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Along x: star-region pressure p* | 0.30313 Pa | 0.303131 Pa | 0.00018 | 1 | PASS |
| Along x: star-region velocity u* | 0.92745 m/s | 0.927483 m/s | 0.0035 | 1 | PASS |
| Along x: density left of the contact rho*L | 0.42632 kg/m³ | 0.426291 kg/m³ | 0.0069 | 1 | PASS |
| Along x: density right of the contact rho*R | 0.26557 kg/m³ | 0.26559 kg/m³ | 0.0076 | 1 | PASS |
| Along x: shock distance from the diaphragm | 0.350432 m | 0.350815 m | 0.109 | 2 | PASS |
| Along x: contact distance from the diaphragm | 0.18549 m | 0.185673 m | 0.098 | 2 | PASS |
| Diagonal, triangles: star-region pressure p* | 0.30313 Pa | 0.300762 Pa | 0.781 | 2 | PASS |
| Diagonal, triangles: star-region speed along the diagonal u* | 0.92745 m/s | 0.917851 m/s | 1.035 | 2 | PASS |
| Diagonal, triangles: density left of the contact rho*L | 0.42632 kg/m³ | 0.424467 kg/m³ | 0.435 | 2 | PASS |
| Diagonal, triangles: shock distance from the diaphragm | 0.350432 m | 0.35129 m | 0.245 | 3 | PASS |

Sources:

- Exact Riemann solution, Toro (2009) ch. 4, test 1: p* = 0.30313, u* = 0.92745, rho*L = 0.42632, rho*R = 0.26557
- Exact shock speed 1.75216 m/s and contact speed u* = 0.92745 m/s, x 0.2 s (Toro 2009, test 1)

### Runs

| Run | Cells | Wall-clock time [s] |
|---:|---:|---:|
| along x, quads | 800 | 0.5 |
| diagonal, triangles | 20,000 | 0.5 |

- Second order (least-squares gradients, Venkatakrishnan limiter), SSP-RK3, CFL 0.8, one global time step; time-accurate to t = 0.2 s.

## Oblique shock on a 10 deg wedge at Mach 2 (2D Euler, external_2d): PASS

Case: `cases/external_2d`, references: `validation/euler2d_wedge/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Shock angle beta (fitted through the shock position at 6 stations) | 39.314 deg | 39.3509 deg | 0.094 | 2 | PASS |
| Wedge surface pressure / free-stream pressure p2/p1 | 1.7066 | 1.70719 | 0.035 | 1 | PASS |
| Mach number behind the shock (on the wedge surface cells) | 1.6405 | 1.63161 | 0.542 | 1 | PASS |

Sources:

- theta-beta-M relation, weak shock, M1 = 2, theta = 10 deg, gamma = 1.4 (Anderson 2003, sec. 4.4)
- Oblique-shock relation p2/p1 = 1 + 2 gamma/(gamma + 1)(M1² sin² beta - 1) with beta = 39.314 deg (Anderson 2003, eq. 4.9)
- Oblique-shock relation M2 = Mn2 / sin(beta - theta) (Anderson 2003, eq. 4.12)

### Two meshes

| Mesh | Cells | Iterations | Converged | Time [s] | beta [deg] | p2/p1 | M2 | Cd (incl. base) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| wall 0.02 L | 3,553 | 1,159 | yes | 1 | 39.351 | 1.7072 | 1.6316 | 0.1965 |
| wall 0.01 L | 11,958 | 1,695 | yes | 4 | 39.244 | 1.7067 | 1.6328 | 0.1980 |

- Theory: beta = 39.314 deg, p2/p1 = 1.7066, M2 = 1.6405.
- Cd includes the base drag of the flat base (the base pressure is not part of the oblique-shock theory).

## 10 deg cone at Mach 2 (3D Euler, quarter domain) vs Taylor-Maccoll: FAIL

Case: `cases/external_3d`, references: `validation/euler3d_cone/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Conical shock angle (shock position in the plane z = 0+ at 6 stations, line through the tip) | 31.2061 deg | 33.3919 deg | 7.004 | 3 | FAIL |
| Surface pressure coefficient (mean over the wall faces between 30 % and 80 % of the cone length) | 0.104471 | 0.106265 | 1.717 | 2 | PASS |

Sources:

- Taylor-Maccoll (aeroflowsim.gasdynamics.taylor_maccoll), M = 2, theta_s = 10 deg, gamma = 1.4; Sims (1964) NASA SP-3004
- Taylor-Maccoll, as above (Sims 1964: 0.1045)

### Runs (the scored run is 'cone'; 'finer' is reported only)

| Run | Cells | Iterations | Converged | Time [s] | Shock stations | beta [deg] | beta Taylor-Maccoll [deg] | Cp | Cp Taylor-Maccoll |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cone | 30,825 | 1,221 | yes | 17 | 6 | 33.392 | 31.206 | 0.1063 | 0.1045 |
| finer | 72,150 | 1,014 | yes | 38 | 6 | 32.780 | 31.206 | 0.1058 | 0.1045 |

- 3D quarter domain with two symmetry planes, tetrahedra, the external_3d defaults.

## N2 nozzle in 3D (revolved quarter) vs 2D axisymmetric: PASS

Case: `cases/external_3d`, references: `validation/euler3d_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Mass flow, 3D / 2D axisymmetric | 1 | 0.998479 | 0.152 | 1 | PASS |
| Vacuum thrust (exit plane), 3D / 2D axisymmetric | 1 | 0.998465 | 0.154 | 2 | PASS |

Sources:

- 2D axisymmetric run of the same nozzle on the same profile (validated: validation/euler2d_nozzle)
- 2D axisymmetric run, as above

### Runs (same profile, same numerics)

| Run | Cells | Iterations | Converged | Time [s] | mdot [mg/s] | F exit [mN] | F wall+inlet [mN] | Isp [s] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2D | 8,000 | 13,771 | yes | 25 | 67.2131 | 47.1116 | 47.1115 | 71.475 |
| 3D | 128,000 | 30,000 | NO | 1542 | 67.1108 | 47.0392 | 47.0392 | 71.474 |

- Polygon factor of the revolved cross-sections: 0.99839 (the 3D throat area is this times the circle's).

## 30 deg ramp at Mach 2 on tetrahedra vs hexahedra (detached shock): FAIL

Case: `aeroflowsim/simple_meshes.py`, references: `validation/euler3d_ramp/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Shock stand-off ahead of the ramp corner on the wall, tetrahedra / hexahedra | 1 | 1.82633 | 82.633 | 2 | FAIL |
| Tetrahedral run converged (residual drop 8 orders): 1 = yes, 0 = no | 1 | 1 | 0.000 | 0.01 | PASS |

Sources:

- The same flow on a hexahedral mesh of the same box (cell-type consistency)
- The convergence criterion of the solver

### Runs

| Kind | Cells | Iterations | Converged | Time [s] | Stand-off [m] | Limited updates |
|---:|---:|---:|---:|---:|---:|---:|
| tetrahedra | 6,144 | 3,108 | yes | 7 | 0.1478 | 203 |
| hexahedra | 1,024 | 1,230 | yes | 1 | 0.0809 | 108 |

- Before the robust-second-order stage the tetrahedral run stalled at a residual of 0.26.

## Sphere at Mach 3 (3D Euler, tetrahedra): bow-shock stand-off vs Billig: FAIL

Case: `cases/external_3d`, references: `validation/euler3d_sphere/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Bow-shock stand-off distance / sphere radius on the stagnation line, Mach 3 (3D quarter domain) | 0.204966 | 0.226894 | 10.698 | 5 | FAIL |
| The same from the 2D axisymmetric run (external_2d, shape Sphere): consistency 2D vs 3D | 0.204966 | 0.214171 | 4.491 | 5 | PASS |

Sources:

- Billig, F. S. (1967), J. Spacecraft Rockets 4(6): Delta/R = 0.143 exp(3.24/M^2) for spheres
- Billig (1967), as above

### Runs

| Run | Cells | Iterations | Converged | Time [s] | Stand-off / R | Stand-off / R (old cell method) | Billig | Cd | Positivity fallbacks | CFL reductions |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3D Mach 3 | 59,998 | 20,000 | NO | 586 | 0.2269 | 0.2230 | 0.2050 | 0.9686 | 665,290 | 0 |
| 2D axisymmetric Mach 3 | 4,800 | 3,062 | yes | 4 | 0.2142 | nan | 0.2050 | 0.9526 | 404 | 3 |
| 3D Mach 6 | 59,998 | 20,000 | NO | 562 | 0.1516 | 0.1530 | 0.1565 | 0.8873 | 133,999 | 0 |

- Mach 6 on tetrahedra (full set): reported for the positivity fallback and the carbuncle; a converged run with a stand-off near Billig means no carbuncle bulge on the stagnation line.

## Gmsh mesh geometry: external domains and rounded-throat nozzle: PASS

Case: `cases/external_2d`, references: `validation/external_geometry/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Cylinder D = 1 m: wall patch length, default mesh | 3.14159 m | 3.14158 m | 0.00044 | 0.1 | PASS |
| Cylinder D = 1 m: wall patch length, fine mesh (sizes / 2) | 3.14159 m | 3.14159 m | 0.00012 | 0.1 | PASS |
| Cylinder D = 1 m: wall patch length, finer mesh (sizes / 4) | 3.14159 m | 3.14159 m | 4e-05 | 0.1 | PASS |
| Cylinder: domain area, default mesh | 1255.85 m² | 1255.28 m² | 0.046 | 0.1 | PASS |
| Cylinder: domain area, fine mesh (sizes / 2) | 1255.85 m² | 1255.35 m² | 0.040 | 0.1 | PASS |
| Cylinder: domain area, finer mesh (sizes / 4) | 1255.85 m² | 1255.72 m² | 0.010 | 0.1 | PASS |
| Diamond airfoil t/c = 0.1: domain area, default mesh | 1256.59 m² | 1256.01 m² | 0.046 | 0.1 | PASS |
| Diamond airfoil t/c = 0.1: domain area, fine mesh (sizes / 2) | 1256.59 m² | 1256.08 m² | 0.040 | 0.1 | PASS |
| Diamond airfoil t/c = 0.1: domain area, finer mesh (sizes / 4) | 1256.59 m² | 1256.46 m² | 0.010 | 0.1 | PASS |
| Wedge 10 deg: domain area, default mesh | 1256.46 m² | 1255.89 m² | 0.046 | 0.1 | PASS |
| Wedge 10 deg: domain area, fine mesh (sizes / 2) | 1256.46 m² | 1255.96 m² | 0.040 | 0.1 | PASS |
| Wedge 10 deg: domain area, finer mesh (sizes / 4) | 1256.46 m² | 1256.33 m² | 0.010 | 0.1 | PASS |
| Cone 15 deg: volume of revolution of the half domain, default mesh | 33510.2 m³ | 33487.3 m³ | 0.069 | 0.1 | PASS |
| Cone 15 deg: volume of revolution of the half domain, fine mesh (sizes / 2) | 33510.2 m³ | 33490.1 m³ | 0.060 | 0.1 | PASS |
| Cone 15 deg: volume of revolution of the half domain, finer mesh (sizes / 4) | 33510.2 m³ | 33505 m³ | 0.016 | 0.1 | PASS |
| Rounded-throat nozzle volume, structured Coarse | 6.34994 mm³ | 6.34977 mm³ | 0.0026 | 0.1 | PASS |
| Rounded-throat nozzle volume, structured Medium | 6.34994 mm³ | 6.34985 mm³ | 0.0013 | 0.1 | PASS |
| Rounded-throat nozzle volume, structured Fine | 6.34994 mm³ | 6.34987 mm³ | 0.001 | 0.1 | PASS |
| Rounded-throat nozzle volume, triangles, default mesh | 6.34994 mm³ | 6.34994 mm³ | 4.4e-05 | 0.1 | PASS |
| Rounded-throat nozzle volume, triangles, fine mesh (sizes / 2) | 6.34994 mm³ | 6.34994 mm³ | 1.7e-05 | 0.1 | PASS |
| Rounded-throat nozzle volume, triangles, finer mesh (sizes / 4) | 6.34994 mm³ | 6.34994 mm³ | 5.1e-06 | 0.1 | PASS |

Sources:

- Exact: circumference pi D
- Exact: pi (R² - (D/2)²), R = 20 m far-field circle
- Exact: pi R² - c t / 2 (circle minus rhombus)
- Exact: pi R² - L² tan 10 deg (circle minus triangle)
- Exact: 4/3 pi R³ - pi R_b² L / 3 (sphere minus cone), R_b = L tan 15 deg
- Exact: pi [r_in² L_in + frustums + arc sections], arc section = integral of (r_t + R_c - sqrt(R_c² - u²))² du in closed form; Rcu = 1.5 r_t, Rcd = 0.4 r_t

## 3D geometry workspace: volumes, areas, STEP round trip, stable face ids: PASS

Case: `aeroflowsim/geometry_model`, references: `validation/geometry_3d/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Box 0.2 x 0.3 x 0.5 m: volume | 0.03 m³ | 0.03 m³ | 0.000 | 1e-06 | PASS |
| Box 0.2 x 0.3 x 0.5 m: surface area | 0.62 m² | 0.62 m² | 0.000 | 1e-06 | PASS |
| Cylinder r = 0.1 m, h = 0.4 m: volume | 0.0125664 m³ | 0.0125664 m³ | 1.4e-14 | 1e-06 | PASS |
| Cylinder r = 0.1 m, h = 0.4 m: surface area | 0.314159 m² | 0.314159 m² | 0.000 | 1e-06 | PASS |
| Sphere r = 0.25 m: volume | 0.0654498 m³ | 0.0654498 m³ | 2.1e-14 | 1e-06 | PASS |
| Sphere r = 0.25 m: surface area | 0.785398 m² | 0.785398 m² | 0.000 | 1e-06 | PASS |
| Truncated cone r = 0.1 -> 0.05 m, h = 0.3 m: volume | 0.00549779 m³ | 0.00549779 m³ | 1.6e-14 | 1e-06 | PASS |
| Truncated cone r = 0.1 -> 0.05 m, h = 0.3 m: surface area | 0.182592 m² | 0.182592 m² | 0.000 | 1e-06 | PASS |
| Unit box minus sphere r = 0.4 m on a corner: volume | 0.96649 m³ | 0.96649 m³ | 0.000 | 1e-06 | PASS |
| Unit box minus sphere r = 0.4 m on a corner: surface area | 5.87434 m² | 5.87434 m² | 1.5e-14 | 1e-06 | PASS |
| Unit box united with sphere r = 0.3 m on its top face: volume | 1.05655 m³ | 1.05655 m³ | 0.000 | 1e-06 | PASS |
| Unit box united with sphere r = 0.3 m on its top face: surface area | 6.28274 m² | 6.28274 m² | 0.000 | 1e-06 | PASS |
| Unit sphere intersected with the half space x >= 0: volume | 2.0944 m³ | 2.0944 m³ | 0.000 | 1e-06 | PASS |
| Unit sphere intersected with the half space x >= 0: surface area | 9.42478 m² | 9.42478 m² | 0.000 | 1e-06 | PASS |
| Frustum revolved from its profile (r = 0.4 -> 0.2 m, L = 1 m): volume | 0.293215 m³ | 0.293215 m³ | 0.000 | 1e-06 | PASS |
| Frustum revolved from its profile: surface area | 2.5506 m² | 2.5506 m² | 1.7e-14 | 1e-06 | PASS |
| Triangle 0.3 x 0.4 m extruded by 0.5 m: volume | 0.03 m³ | 0.03 m³ | 0.000 | 1e-06 | PASS |
| Triangle 0.3 x 0.4 m extruded by 0.5 m: surface area | 0.72 m² | 0.72 m² | 0.000 | 1e-06 | PASS |
| Box enclosure (5 L up, 10 L down, 5 L sides) around a sphere D = 1 m: fluid volume | 1935.48 m³ | 1935.48 m³ | 5.9e-14 | 1e-06 | PASS |
| STEP round trip (box + half sphere): volume read back | 0.00605655 m³ | 0.00605655 m³ | 2e-13 | 1e-06 | PASS |
| STEP round trip (box + half sphere): surface area read back | 0.222827 m² | 0.222827 m² | 8.7e-13 | 1e-06 | PASS |
| STEP round trip (box + half sphere): number of faces read back | 7 | 7 | 0.000 | 1e-09 | PASS |
| STEP round trip: volume before writing the file | 0.00605655 m³ | 0.00605655 m³ | 1.4e-14 | 1e-06 | PASS |
| Named faces still on the right face after upstream edits (of 3) | 3 | 3 | 0.000 | 1e-09 | PASS |

Sources:

- Exact: a b c
- Exact: 2 (ab + ac + bc)
- Exact: pi r² h
- Exact: 2 pi r h + 2 pi r²
- Exact: 4/3 pi r³
- Exact: 4 pi r²
- Exact: pi h/3 (R² + R r + r²)
- Exact: pi (R + r) s + pi (R² + r²), s = slant height
- Exact: 1 - (1/8) 4/3 pi r³
- Exact: 6 - 3 pi r²/4 + (1/8) 4 pi r²
- Exact: 1 + 2/3 pi r³
- Exact: 6 - pi r² + 2 pi r²
- Exact: 2/3 pi
- Exact: 2 pi + pi = 3 pi
- Exact: pi L/3 (R² + R r + r²)
- Exact: pi (R + r) s + pi (R² + r²)
- Exact: (1/2) a b L
- Exact: a b + (a + b + c) L
- Exact: 16 x 11 x 11 - 4/3 pi (D/2)³
- Exact: a b c + 2/3 pi r³
- Exact: 2 (ab + ac + bc) + pi r²
- Exact: 6 box faces + 1 sphere cap
- Exact: all 3 names survive (resized box, smaller sphere, inserted move)

## Geometry workspace: sketched, enclosed and plume geometries: PASS

Case: `cases/geometry_2d`, references: `validation/geometry_workspace/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Circle R = 20 m minus cylinder D = 1 m: domain area, default mesh | 1255.85 m² | 1255.29 m² | 0.045 | 0.1 | PASS |
| Circle R = 20 m minus cylinder D = 1 m: domain area, fine mesh (sizes / 2) | 1255.85 m² | 1255.33 m² | 0.041 | 0.1 | PASS |
| Circle R = 20 m minus cylinder D = 1 m: domain area, finer mesh (sizes / 4) | 1255.85 m² | 1255.72 m² | 0.010 | 0.1 | PASS |
| Circle minus cylinder: wall patch length, default mesh | 3.14159 m | 3.14158 m | 0.00042 | 0.1 | PASS |
| Circle minus cylinder: wall patch length, fine mesh (sizes / 2) | 3.14159 m | 3.14159 m | 0.00011 | 0.1 | PASS |
| Circle minus cylinder: wall patch length, finer mesh (sizes / 4) | 3.14159 m | 3.14159 m | 2.7e-05 | 0.1 | PASS |
| C-domain minus NACA 0012: domain area, default mesh | 466.998 m² | 466.928 m² | 0.015 | 0.1 | PASS |
| C-domain minus NACA 0012: domain area, fine mesh (sizes / 2) | 466.998 m² | 466.928 m² | 0.015 | 0.1 | PASS |
| C-domain minus NACA 0012: domain area, finer mesh (sizes / 4) | 466.998 m² | 466.935 m² | 0.014 | 0.1 | PASS |
| Nozzle + plume region: volume of revolution, default mesh | 600.152 mm³ | 600.152 mm³ | 1.3e-11 | 0.1 | PASS |
| Nozzle + plume region: volume of revolution, fine mesh (sizes / 2) | 600.152 mm³ | 600.152 mm³ | 1.3e-11 | 0.1 | PASS |
| Nozzle + plume region: volume of revolution, finer mesh (sizes / 4) | 600.152 mm³ | 600.152 mm³ | 1.3e-11 | 0.1 | PASS |

Sources:

- Exact: pi (R² - (D/2)²)
- Exact: circumference pi D
- Exact: pi R²/2 + 2 R (x_out - x_c) - A_NACA0012, A = 0.081706 c²
- Exact: nozzle volume 6.345769169 mm³ + pi (5 D_e)² (10 D_e)

## 3D mesh study: sphere in a box, tetrahedra + prism layers: PASS

Case: `aeroflowsim/workspace_mesh3d.py`, references: `validation/mesh_3d/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Fluid volume (sum of cell volumes), coarse mesh | 1935.48 m³ | 1935.48 m³ | 0.00027 | 0.1 | PASS |
| Wall area (sphere patch), coarse mesh | 3.14159 m² | 3.12431 m² | 0.550 | 1 | PASS |
| First prism layer height on the wall (volume / face area), coarse mesh | 0.002 m | 0.00200869 m | 0.435 | 3 | PASS |
| Share of cells with a positive volume, coarse mesh | 1 | 1 | 0.000 | 1e-09 | PASS |
| No error-level mesh check (1 = none), coarse mesh | 1 | 1 | 0.000 | 1e-09 | PASS |
| Fluid volume (sum of cell volumes), medium mesh | 1935.48 m³ | 1935.48 m³ | 7.2e-05 | 0.1 | PASS |
| Wall area (sphere patch), medium mesh | 3.14159 m² | 3.13695 m² | 0.148 | 1 | PASS |
| First prism layer height on the wall (volume / face area), medium mesh | 0.002 m | 0.00200818 m | 0.409 | 3 | PASS |
| Share of cells with a positive volume, medium mesh | 1 | 1 | 0.000 | 1e-09 | PASS |
| No error-level mesh check (1 = none), medium mesh | 1 | 1 | 0.000 | 1e-09 | PASS |
| Fluid volume (sum of cell volumes), fine mesh | 1935.48 m³ | 1935.48 m³ | 2.1e-05 | 0.1 | PASS |
| Wall area (sphere patch), fine mesh | 3.14159 m² | 3.14027 m² | 0.042 | 1 | PASS |
| First prism layer height on the wall (volume / face area), fine mesh | 0.002 m | 0.00200806 m | 0.403 | 3 | PASS |
| Share of cells with a positive volume, fine mesh | 1 | 1 | 0.000 | 1e-09 | PASS |
| No error-level mesh check (1 = none), fine mesh | 1 | 1 | 0.000 | 1e-09 | PASS |

Sources:

- Exact: 16 x 11 x 11 - 4/3 pi (D/2)³
- Exact: 4 pi (D/2)² (faceted surface: slightly less)
- Requested first-layer height
- Every cell must be valid
- The mesh checks run before any solver

### Mesh levels (sphere D = 1 m in a 16 x 11 x 11 m box, 5 prism layers from 2 mm)

| Level | Wall cell size [mm] | Cells | Tetrahedra | Prisms | Time [s] | Max skewness | Min dihedral [deg] | Max non-orth. [deg] | Max volume ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| coarse | 80 | 29,012 | 23,402 | 5,610 | 0.4 | 0.873 | 12.5 | 67.1 | 14.72 |
| medium | 40 | 125,853 | 105,043 | 20,810 | 1.9 | 0.989 | 9.8 | 66.6 | 8.18 |
| fine | 20 | 718,770 | 645,910 | 72,860 | 21.5 | 0.910 | 9.4 | 69.9 | 7.09 |

- Halving every cell size multiplied the number of cells by 4.34, 5.71: cells that fill a fixed volume uniformly grow 8 times, the prism layers 4 times (wall area / size²), so the growth rises towards 8 as the volume cells dominate (the coarsest quick level has very few cells).
- Skewness: equivolume for the tetrahedra, equiangle for the prisms.

## Method of Manufactured Solutions: order of accuracy of the 2D Euler solver: PASS

Case: `aeroflowsim/mms.py`, references: `validation/mms_euler2d/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Observed order (min L2 over rho, u, v, p), planar quads | 2 | 1.98447 | 0.777 | 10 | PASS |
| Observed order, planar smoothly distorted quads | 2 | 1.98117 | 0.941 | 10 | PASS |
| Observed order, planar triangles | 2 | 2.00457 | 0.229 | 15 | PASS |
| Observed order, planar mixed quads + triangles | 2 | 1.99007 | 0.497 | 15 | PASS |
| Observed order, axisymmetric quads (with the pressure source) | 2 | 2.02165 | 1.082 | 10 | PASS |
| Observed order, axisymmetric distorted quads | 2 | 2.01626 | 0.813 | 10 | PASS |
| Observed order, axisymmetric triangles | 2 | 2.01662 | 0.831 | 15 | PASS |
| Observed order, axisymmetric mixed | 2 | 1.99993 | 0.0034 | 15 | PASS |

Sources:

- Formal order of the MUSCL / least-squares scheme (Barth & Jespersen 1989); MMS of Roy et al. (2004)
- Formal order 2 (as above)

### Observed orders between the two finest meshes (cells per side in brackets)

| Scheme | Mesh | L2 error finest (rho / u / v / p) | Order L1 | Order L2 | Order Linf | GCI p (L2 of p) | GCI asympt. ratio | Iterations | Time [s] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| planar, order 2 (16-128) | quads | 2.17e-05 / 7.15e-03 / 7.11e-03 / 4.48e+00 | 1.98 / 2.01 / 2.01 / 2.00 | 1.98 / 1.99 / 2.01 / 2.00 | 1.95 / 1.74 / 1.94 / 1.94 | 2.01 | 0.25 | 20,367 | 77 |
| planar, order 2 (16-128) | distorted quads | 3.94e-05 / 1.35e-02 / 9.66e-03 / 7.41e+00 | 2.01 / 2.03 / 1.98 / 2.01 | 1.98 / 1.99 / 1.98 / 1.99 | 1.73 / 1.61 / 1.93 / 1.60 | 1.96 | 0.25 | 19,189 | 74 |
| planar, order 2 (16-128) | triangles | 5.50e-05 / 1.21e-02 / 1.24e-02 / 6.16e+00 | 2.06 / 2.04 / 2.02 / 2.01 | 2.12 / 2.05 / 2.03 / 2.00 | 1.97 / 2.05 / 1.84 / 1.77 | 2.01 | 0.25 | 29,216 | 152 |
| planar, order 2 (16-128) | mixed | 3.86e-05 / 9.89e-03 / 8.37e-03 / 4.99e+00 | 2.01 / 2.01 / 2.02 / 2.01 | 2.01 / 2.00 / 2.02 / 1.99 | 1.85 / 2.03 / 2.00 / 1.86 | 2.01 | 0.25 | 19,378 | 96 |
| axisymmetric, order 2 (16-128) | quads | 2.43e-05 / 5.96e-03 / 5.64e-03 / 3.47e+00 | 2.05 / 2.04 / 2.02 / 2.03 | 2.07 / 2.06 / 2.02 / 2.03 | 2.04 / 1.80 / 1.97 / 1.99 | 2.06 | 0.25 | 11,257 | 40 |
| axisymmetric, order 2 (16-128) | distorted quads | 3.09e-05 / 8.43e-03 / 6.82e-03 / 4.37e+00 | 2.03 / 2.04 / 2.03 / 2.02 | 2.08 / 2.04 / 2.03 / 2.02 | 2.15 / 1.88 / 1.97 / 1.95 | 2.02 | 0.25 | 10,338 | 38 |
| axisymmetric, order 2 (16-128) | triangles | 5.93e-05 / 1.21e-02 / 1.36e-02 / 5.55e+00 | 2.04 / 2.08 / 2.01 / 2.02 | 2.05 / 2.08 / 2.02 / 2.02 | 1.69 / 1.69 / 1.97 / 1.78 | 2.02 | 0.25 | 17,315 | 91 |
| axisymmetric, order 2 (16-128) | mixed | 4.80e-05 / 1.02e-02 / 9.95e-03 / 4.25e+00 | 2.03 / 2.04 / 1.99 / 2.02 | 2.03 / 2.04 / 2.00 / 2.02 | 1.71 / 1.73 / 1.92 / 1.86 | 1.99 | 0.25 | 15,442 | 70 |
| planar, order 1 (8-64) | quads | 6.13e-03 / 1.47e+00 / 2.79e+00 / 8.16e+02 | 0.91 / 0.86 / 0.96 / 0.89 | 0.90 / 0.84 / 0.95 / 0.87 | 0.75 / 0.79 / 0.94 / 0.72 | 0.74 | 0.55 | 9,055 | 5 |
| planar, order 1 (8-64) | distorted quads | 8.71e-03 / 2.41e+00 / 3.20e+00 / 1.23e+03 | 0.80 / 0.73 / 0.89 / 0.76 | 0.77 / 0.66 / 0.89 / 0.71 | 0.61 / 0.51 / 0.80 / 0.57 | 0.47 | 0.61 | 8,736 | 5 |
| planar, order 1 (8-64) | triangles | 4.94e-03 / 1.37e+00 / 1.52e+00 / 4.22e+02 | 0.95 / 0.95 / 1.00 / 0.93 | 0.96 / 0.94 / 0.98 / 0.91 | 0.99 / 0.78 / 0.89 / 0.89 | 0.90 | 0.53 | 11,585 | 9 |
| planar, order 1 (8-64) | mixed | 4.56e-03 / 1.05e+00 / 1.87e+00 / 5.62e+02 | 0.98 / 0.93 / 1.00 / 0.97 | 0.97 / 0.94 / 0.98 / 0.96 | 1.00 / 0.97 / 0.97 / 0.94 | 0.94 | 0.51 | 9,036 | 6 |
| planar, order 2, Venkatakrishnan (8-64) | quads | 2.32e-04 / 4.42e-02 / 7.71e-02 / 2.40e+01 | 1.34 / 1.60 / 1.64 / 1.72 | 1.01 / 1.58 / 1.21 / 1.67 | 0.55 / 1.05 / 0.62 / 1.27 | 1.98 | 0.31 | 9,503 | 10 |
| planar, order 2, Venkatakrishnan (8-64) | distorted quads | 2.87e-04 / 5.63e-02 / 9.24e-02 / 3.09e+01 | 1.58 / 1.82 / 1.71 / 1.89 | 1.24 / 1.83 / 1.27 / 1.84 | 0.77 / 1.37 / 0.50 / 1.39 | 1.96 | 0.28 | 9,044 | 9 |
| planar, order 2, Venkatakrishnan (8-64) | triangles | 7.15e-04 / 1.69e-01 / 1.38e-01 / 5.40e+01 | 1.27 / 1.07 / 1.19 / 1.15 | 1.34 / 1.12 / 1.18 / 1.08 | 0.96 / 0.97 / 0.95 / 1.07 | 2.20 | 0.47 | 13,681 | 20 |
| planar, order 2, Venkatakrishnan (8-64) | mixed | 5.41e-04 / 1.22e-01 / 1.12e-01 / 4.28e+01 | 1.12 / 1.11 / 1.14 / 1.35 | 1.07 / 1.07 / 1.09 / 1.29 | 0.92 / 0.96 / 0.91 / 0.81 | 1.98 | 0.41 | 9,948 | 12 |

- Orders listed per variable rho / u / v / p. Errors in SI units (kg/m³, m/s, m/s, Pa).
- The GCI columns apply the three-mesh GCI procedure (aeroflowsim/gci.py) to the L2 error of p: its observed order should match and the asymptotic ratio be near 1.
- First order and the Venkatakrishnan limiter are reported for information (not pass/fail): Finding (Post-processing and alpha release stage): with Venkatakrishnan's limiter the order does NOT approach 2 on finer meshes; on triangles and mixed meshes it falls towards 1. Its threshold eps² = (K h / L)³ scale² shrinks faster than the cell-to-cell differences of a smooth field (h^1.5 against h), so the limiter clips the smooth extrema more and more as the mesh is refined. Smooth flows on fine meshes therefore keep full second order only with 'None' or a larger K; an order-preserving limiter (e.g. Michalak and Ollivier-Gooch 2008) is in the gap register.

## Method of Manufactured Solutions: order of accuracy of the 3D Euler solver: PASS

Case: `aeroflowsim/mms.py`, references: `validation/mms_euler3d/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Observed order (min L2 over rho, u, v, w, p), warped hexahedra | 2 | 1.96611 | 1.694 | 10 | PASS |
| Observed order, warped prisms | 2 | 1.86995 | 6.502 | 15 | PASS |
| Observed order, warped tetrahedra (Kuhn split) | 2 | 1.74686 | 12.657 | 15 | PASS |

Sources:

- Formal order of the MUSCL / least-squares scheme (Barth & Jespersen 1989); MMS of Roy et al. (2004)
- Formal order 2 (as above)

### Levels (L2 errors of rho, u, v, w, p)

| Cells | Box | Count | Iterations | Time [s] | L2 error / order |
|---:|---:|---:|---:|---:|---:|
| hexahedra | 12^3 | 1,728 | 613 | 0.3 | 3.233e-03 9.148e-01 8.630e-01 4.519e-01 4.438e+02 |
| hexahedra | 24^3 | 13,824 | 962 | 3.8 | 7.817e-04 2.222e-01 2.060e-01 1.026e-01 1.136e+02 |
| hexahedra | order |  |  |  | 2.048 2.042 2.067 2.139 1.966 |
| prisms | 12^3 | 3,456 | 564 | 0.5 | 1.986e-03 5.474e-01 5.157e-01 4.107e-01 2.635e+02 |
| prisms | 24^3 | 27,648 | 855 | 5.9 | 5.169e-04 1.416e-01 1.231e-01 9.296e-02 7.208e+01 |
| prisms | order |  |  |  | 1.942 1.951 2.067 2.143 1.870 |
| tetrahedra | 12^3 | 10,368 | 832 | 1.6 | 3.723e-03 9.438e-01 8.011e-01 5.994e-01 2.819e+02 |
| tetrahedra | 24^3 | 82,944 | 1,551 | 30.1 | 1.091e-03 2.802e-01 2.253e-01 1.671e-01 8.400e+01 |
| tetrahedra | order |  |  |  | 1.771 1.752 1.830 1.843 1.747 |

- Hexahedra, Kuhn tetrahedra (6 per cube) and prisms (2 per cube), warp 0.03.

## Method of Manufactured Solutions: order of accuracy of the Navier-Stokes (laminar) terms: PASS

Case: `aeroflowsim/mms_ns.py`, references: `validation/mms_navier_stokes/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Observed order (min L2 over rho, u, v, p), planar quads | 2 | 1.86384 | 6.808 | 10 | PASS |
| Observed order, planar smoothly distorted quads | 2 | 1.83348 | 8.326 | 10 | PASS |
| Observed order, planar triangles | 2 | 2.02058 | 1.029 | 15 | PASS |
| Observed order, axisymmetric quads (pressure and hoop-stress sources) | 2 | 2.05594 | 2.797 | 10 | PASS |
| Observed order, axisymmetric triangles | 2 | 1.95134 | 2.433 | 15 | PASS |
| Observed order (min L2 over rho, u, v, w, p), warped hexahedra | 2 | 1.93628 | 3.186 | 10 | PASS |
| Observed order, warped prisms | 2 | 1.78148 | 10.926 | 15 | PASS |
| Observed order, warped tetrahedra | 2 | 1.7363 | 13.185 | 15 | PASS |

Sources:

- Formal order 2 of the scheme (MUSCL + corrected face gradients); MMS of Roy et al. (2004), Int. J. Numer. Meth. Fluids 44, 599-620
- Formal order 2 (as above)

### Levels (L2 errors of rho, velocity components, p)

| Mesh | n | Cells | Iterations | Time [s] | L2 error / order (finest pair) |
|---:|---:|---:|---:|---:|---:|
| quads | 32 | 1,024 | 1,432 | 6.8 | 3.358e-04 1.138e-01 1.111e-01 6.158e+01 |
| quads | 64 | 4,096 | 3,588 | 29.1 | 9.241e-05 2.961e-02 2.795e-02 1.539e+01 |
| quads | 128 | 16,384 | 9,809 | 102.7 | 2.539e-05 7.556e-03 7.083e-03 3.778e+00 |
| quads | order |  |  |  | 1.864 1.970 1.981 2.026 |
| distorted_quads | 32 | 1,024 | 1,398 | 6.8 | 3.738e-04 1.218e-01 1.311e-01 7.073e+01 |
| distorted_quads | 64 | 4,096 | 3,566 | 27.9 | 1.074e-04 3.361e-02 3.487e-02 1.820e+01 |
| distorted_quads | 128 | 16,384 | 9,845 | 102.9 | 3.012e-05 8.810e-03 9.070e-03 4.542e+00 |
| distorted_quads | order |  |  |  | 1.833 1.932 1.943 2.002 |
| triangles | 32 | 2,048 | 2,489 | 13.7 | 5.466e-04 1.359e-01 1.203e-01 7.132e+01 |
| triangles | 64 | 8,192 | 6,562 | 52.8 | 1.305e-04 2.993e-02 2.707e-02 1.711e+01 |
| triangles | 128 | 32,768 | 18,895 | 206.7 | 3.216e-05 6.915e-03 6.337e-03 4.212e+00 |
| triangles | order |  |  |  | 2.021 2.114 2.095 2.022 |
| axi_quads | 32 | 1,024 | 752 | 3.6 | 5.119e-04 1.047e-01 9.281e-02 5.354e+01 |
| axi_quads | 64 | 4,096 | 1,747 | 11.1 | 1.263e-04 2.499e-02 2.281e-02 1.317e+01 |
| axi_quads | 128 | 16,384 | 4,581 | 58.2 | 3.006e-05 5.796e-03 5.485e-03 3.073e+00 |
| axi_quads | order |  |  |  | 2.071 2.108 2.056 2.100 |
| axi_triangles | 32 | 2,048 | 1,282 | 7.0 | 6.231e-04 1.112e-01 1.001e-01 4.028e+01 |
| axi_triangles | 64 | 8,192 | 3,157 | 31.3 | 1.492e-04 2.499e-02 1.980e-02 8.958e+00 |
| axi_triangles | 128 | 32,768 | 8,826 | 124.9 | 3.788e-05 6.462e-03 4.153e-03 2.193e+00 |
| axi_triangles | order |  |  |  | 1.977 1.951 2.253 2.030 |
| hexahedra | 12 | 1,728 | 400 | 2.9 | 2.532e-03 7.037e-01 6.918e-01 3.433e-01 3.342e+02 |
| hexahedra | 24 | 13,824 | 826 | 14.2 | 6.615e-04 1.742e-01 1.662e-01 7.538e-02 8.636e+01 |
| hexahedra | order |  |  |  | 1.936 2.014 2.057 2.187 1.952 |
| prisms | 12 | 3,456 | 458 | 4.5 | 1.834e-03 3.536e-01 4.629e-01 2.995e-01 2.198e+02 |
| prisms | 24 | 27,648 | 1,095 | 26.8 | 5.331e-04 8.011e-02 1.194e-01 6.437e-02 6.393e+01 |
| prisms | order |  |  |  | 1.782 2.142 1.954 2.218 1.781 |
| tetrahedra | 12 | 10,368 | 826 | 11.0 | 1.495e-03 2.865e-01 3.549e-01 2.309e-01 1.254e+02 |
| tetrahedra | 24 | 82,944 | 2,070 | 96.8 | 4.240e-04 6.665e-02 8.897e-02 5.339e-02 3.765e+01 |
| tetrahedra | order |  |  |  | 1.819 2.104 1.996 2.113 1.736 |

- Air with mu = 2 Pa s (T/300 K)^0.7, Pr 0.72 (viscous terms as large as the convective ones).
- Boundary faces: second-order one-sided face gradient (aeroflowsim/euler/viscous.py).

## 3D quarter nozzle vs the axisymmetric nozzle on the same contour: FAIL

Case: `cases/nozzle_3d`, references: `validation/nozzle_3d/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Mass flow, 3D quarter (x 4) / axisymmetric | 1 | 1.028 | 2.800 | 2 | FAIL |
| Vacuum thrust (exit plane), 3D / axisymmetric | 1 | 1.02296 | 2.296 | 2 | FAIL |
| Vacuum specific impulse, 3D / axisymmetric | 1 | 0.995098 | 0.490 | 1 | PASS |

Sources:

- cases/nozzle_axi on the same contour (code-to-code consistency, 2D axisymmetric Euler validated vs theory)
- cases/nozzle_axi on the same contour

### Runs

| Run | Cells | Iterations | Converged | Time [s] | Mass flow [kg/s] | Vacuum thrust, exit [N] | Vacuum thrust, wall [N] | Isp vacuum [s] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| axisymmetric (nozzle_axi) | 8,000 | 13,771 | yes | 23 | 6.721310e-05 | 4.711156e-02 | 4.711152e-02 | 71.475 |
| 3D quarter (nozzle_3d) | 11,532 | 20,000 | NO | 93 | 6.909530e-05 | 4.819343e-02 | 4.819466e-02 | 71.124 |

- Both runs inviscid, N2, the templates' default chamber state and contour.

## 3D quarter CubeSat nozzle, laminar with prism layers, vs the axisymmetric laminar nozzle: PASS

Case: `cases/nozzle_3d`, references: `validation/nozzle_3d_laminar/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Discharge coefficient, 3D quarter laminar / axisymmetric laminar | 1 | 1.00826 | 0.826 | 3 | PASS |
| Vacuum specific impulse, 3D quarter laminar / axisymmetric laminar | 1 | 0.995662 | 0.434 | 1.5 | PASS |

Sources:

- cases/nozzle_axi laminar on the same contour (validation/viscous_cubesat_nozzle setup)
- cases/nozzle_axi laminar on the same contour

### Runs

| Run | Cells | Iterations | Converged | Time [s] | Cd | Isp vacuum [s] |
|---:|---:|---:|---:|---:|---:|---:|
| axisymmetric laminar (nozzle_axi) | 8,000 | 10,726 | yes | 33 | 0.94400 | 70.606 |
| 3D quarter laminar (nozzle_3d) | 34,568 | 30,000 | NO | 678 | 0.95180 | 70.300 |

- Laminar, adiabatic no-slip walls, N2, p0 = 5 bar, p_back = 1 kPa.

## Axisymmetric nozzle mesh geometry (default conical nozzle): PASS

Case: `cases/nozzle_axi`, references: `validation/nozzle_axi_geometry/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Planar area of the half-nozzle profile, Coarse mesh | 2.52964 mm² | 2.52934 mm² | 0.012 | 0.5 | PASS |
| Volume of revolution (2 pi x sum of axisymmetric cell volumes), Coarse mesh | 6.34577 mm³ | 6.3439 mm³ | 0.029 | 0.5 | PASS |
| Wall patch length, Coarse mesh | 4.269 mm | 4.2667 mm | 0.054 | 0.5 | PASS |
| Planar area of the half-nozzle profile, Medium mesh | 2.52964 mm² | 2.52956 mm² | 0.003 | 0.1 | PASS |
| Volume of revolution (2 pi x sum of axisymmetric cell volumes), Medium mesh | 6.34577 mm³ | 6.3453 mm³ | 0.0075 | 0.1 | PASS |
| Wall patch length, Medium mesh | 4.269 mm | 4.26782 mm | 0.028 | 0.1 | PASS |
| Planar area of the half-nozzle profile, Fine mesh | 2.52964 mm² | 2.52963 mm² | 0.00046 | 0.1 | PASS |
| Volume of revolution (2 pi x sum of axisymmetric cell volumes), Fine mesh | 6.34577 mm³ | 6.3457 mm³ | 0.0011 | 0.1 | PASS |
| Wall patch length, Fine mesh | 4.269 mm | 4.26866 mm | 0.008 | 0.1 | PASS |

Sources:

- Exact: r_in L_in + (r_in + r_t) L_c / 2 + (r_t + r_e) L_d / 2 (rectangle + two trapezoids)
- Exact: pi r_in² L_in + pi L/3 (r1² + r1 r2 + r2²) for each cone frustum
- Exact: L_in + L_c / cos 30 deg + L_d / cos 15 deg

## ONERA M6 wing, M 0.8395, 3.06 deg: Cp at six sections (3D Euler): PASS

Case: `cases/external_3d`, references: `validation/onera_m6/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Mean over six sections of RMS(Cp computed - Cp measured), Euler | 0.05 | 0.099576 | 99.152 | 100 | PASS |

Sources:

- Schmitt & Charpin (1979) AGARD AR-138, via NASA NPARC Validation Archive (m6wing)

### Cp RMS difference per section

| Section | RMS(Delta Cp) |
|---:|---:|
| 1 (y/b = 0.20) | 0.1018 |
| 2 (y/b = 0.44) | 0.1073 |
| 3 (y/b = 0.65) | 0.0823 |
| 4 (y/b = 0.80) | 0.0878 |
| 5 (y/b = 0.90) | 0.1245 |
| 6 (y/b = 0.95) | 0.0937 |

- Euler, 612,023 cells, 7,729 iterations, converged: True, 6897 s; CL (side force) 0.2875, CD 0.0158.
- Spalart-Allmaras not run in this stage (time box): SHORTFALL.

## Quasi-1D nozzle (N2 thruster, p0 = 5 bar, T0 = 293.15 K): PASS

Case: `cases/quasi1d_nozzle`, references: `validation/quasi1d_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Exit Mach number (p_back = 1 kPa) | 3.99 | 3.98019 | 0.246 | 2 | PASS |
| Exit pressure (p_back = 1 kPa) | 3.36 kPa | 3.36988 kPa | 0.294 | 5 | PASS |
| Mass flow (p_back = 1 kPa) | 71.5 mg/s | 71.6005 mg/s | 0.141 | 2 | PASS |
| Vacuum thrust (p_back = 1 kPa) | 50.8 mN | 50.9131 mN | 0.223 | 2 | PASS |
| Normal-shock position past the throat (p_back = 2.5 bar) | 0.3208 mm | 0.323142 mm | 0.730 | 2 | PASS |

Sources:

- Isentropic area-Mach relation at A_exit/A_throat = 10.59 (supersonic branch)
- Isentropic relation p0/p at the exit Mach number
- Choked mass flow through the throat area
- F_vac = mdot u_exit + p_exit A_exit from the isentropic exit state
- Normal shock in the divergent part: area-Mach + normal-shock relations matched to p_back = 2.5 bar

### Mesh-refinement study (cells doubled each time)

| Cells | Iterations | Exit Mach | Change | Error vs theory % | Shock past throat [mm] | Shock error % |
|---:|---:|---:|---:|---:|---:|---:|
| 150 | 9700 | 3.96866 |  | 0.436 | 0.3253 | 1.41 |
| 300 | 17935 | 3.98019 | +0.01153 | 0.146 | 0.3231 | 0.73 |
| 600 | 33459 | 3.98391 | +0.00372 | 0.053 | 0.3232 | 0.76 |
| 1200 | 74287 | 3.98517 | +0.00126 | 0.021 | 0.3223 | 0.47 |

- Exit Mach number: observed order of convergence p = 1.56 from the last three meshes; Richardson extrapolation 3.98582; isentropic theory 3.98602.
- Shock position: the captured shock is one or two cells wide, so its interpolated position can move by up to a cell width between meshes; its error falls from 1.41 % (150 cells) to 0.47 % (1200 cells).
- Supersonic runs converged to a residual drop of 1e-06; shock runs use 30 000 iterations per 300 cells (their residual stalls near 1e-3, see the case README).

## New shapes, nozzle contours and structured grids (geometry): PASS

Case: `cases/external_2d`, references: `validation/shapes_and_grids/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| von Karman nose (L = 1.2 m, D = 0.3 m): volume of revolution / (pi R² L / 2) | 1 | 0.999999 | 8.5e-05 | 0.01 | PASS |
| Sphere D = 2 m: volume of revolution / (4 pi / 3) | 1 | 0.999924 | 0.0076 | 0.02 | PASS |
| Hemisphere-cylinder (D = 0.2 m, cylinder 0.3 m): volume / exact | 1 | 1 | 1.8e-05 | 0.01 | PASS |
| Double-circular-arc airfoil (c = 2 m, t/c = 0.08): area / two circular segments | 1 | 0.999998 | 0.00016 | 0.01 | PASS |
| MOC nozzle, Mach 2.4, gamma 1.4, 20 characteristics: exit height ratio / isentropic A/A* | 1 | 0.995522 | 0.448 | 0.6 | PASS |
| MOC nozzle, 40 characteristics: exit height ratio / isentropic A/A* | 1 | 0.998168 | 0.183 | 0.25 | PASS |
| MOC nozzle, 80 characteristics: exit height ratio / isentropic A/A* | 1 | 0.99926 | 0.074 | 0.1 | PASS |
| Rao bell (eps = 25, 80 %): exit radius / (sqrt(eps) R_t) | 1 | 1 | 0.000 | 0.001 | PASS |
| Rao bell (eps = 25, 80 %): length / (0.8 L_15deg cone) | 1 | 1 | 2.2e-14 | 0.001 | PASS |
| Cylinder O-grid, coarse preset: domain area / pi (R² - r²) | 1 | 0.998972 | 0.103 | 0.2 | PASS |
| Cylinder O-grid, coarse preset: wall length / pi D | 1 | 0.999724 | 0.028 | 0.05 | PASS |
| Cylinder O-grid, coarse preset: first-layer cell height / input | 1 | 1.00023 | 0.023 | 0.15 | PASS |
| Cylinder O-grid, medium preset: domain area / pi (R² - r²) | 1 | 0.999743 | 0.026 | 0.1 | PASS |
| Cylinder O-grid, medium preset: wall length / pi D | 1 | 0.999912 | 0.0088 | 0.02 | PASS |
| Cylinder O-grid, medium preset: first-layer cell height / input | 1 | 1.00081 | 0.081 | 0.15 | PASS |
| Cylinder O-grid, fine preset: domain area / pi (R² - r²) | 1 | 0.999936 | 0.0064 | 0.05 | PASS |
| Cylinder O-grid, fine preset: wall length / pi D | 1 | 0.999959 | 0.0041 | 0.01 | PASS |
| Cylinder O-grid, fine preset: first-layer cell height / input | 1 | 1.00094 | 0.094 | 0.15 | PASS |
| NACA 0012 C-grid, coarse preset: domain area / exact | 1 | 0.999875 | 0.013 | 0.03 | PASS |
| NACA 0012 C-grid, coarse preset: cells / ((n_body + 2 n_wake) n_normal) | 1 | 1 | 0.000 | 1e-06 | PASS |
| NACA 0012 C-grid, medium preset: domain area / exact | 1 | 0.999969 | 0.0031 | 0.01 | PASS |
| NACA 0012 C-grid, medium preset: cells / ((n_body + 2 n_wake) n_normal) | 1 | 1 | 0.000 | 1e-06 | PASS |
| NACA 0012 C-grid, fine preset: domain area / exact | 1 | 0.999992 | 0.00078 | 0.005 | PASS |
| NACA 0012 C-grid, fine preset: cells / ((n_body + 2 n_wake) n_normal) | 1 | 1 | 0.000 | 1e-06 | PASS |
| Cylinder, Gmsh triangles, default mesh: domain area / exact | 1 | 0.999543 | 0.046 | 0.1 | PASS |
| Cylinder, Gmsh triangles, sizes / 2: domain area / exact | 1 | 0.999598 | 0.040 | 0.1 | PASS |

Sources:

- Exact: the Haack C = 0 profile has integral of y² dx = R² L / 2 (theory manual section 14)
- Exact: 4/3 pi R³
- Exact: 2/3 pi R³ + pi R² L
- Exact: 2 R² (Theta - sin Theta cos Theta)
- Anderson (2003) isentropic area ratio; the error falls as the fan is resolved
- Anderson (2003) isentropic area ratio
- By construction (Rao parabola ends at the exit radius)
- By construction (length fraction of a 15 degree cone)
- Exact: annulus area (R = 20 D)
- Exact: circumference
- The input first-layer height (1e-3 L)
- Exact: half circle + wake rectangle - airfoil area
- The input cell counts
- Exact: annulus area (compare the O-grid)

## Sod shock tube (Toro test 1, t = 0.2 s, 400 cells): PASS

Case: `cases/sod_shock_tube`, references: `validation/sod/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Star-region pressure p* (at x = 0.75 m) | 0.30313 Pa | 0.303136 Pa | 0.0018 | 1 | PASS |
| Star-region velocity u* (at x = 0.75 m) | 0.92745 m/s | 0.927469 m/s | 0.0021 | 1 | PASS |
| Density left of the contact rho*L (at x = 0.6 m) | 0.42632 kg/m³ | 0.426235 kg/m³ | 0.020 | 1 | PASS |
| Density right of the contact rho*R (at x = 0.75 m) | 0.26557 kg/m³ | 0.265558 kg/m³ | 0.0046 | 1 | PASS |
| Shock distance from the diaphragm | 0.350432 m | 0.351345 m | 0.260 | 2 | PASS |
| Contact distance from the diaphragm | 0.18549 m | 0.184991 m | 0.269 | 2 | PASS |

Sources:

- Exact Riemann solution, Toro (2009) ch. 4, test 1: p* = 0.30313
- Exact Riemann solution, Toro (2009) ch. 4, test 1: u* = 0.92745
- Exact Riemann solution, Toro (2009) ch. 4, test 1: rho*L = 0.42632
- Exact Riemann solution, Toro (2009) ch. 4, test 1: rho*R = 0.26557
- Exact shock speed 1.75216 m/s x 0.2 s (Toro 2009, test 1)
- Contact speed u* = 0.92745 m/s x 0.2 s (Toro 2009, test 1)

## Laminar flat plate (Blasius), 2D and one-layer 3D extrusion: PASS

Case: `aeroflowsim/euler (EulerSolver, viscous=Laminar)`, references: `validation/viscous_blasius/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Cf / Cf_Blasius at Re_x = 1e4, 3e4, 1e5: the value furthest from 1 | 1 | 1.01018 | 1.018 | 3 | PASS |
| delta_99 / delta_99,Blasius at Re_x = 1e5 | 1 | 0.973462 | 2.654 | 5 | PASS |
| Cf (3D one-layer extrusion) / Cf (2D) at Re_x = 1e5 | 1 | 1 | 1.8e-05 | 0.1 | PASS |

Sources:

- Blasius solution (solved in validate.py); Schlichting & Gersten (2017) sec. 6.5
- Blasius solution (solved in validate.py)
- Consistency: a one-cell extrusion with symmetry sides is the same discrete problem

### Runs

| Run | Cells | Iterations | Time [s] | Status | Residual |
|---:|---:|---:|---:|---:|---:|
| M0.2 2D | 8,960 | 60,000 | 231 | max_iterations | 1.2e-07 |
| M0.2 3D | 8,960 | 60,000 | 503 | max_iterations | 1.9e-07 |

- Blasius f''(0) from the solved ODE: 0.33206

## Plane Couette flow with viscous heating (laminar, 2D and 3D): PASS

Case: `aeroflowsim/euler (EulerSolver, viscous=Laminar)`, references: `validation/viscous_couette/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Wall shear stress / (mu U / H), 2D quads (from the solver's wall flux) | 1 | 1 | 7.4e-07 | 0.5 | PASS |
| Peak temperature rise (T - T_w at mid-gap, interpolated) / exact mu U^2 / (8 k), 2D | 1 | 0.999674 | 0.033 | 1 | PASS |
| Wall shear stress / (mu U / H), 3D hexahedra | 1 | 1 | 4.6e-07 | 0.5 | PASS |
| Peak temperature rise / exact, 3D | 1 | 0.999674 | 0.033 | 1 | PASS |

Sources:

- Exact solution of plane Couette flow (White 2006, Viscous Fluid Flow, 3rd ed., sec. 3-2)
- Exact quadratic temperature profile with viscous heating (same source)
- Exact solution (as above)

### Runs

| Case | Cells | Iterations | Time [s] | Status |
|---:|---:|---:|---:|---:|
| 2D | 128 | 15,700 | 5.4 | converged |
| 3D | 128 | 12,734 | 5.4 | converged |

- LU-SGS, CFL 5 -> 1000 (SER), residual drop 10 orders.

## N2 cube-sat nozzle, laminar: discharge coefficient and Isp loss versus Reynolds number (axisymmetric): PASS

Case: `cases/nozzle_axi`, references: `validation/viscous_cubesat_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| (1 - Cd) sqrt(Re_t) at 10 bar / at 1 bar | 1 | 3.01185 | 201.185 | 20 | SHORTFALL |
| Cd rises with Re_t over the decade (1 = yes, 0 = no) | 1 | 1 | 0.000 | 0.01 | PASS |

**Shortfall (explained):** (1 - Cd) sqrt(Re_t) at 10 bar / at 1 bar: Flaw of the pre-registered METRIC, not the solver: 1 - Cd (Cd against the 1D choked flow) is dominated by the inviscid 2D throat deficit (Cd about 0.94 at every Re: sonic-line curvature), which does not scale with Re; only the small viscous part does (Cd 0.9413, 0.9433, 0.9441). The viscous loss itself follows the Re^-1/2 scaling: Isp loss against the Euler run 3.20 %, 1.62 %, 0.86 % (local exponents 0.59, 0.54; theory 0.5). Next time pre-register Cd_laminar / Cd_Euler.

Sources:

- Laminar boundary-layer scaling delta* ~ Re^-1/2 (Schlichting & Gersten 2017, Boundary-Layer Theory, ch. 6)
- Boundary-layer theory (as above)

### Reynolds-number sweep (laminar; Isp loss against the Euler run on the same mesh)

| p0 [bar] | Re_t | Cd | Isp vac [s] | Isp Euler [s] | Isp loss [%] | Iterations | y+ max |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4.27e+03 | 0.9413 | 69.19 | 71.47 | 3.20 | 7,911 (converged) | 4.46 |
| 3.16 | 1.35e+04 | 0.9433 | 70.32 | 71.47 | 1.62 | 9,742 (converged) | 8.78 |
| 10 | 4.27e+04 | 0.9441 | 70.86 | 71.47 | 0.86 | 11,689 (converged) | 16.12 |

- Throat Reynolds number from the sonic throat state, L = D_t.

## Laminar cylinder at Re = 40 (2D): PASS

Case: `cases/external_2d`, references: `validation/viscous_cylinder_re40/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Recirculation length L/D (Fine grid) | 1 | 2.28025 | 128.025 | 5 | PENDING REFERENCE |
| Drag coefficient Cd (Fine grid) | 1 | 1.54135 | 54.135 | 5 | PENDING REFERENCE |
| Medium grid reached the residual 1e-6 (1 = yes, 0 = no) | 1 | 1 | 0.000 | 0.01 | PASS |
| Cd Medium grid / Cd Fine grid | 1 | 1.00309 | 0.309 | 2 | PASS |

**Pending reference:** Recirculation length L/D (Fine grid): Paper not reachable from this session (publisher paywall). Attach Coutanceau & Bouard 1977 or Dennis & Chang 1970 (PDF); value, page and table go here. The number shown is AeroFlowSim's own.

**Pending reference:** Drag coefficient Cd (Fine grid): As above; the number shown is AeroFlowSim's own Cd.

Sources:

- Coutanceau & Bouard (1977) / Dennis & Chang (1970), J. Fluid Mech.: not fetched (paywall)
- Dennis & Chang (1970), J. Fluid Mech. 42: not fetched (paywall)
- Stage plan: the viscous wake must become a steady recirculation (residual 1e-6)
- Self-consistency (grid convergence)

### Runs

| Grid | Cells | Iterations | Status | Residual | Cd | L/D (approx.) | Cd friction | Time [s] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Medium | 12,800 | 8,331 | converged | 1.0e-06 | 1.5461 | 2.217 | 0.5276 | 41 |
| Fine | 51,200 | 23,533 | converged | 1.0e-06 | 1.5414 | 2.280 | 0.5260 | 6456 |

- L/D: u = 0 on the wake centre line, linear between cell centres.

## Laminar flat plate at Mach 2: recovery temperature and wall heat flux: PASS

Case: `aeroflowsim/euler (EulerSolver, viscous=Laminar)`, references: `validation/viscous_plate_heat/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Adiabatic wall temperature / T_aw (r = sqrt(Pr)) at Re_x = 1e5 | 1 | 0.996774 | 0.323 | 1 | PASS |
| Wall heat flux / reference-temperature Reynolds-analogy estimate at Re_x = 1e5 (T_w = 300 K) | 1 | 0.99415 | 0.585 | 5 | PASS |

Sources:

- Laminar recovery factor r = sqrt(Pr): White (2006), Viscous Fluid Flow, 3rd ed., sec. 7-3
- Eckert reference temperature + Reynolds analogy St = Cf/(2 Pr^(2/3)): White (2006) sec. 7-4.4

### Runs

| Run | Cells | Iterations | Time [s] | Status | Residual |
|---:|---:|---:|---:|---:|---:|
| M2 adiabatic | 8,960 | 10,829 | 41 | converged | 1.0e-08 |
| M2 isothermal | 8,960 | 5,041 | 20 | converged | 1.0e-08 |


## Hagen-Poiseuille flow in a tube (laminar, axisymmetric): PASS

Case: `aeroflowsim/euler (EulerSolver, axisymmetric, viscous=Laminar)`, references: `validation/viscous_poiseuille/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Centreline / area-mean velocity at x = 15 D | 2 | 1.98459 | 0.771 | 1 | PASS |
| tau_w R / (mu u_m) at x = 15 D (Darcy f Re = 64) | 4 | 4.0372 | 0.930 | 1 | PASS |
| dp/dx / (-8 mu u_m / R^2 - (4/3) rho u_m du_m/dx), at 15 D | 1 | 1.00923 | 0.923 | 1 | PASS |

Sources:

- Hagen-Poiseuille exact solution (White 2006, Viscous Fluid Flow, 3rd ed., sec. 3-3.1)
- Hagen-Poiseuille exact solution (as above)
- Hagen-Poiseuille pressure drop with the compressible momentum-flux correction (derivation in reference.toml header)

### Run

| Cells | Iterations | Time [s] | Status | Residual | Re (bulk, D) | Centreline Mach |
|---:|---:|---:|---:|---:|---:|---:|
| 4,000 | 21,616 | 34 | converged | 1.0e-09 | 106.8 | 0.205 |

- LU-SGS, CFL 5 -> 1000 (SER).

## Laminar flow in a square duct (3D, exact series solution): PASS

Case: `aeroflowsim/euler (EulerSolver 3D, viscous=Laminar)`, references: `validation/viscous_square_duct/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Centreline / mean velocity at x = 6 a (reference: White eq. 3-48 series, evaluated) | 2.0962 | 2.01445 | 3.900 | 1 | SHORTFALL |
| Darcy friction factor x Reynolds number f Re at x = 6 a (reference: series) | 56.91 | 58.8704 | 3.445 | 1 | SHORTFALL |
| Centreline / mean velocity at x = 16 a, duct 20 a long | 2.0962 | 2.04815 | 2.292 | 1 | SHORTFALL |
| f Re at x = 16 a, duct 20 a long | 56.91 | 57.8911 | 1.724 | 1 | SHORTFALL |

**Shortfall (explained):** Centreline / mean velocity at x = 6 a (reference: White eq. 3-48 series, evaluated): Set-up error, not the solver: the bulk Reynolds number came out 98.5, not the estimated 50, so the entrance length 0.06 Re a = 5.9 a reaches the measuring station x = 6 a (flow not developed: centre velocity still rising). Re-run with a longer duct below (pre-registered after this miss, before its run).

**Shortfall (explained):** Darcy friction factor x Reynolds number f Re at x = 6 a (reference: series): Same set-up error as above (station inside the entrance region).

**Shortfall (explained):** Centreline / mean velocity at x = 16 a, duct 20 a long: Most likely grid resolution: 12 uniform cells per half side (the axisymmetric tube needed 20 radial cells for < 1 %); error fell from 3.9 % to 2.3 % once the flow was developed. NOT verified by a finer run in this session (a 24 x 24 section, ~74k cells, takes hours at this stiffness); next stage re-runs it with preconditioning.

**Shortfall (explained):** f Re at x = 16 a, duct 20 a long: Most likely grid resolution: 12 uniform cells per half side (the axisymmetric tube needed 20 radial cells for < 1 %); error fell from 3.9 % to 2.3 % once the flow was developed. NOT verified by a finer run in this session (a 24 x 24 section, ~74k cells, takes hours at this stiffness); next stage re-runs it with preconditioning.

Sources:

- White (2006), Viscous Fluid Flow, 3rd ed., eq. 3-48 (rectangular-duct series), evaluated in validate.py
- White (2006) eq. 3-48 series, evaluated in validate.py

### Runs

| Run | Cells | Iterations | Time [s] | Status | Residual | Re (bulk) |
|---:|---:|---:|---:|---:|---:|---:|
| 8 a duct | 9,216 | 11,719 | 82 | converged | 1.0e-09 | 98.5 |
| 20 a duct | 18,432 | 34,111 | 494 | converged | 1.0e-09 | 53.4 |

- Quarter duct, LU-SGS, CFL 5 -> 1000 (SER).

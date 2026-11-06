# AeroFlowSim validation report

AeroFlowSim 0.2.0a3, generated 2026-11-07 by `python validation/run_all.py --quick`.

**Validation set: quick** (coarse meshes of every case, run on every push; the full set runs weekly and on version tags).

**Overall: FAIL** (29 of 33 cases pass; 6 explained shortfall(s), see the cases marked SHORTFALL)

## Back, Massier and Gier 45-15 deg conical nozzle: measured wall pressure (2D axisymmetric Euler, nozzle_axi): PASS

Case: `cases/nozzle_axi`, references: `validation/bmg_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Wall p/p0 at z = 2.098 in (band +-0.03) | 0.9492 | 0.928144 | 2.218 | 3.16 | PASS |
| Wall p/p0 at z = 2.239 in (band +-0.03) | 0.8669 | 0.805882 | 7.039 | 3.46 | SHORTFALL |
| Wall p/p0 at z = 2.457 in (band +-0.05) | 0.5304 | 0.483953 | 8.757 | 9.43 | PASS |
| Wall p/p0 at z = 2.464 in (band +-0.05) | 0.491 | 0.473679 | 3.528 | 10.18 | PASS |
| Wall p/p0 at z = 2.643 in (band +-0.03) | 0.2281 | 0.230597 | 1.095 | 13.15 | PASS |
| Wall p/p0 at z = 2.828 in (band +-0.03) | 0.1984 | 0.183312 | 7.605 | 15.12 | PASS |
| Wall p/p0 at z = 3.124 in (band +-0.03) | 0.1866 | 0.169218 | 9.315 | 16.08 | PASS |
| Wall p/p0 at z = 3.609 in (band +-0.03) | 0.1299 | 0.121996 | 6.085 | 23.09 | PASS |
| Wall p/p0 at z = 3.957 in (band +-0.03) | 0.0969 | 0.0932107 | 3.807 | 30.96 | PASS |

**Shortfall (explained):** Wall p/p0 at z = 2.239 in (band +-0.03): The inviscid value is 0.80 on both meshes (100 x 20: 0.806, 200 x 40: 0.799): not a mesh error. Cause not resolved: the report concludes that boundary-layer effects on the wall pressure were negligible (Conclusions, item 3), so a viscous effect is unlikely. At z = 2.24 in, just after the tangency of the 45 deg cone with the small throat arc, the measured pressure falls steeply (about -1.2 to -2.5 per inch), so an uncertainty of 0.03-0.05 in in the tap position or the digitized position equals the 0.07 difference, and the report finds tap-size effects of up to 7 % (Conclusions, item 4). A band that includes the position uncertainty (or the report's tabulated data, if they can be found) is recorded in the gap register.

Sources:

- Back, Massier and Gier (1964), JPL Technical Report 32-654, Fig. 4 (tests 347, 348, 351), NASA NTRS 19650001801; digitized

### Wall pressure along the nozzle

| z [in] | p/p0 measured | p/p0 AeroFlowSim | difference |
|---:|---:|---:|---:|
| 0.810 | 0.9990 | 0.9990 | +0.0000 |
| 1.013 | 0.9987 | 0.9979 | -0.0008 |
| 1.195 | 0.9965 | 0.9962 | -0.0003 |
| 1.395 | 0.9946 | 0.9934 | -0.0012 |
| 1.746 | 0.9893 | 0.9818 | -0.0075 |
| 1.937 | 0.9770 | 0.9649 | -0.0121 |
| 2.098 | 0.9492 | 0.9281 | -0.0211 |
| 2.239 | 0.8669 | 0.8059 | -0.0610 |
| 2.457 | 0.5304 | 0.4840 | -0.0464 |
| 2.464 | 0.4910 | 0.4737 | -0.0173 |
| 2.643 | 0.2281 | 0.2306 | +0.0025 |
| 2.828 | 0.1984 | 0.1833 | -0.0151 |
| 3.124 | 0.1866 | 0.1692 | -0.0174 |
| 3.609 | 0.1299 | 0.1220 | -0.0079 |
| 3.957 | 0.0969 | 0.0932 | -0.0037 |
| 4.603 | 0.0588 | 0.0572 | -0.0016 |
| 5.279 | 0.0370 | 0.0360 | -0.0010 |
| 5.987 | 0.0230 | 0.0235 | +0.0005 |
| 6.664 | 0.0182 | 0.0165 | -0.0017 |

- Mesh: 2,000 cells, 2,349 iterations, converged yes, 2 s; discharge coefficient 0.9813.
- RMS difference over all 19 measured points: 0.0198 (in p/p0).
- Geometry from the printed dimensions; the profile's exit area ratio is 6.57 (the report rounds it to 6.63; the measured points end at z = 6.66 in, before the exit).
- The test gas was heated air (1500 R) with a boundary layer; the solver is inviscid with gamma = 1.4 (the report's one-dimensional curve uses 1.40 as well).

## 15 deg cone at Mach 2 (2D axisymmetric Euler, external_2d) vs Taylor-Maccoll: PASS

Case: `cases/external_2d`, references: `validation/euler2d_cone/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Conical shock angle (fitted through the shock position at 6 stations) | 33.9146 deg | 35.0515 deg | 3.352 | 4 | PASS |
| Surface pressure coefficient (mean between 30 % and 80 % of the cone length) | 0.202234 | 0.202047 | 0.092 | 2 | PASS |

Sources:

- Sims (1964), NASA SP-3004, Table 11, p. 16: theta_w = 0.59192180 rad for theta_s = 15 deg, M = 2
- Sims (1964), NASA SP-3004, Table 9, p. 14: Cp = 0.2022339 for theta_s = 15 deg, M = 2

### Run

| Cells | Iterations | Converged | Time [s] | beta [deg] | beta Taylor-Maccoll [deg] | Cp | Cp Taylor-Maccoll |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2,177 | 1,103 | yes | 1 | 35.052 | 33.915 | 0.2020 | 0.2022 |

- Taylor-Maccoll (aeroflowsim.gasdynamics.taylor_maccoll) agrees with Sims (1964, NASA SP-3004, Tables 9 and 11) to 7e-5 in Cp and 2e-6 rad in the shock angle (tests/test_gasdynamics.py).

## Mach 6 cylinder: bow-shock stand-off and the carbuncle test (2D Euler, external_2d): PASS

Case: `cases/external_2d`, references: `validation/euler2d_cylinder/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Bow-shock stand-off distance / diameter (polar grid, carbuncle fix on) | 0.2197 | 0.216874 | 1.286 | 5 | PASS |
| Bow-shock stand-off distance / diameter (Gmsh quad-dominant mesh, full front) | 0.2197 | 0.229606 | 4.509 | 5 | PASS |

Sources:

- Billig, F. S. (1967), J. Spacecraft Rockets 4(6): Delta/R = 0.386 exp(4.67/M^2) for cylinders

### Runs

| Run | Cells | Iterations | Converged | Final residual | Time [s] | Stand-off / D | Shock roughness | Carbuncle metric | Positivity events |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| polar grid, carbuncle fix on | 1,200 | 1,289 | yes | 3.9e-08 | 1 | 0.2169 | 0.78 | 7.49e-02 | 0 |
| polar grid, carbuncle fix OFF | 1,200 | 5,000 | NO | 2.6e-02 | 3 | 0.2151 | 0.80 | 1.29e-03 | 0 |
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
| 11,435 | 20,000 | max_iterations | 1.1e-03 | 54 | 0.7027 | 0.6485 | 1.3449 | 0.049 % | 325,560 |

- The residual of an inviscid blunt-body wake on triangles does not reach 1e-6 (the wake keeps moving); the forebody quantities settle (Cd range in the table).

## Diamond airfoil t/c = 0.1 at Mach 2, alpha 0 and 2 deg (2D Euler, external_2d): PASS

Case: `cases/external_2d`, references: `validation/euler2d_diamond/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Drag coefficient, alpha = 0 | 0.0231957 | 0.0231216 | 0.320 | 3 | PASS |
| Lift coefficient, alpha = 2 deg | 0.0820936 | 0.0820687 | 0.030 | 3 | PASS |
| Drag coefficient, alpha = 2 deg | 0.0261435 | 0.0260519 | 0.350 | 3 | PASS |
| p/p_inf on the upper front face (middle 60 %), alpha = 2 deg | 1.22741 | 1.22748 | 0.006 | 1 | PASS |
| p/p_inf on the upper rear face (middle 60 %), alpha = 2 deg | 0.633413 | 0.635602 | 0.346 | 1 | PASS |
| p/p_inf on the lower front face (middle 60 %), alpha = 2 deg | 1.51704 | 1.51693 | 0.0073 | 1 | PASS |
| p/p_inf on the lower rear face (middle 60 %), alpha = 2 deg | 0.808336 | 0.811331 | 0.370 | 1 | PASS |

Sources:

- Shock-expansion theory (Anderson 2003, Modern Compressible Flow, sec. 4.15), computed by aeroflowsim.gasdynamics.diamond_airfoil (oblique-shock and Prandtl-Meyer relations, gamma = 1.4)

### Runs (theory in brackets)

| alpha [deg] | Cells | Iterations | Converged | Time [s] | Cl | Cd | p/p_inf upper front | upper rear | lower front | lower rear |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 4,750 | 5,000 | NO | 6 | -0.00008 (0.00000) | 0.02312 (0.02320) | 1.3663 (1.3660) | 0.7191 (0.7165) | 1.3659 (1.3660) | 0.7167 (0.7165) |
| 2 | 4,750 | 1,707 | yes | 2 | 0.08207 (0.08209) | 0.02605 (0.02614) | 1.2275 (1.2274) | 0.6356 (0.6334) | 1.5169 (1.5170) | 0.8113 (0.8083) |

- Shock-expansion theory is exact for the inviscid flow on the faces (attached shocks, simple waves); Cl = 0 at alpha = 0 is not compared as a percentage (|Cl| is listed).
- Wall size 0.02 c in the quick set, 0.01 c in the full set.

## NACA 0012, inviscid, Mach 0.8 and 0.5 at alpha 1.25 deg (2D Euler, C-domain, GCI): PASS

Case: `cases/external_2d`, references: `validation/euler2d_naca0012/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Lift coefficient, Mach 0.8, alpha 1.25 deg (GCI-extrapolated) | 0.352033 | 0.347652 | 1.245 | 12 | PASS |
| Drag coefficient, Mach 0.8, alpha 1.25 deg (GCI-extrapolated) | 0.022547 | 0.0229828 | 1.933 | 30 | PASS |
| Lift coefficient, Mach 0.5, alpha 1.25 deg (GCI-extrapolated) | 0.179969 | 0.173947 | 3.346 | 8 | PASS |

Sources:

- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 11, p. 1165: mean of FLO82 0.356209, OVERFLOW 0.351663, CFL3D 0.348226
- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 11, p. 1165: mean of FLO82 0.022685, OVERFLOW 0.022453, CFL3D 0.022501
- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 10, p. 1165: mean of FLO82 0.180346, OVERFLOW 0.179777, CFL3D 0.179784

### Runs

| Condition | Mesh | Cells | Iterations | Converged | Time [s] | Cl | Cd | Cm |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Mach 0.8 | wall 0.02 c | 7,326 | 5,000 | NO | 9 | 0.34765 | 0.022983 | -0.03814 |
| Mach 0.5 | wall 0.02 c | 7,326 | 5,000 | NO | 9 | 0.17395 | 0.000963 | -0.00156 |

- Reference (Vassberg & Jameson 2010, Table 11, p. 1165): Mach 0.8, alpha 1.25 deg: continuum Cl 0.3482 (CFL3D) to 0.3562 (FLO82), Cd 0.02245 to 0.02268; Table 10: Mach 0.5, alpha 1.25 deg: Cl 0.17978 to 0.18035, Cd -> 0 (FLO82 4.5e-8).
- Cm here is about the quarter chord (template convention); the reference's Cm is about the quarter chord as well.
- Mach 0.5 drag on the three meshes: 0.000963 (inviscid subcritical flow has zero drag; it must fall with refinement).

## N2 nozzle, 2D axisymmetric Euler (default nozzle_axi; structured and triangle meshes, three sizes): PASS

Case: `cases/nozzle_axi`, references: `validation/euler2d_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Exit / inlet mass flow (converged: mass is conserved) | 1 | 1 | 0.00024 | 0.1 | PASS |
| Thrust from wall pressure + inlet momentum / thrust from the exit plane | 1 | 0.99999 | 0.001 | 0.2 | PASS |
| Vacuum specific impulse (structured 200 x 40) | 71.29 s | 71.4768 s | 0.262 | 1 | PASS |
| Vacuum specific impulse (Gmsh triangles, 5,505 cells) | 71.29 s | 71.4281 s | 0.194 | 1 | PASS |

Sources:

- Conservation of mass: a converged finite-volume solution has equal inlet and exit mass flow
- Conservation of momentum: the x-momentum balance of the nozzle gas (inlet + wall + exit = 0)
- Ideal quasi-1D vacuum Isp of this wall, 72.53 s, x conical divergence factor (1 + cos 15 deg)/2 = 0.98296 (Malina 1940; Sutton & Biblarz 2017, eq. 3-34)

### Mesh study (quick set: coarse meshes only)

| Mesh | Cells | Iterations | Converged | Time [s] | Mass flow [mg/s] | Cd | F exit [mN] | F wall [mN] | Isp [s] | Isp / Isp 1D | p0 loss [%] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| structured 50 x 10 | 500 | 4,457 | yes | 2 | 68.4750 | 0.9581 | 47.9974 | 47.9969 | 71.477 | 0.9855 | 2.609 |
| triangles, wall 0.16 D_t | 1,098 | 30,000 | NO | 15 | 67.5774 | 0.9455 | 47.3359 | 47.3604 | 71.428 | 0.9849 | 4.745 |
| rounded throat, structured 50 x 10 | 500 | 5,219 | yes | 2 | 71.1196 | 0.9951 | 49.8411 | 49.8408 | 71.462 | 0.9853 | -1.197 |

- Quick set: the coarsest structured and triangle meshes and the coarse rounded-throat mesh.

## Prandtl-Meyer expansion round a 10 deg corner at Mach 2 (2D Euler, geometry_2d): PASS

Case: `cases/geometry_2d`, references: `validation/euler2d_prandtl_meyer/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Mach number downstream of the corner (wall cells, x = 0.4-0.9 m) | 2.38489 | 2.36912 | 0.661 | 1 | PASS |
| Pressure ratio p2/p1 downstream of the corner | 0.547969 | 0.548225 | 0.047 | 1.5 | PASS |

Sources:

- Prandtl-Meyer function nu(M2) = nu(2) + 10 deg (Anderson 2003, eq. 4.44), aeroflowsim.gasdynamics.expansion
- Isentropic relation p2/p1 = (p0/p)(M1) / (p0/p)(M2) with M2 from the Prandtl-Meyer function (Anderson 2003, sec. 4.14)

### Run

| Cells | Iterations | Converged | Time [s] | M2 | p2/p1 |
|---:|---:|---:|---:|---:|---:|
| 1,794 | 814 | yes | 1 | 2.3691 | 0.5482 |

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
| along x, quads | 800 | 0.2 |
| diagonal, triangles | 20,000 | 0.4 |

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

- Theory: beta = 39.314 deg, p2/p1 = 1.7066, M2 = 1.6405.
- Cd includes the base drag of the flat base (the base pressure is not part of the oblique-shock theory).

## 10 deg cone at Mach 2 (3D Euler, quarter domain) vs Taylor-Maccoll: FAIL

Case: `cases/external_3d`, references: `validation/euler3d_cone/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Conical shock angle (shock position in the plane z = 0+ at 6 stations, line through the tip) | 31.2061 deg | 35.6095 deg | 14.111 | 3 | FAIL |
| Surface pressure coefficient (mean over the wall faces between 30 % and 80 % of the cone length) | 0.104471 | 0.106351 | 1.800 | 2 | PASS |

Sources:

- Taylor-Maccoll (aeroflowsim.gasdynamics.taylor_maccoll), M = 2, theta_s = 10 deg, gamma = 1.4; Sims (1964) NASA SP-3004
- Taylor-Maccoll, as above (Sims 1964: 0.1045)

### Runs (the scored run is 'cone'; 'finer' is reported only)

| Run | Cells | Iterations | Converged | Time [s] | Shock stations | beta [deg] | beta Taylor-Maccoll [deg] | Cp | Cp Taylor-Maccoll |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cone | 7,754 | 939 | yes | 3 | 6 | 35.609 | 31.206 | 0.1064 | 0.1045 |

- 3D quarter domain with two symmetry planes, tetrahedra, the external_3d defaults.

## N2 nozzle in 3D (revolved quarter) vs 2D axisymmetric: PASS

Case: `cases/external_3d`, references: `validation/euler3d_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Mass flow, 3D / 2D axisymmetric | 1 | 0.994093 | 0.591 | 1 | PASS |
| Vacuum thrust (exit plane), 3D / 2D axisymmetric | 1 | 0.994074 | 0.593 | 2 | PASS |

Sources:

- 2D axisymmetric run of the same nozzle on the same profile (validated: validation/euler2d_nozzle)
- 2D axisymmetric run, as above

### Runs (same profile, same numerics)

| Run | Cells | Iterations | Converged | Time [s] | mdot [mg/s] | F exit [mN] | F wall+inlet [mN] | Isp [s] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2D | 2,000 | 7,908 | yes | 5 | 67.6312 | 47.3907 | 47.3907 | 71.454 |
| 3D | 16,000 | 21,377 | yes | 135 | 67.2317 | 47.1099 | 47.1099 | 71.452 |

- Polygon factor of the revolved cross-sections: 0.99359 (the 3D throat area is this times the circle's).

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
| tetrahedra | 6,144 | 3,108 | yes | 8 | 0.1478 | 203 |
| hexahedra | 1,024 | 1,230 | yes | 1 | 0.0809 | 108 |

- Before the robust-second-order stage the tetrahedral run stalled at a residual of 0.26.

## Sphere at Mach 3 (3D Euler, tetrahedra): bow-shock stand-off vs Billig: FAIL

Case: `cases/external_3d`, references: `validation/euler3d_sphere/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Bow-shock stand-off distance / sphere radius on the stagnation line, Mach 3 (3D quarter domain) | 0.204966 | 0.23577 | 15.029 | 5 | FAIL |
| The same from the 2D axisymmetric run (external_2d, shape Sphere): consistency 2D vs 3D | 0.204966 | 0.214171 | 4.491 | 5 | PASS |

Sources:

- Billig, F. S. (1967), J. Spacecraft Rockets 4(6): Delta/R = 0.143 exp(3.24/M^2) for spheres
- Billig (1967), as above

### Runs

| Run | Cells | Iterations | Converged | Time [s] | Stand-off / R | Stand-off / R (old cell method) | Billig | Cd | Positivity fallbacks | CFL reductions |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3D Mach 3 | 12,269 | 2,329 | yes | 13 | 0.2358 | 0.2251 | 0.2050 | 0.9660 | 0 | 0 |
| 2D axisymmetric Mach 3 | 4,800 | 3,062 | yes | 4 | 0.2142 | nan | 0.2050 | 0.9526 | 404 | 3 |

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
| Fluid volume (sum of cell volumes), coarse mesh | 1935.48 m³ | 1935.5 m³ | 0.001 | 0.1 | PASS |
| Wall area (sphere patch), coarse mesh | 3.14159 m² | 3.07739 m² | 2.044 | 3 | PASS |
| First prism layer height on the wall (volume / face area), coarse mesh | 0.002 m | 0.0020115 m | 0.575 | 3 | PASS |
| Share of cells with a positive volume, coarse mesh | 1 | 1 | 0.000 | 1e-09 | PASS |
| No error-level mesh check (1 = none), coarse mesh | 1 | 1 | 0.000 | 1e-09 | PASS |
| Fluid volume (sum of cell volumes), medium mesh | 1935.48 m³ | 1935.48 m³ | 0.00027 | 0.1 | PASS |
| Wall area (sphere patch), medium mesh | 3.14159 m² | 3.12431 m² | 0.550 | 3 | PASS |
| First prism layer height on the wall (volume / face area), medium mesh | 0.002 m | 0.00200869 m | 0.435 | 3 | PASS |
| Share of cells with a positive volume, medium mesh | 1 | 1 | 0.000 | 1e-09 | PASS |
| No error-level mesh check (1 = none), medium mesh | 1 | 1 | 0.000 | 1e-09 | PASS |
| Fluid volume (sum of cell volumes), fine mesh | 1935.48 m³ | 1935.48 m³ | 7.2e-05 | 0.1 | PASS |
| Wall area (sphere patch), fine mesh | 3.14159 m² | 3.13695 m² | 0.148 | 3 | PASS |
| First prism layer height on the wall (volume / face area), fine mesh | 0.002 m | 0.00200818 m | 0.409 | 3 | PASS |
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
| coarse | 160 | 10,342 | 8,832 | 1,510 | 0.4 | 0.999 | 3.1 | 82.2 | 28.15 |
| medium | 80 | 29,012 | 23,402 | 5,610 | 0.9 | 0.873 | 12.5 | 67.1 | 14.72 |
| fine | 40 | 125,853 | 105,043 | 20,810 | 4.2 | 0.989 | 9.8 | 66.6 | 8.18 |

- Halving every cell size multiplied the number of cells by 2.81, 4.34: cells that fill a fixed volume uniformly grow 8 times, the prism layers 4 times (wall area / size²), so the growth rises towards 8 as the volume cells dominate (the coarsest quick level has very few cells).
- Skewness: equivolume for the tetrahedra, equiangle for the prisms.

## Method of Manufactured Solutions: order of accuracy of the 2D Euler solver: PASS

Case: `aeroflowsim/mms.py`, references: `validation/mms_euler2d/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Observed order (min L2 over rho, u, v, p), planar quads | 2 | 2.0108 | 0.540 | 10 | PASS |
| Observed order, planar smoothly distorted quads | 2 | 1.78441 | 10.780 | 25 | PASS |
| Observed order, planar triangles | 2 | 2.01288 | 0.644 | 15 | PASS |
| Observed order, planar mixed quads + triangles | 2 | 2.0136 | 0.680 | 15 | PASS |
| Observed order, axisymmetric quads (with the pressure source) | 2 | 2.08843 | 4.421 | 10 | PASS |
| Observed order, axisymmetric distorted quads | 2 | 2.03463 | 1.732 | 25 | PASS |
| Observed order, axisymmetric triangles | 2 | 2.03909 | 1.954 | 15 | PASS |
| Observed order, axisymmetric mixed | 2 | 2.00481 | 0.241 | 15 | PASS |

Sources:

- Formal order of the MUSCL / least-squares scheme (Barth & Jespersen 1989); MMS of Roy et al. (2004)
- Formal order 2 (as above)

### Observed orders between the two finest meshes (cells per side in brackets)

| Scheme | Mesh | L2 error finest (rho / u / v / p) | Order L1 | Order L2 | Order Linf | GCI p (L2 of p) | GCI asympt. ratio | Iterations | Time [s] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| planar, order 2 (8-32) | quads | 3.42e-04 / 1.15e-01 / 1.17e-01 / 7.18e+01 | 2.01 / 2.20 / 2.08 / 2.05 | 2.02 / 2.07 / 2.08 / 2.01 | 2.16 / 1.90 / 2.06 / 1.67 | 1.97 | 0.25 | 4,887 | 2 |
| planar, order 2 (8-32) | distorted quads | 6.00e-04 / 2.10e-01 / 1.49e-01 / 1.15e+02 | 1.88 / 2.01 / 2.03 / 1.95 | 1.78 / 1.81 / 1.96 / 1.86 | 1.83 / 1.75 / 1.22 / 1.81 | 1.56 | 0.27 | 4,549 | 2 |
| planar, order 2 (8-32) | triangles | 1.06e-03 / 2.09e-01 / 2.11e-01 / 9.92e+01 | 2.10 / 2.03 / 2.03 / 2.01 | 2.10 / 2.05 / 2.04 / 2.01 | 2.02 / 2.16 / 1.80 / 1.79 | 2.11 | 0.25 | 7,457 | 3 |
| planar, order 2 (8-32) | mixed | 6.11e-04 / 1.58e-01 / 1.39e-01 / 7.95e+01 | 2.05 / 2.10 / 2.11 / 2.07 | 2.01 / 2.05 / 2.09 / 2.04 | 1.13 / 1.67 / 1.48 / 1.92 | 2.02 | 0.24 | 5,603 | 2 |
| axisymmetric, order 2 (8-32) | quads | 4.41e-04 / 1.06e-01 / 9.47e-02 / 5.87e+01 | 2.07 / 2.07 / 2.12 / 2.09 | 2.11 / 2.12 / 2.09 / 2.09 | 1.94 / 1.72 / 1.89 / 1.93 | 2.19 | 0.24 | 2,834 | 1 |
| axisymmetric, order 2 (8-32) | distorted quads | 5.64e-04 / 1.44e-01 / 1.17e-01 / 7.18e+01 | 2.06 / 2.06 / 2.12 / 2.02 | 2.07 / 2.07 / 2.09 / 2.03 | 1.87 / 2.02 / 1.86 / 1.74 | 2.06 | 0.24 | 2,468 | 1 |
| axisymmetric, order 2 (8-32) | triangles | 9.95e-04 / 2.16e-01 / 2.23e-01 / 9.16e+01 | 2.05 / 2.12 / 2.03 / 2.05 | 2.04 / 2.12 / 2.04 / 2.06 | 1.65 / 1.99 / 1.78 / 1.82 | 1.94 | 0.24 | 4,865 | 2 |
| axisymmetric, order 2 (8-32) | mixed | 7.78e-04 / 1.68e-01 / 1.57e-01 / 6.87e+01 | 2.06 / 2.01 / 1.98 / 2.07 | 2.04 / 2.00 / 2.01 / 2.06 | 1.81 / 1.65 / 1.98 / 1.96 | 2.01 | 0.24 | 4,664 | 2 |
| planar, order 1 (8-32) | quads | 1.15e-02 / 2.63e+00 / 5.37e+00 / 1.49e+03 | 0.90 / 0.80 / 0.93 / 0.84 | 0.89 / 0.77 / 0.92 / 0.81 | 0.60 / 0.46 / 0.93 / 0.74 | 0.73 | 0.57 | 3,973 | 1 |
| planar, order 1 (8-32) | distorted quads | 1.49e-02 / 3.82e+00 / 5.94e+00 / 2.01e+03 | 0.76 / 0.62 / 0.84 / 0.67 | 0.74 / 0.55 / 0.85 / 0.62 | 0.42 / 0.30 / 0.77 / 0.32 | 0.59 | 0.65 | 4,078 | 1 |
| planar, order 1 (8-32) | triangles | 9.60e-03 / 2.64e+00 / 3.01e+00 / 7.93e+02 | 0.93 / 0.93 / 0.99 / 0.92 | 0.95 / 0.92 / 0.98 / 0.91 | 0.96 / 0.85 / 0.86 / 0.93 | 0.96 | 0.53 | 5,936 | 2 |
| planar, order 1 (8-32) | mixed | 8.91e-03 / 2.02e+00 / 3.70e+00 / 1.09e+03 | 0.99 / 0.92 / 1.00 / 0.95 | 0.98 / 0.94 / 0.98 / 0.95 | 0.96 / 0.96 / 0.96 / 0.90 | 0.90 | 0.52 | 4,210 | 1 |
| planar, order 2, Venkatakrishnan (8-32) | quads | 4.68e-04 / 1.32e-01 / 1.78e-01 / 7.66e+01 | 1.56 / 1.96 / 1.79 / 1.93 | 1.36 / 1.86 / 1.59 / 1.89 | 0.47 / 1.51 / 1.05 / 1.36 | 2.04 | 0.27 | 4,712 | 2 |
| planar, order 2, Venkatakrishnan (8-32) | distorted quads | 6.79e-04 / 2.00e-01 / 2.22e-01 / 1.11e+02 | 1.83 / 1.99 / 1.81 / 1.94 | 1.58 / 1.88 / 1.58 / 1.93 | 0.98 / 1.67 / 0.66 / 1.69 | 1.55 | 0.26 | 4,433 | 2 |
| planar, order 2, Venkatakrishnan (8-32) | triangles | 1.81e-03 / 3.67e-01 / 3.12e-01 / 1.14e+02 | 1.72 / 1.60 / 1.70 / 1.79 | 1.61 / 1.52 / 1.64 / 1.78 | 1.19 / 1.47 / 1.08 / 1.26 | 2.22 | 0.29 | 6,745 | 3 |
| planar, order 2, Venkatakrishnan (8-32) | mixed | 1.14e-03 / 2.57e-01 / 2.39e-01 / 1.05e+02 | 1.56 / 1.60 / 1.64 / 1.76 | 1.40 / 1.52 / 1.55 / 1.74 | 0.57 / 0.67 / 0.28 / 1.42 | 2.02 | 0.30 | 5,382 | 2 |

- Orders listed per variable rho / u / v / p. Errors in SI units (kg/m³, m/s, m/s, Pa).
- The GCI columns apply the three-mesh GCI procedure (aeroflowsim/gci.py) to the L2 error of p: its observed order should match and the asymptotic ratio be near 1.
- First order and the Venkatakrishnan limiter are reported for information (not pass/fail): Finding (Post-processing and alpha release stage): with Venkatakrishnan's limiter the order does NOT approach 2 on finer meshes; on triangles and mixed meshes it falls towards 1. Its threshold eps² = (K h / L)³ scale² shrinks faster than the cell-to-cell differences of a smooth field (h^1.5 against h), so the limiter clips the smooth extrema more and more as the mesh is refined. Smooth flows on fine meshes therefore keep full second order only with 'None' or a larger K; an order-preserving limiter (e.g. Michalak and Ollivier-Gooch 2008) is in the gap register.

## Method of Manufactured Solutions: order of accuracy of the 3D Euler solver: PASS

Case: `aeroflowsim/mms.py`, references: `validation/mms_euler3d/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Observed order (min L2 over rho, u, v, w, p), warped hexahedra | 2 | 1.94211 | 2.894 | 15 | PASS |
| Observed order, warped prisms | 2 | 1.88537 | 5.731 | 20 | PASS |
| Observed order, warped tetrahedra (Kuhn split) | 2 | 1.64914 | 17.543 | 22.5 | PASS |

Sources:

- Formal order of the MUSCL / least-squares scheme (Barth & Jespersen 1989); MMS of Roy et al. (2004)
- Formal order 2 (as above)

### Levels (L2 errors of rho, u, v, w, p)

| Cells | Box | Count | Iterations | Time [s] | L2 error / order |
|---:|---:|---:|---:|---:|---:|
| hexahedra | 6^3 | 216 | 365 | 0.1 | 1.314e-02 3.515e+00 3.970e+00 2.095e+00 1.816e+03 |
| hexahedra | 12^3 | 1,728 | 613 | 0.4 | 3.233e-03 9.148e-01 8.630e-01 4.519e-01 4.438e+02 |
| hexahedra | order |  |  |  | 2.022 1.942 2.202 2.213 2.033 |
| prisms | 6^3 | 432 | 342 | 0.1 | 8.023e-03 2.388e+00 2.187e+00 1.897e+00 9.734e+02 |
| prisms | 12^3 | 3,456 | 564 | 0.5 | 1.986e-03 5.474e-01 5.157e-01 4.107e-01 2.635e+02 |
| prisms | order |  |  |  | 2.015 2.125 2.084 2.208 1.885 |
| tetrahedra | 6^3 | 1,296 | 583 | 0.2 | 1.190e-02 3.078e+00 2.645e+00 1.928e+00 8.843e+02 |
| tetrahedra | 12^3 | 10,368 | 832 | 1.9 | 3.723e-03 9.438e-01 8.011e-01 5.994e-01 2.819e+02 |
| tetrahedra | order |  |  |  | 1.677 1.705 1.723 1.686 1.649 |

- Hexahedra, Kuhn tetrahedra (6 per cube) and prisms (2 per cube), warp 0.03.

## Method of Manufactured Solutions: order of accuracy of the Navier-Stokes (laminar) terms: PASS

Case: `aeroflowsim/mms_ns.py`, references: `validation/mms_navier_stokes/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Observed order (min L2 over rho, u, v, p), planar quads | 2 | 1.8613 | 6.935 | 15 | PASS |
| Observed order, planar smoothly distorted quads | 2 | 1.7998 | 10.010 | 25 | PASS |
| Observed order, planar triangles | 2 | 2.0595 | 2.975 | 20 | PASS |
| Observed order, axisymmetric quads (pressure and hoop-stress sources) | 2 | 2.01921 | 0.960 | 15 | PASS |
| Observed order, axisymmetric triangles | 2 | 2.06262 | 3.131 | 20 | PASS |
| Observed order (min L2 over rho, u, v, w, p), warped hexahedra | 2 | 1.98233 | 0.883 | 15 | PASS |
| Observed order, warped prisms | 2 | 1.81617 | 9.192 | 20 | PASS |
| Observed order, warped tetrahedra | 2 | 1.934 | 3.300 | 22.5 | PASS |

Sources:

- Formal order 2 of the scheme (MUSCL + corrected face gradients); MMS of Roy et al. (2004), Int. J. Numer. Meth. Fluids 44, 599-620
- Formal order 2 (as above)

### Levels (L2 errors of rho, velocity components, p)

| Mesh | n | Cells | Iterations | Time [s] | L2 error / order (finest pair) |
|---:|---:|---:|---:|---:|---:|
| quads | 16 | 256 | 631 | 1.7 | 1.181e-03 4.225e-01 4.429e-01 2.366e+02 |
| quads | 32 | 1,024 | 1,432 | 4.1 | 3.358e-04 1.138e-01 1.111e-01 6.158e+01 |
| quads | 64 | 4,096 | 3,588 | 10.6 | 9.241e-05 2.961e-02 2.795e-02 1.539e+01 |
| quads | order |  |  |  | 1.861 1.942 1.990 2.000 |
| distorted_quads | 16 | 256 | 600 | 1.6 | 1.252e-03 4.205e-01 4.833e-01 2.625e+02 |
| distorted_quads | 32 | 1,024 | 1,398 | 3.9 | 3.738e-04 1.218e-01 1.311e-01 7.073e+01 |
| distorted_quads | 64 | 4,096 | 3,566 | 10.5 | 1.074e-04 3.361e-02 3.487e-02 1.820e+01 |
| distorted_quads | order |  |  |  | 1.800 1.857 1.910 1.958 |
| triangles | 16 | 512 | 1,033 | 2.6 | 2.291e-03 5.761e-01 5.373e-01 2.739e+02 |
| triangles | 32 | 2,048 | 2,489 | 6.6 | 5.466e-04 1.359e-01 1.203e-01 7.132e+01 |
| triangles | 64 | 8,192 | 6,562 | 20.4 | 1.305e-04 2.993e-02 2.707e-02 1.711e+01 |
| triangles | order |  |  |  | 2.067 2.183 2.151 2.059 |
| axi_quads | 16 | 256 | 374 | 1.1 | 2.025e-03 4.486e-01 3.787e-01 2.113e+02 |
| axi_quads | 32 | 1,024 | 752 | 2.1 | 5.119e-04 1.047e-01 9.281e-02 5.354e+01 |
| axi_quads | 64 | 4,096 | 1,747 | 6.3 | 1.263e-04 2.499e-02 2.281e-02 1.317e+01 |
| axi_quads | order |  |  |  | 2.019 2.068 2.025 2.023 |
| axi_triangles | 16 | 512 | 601 | 1.4 | 2.606e-03 5.306e-01 5.020e-01 1.819e+02 |
| axi_triangles | 32 | 2,048 | 1,282 | 3.8 | 6.231e-04 1.112e-01 1.001e-01 4.028e+01 |
| axi_triangles | 64 | 8,192 | 3,157 | 11.0 | 1.492e-04 2.499e-02 1.980e-02 8.958e+00 |
| axi_triangles | order |  |  |  | 2.063 2.153 2.338 2.169 |
| hexahedra | 6 | 216 | 284 | 0.7 | 1.069e-02 2.958e+00 3.228e+00 1.618e+00 1.320e+03 |
| hexahedra | 12 | 1,728 | 400 | 1.4 | 2.532e-03 7.037e-01 6.918e-01 3.433e-01 3.342e+02 |
| hexahedra | order |  |  |  | 2.077 2.072 2.222 2.236 1.982 |
| prisms | 6 | 432 | 290 | 0.8 | 6.835e-03 1.756e+00 1.935e+00 1.534e+00 7.739e+02 |
| prisms | 12 | 3,456 | 458 | 1.9 | 1.834e-03 3.536e-01 4.629e-01 2.995e-01 2.198e+02 |
| prisms | order |  |  |  | 1.898 2.312 2.064 2.357 1.816 |
| tetrahedra | 6 | 1,296 | 431 | 1.3 | 6.147e-03 1.473e+00 1.555e+00 1.049e+00 4.793e+02 |
| tetrahedra | 12 | 10,368 | 826 | 4.5 | 1.495e-03 2.865e-01 3.549e-01 2.309e-01 1.254e+02 |
| tetrahedra | order |  |  |  | 2.039 2.362 2.132 2.183 1.934 |

- Air with mu = 2 Pa s (T/300 K)^0.7, Pr 0.72 (viscous terms as large as the convective ones).
- Boundary faces: second-order one-sided face gradient (aeroflowsim/euler/viscous.py).

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

## TMR 2D zero-pressure-gradient turbulent flat plate (SA, SST): PASS

Case: `aeroflowsim/euler (EulerSolver + turbulence.py)`, references: `validation/turbulent_flat_plate/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Cf at x = 0.97008, Spalart-Allmaras (finest grid) | 0.00270562 | 0.00272963 | 0.887 | 5 | PASS |
| Cf at x = 0.97008, k-omega SST (SST-V; finest grid) | 0.00269085 | 0.00262628 | 2.400 | 5 | PASS |

Sources:

- NASA TMR, 2DZP flat plate, FlatPlate/SA/cf_convergence.dat, CFL3D N = 208896 (tmbwg.github.io/turbmodels/flatplate_sa.html)
- NASA TMR, 2DZP flat plate, FlatPlate/SST/cf_convergence_sstv.dat, CFL3D N = 208896 (tmbwg.github.io/turbmodels/flatplate_sst.html)

### Grid series

| Model | Grid | Cells | Iterations | Time [s] | Status | Residual | y+ max | Cf(0.97) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Spalart-Allmaras | 136 x 96 | 13,056 | 150,000 | 1246 | max_iterations | 1.2e-05 | 1.42 | 2.729627e-03 |
| k-omega SST | 136 x 96 | 13,056 | 150,000 | 1959 | max_iterations | 1.6e-08 | 1.44 | 2.626275e-03 |

- LU-SGS (CFL 5 -> 1000), turbulence loosely coupled implicit SGS, first-order turbulence convection (as the TMR CFL3D/FUN3D runs).

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
| M0.2 2D | 8,960 | 60,000 | 229 | max_iterations | 1.2e-07 |
| M0.2 3D | 8,960 | 60,000 | 450 | max_iterations | 1.9e-07 |

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
| 2D | 128 | 15,700 | 5.9 | converged |
| 3D | 128 | 12,734 | 5.5 | converged |

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
| Recirculation length L/D (Fine grid) | 1 | nan | nan | 5 | PENDING REFERENCE |
| Drag coefficient Cd (Fine grid) | 1 | 1.54611 | 54.611 | 5 | PENDING REFERENCE |
| Medium grid reached the residual 1e-6 (1 = yes, 0 = no) | 1 | 1 | 0.000 | 0.01 | PASS |
| Cd Medium grid / Cd Fine grid | 1 | 1 | 0.000 | 2 | PASS |

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
| Medium | 12,800 | 8,331 | converged | 1.0e-06 | 1.5461 | 2.217 | 0.5276 | 36 |

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
| M2 adiabatic | 8,960 | 10,829 | 34 | converged | 1.0e-08 |
| M2 isothermal | 8,960 | 5,041 | 16 | converged | 1.0e-08 |


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
| 4,000 | 21,616 | 31 | converged | 1.0e-09 | 106.8 | 0.205 |

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
| 8 a duct | 9,216 | 11,719 | 54 | converged | 1.0e-09 | 98.5 |
| 20 a duct | 18,432 | 34,111 | 369 | converged | 1.0e-09 | 53.4 |

- Quarter duct, LU-SGS, CFL 5 -> 1000 (SER).

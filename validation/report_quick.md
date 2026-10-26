# AeroFlowSim validation report

AeroFlowSim 0.1.0.dev0, generated 2026-10-26 by `python validation/run_all.py --quick`.

**Validation set: quick** (coarse meshes of every case, run on every push; the full set runs weekly and on version tags).

**Overall: FAIL** (13 of 15 cases pass)

## Back, Massier and Gier 45-15 deg conical nozzle: measured wall pressure (2D axisymmetric Euler, nozzle_axi): FAIL

Case: `cases/nozzle_axi`, references: `validation/bmg_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Wall p/p0 at z = 2.098 in (band +-0.03) | 0.9492 | 0.928144 | 2.218 | 3.16 | PASS |
| Wall p/p0 at z = 2.239 in (band +-0.03) | 0.8669 | 0.805882 | 7.039 | 3.46 | FAIL |
| Wall p/p0 at z = 2.457 in (band +-0.05) | 0.5304 | 0.483953 | 8.757 | 9.43 | PASS |
| Wall p/p0 at z = 2.464 in (band +-0.05) | 0.491 | 0.473678 | 3.528 | 10.18 | PASS |
| Wall p/p0 at z = 2.643 in (band +-0.03) | 0.2281 | 0.230597 | 1.095 | 13.15 | PASS |
| Wall p/p0 at z = 2.828 in (band +-0.03) | 0.1984 | 0.183312 | 7.605 | 15.12 | PASS |
| Wall p/p0 at z = 3.124 in (band +-0.03) | 0.1866 | 0.169218 | 9.315 | 16.08 | PASS |
| Wall p/p0 at z = 3.609 in (band +-0.03) | 0.1299 | 0.121996 | 6.085 | 23.09 | PASS |
| Wall p/p0 at z = 3.957 in (band +-0.03) | 0.0969 | 0.0932107 | 3.807 | 30.96 | PASS |

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

- Mesh: 2,000 cells, 1,883 iterations, converged yes, 16 s; discharge coefficient 0.9813.
- RMS difference over all 19 measured points: 0.0198 (in p/p0).
- Geometry from the printed dimensions; the profile's exit area ratio is 6.57 (the report rounds it to 6.63; the measured points end at z = 6.66 in, before the exit).
- The test gas was heated air (1500 R) with a boundary layer; the solver is inviscid with gamma = 1.4 (the report's one-dimensional curve uses 1.40 as well).

## 15 deg cone at Mach 2 (2D axisymmetric Euler, external_2d) vs Taylor-Maccoll: FAIL

Case: `cases/external_2d`, references: `validation/euler2d_cone/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Conical shock angle (fitted through the shock position at 6 stations) | 33.9146 deg | 35.0515 deg | 3.352 | 2 | FAIL |
| Surface pressure coefficient (mean between 30 % and 80 % of the cone length) | 0.202234 | 0.202047 | 0.092 | 2 | PASS |

Sources:

- Sims (1964), NASA SP-3004, Table 11, p. 16: theta_w = 0.59192180 rad for theta_s = 15 deg, M = 2
- Sims (1964), NASA SP-3004, Table 9, p. 14: Cp = 0.2022339 for theta_s = 15 deg, M = 2

### Run

| Cells | Iterations | Converged | Time [s] | beta [deg] | beta Taylor-Maccoll [deg] | Cp | Cp Taylor-Maccoll |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2,177 | 5,557 | yes | 50 | 35.052 | 33.915 | 0.2020 | 0.2022 |

- Taylor-Maccoll (aeroflowsim.gasdynamics.taylor_maccoll) agrees with Sims (1964, NASA SP-3004, Tables 9 and 11) to 7e-5 in Cp and 2e-6 rad in the shock angle (tests/test_gasdynamics.py).

## Mach 6 cylinder: bow-shock stand-off and the carbuncle test (2D Euler, external_2d): PASS

Case: `cases/external_2d`, references: `validation/euler2d_cylinder/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Bow-shock stand-off distance / diameter (polar grid, carbuncle fix on) | 0.2197 | 0.217158 | 1.157 | 5 | PASS |
| Bow-shock stand-off distance / diameter (Gmsh quad-dominant mesh, full front) | 0.2197 | 0.229327 | 4.382 | 5 | PASS |

Sources:

- Billig, F. S. (1967), J. Spacecraft Rockets 4(6): Delta/R = 0.386 exp(4.67/M^2) for cylinders

### Runs

| Run | Cells | Iterations | Converged | Final residual | Time [s] | Stand-off / D | Shock roughness | Carbuncle metric | Positivity events |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| polar grid, carbuncle fix on | 1,200 | 2,503 | yes | 9.7e-07 | 14 | 0.2172 | 0.79 | 3.61e-04 | 0 |
| polar grid, carbuncle fix OFF | 1,200 | 5,000 | NO | 2.1e-06 | 25 | 0.2156 | 0.80 | 9.00e-07 | 0 |
| Gmsh quad-dominant, fix on | 1,329 | 2,423 | yes | 9.9e-07 | 14 | 0.2293 | - | 1.23e-04 | 0 |

- Billig correlation: stand-off / D = 0.2197.
- Shock roughness: largest second difference of the shock radius between neighbouring grid rays, divided by the radial cell size (below 1: the front never jumps a whole cell between rays; it is similar with and without the fix here, so convergence is the clearer sign).
- Carbuncle metric: peak-to-peak change of the volume-weighted pressure in the shock layer (box x = -0.45 to 0 D, y = 0 to 0.35 D) over the last 1,000 iterations, divided by its mean. It separates the runs clearly; the shock roughness above does not.
- Without the fix (pure HLLC) the bow shock never settles on the shock-aligned grid: the residual stalls high; with the HLLE blend near the shock the run converges.
- Inviscid, calorically perfect air (gamma = 1.4): a numerics test, not real Mach 6 air.

## Diamond airfoil t/c = 0.1 at Mach 2, alpha 0 and 2 deg (2D Euler, external_2d): PASS

Case: `cases/external_2d`, references: `validation/euler2d_diamond/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Drag coefficient, alpha = 0 | 0.0231957 | 0.0231101 | 0.369 | 3 | PASS |
| Lift coefficient, alpha = 2 deg | 0.0820936 | 0.0820827 | 0.013 | 3 | PASS |
| Drag coefficient, alpha = 2 deg | 0.0261435 | 0.0260591 | 0.323 | 3 | PASS |
| p/p_inf on the upper front face (middle 60 %), alpha = 2 deg | 1.22741 | 1.22748 | 0.006 | 1 | PASS |
| p/p_inf on the upper rear face (middle 60 %), alpha = 2 deg | 0.633413 | 0.635602 | 0.346 | 1 | PASS |
| p/p_inf on the lower front face (middle 60 %), alpha = 2 deg | 1.51704 | 1.51693 | 0.0074 | 1 | PASS |
| p/p_inf on the lower rear face (middle 60 %), alpha = 2 deg | 0.808336 | 0.811048 | 0.335 | 1 | PASS |

Sources:

- Shock-expansion theory (Anderson 2003, Modern Compressible Flow, sec. 4.15), computed by aeroflowsim.gasdynamics.diamond_airfoil (oblique-shock and Prandtl-Meyer relations, gamma = 1.4)

### Runs (theory in brackets)

| alpha [deg] | Cells | Iterations | Converged | Time [s] | Cl | Cd | p/p_inf upper front | upper rear | lower front | lower rear |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 4,750 | 2,755 | yes | 47 | -0.00010 (0.00000) | 0.02311 (0.02320) | 1.3663 (1.3660) | 0.7191 (0.7165) | 1.3659 (1.3660) | 0.7192 (0.7165) |
| 2 | 4,750 | 5,000 | NO | 89 | 0.08208 (0.08209) | 0.02606 (0.02614) | 1.2275 (1.2274) | 0.6356 (0.6334) | 1.5169 (1.5170) | 0.8110 (0.8083) |

- Shock-expansion theory is exact for the inviscid flow on the faces (attached shocks, simple waves); Cl = 0 at alpha = 0 is not compared as a percentage (|Cl| is listed).
- Wall size 0.02 c in the quick set, 0.01 c in the full set.

## NACA 0012, inviscid, Mach 0.8 and 0.5 at alpha 1.25 deg (2D Euler, C-domain, GCI): PASS

Case: `cases/external_2d`, references: `validation/euler2d_naca0012/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Lift coefficient, Mach 0.8, alpha 1.25 deg (GCI-extrapolated) | 0.352033 | 0.331357 | 5.873 | 12 | PASS |
| Drag coefficient, Mach 0.8, alpha 1.25 deg (GCI-extrapolated) | 0.022547 | 0.0217969 | 3.327 | 30 | PASS |
| Lift coefficient, Mach 0.5, alpha 1.25 deg (GCI-extrapolated) | 0.179969 | 0.172128 | 4.357 | 8 | PASS |

Sources:

- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 11, p. 1165: mean of FLO82 0.356209, OVERFLOW 0.351663, CFL3D 0.348226
- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 11, p. 1165: mean of FLO82 0.022685, OVERFLOW 0.022453, CFL3D 0.022501
- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 10, p. 1165: mean of FLO82 0.180346, OVERFLOW 0.179777, CFL3D 0.179784

### Runs

| Condition | Mesh | Cells | Iterations | Converged | Time [s] | Cl | Cd | Cm |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Mach 0.8 | wall 0.01 c | 9,400 | 12,771 | yes | 412 | 0.33136 | 0.021797 | -0.03324 |
| Mach 0.5 | wall 0.01 c | 9,400 | 28,388 | yes | 924 | 0.17213 | 0.000460 | -0.00097 |

- Reference (Vassberg & Jameson 2010, Table 11, p. 1165): Mach 0.8, alpha 1.25 deg: continuum Cl 0.3482 (CFL3D) to 0.3562 (FLO82), Cd 0.02245 to 0.02268; Table 10: Mach 0.5, alpha 1.25 deg: Cl 0.17978 to 0.18035, Cd -> 0 (FLO82 4.5e-8).
- Cm here is about the quarter chord (template convention); the reference's Cm is about the quarter chord as well.
- Mach 0.5 drag on the three meshes: 0.000460 (inviscid subcritical flow has zero drag; it must fall with refinement).

## N2 nozzle, 2D axisymmetric Euler (default nozzle_axi; structured and triangle meshes, three sizes): PASS

Case: `cases/nozzle_axi`, references: `validation/euler2d_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Exit / inlet mass flow (converged: mass is conserved) | 1 | 1 | 0.00022 | 0.1 | PASS |
| Thrust from wall pressure + inlet momentum / thrust from the exit plane | 1 | 1 | 0.00032 | 0.2 | PASS |
| Vacuum specific impulse (structured 200 x 40) | 71.29 s | 71.4768 s | 0.262 | 1 | PASS |
| Vacuum specific impulse (Gmsh triangles, 5,505 cells) | 71.29 s | 71.4324 s | 0.200 | 1 | PASS |

Sources:

- Conservation of mass: a converged finite-volume solution has equal inlet and exit mass flow
- Conservation of momentum: the x-momentum balance of the nozzle gas (inlet + wall + exit = 0)
- Ideal quasi-1D vacuum Isp of this wall, 72.53 s, x conical divergence factor (1 + cos 15 deg)/2 = 0.98296 (Malina 1940; Sutton & Biblarz 2017, eq. 3-34)

### Mesh study (quick set: coarse meshes only)

| Mesh | Cells | Iterations | Converged | Time [s] | Mass flow [mg/s] | Cd | F exit [mN] | F wall [mN] | Isp [s] | Isp / Isp 1D | p0 loss [%] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| structured 50 x 10 | 500 | 4,672 | yes | 15 | 68.4750 | 0.9581 | 47.9973 | 47.9975 | 71.477 | 0.9855 | 2.609 |
| triangles, wall 0.16 D_t | 1,098 | 30,000 | NO | 123 | 67.5969 | 0.9458 | 47.3525 | 47.3324 | 71.432 | 0.9849 | 4.715 |
| rounded throat, structured 50 x 10 | 500 | 5,552 | yes | 15 | 71.1196 | 0.9951 | 49.8411 | 49.8411 | 71.462 | 0.9853 | -1.197 |

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
| 1,794 | 930 | yes | 5 | 2.3691 | 0.5482 |

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
| along x, quads | 800 | 1.8 |
| diagonal, triangles | 20,000 | 16.9 |

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
| wall 0.02 L | 3,553 | 1,935 | yes | 23 | 39.351 | 1.7072 | 1.6316 | 0.1965 |

- Theory: beta = 39.314 deg, p2/p1 = 1.7066, M2 = 1.6405.
- Cd includes the base drag of the flat base (the base pressure is not part of the oblique-shock theory).

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
| planar, order 2 (8-32) | quads | 3.42e-04 / 1.15e-01 / 1.17e-01 / 7.18e+01 | 2.01 / 2.20 / 2.08 / 2.05 | 2.02 / 2.07 / 2.08 / 2.01 | 2.16 / 1.90 / 2.06 / 1.67 | 1.97 | 0.25 | 4,887 | 13 |
| planar, order 2 (8-32) | distorted quads | 6.00e-04 / 2.10e-01 / 1.49e-01 / 1.15e+02 | 1.88 / 2.01 / 2.03 / 1.95 | 1.78 / 1.81 / 1.96 / 1.86 | 1.83 / 1.75 / 1.22 / 1.81 | 1.56 | 0.27 | 4,549 | 12 |
| planar, order 2 (8-32) | triangles | 1.06e-03 / 2.09e-01 / 2.11e-01 / 9.92e+01 | 2.10 / 2.03 / 2.03 / 2.01 | 2.10 / 2.05 / 2.04 / 2.01 | 2.02 / 2.16 / 1.80 / 1.79 | 2.11 | 0.25 | 7,457 | 27 |
| planar, order 2 (8-32) | mixed | 6.11e-04 / 1.58e-01 / 1.39e-01 / 7.95e+01 | 2.05 / 2.10 / 2.11 / 2.07 | 2.01 / 2.05 / 2.09 / 2.04 | 1.13 / 1.67 / 1.48 / 1.92 | 2.02 | 0.24 | 5,603 | 18 |
| axisymmetric, order 2 (8-32) | quads | 4.41e-04 / 1.06e-01 / 9.47e-02 / 5.87e+01 | 2.07 / 2.07 / 2.12 / 2.09 | 2.11 / 2.12 / 2.09 / 2.09 | 1.94 / 1.72 / 1.89 / 1.93 | 2.19 | 0.24 | 2,834 | 8 |
| axisymmetric, order 2 (8-32) | distorted quads | 5.64e-04 / 1.44e-01 / 1.17e-01 / 7.18e+01 | 2.06 / 2.06 / 2.12 / 2.02 | 2.07 / 2.07 / 2.09 / 2.03 | 1.87 / 2.02 / 1.86 / 1.74 | 2.06 | 0.24 | 2,468 | 7 |
| axisymmetric, order 2 (8-32) | triangles | 9.95e-04 / 2.16e-01 / 2.23e-01 / 9.16e+01 | 2.05 / 2.12 / 2.03 / 2.05 | 2.04 / 2.12 / 2.04 / 2.06 | 1.65 / 1.99 / 1.78 / 1.82 | 1.94 | 0.24 | 4,865 | 18 |
| axisymmetric, order 2 (8-32) | mixed | 7.78e-04 / 1.68e-01 / 1.57e-01 / 6.87e+01 | 2.06 / 2.01 / 1.98 / 2.07 | 2.04 / 2.00 / 2.01 / 2.06 | 1.81 / 1.65 / 1.98 / 1.96 | 2.01 | 0.24 | 4,664 | 15 |
| planar, order 1 (8-32) | quads | 1.15e-02 / 2.63e+00 / 5.37e+00 / 1.49e+03 | 0.90 / 0.80 / 0.93 / 0.84 | 0.89 / 0.77 / 0.92 / 0.81 | 0.60 / 0.46 / 0.93 / 0.74 | 0.73 | 0.57 | 3,973 | 8 |
| planar, order 1 (8-32) | distorted quads | 1.49e-02 / 3.82e+00 / 5.94e+00 / 2.01e+03 | 0.76 / 0.62 / 0.84 / 0.67 | 0.74 / 0.55 / 0.85 / 0.62 | 0.42 / 0.30 / 0.77 / 0.32 | 0.59 | 0.65 | 4,078 | 8 |
| planar, order 1 (8-32) | triangles | 9.60e-03 / 2.64e+00 / 3.01e+00 / 7.93e+02 | 0.93 / 0.93 / 0.99 / 0.92 | 0.95 / 0.92 / 0.98 / 0.91 | 0.96 / 0.85 / 0.86 / 0.93 | 0.96 | 0.53 | 5,936 | 15 |
| planar, order 1 (8-32) | mixed | 8.91e-03 / 2.02e+00 / 3.70e+00 / 1.09e+03 | 0.99 / 0.92 / 1.00 / 0.95 | 0.98 / 0.94 / 0.98 / 0.95 | 0.96 / 0.96 / 0.96 / 0.90 | 0.90 | 0.52 | 4,210 | 10 |
| planar, order 2, Venkatakrishnan (8-32) | quads | 4.68e-04 / 1.32e-01 / 1.78e-01 / 7.66e+01 | 1.56 / 1.96 / 1.79 / 1.93 | 1.36 / 1.86 / 1.59 / 1.89 | 0.47 / 1.51 / 1.05 / 1.36 | 2.04 | 0.27 | 4,712 | 20 |
| planar, order 2, Venkatakrishnan (8-32) | distorted quads | 6.79e-04 / 2.00e-01 / 2.22e-01 / 1.11e+02 | 1.83 / 1.99 / 1.81 / 1.94 | 1.58 / 1.88 / 1.58 / 1.93 | 0.98 / 1.67 / 0.66 / 1.69 | 1.55 | 0.26 | 4,433 | 19 |
| planar, order 2, Venkatakrishnan (8-32) | triangles | 1.81e-03 / 3.67e-01 / 3.12e-01 / 1.14e+02 | 1.72 / 1.60 / 1.70 / 1.79 | 1.61 / 1.52 / 1.64 / 1.78 | 1.19 / 1.47 / 1.08 / 1.26 | 2.22 | 0.29 | 6,745 | 39 |
| planar, order 2, Venkatakrishnan (8-32) | mixed | 1.14e-03 / 2.57e-01 / 2.39e-01 / 1.05e+02 | 1.56 / 1.60 / 1.64 / 1.76 | 1.40 / 1.52 / 1.55 / 1.74 | 0.57 / 0.67 / 0.28 / 1.42 | 2.02 | 0.30 | 5,382 | 28 |

- Orders listed per variable rho / u / v / p. Errors in SI units (kg/m³, m/s, m/s, Pa).
- The GCI columns apply the three-mesh GCI procedure (aeroflowsim/gci.py) to the L2 error of p: its observed order should match and the asymptotic ratio be near 1.
- First order and the Venkatakrishnan limiter are reported for information (not pass/fail): Finding (Prompt 7b): with Venkatakrishnan's limiter the order does NOT approach 2 on finer meshes; on triangles and mixed meshes it falls towards 1. Its threshold eps² = (K h / L)³ scale² shrinks faster than the cell-to-cell differences of a smooth field (h^1.5 against h), so the limiter clips the smooth extrema more and more as the mesh is refined. Smooth flows on fine meshes therefore keep full second order only with 'None' or a larger K; an order-preserving limiter (e.g. Michalak and Ollivier-Gooch 2008) is in the gap register.

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

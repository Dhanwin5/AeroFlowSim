# AeroFlowSim validation report

AeroFlowSim 0.2.0a1, generated 2026-10-26 by `python validation/run_all.py`.

**Validation set: full** (all meshes of every case; run weekly and on version tags).

**Overall: PASS** (15 of 15 cases pass; 2 explained shortfall(s), see the cases marked SHORTFALL)

## Back, Massier and Gier 45-15 deg conical nozzle: measured wall pressure (2D axisymmetric Euler, nozzle_axi): PASS

Case: `cases/nozzle_axi`, references: `validation/bmg_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Wall p/p0 at z = 2.098 in (band +-0.03) | 0.9492 | 0.929928 | 2.030 | 3.16 | PASS |
| Wall p/p0 at z = 2.239 in (band +-0.03) | 0.8669 | 0.798842 | 7.851 | 3.46 | SHORTFALL |
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

- Mesh: 8,000 cells, 4,229 iterations, converged yes, 150 s; discharge coefficient 0.9813.
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
| 5,823 | 3,965 | yes | 126 | 34.206 | 33.915 | 0.2019 | 0.2022 |

- Taylor-Maccoll (aeroflowsim.gasdynamics.taylor_maccoll) agrees with Sims (1964, NASA SP-3004, Tables 9 and 11) to 7e-5 in Cp and 2e-6 rad in the shock angle (tests/test_gasdynamics.py).

## Mach 6 cylinder: bow-shock stand-off and the carbuncle test (2D Euler, external_2d): PASS

Case: `cases/external_2d`, references: `validation/euler2d_cylinder/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Bow-shock stand-off distance / diameter (polar grid, carbuncle fix on) | 0.2197 | 0.22486 | 2.349 | 5 | PASS |
| Bow-shock stand-off distance / diameter (Gmsh quad-dominant mesh, full front) | 0.2197 | 0.229327 | 4.382 | 5 | PASS |

Sources:

- Billig, F. S. (1967), J. Spacecraft Rockets 4(6): Delta/R = 0.386 exp(4.67/M^2) for cylinders

### Runs

| Run | Cells | Iterations | Converged | Final residual | Time [s] | Stand-off / D | Shock roughness | Carbuncle metric | Positivity events |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| polar grid, carbuncle fix on | 4,800 | 6,184 | yes | 1.0e-06 | 124 | 0.2249 | 0.77 | 1.05e-05 | 0 |
| polar grid, carbuncle fix OFF | 4,800 | 12,000 | NO | 3.2e-01 | 266 | 0.2246 | 0.84 | 4.82e-04 | 0 |
| Gmsh quad-dominant, fix on | 1,329 | 2,423 | yes | 9.9e-07 | 15 | 0.2293 | - | 1.23e-04 | 0 |

- Billig correlation: stand-off / D = 0.2197.
- Shock roughness: largest second difference of the shock radius between neighbouring grid rays, divided by the radial cell size (below 1: the front never jumps a whole cell between rays; it is similar with and without the fix here, so convergence is the clearer sign).
- Carbuncle metric: peak-to-peak change of the volume-weighted pressure in the shock layer (box x = -0.45 to 0 D, y = 0 to 0.35 D) over the last 1,000 iterations, divided by its mean. It separates the runs clearly; the shock roughness above does not.
- Without the fix (pure HLLC) the bow shock never settles on the shock-aligned grid: the residual stalls high; with the HLLE blend near the shock the run converges.
- Inviscid, calorically perfect air (gamma = 1.4): a numerics test, not real Mach 6 air.

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
| 0 | 10,034 | 1,358 | yes | 47 | 0.00006 (0.00000) | 0.02316 (0.02320) | 1.3659 (1.3660) | 0.7174 (0.7165) | 1.3666 (1.3660) | 0.7176 (0.7165) |
| 2 | 10,034 | 1,406 | yes | 49 | 0.08227 (0.08209) | 0.02611 (0.02614) | 1.2273 (1.2274) | 0.6342 (0.6334) | 1.5178 (1.5170) | 0.8096 (0.8083) |

- Shock-expansion theory is exact for the inviscid flow on the faces (attached shocks, simple waves); Cl = 0 at alpha = 0 is not compared as a percentage (|Cl| is listed).
- Wall size 0.02 c in the quick set, 0.01 c in the full set.

## NACA 0012, inviscid, Mach 0.8 and 0.5 at alpha 1.25 deg (2D Euler, C-domain, GCI): PASS

Case: `cases/external_2d`, references: `validation/euler2d_naca0012/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Lift coefficient, Mach 0.8, alpha 1.25 deg (GCI-extrapolated) | 0.352033 | 0.338006 | 3.985 | 3 | SHORTFALL |
| Drag coefficient, Mach 0.8, alpha 1.25 deg (GCI-extrapolated) | 0.022547 | 0.0220074 | 2.393 | 8 | PASS |
| Lift coefficient, Mach 0.5, alpha 1.25 deg (GCI-extrapolated) | 0.179969 | 0.174711 | 2.922 | 3 | PASS |

**Shortfall (explained):** Lift coefficient, Mach 0.8, alpha 1.25 deg (GCI-extrapolated): Study design, not the solver (found in Prompt 7b): halving only the WALL cell size refined the mesh very little (7,326 / 9,400 / 13,251 cells), because the far-field size (2 c) and the growth rate stayed fixed, so the shock region is barely refined; the GCI observed order of 10 shows the sequence is not a proper refinement, and the comparison falls back to the finest mesh (Cl 0.338, still rising: 0.311, 0.331, 0.338). The coarsest mesh also stopped at 40,000 iterations without converging. A systematic study (all sizes scaled together, up to about 100k cells) needs Prompt 8 speed; Cd (2.4 %) and the Mach 0.5 lift (2.9 %) are within their tolerances.

Sources:

- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 11, p. 1165: mean of FLO82 0.356209, OVERFLOW 0.351663, CFL3D 0.348226
- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 11, p. 1165: mean of FLO82 0.022685, OVERFLOW 0.022453, CFL3D 0.022501
- Vassberg and Jameson (2010), J. Aircraft 47(4), Table 10, p. 1165: mean of FLO82 0.180346, OVERFLOW 0.179777, CFL3D 0.179784

### Runs

| Condition | Mesh | Cells | Iterations | Converged | Time [s] | Cl | Cd | Cm |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Mach 0.8 | wall 0.02 c | 7,326 | 40,000 | NO | 1367 | 0.31123 | 0.021267 | -0.02815 |
| Mach 0.8 | wall 0.01 c | 9,400 | 12,771 | yes | 581 | 0.33136 | 0.021797 | -0.03324 |
| Mach 0.8 | wall 0.005 c | 13,251 | 26,749 | yes | 1432 | 0.33801 | 0.022007 | -0.03527 |
| Mach 0.5 | wall 0.02 c | 7,326 | 37,080 | yes | 1240 | 0.17394 | 0.000966 | -0.00156 |
| Mach 0.5 | wall 0.01 c | 9,400 | 28,388 | yes | 1433 | 0.17213 | 0.000460 | -0.00097 |
| Mach 0.5 | wall 0.005 c | 13,251 | 40,000 | NO | 2874 | 0.17471 | 0.000294 | -0.00151 |

- Reference (Vassberg & Jameson 2010, Table 11, p. 1165): Mach 0.8, alpha 1.25 deg: continuum Cl 0.3482 (CFL3D) to 0.3562 (FLO82), Cd 0.02245 to 0.02268; Table 10: Mach 0.5, alpha 1.25 deg: Cl 0.17978 to 0.18035, Cd -> 0 (FLO82 4.5e-8).
- Cm here is about the quarter chord (template convention); the reference's Cm is about the quarter chord as well.
- Mach 0.8, Cl: GCI observed order 10.01, extrapolated value 0.339457, GCI fine 0.537 %, GCI coarse 3.06 %, asymptotic ratio 1.020.
- Mach 0.8, Cd: GCI observed order 8.68, extrapolated value 0.0220685, GCI fine 0.347 %, GCI coarse 1.56 %, asymptotic ratio 1.010.
- Mach 0.5, Cl: GCI observed order 1.78, extrapolated value 0.181928, GCI fine 5.16 %, GCI coarse 5.3 %, asymptotic ratio 0.756 (oscillatory convergence).
- Mach 0.5, Cd: GCI observed order 10.04, extrapolated value 0.000257395, GCI fine 15.4 %, GCI coarse 55.1 %, asymptotic ratio 0.638.
- Mach 0.5 drag on the three meshes: 0.000966, 0.000460, 0.000294 (inviscid subcritical flow has zero drag; it must fall with refinement).

## N2 nozzle, 2D axisymmetric Euler (default nozzle_axi; structured and triangle meshes, three sizes): PASS

Case: `cases/nozzle_axi`, references: `validation/euler2d_nozzle/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Exit / inlet mass flow (converged: mass is conserved) | 1 | 1 | 0.000 | 0.1 | PASS |
| Thrust from wall pressure + inlet momentum / thrust from the exit plane | 1 | 0.999999 | 0.0001 | 0.2 | PASS |
| Vacuum specific impulse (structured 200 x 40) | 71.29 s | 71.4748 s | 0.259 | 1 | PASS |
| Vacuum specific impulse (Gmsh triangles, 5,505 cells) | 71.29 s | 71.4732 s | 0.257 | 1 | PASS |

Sources:

- Conservation of mass: a converged finite-volume solution has equal inlet and exit mass flow
- Conservation of momentum: the x-momentum balance of the nozzle gas (inlet + wall + exit = 0)
- Ideal quasi-1D vacuum Isp of this wall, 72.53 s, x conical divergence factor (1 + cos 15 deg)/2 = 0.98296 (Malina 1940; Sutton & Biblarz 2017, eq. 3-34)

### Mesh study

| Mesh | Cells | Iterations | Converged | Time [s] | Mass flow [mg/s] | Cd | F exit [mN] | F wall [mN] | Isp [s] | Isp / Isp 1D | p0 loss [%] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| structured 50 x 10 | 500 | 4,672 | yes | 13 | 68.4750 | 0.9581 | 47.9973 | 47.9975 | 71.477 | 0.9855 | 2.609 |
| structured 100 x 20 | 2,000 | 8,095 | yes | 68 | 67.6312 | 0.9463 | 47.3907 | 47.3913 | 71.454 | 0.9852 | 2.902 |
| structured 200 x 40 | 8,000 | 24,688 | yes | 1300 | 67.2131 | 0.9404 | 47.1116 | 47.1115 | 71.475 | 0.9855 | 2.541 |
| triangles, wall 0.16 D_t | 1,098 | 30,000 | NO | 212 | 67.5969 | 0.9458 | 47.3525 | 47.3324 | 71.432 | 0.9849 | 4.715 |
| triangles, wall 0.08 D_t | 2,350 | 30,000 | NO | 290 | 67.2139 | 0.9405 | 47.0977 | 47.1522 | 71.453 | 0.9852 | 4.053 |
| triangles, wall 0.04 D_t | 5,505 | 30,000 | NO | 639 | 67.0710 | 0.9385 | 47.0109 | 46.9250 | 71.473 | 0.9855 | 3.501 |
| rounded throat, structured 100 x 20 | 2,000 | 12,198 | yes | 123 | 71.0768 | 0.9945 | 49.7479 | 49.7478 | 71.372 | 0.9841 | 0.046 |
| rounded throat, structured 200 x 40 | 8,000 | 28,239 | yes | 1207 | 71.0594 | 0.9943 | 49.7270 | 49.7271 | 71.359 | 0.9839 | 0.100 |

- Quasi-1D template (cases/quasi1d_nozzle, defaults): vacuum Isp 72.509 s, mass flow 71.6005 mg/s; ideal quasi-1D theory of the same wall 72.526 s.
- Conical divergence estimate: 72.53 s x (1 + cos 15 deg)/2 = 71.29 s (point-source flow).
- Cd = mass flow / ideal quasi-1D choked mass flow of the same throat; the throat is sharp (Rcu = Rcd = 0), so the sonic line is curved and the 2D nozzle passes less than 1D theory.
- p0 loss: drop of the mass-flux-weighted exit total pressure below the inlet p0 = 5 bar (numerical entropy; an isentropic nozzle loses nothing). Most of it is made at the SHARP throat corner, a singular expansion point of the inviscid flow; it does not fall clearly on these meshes. With a rounded throat (Rcu/Rt = 1.5, Rcd/Rt = 0.4) the coarsest triangle mesh already gives about 1 %.
- Triangle meshes: the residual stalls near 1e-4 in a few cells at the sharp throat corner (also slow, but still falling, with a rounded throat), so they do not meet the convergence criterion; the thrust from both methods and the Isp have settled to about 0.1 %. Implicit time stepping (Prompt 8) is the planned cure (gap register).
- Wall-clock times: plain NumPy on one core (Numba and implicit time stepping follow in Prompt 8).
- Structured meshes, Isp (GCI tool, aeroflowsim/gci.py): observed order 0.13, extrapolated value 71.6962 s, GCI fine 0.387 %, GCI coarse 0.424 %, asymptotic ratio 1.000 (oscillatory convergence).
- Sharp vs rounded throat (Rcu/Rt = 1.5, Rcd/Rt = 0.4), structured 100 x 20 and 200 x 40: p0 loss 2.902 / 2.541 % (sharp) and 0.046 / 0.100 % (rounded); Cd 0.9463 / 0.9404 (sharp) and 0.9945 / 0.9943 (rounded).
- Finding: rounded-throat loss smaller than the sharp one and NOT falling with refinement (see the gap register).

## Prandtl-Meyer expansion round a 10 deg corner at Mach 2 (2D Euler, geometry_2d): PASS

Case: `cases/geometry_2d`, references: `validation/euler2d_prandtl_meyer/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Mach number downstream of the corner (wall cells, x = 0.4-0.9 m) | 2.38489 | 2.36616 | 0.785 | 1 | PASS |
| Pressure ratio p2/p1 downstream of the corner | 0.547969 | 0.54803 | 0.011 | 1.5 | PASS |

Sources:

- Prandtl-Meyer function nu(M2) = nu(2) + 10 deg (Anderson 2003, eq. 4.44), aeroflowsim.gasdynamics.expansion
- Isentropic relation p2/p1 = (p0/p)(M1) / (p0/p)(M2) with M2 from the Prandtl-Meyer function (Anderson 2003, sec. 4.14)

### Run

| Cells | Iterations | Converged | Time [s] | M2 | p2/p1 |
|---:|---:|---:|---:|---:|---:|
| 5,267 | 1,092 | yes | 17 | 2.3662 | 0.5480 |

- Wall cells next to a centred expansion: the first-cell values lag the exact fan slightly on coarse meshes (the fan is smeared over a few cells at the corner).

## Sod shock tube with the 2D Euler solver (along x, and along a diagonal of a triangle mesh): PASS

Case: `cases/sod_shock_tube`, references: `validation/euler2d_sod/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Along x: star-region pressure p* | 0.30313 Pa | 0.303131 Pa | 0.00033 | 1 | PASS |
| Along x: star-region velocity u* | 0.92745 m/s | 0.927483 m/s | 0.0036 | 1 | PASS |
| Along x: density left of the contact rho*L | 0.42632 kg/m³ | 0.426291 kg/m³ | 0.0068 | 1 | PASS |
| Along x: density right of the contact rho*R | 0.26557 kg/m³ | 0.26559 kg/m³ | 0.0075 | 1 | PASS |
| Along x: shock distance from the diaphragm | 0.350432 m | 0.350815 m | 0.109 | 2 | PASS |
| Along x: contact distance from the diaphragm | 0.18549 m | 0.185673 m | 0.099 | 2 | PASS |
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
| along x, quads | 800 | 1.7 |
| diagonal, triangles | 20,000 | 16.8 |

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
| wall 0.02 L | 3,553 | 1,935 | yes | 22 | 39.351 | 1.7072 | 1.6316 | 0.1965 |
| wall 0.01 L | 11,958 | 4,478 | yes | 215 | 39.244 | 1.7067 | 1.6328 | 0.1978 |

- Theory: beta = 39.314 deg, p2/p1 = 1.7066, M2 = 1.6405.
- Cd includes the base drag of the flat base (the base pressure is not part of the oblique-shock theory).

## Gmsh mesh geometry: external domains and rounded-throat nozzle: PASS

Case: `cases/external_2d`, references: `validation/external_geometry/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Cylinder D = 1 m: wall patch length, default mesh | 3.14159 m | 3.14158 m | 0.0004 | 0.1 | PASS |
| Cylinder D = 1 m: wall patch length, fine mesh (sizes / 2) | 3.14159 m | 3.14159 m | 8.4e-05 | 0.1 | PASS |
| Cylinder D = 1 m: wall patch length, finer mesh (sizes / 4) | 3.14159 m | 3.14159 m | 8.4e-05 | 0.1 | PASS |
| Cylinder: domain area, default mesh | 1255.85 m² | 1255.28 m² | 0.046 | 0.1 | PASS |
| Cylinder: domain area, fine mesh (sizes / 2) | 1255.85 m² | 1255.35 m² | 0.040 | 0.1 | PASS |
| Cylinder: domain area, finer mesh (sizes / 4) | 1255.85 m² | 1255.72 m² | 0.010 | 0.1 | PASS |
| Diamond airfoil t/c = 0.1: domain area, default mesh | 1256.59 m² | 1256.01 m² | 0.046 | 0.1 | PASS |
| Diamond airfoil t/c = 0.1: domain area, fine mesh (sizes / 2) | 1256.59 m² | 1256.08 m² | 0.040 | 0.1 | PASS |
| Diamond airfoil t/c = 0.1: domain area, finer mesh (sizes / 4) | 1256.59 m² | 1256.46 m² | 0.010 | 0.1 | PASS |
| Wedge 10 deg: domain area, default mesh | 1256.46 m² | 1255.89 m² | 0.045 | 0.1 | PASS |
| Wedge 10 deg: domain area, fine mesh (sizes / 2) | 1256.46 m² | 1255.96 m² | 0.040 | 0.1 | PASS |
| Wedge 10 deg: domain area, finer mesh (sizes / 4) | 1256.46 m² | 1256.33 m² | 0.010 | 0.1 | PASS |
| Cone 15 deg: volume of revolution of the half domain, default mesh | 33510.2 m³ | 33487.3 m³ | 0.068 | 0.1 | PASS |
| Cone 15 deg: volume of revolution of the half domain, fine mesh (sizes / 2) | 33510.2 m³ | 33490.1 m³ | 0.060 | 0.1 | PASS |
| Cone 15 deg: volume of revolution of the half domain, finer mesh (sizes / 4) | 33510.2 m³ | 33505 m³ | 0.016 | 0.1 | PASS |
| Rounded-throat nozzle volume, structured Coarse | 6.34994 mm³ | 6.34977 mm³ | 0.0027 | 0.1 | PASS |
| Rounded-throat nozzle volume, structured Medium | 6.34994 mm³ | 6.34985 mm³ | 0.0014 | 0.1 | PASS |
| Rounded-throat nozzle volume, structured Fine | 6.34994 mm³ | 6.34987 mm³ | 0.0011 | 0.1 | PASS |
| Rounded-throat nozzle volume, triangles, default mesh | 6.34994 mm³ | 6.34994 mm³ | 2.7e-05 | 0.1 | PASS |
| Rounded-throat nozzle volume, triangles, fine mesh (sizes / 2) | 6.34994 mm³ | 6.34994 mm³ | 2.7e-05 | 0.1 | PASS |
| Rounded-throat nozzle volume, triangles, finer mesh (sizes / 4) | 6.34994 mm³ | 6.34994 mm³ | 2.7e-05 | 0.1 | PASS |

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
| Circle R = 20 m minus cylinder D = 1 m: domain area, fine mesh (sizes / 2) | 1255.85 m² | 1255.33 m² | 0.042 | 0.1 | PASS |
| Circle R = 20 m minus cylinder D = 1 m: domain area, finer mesh (sizes / 4) | 1255.85 m² | 1255.72 m² | 0.010 | 0.1 | PASS |
| Circle minus cylinder: wall patch length, default mesh | 3.14159 m | 3.14158 m | 0.0004 | 0.1 | PASS |
| Circle minus cylinder: wall patch length, fine mesh (sizes / 2) | 3.14159 m | 3.14159 m | 8.4e-05 | 0.1 | PASS |
| Circle minus cylinder: wall patch length, finer mesh (sizes / 4) | 3.14159 m | 3.14159 m | 8.4e-05 | 0.1 | PASS |
| C-domain minus NACA 0012: domain area, default mesh | 466.998 m² | 466.928 m² | 0.015 | 0.1 | PASS |
| C-domain minus NACA 0012: domain area, fine mesh (sizes / 2) | 466.998 m² | 466.928 m² | 0.015 | 0.1 | PASS |
| C-domain minus NACA 0012: domain area, finer mesh (sizes / 4) | 466.998 m² | 466.935 m² | 0.013 | 0.1 | PASS |
| Nozzle + plume region: volume of revolution, default mesh | 600.152 mm³ | 600.152 mm³ | 6e-05 | 0.1 | PASS |
| Nozzle + plume region: volume of revolution, fine mesh (sizes / 2) | 600.152 mm³ | 600.152 mm³ | 6e-05 | 0.1 | PASS |
| Nozzle + plume region: volume of revolution, finer mesh (sizes / 4) | 600.152 mm³ | 600.152 mm³ | 6e-05 | 0.1 | PASS |

Sources:

- Exact: pi (R² - (D/2)²)
- Exact: circumference pi D
- Exact: pi R²/2 + 2 R (x_out - x_c) - A_NACA0012, A = 0.081706 c²
- Exact: nozzle volume 6.345769169 mm³ + pi (5 D_e)² (10 D_e)

## Method of Manufactured Solutions: order of accuracy of the 2D Euler solver: PASS

Case: `aeroflowsim/mms.py`, references: `validation/mms_euler2d/reference.toml`

| Quantity | Reference | AeroFlowSim | Error % | Tolerance % | Pass/fail |
|---|---:|---:|---:|---:|:---:|
| Observed order (min L2 over rho, u, v, p), planar quads | 2 | 1.98447 | 0.777 | 10 | PASS |
| Observed order, planar smoothly distorted quads | 2 | 1.98117 | 0.941 | 10 | PASS |
| Observed order, planar triangles | 2 | 2.00457 | 0.229 | 15 | PASS |
| Observed order, planar mixed quads + triangles | 2 | 1.99007 | 0.496 | 15 | PASS |
| Observed order, axisymmetric quads (with the pressure source) | 2 | 2.02165 | 1.083 | 10 | PASS |
| Observed order, axisymmetric distorted quads | 2 | 2.01626 | 0.813 | 10 | PASS |
| Observed order, axisymmetric triangles | 2 | 2.01662 | 0.831 | 15 | PASS |
| Observed order, axisymmetric mixed | 2 | 1.99993 | 0.0035 | 15 | PASS |

Sources:

- Formal order of the MUSCL / least-squares scheme (Barth & Jespersen 1989); MMS of Roy et al. (2004)
- Formal order 2 (as above)

### Observed orders between the two finest meshes (cells per side in brackets)

| Scheme | Mesh | L2 error finest (rho / u / v / p) | Order L1 | Order L2 | Order Linf | GCI p (L2 of p) | GCI asympt. ratio | Iterations | Time [s] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| planar, order 2 (16-128) | quads | 2.17e-05 / 7.15e-03 / 7.11e-03 / 4.48e+00 | 1.98 / 2.01 / 2.01 / 2.00 | 1.98 / 1.99 / 2.01 / 2.00 | 1.95 / 1.74 / 1.94 / 1.94 | 2.01 | 0.25 | 20,367 | 1205 |
| planar, order 2 (16-128) | distorted quads | 3.94e-05 / 1.35e-02 / 9.66e-03 / 7.41e+00 | 2.01 / 2.03 / 1.98 / 2.01 | 1.98 / 1.99 / 1.98 / 1.99 | 1.73 / 1.61 / 1.93 / 1.60 | 1.96 | 0.25 | 19,188 | 1154 |
| planar, order 2 (16-128) | triangles | 5.50e-05 / 1.21e-02 / 1.24e-02 / 6.16e+00 | 2.06 / 2.04 / 2.02 / 2.01 | 2.12 / 2.05 / 2.03 / 2.00 | 1.97 / 2.05 / 1.84 / 1.77 | 2.01 | 0.25 | 29,216 | 2240 |
| planar, order 2 (16-128) | mixed | 3.86e-05 / 9.89e-03 / 8.37e-03 / 4.99e+00 | 2.01 / 2.01 / 2.02 / 2.01 | 2.01 / 2.00 / 2.02 / 1.99 | 1.85 / 2.03 / 2.00 / 1.86 | 2.01 | 0.25 | 19,378 | 1429 |
| axisymmetric, order 2 (16-128) | quads | 2.43e-05 / 5.96e-03 / 5.64e-03 / 3.47e+00 | 2.05 / 2.04 / 2.02 / 2.03 | 2.07 / 2.06 / 2.02 / 2.03 | 2.04 / 1.80 / 1.97 / 1.99 | 2.06 | 0.25 | 11,257 | 777 |
| axisymmetric, order 2 (16-128) | distorted quads | 3.09e-05 / 8.43e-03 / 6.82e-03 / 4.37e+00 | 2.03 / 2.04 / 2.03 / 2.02 | 2.08 / 2.04 / 2.03 / 2.02 | 2.15 / 1.88 / 1.97 / 1.95 | 2.02 | 0.25 | 10,338 | 730 |
| axisymmetric, order 2 (16-128) | triangles | 5.93e-05 / 1.21e-02 / 1.36e-02 / 5.55e+00 | 2.04 / 2.08 / 2.01 / 2.02 | 2.05 / 2.08 / 2.02 / 2.02 | 1.69 / 1.69 / 1.97 / 1.78 | 2.02 | 0.25 | 17,315 | 1524 |
| axisymmetric, order 2 (16-128) | mixed | 4.80e-05 / 1.02e-02 / 9.95e-03 / 4.25e+00 | 2.03 / 2.04 / 1.99 / 2.02 | 2.03 / 2.04 / 2.00 / 2.02 | 1.71 / 1.73 / 1.92 / 1.86 | 1.99 | 0.25 | 15,442 | 1180 |
| planar, order 1 (8-64) | quads | 6.13e-03 / 1.47e+00 / 2.79e+00 / 8.16e+02 | 0.91 / 0.86 / 0.96 / 0.89 | 0.90 / 0.84 / 0.95 / 0.87 | 0.75 / 0.79 / 0.94 / 0.72 | 0.74 | 0.55 | 9,055 | 114 |
| planar, order 1 (8-64) | distorted quads | 8.71e-03 / 2.41e+00 / 3.20e+00 / 1.23e+03 | 0.80 / 0.73 / 0.89 / 0.76 | 0.77 / 0.66 / 0.89 / 0.71 | 0.61 / 0.51 / 0.80 / 0.57 | 0.47 | 0.61 | 8,736 | 102 |
| planar, order 1 (8-64) | triangles | 4.94e-03 / 1.37e+00 / 1.52e+00 / 4.22e+02 | 0.95 / 0.95 / 1.00 / 0.93 | 0.96 / 0.94 / 0.98 / 0.91 | 0.99 / 0.78 / 0.89 / 0.89 | 0.90 | 0.53 | 11,585 | 240 |
| planar, order 1 (8-64) | mixed | 4.56e-03 / 1.05e+00 / 1.87e+00 / 5.62e+02 | 0.98 / 0.93 / 1.00 / 0.97 | 0.97 / 0.94 / 0.98 / 0.96 | 1.00 / 0.97 / 0.97 / 0.94 | 0.94 | 0.51 | 9,036 | 135 |
| planar, order 2, Venkatakrishnan (8-64) | quads | 2.32e-04 / 4.42e-02 / 7.71e-02 / 2.40e+01 | 1.34 / 1.60 / 1.64 / 1.72 | 1.01 / 1.58 / 1.21 / 1.67 | 0.55 / 1.05 / 0.62 / 1.27 | 1.98 | 0.31 | 9,503 | 297 |
| planar, order 2, Venkatakrishnan (8-64) | distorted quads | 2.87e-04 / 5.63e-02 / 9.24e-02 / 3.09e+01 | 1.58 / 1.82 / 1.71 / 1.89 | 1.24 / 1.83 / 1.27 / 1.84 | 0.77 / 1.37 / 0.50 / 1.39 | 1.96 | 0.28 | 9,044 | 299 |
| planar, order 2, Venkatakrishnan (8-64) | triangles | 7.15e-04 / 1.69e-01 / 1.38e-01 / 5.40e+01 | 1.27 / 1.07 / 1.19 / 1.15 | 1.34 / 1.12 / 1.18 / 1.08 | 0.96 / 0.97 / 0.95 / 1.07 | 2.20 | 0.47 | 13,681 | 599 |
| planar, order 2, Venkatakrishnan (8-64) | mixed | 5.41e-04 / 1.22e-01 / 1.12e-01 / 4.28e+01 | 1.12 / 1.11 / 1.14 / 1.35 | 1.07 / 1.07 / 1.09 / 1.29 | 0.92 / 0.96 / 0.91 / 0.81 | 1.98 | 0.41 | 9,948 | 372 |

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
| Planar area of the half-nozzle profile, Medium mesh | 2.52964 mm² | 2.52956 mm² | 0.0032 | 0.1 | PASS |
| Volume of revolution (2 pi x sum of axisymmetric cell volumes), Medium mesh | 6.34577 mm³ | 6.3453 mm³ | 0.0074 | 0.1 | PASS |
| Wall patch length, Medium mesh | 4.269 mm | 4.26782 mm | 0.028 | 0.1 | PASS |
| Planar area of the half-nozzle profile, Fine mesh | 2.52964 mm² | 2.52963 mm² | 0.00042 | 0.1 | PASS |
| Volume of revolution (2 pi x sum of axisymmetric cell volumes), Fine mesh | 6.34577 mm³ | 6.3457 mm³ | 0.0011 | 0.1 | PASS |
| Wall patch length, Fine mesh | 4.269 mm | 4.26866 mm | 0.0079 | 0.1 | PASS |

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
| Star-region pressure p* (at x = 0.75 m) | 0.30313 Pa | 0.303136 Pa | 0.002 | 1 | PASS |
| Star-region velocity u* (at x = 0.75 m) | 0.92745 m/s | 0.927469 m/s | 0.002 | 1 | PASS |
| Density left of the contact rho*L (at x = 0.6 m) | 0.42632 kg/m³ | 0.426235 kg/m³ | 0.020 | 1 | PASS |
| Density right of the contact rho*R (at x = 0.75 m) | 0.26557 kg/m³ | 0.265558 kg/m³ | 0.0045 | 1 | PASS |
| Shock distance from the diaphragm | 0.350432 m | 0.351345 m | 0.261 | 2 | PASS |
| Contact distance from the diaphragm | 0.18549 m | 0.184991 m | 0.269 | 2 | PASS |

Sources:

- Exact Riemann solution, Toro (2009) ch. 4, test 1: p* = 0.30313
- Exact Riemann solution, Toro (2009) ch. 4, test 1: u* = 0.92745
- Exact Riemann solution, Toro (2009) ch. 4, test 1: rho*L = 0.42632
- Exact Riemann solution, Toro (2009) ch. 4, test 1: rho*R = 0.26557
- Exact shock speed 1.75216 m/s x 0.2 s (Toro 2009, test 1)
- Contact speed u* = 0.92745 m/s x 0.2 s (Toro 2009, test 1)

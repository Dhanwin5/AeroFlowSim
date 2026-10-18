# AeroFlowSim validation report

AeroFlowSim 0.1.0.dev0, generated 2026-10-18 by `python validation/run_all.py`.

**Overall: PASS** (3 of 3 cases pass)

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

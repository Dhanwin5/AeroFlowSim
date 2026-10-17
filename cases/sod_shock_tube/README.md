# Sod shock tube

A tube is split by a diaphragm at `x0`. The left gas is at high pressure and the right
gas at low pressure, both at rest. At `t = 0` the diaphragm bursts. A rarefaction runs
into the high-pressure gas, a shock runs into the low-pressure gas, and between them a
contact discontinuity separates the two gases. This is the standard first test for any
compressible-flow solver, because the exact solution is known.

## Equations

1D Euler equations in conservative form:

    dU/dt + dF(U)/dx = 0

    U = [ rho,  rho u,        E       ]
    F = [ rho u, rho u² + p,  u (E + p) ]

Ideal, calorically perfect gas:  `E = p/(gamma - 1) + rho u²/2`.
Output fields: density, velocity, pressure, specific internal energy `e = p/((gamma-1) rho)`
and Mach number `M = |u|/c` with `c = sqrt(gamma p / rho)`.

Default inputs (standard Sod problem, non-dimensional values entered in SI units):
`rho_L = 1, u_L = 0, p_L = 1, rho_R = 0.125, u_R = 0, p_R = 0.1, gamma = 1.4, L = 1, x0 = 0.5,
t_end = 0.2`, 400 cells, CFL = 0.5.

## Numerical method (code in `aeroflowsim/euler1d.py`)

- **Finite volumes.** Each cell stores the cell average of U. A cell changes only
  through the fluxes at its two faces: `dU_i/dt = -(F_{i+1/2} - F_{i-1/2}) / dx`.
  Mass, momentum and energy are therefore conserved exactly.
- **HLLC flux** (Toro §10.4). The Riemann problem at each face is approximated by
  three waves: the fastest left wave `S_L`, the contact `S*` and the fastest right wave
  `S_R`, with two constant star states around the contact (from Rankine–Hugoniot).
  The flux is chosen by where the face sits in this wave fan. Keeping the contact wave
  (the "C") keeps contact discontinuities sharp.
- **MUSCL reconstruction with the minmod limiter.** The primitive variables (rho, u, p)
  are taken as linear inside each cell, which is second order in smooth flow. By
  Godunov's theorem, a linear second-order scheme would oscillate at shocks. The minmod
  limiter takes the smaller of the two neighbour slopes, or zero at a local extremum.
  This makes the scheme TVD: no new wiggles, and rho and p stay positive. At
  discontinuities the scheme becomes first order.
- **SSP-RK2 (Heun) time stepping.**
  `U1 = U^n + dt L(U^n)`, `U^{n+1} = (U^n + U1 + dt L(U1)) / 2`.
  This is a convex mix of forward-Euler steps, so it keeps the TVD property. The time
  step is `dt = CFL dx / max(|u| + c)`, and the last step is shortened to land exactly
  on `t_end`.
- **Transmissive boundaries.** Two ghost cells at each end copy the end cell.

## Exact solution (code in `aeroflowsim/riemann_exact.py`)

Toro, chapter 4. Pressure p* and velocity u* are continuous across the contact. Each
outer wave is a shock (if `p* > p_K`) or a rarefaction (if `p* <= p_K`), which gives
`u* = u_L - f_L(p*)` and `u* = u_R + f_R(p*)`. Setting these equal gives
`f_L(p) + f_R(p) + (u_R - u_L) = 0`, which is solved by Newton–Raphson from the
two-rarefaction guess. The solution is then sampled at `xi = (x - x0)/t` at every cell
centre. For Sod: p* = 0.30313, u* = 0.92745, shock at x = 0.8504, contact at x = 0.6855
(t = 0.2).

## Assumptions

- Inviscid, adiabatic, one-dimensional flow; calorically perfect ideal gas.
- Transmissive ends are only exact while no wave has reached them. For the defaults the
  rarefaction head reaches x = 0.26 and the shock x = 0.85 at t = 0.2, so this holds.
- Vacuum-generating initial states are rejected by the exact solver.

## Validation (`test_case.py`)

1. The density L1 error decreases for 100 → 200 → 400 cells. The observed order must be
   above 0.6; it is about 0.85, because the discontinuities limit the order to about 1.
2. Totals of mass, momentum and energy match "initial total + boundary flux × t" to a
   relative 1e-10. The ends carry a pressure flux, so total momentum grows by
   `(p_L - p_R) t`.
3. Density and pressure stay positive.
4. Shock and contact positions are within 2 cell widths of the exact ones.
5. Progress is reported every step, and the Stop signal ends the run cleanly.

## Reference

E. F. Toro, *Riemann Solvers and Numerical Methods for Fluid Dynamics: A Practical
Introduction*, 3rd ed., Springer, 2009. Chapter 4 (exact Riemann solver), §10.4 (HLLC),
chapters 13–14 (MUSCL, TVD limiters).
G. A. Sod, "A survey of several finite difference methods for systems of nonlinear
hyperbolic conservation laws", *J. Comput. Phys.* 27 (1978) 1–31.

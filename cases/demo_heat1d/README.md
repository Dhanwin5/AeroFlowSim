# demo_heat1d — steady 1D heat conduction (demo case)

Purpose: prove the case system works end to end (parameters → mesh → solve → compare with exact solution → save).
It is not a nozzle case.

## Physics
Steady conduction in a rod of length `L` with uniform volumetric heat generation `q_gen`:

    k d²T/dx² + q_gen = 0,     0 ≤ x ≤ L
    T(0) = T_left,  T(L) = T_right

## Assumptions
- Steady state, one-dimensional (no radial temperature variation)
- Constant thermal conductivity `k`
- Uniform heat generation; no convection or radiation from the rod surface

## Exact solution
    T(x) = T_left + (T_right − T_left)·x/L + q_gen/(2k)·x·(L − x)

With the defaults (L = 1 m, k = 50 W/(m·K), q_gen = 5·10⁴ W/m³, 300 K / 400 K):
T_max = 480 K at x = 0.6 m; heat leaving the ends q_left = 30 000 W/m², q_right = 20 000 W/m²
(sum = q_gen·L = 50 000 W/m², the global energy balance).

## Numerics
- Uniform mesh, 2nd-order central difference for d²T/dx².
- Solved by **pseudo-time marching to steady state**: march dT/dτ = d²T/dx² + q_gen/k with the largest
  stable explicit step (dτ/dx² = 0.5, which is identical to Jacobi iteration) until the residual stops changing.
  This is the same idea used later for the quasi-1D nozzle solvers. It is deliberately simple, not fast:
  the number of iterations grows with (number of nodes)².
- Residual: RMS of the discrete equation at interior nodes, normalised by its first value.
- End heat fluxes from 2nd-order one-sided differences.

## Validation (test_case.py)
Central differences are exact for a parabola, so the converged numerical solution must equal the exact
solution at the nodes up to the convergence tolerance:
1. max nodal error < 1·10⁻⁶ K
2. q_left + q_right = q_gen·L within 0.1 %
3. progress() is called every iteration and the residual falls below the tolerance.

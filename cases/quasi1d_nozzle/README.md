# Quasi-1D nozzle (`quasi1d_nozzle`)

Steady, inviscid flow of a gas (default nitrogen) through a converging-diverging nozzle, from a
reservoir (p0, T0) to a back pressure p_back. The gas comes from the gas library
(`aeroflowsim/gases/`: N2, air, O2, Ar, He, Kr, Xe, CO2, H2, H2O, R-236fa, or a custom gas); it is a
calorically perfect gas, so this case uses its gamma and R. The default N2 has gamma = 1.4 and
R = 296.8 J/(kg K), exactly the values of the validated results. After every run the validity checks
also judge the gas model: ideal-gas validity (compressibility factor Z), condensation risk (margin to
the saturation / frost temperature) and the temperature range of the gas data. Default geometry: the N2 cold-gas thruster
(inlet Ø 2.0 mm, straight inlet 1.33 mm, 30° convergent cone, throat Ø 0.280 mm,
15° divergent cone, exit Ø 0.911 mm, A_e/A* = 10.59, length 4.00 mm).
The throat is sharp by default; `Rcu/Rt` and `Rcd/Rt` round it with circular arcs (shared nozzle
geometry, see `cases/nozzle_axi/README.md`). The validated results use the sharp default.

```
python -m aeroflowsim run cases/quasi1d_nozzle
python -m aeroflowsim run cases/quasi1d_nozzle --set p_back=250000
python -m aeroflowsim run cases/quasi1d_nozzle --set gas=Kr
python -m aeroflowsim run cases/quasi1d_nozzle --set "geometry_source=Custom profile (CSV)"
```

## Equations

The flow is assumed to vary only along the axis x; at each x it is uniform over the
cross-section A(x). Balancing mass, momentum and energy over a thin slice of the duct (the whole
slice, not per unit area) gives the quasi-1D Euler equations:

    ∂(U A)/∂t + ∂(F A)/∂x = S

    U = [ρ, ρu, E]              E = p/(γ−1) + ρu²/2
    F = [ρu, ρu² + p, u(E + p)]
    S = [0, p dA/dx, 0]

**Why the area term appears.** Mass and energy enter and leave a slice only through its two end
faces, so they have no source. Momentum also gets a force from the side wall: the wall is slanted,
so the wall pressure has an axial component. Over the slice that force is p·dA (pressure times the
wall area projected onto the x-direction). Check with gas at rest in a cone: the end faces give a
net force p·A(x+dx) − p·A(x) = p·dA, and the slanted wall pushes back with exactly −p·dA, so the
gas stays put.

## Numerics

Finite volumes. Cell i lies between faces i−½ and i+½ and has volume V_i = ½(A_{i−½} + A_{i+½}) Δx_i:

    V_i dU_i/dt = −(F A)_{i+½} + (F A)_{i−½} + [0, p_i (A_{i+½} − A_{i−½}), 0]

* Face fluxes: HLLC Riemann solver with MUSCL/minmod reconstruction of ρ, u, p
  (`aeroflowsim/euler1d.py`, the same code as the Sod shock tube).
* **Well-balanced source.** The source uses the cell pressure times the difference of the face
  areas. For gas at rest every face flux is exactly (0, p, 0), so in the momentum equation
  −p A_{i+½} + p A_{i−½} + p (A_{i+½} − A_{i−½}) = 0. To make this exactly zero (not just ~1e-16),
  the code writes it as −[(F_{i+½} − p_i) A_{i+½} − (F_{i−½} − p_i) A_{i−½}].
  Test 3 checks that gas at rest stays at rest to the last bit.
* **Mesh.** One face sits exactly at the throat, so the smallest face area is the throat area. The
  cells are smallest at the throat (default: 10× smaller than evenly spread cells) and grow by a
  constant factor towards both ends. A sharp throat needs this: there M − 1 grows like the square
  root of the distance from the throat, so coarse cells there give a poor throat Mach number.
* **Steady state with local time stepping.** Only the final steady state matters, so "time" is just
  an iteration counter. Every cell takes its own largest stable step,
  Δt_i = CFL · Δx_i / (|u_i| + c_i), with SSP-RK2. Small or fast cells then don't hold back the
  others. The residual is the RMS of the density right-hand side, divided by its value at the
  first iteration. The run stops when it has dropped by `tol` (default 1e-8, 8 orders) or at
  `max_iter`.
* **CFL = 0.2 (default).** At higher CFL numbers the minmod limiter can fall into a limit cycle
  near the sonic throat. Where minmod picks the downwind slope, the scheme acts locally like a
  central scheme, and SSP-RK2 slightly amplifies such modes (|1 + iy − y²/2|² = 1 + y⁴/4). The
  residual then stops falling. At CFL 0.2 the default case converges 8 orders in about 45 000
  iterations (≈ 20 s).
* **Finer meshes (≥ about 450 cells).** The same limit cycle appears at CFL 0.2 once the residual has
  dropped by 6 to 7 orders: the throat cells get smaller and the sonic point sits in fewer of them. The
  solution is steady by then (the exit Mach number agrees with a fully converged CFL 0.1 run to 1e-10),
  so for fine meshes set the residual drop to 1e-6, or use CFL 0.1 for 8 orders (about twice the
  iterations). The number of iterations grows about in proportion to the number of cells (local time
  stepping is explicit); implicit time stepping (Speed stage) removes this. At 5 000 cells (throat
  cells about 1/10 000 of the nozzle length) the residual stalls already near 1e-2, but the mass flow
  through inlet and exit agrees to 0.001 % and the exit Mach number to 1e-5 between CFL 0.1 and 0.2.
* **Initial guess.** The isentropic solution on the correct branch. For a supersonic exit it is
  subsonic before the throat and supersonic after. When the back pressure is high enough for a
  shock (or fully subsonic flow), the run starts subsonic after the throat as well. The outlet
  then "hears" the back pressure, and the supersonic region and the shock form by themselves.
* **Shock cases** stop converging at a residual of about 1e-3. The limiter keeps switching in the
  one or two cells of the captured shock, which is a known property of MUSCL schemes. The shock
  position and all other values are steady by then (about 10 000 iterations). Lower `max_iter`
  for such runs.

## Boundary conditions

Ghost cells (two on each side) carry the boundary information into the HLLC/MUSCL face fluxes.

* **Inlet, subsonic, from a reservoir.** Of the three characteristic waves (u − c, u, u + c), two
  enter the domain and one (u − c) leaves it. So two quantities come from outside, the total
  pressure p0 and the total temperature T0, and one comes from inside: the velocity u of the
  first cell. Then T = T0 − u²/(2c_p), p = p0 (T/T0)^{γ/(γ−1)} and ρ = p/(RT).
* **Outlet.** If the last cell is supersonic, all waves leave, so everything is copied from the
  last cell and the back pressure has no influence (as in reality). If it is subsonic, one wave
  (u − c) enters, so the pressure is set to p_back and ρ and u are copied.

## Outputs

Fields along x (cell centres): Mach number, pressure, temperature, density, velocity.

Key numbers (SI):

| name | meaning |
|---|---|
| `mdot` | mass flow [kg/s] through the exit face (`mdot_inlet`, `mdot_throat`, `mdot_exit` for the conservation check) |
| `mdot_theory` | choked mass flow p0 A* √(γ/(R T0)) (2/(γ+1))^{(γ+1)/(2(γ−1))} |
| `M_throat` | Mach number at the throat face (between the two throat cells) |
| `M_exit`, `p_exit`, `T_exit`, `u_exit` | exit-plane state: the MUSCL state just inside the exit face, the state the exit flux is computed from |
| `F_vacuum` | vacuum thrust ṁ u_e + p_e A_e = (ρu² + p) A at the exit face [N] |
| `Isp_vacuum` | F_vacuum / (ṁ g0), g0 = 9.80665 m/s² [s] |
| `F_at_p_back` | thrust at the given back pressure, F_vacuum − p_back A_e [N] |
| `x_shock`, `x_shock_exact` | shock position (Mach falls through 1) and theory, if a shock stands in the nozzle |

Results tab: the shape view draws the nozzle wall, mirrored about the axis, coloured by the chosen
field, labelled "quasi-1D: varies along x only".

## Reference solution (`reference()`)

`aeroflowsim/gasdynamics.py`, with A* = throat area:

* Isentropic area–Mach relation A/A* = (1/M)[(2/(γ+1))(1 + (γ−1)/2 M²)]^{(γ+1)/(2(γ−1))}:
  subsonic branch before the throat, supersonic branch after it.
* If the back pressure lies between the "shock at the exit" and the "subsonic, just choked"
  exit pressures, a normal shock stands in the divergent part. Its area A_s comes from requiring
  the exit pressure to equal p_back: supersonic flow up to A_s, then a normal-shock jump (total
  pressure ratio p02/p01), then subsonic isentropic flow with the larger sonic area
  A*₂ = A*·p01/p02. The default nozzle at 2.5 bar has A_s/A* = 2.61 and M1 = 2.49, 0.32 mm after
  the throat.
* Back pressure ≥ the subsonic choking pressure: subsonic everywhere (unchoked). Back pressure =
  p0: gas at rest.

## Geometry

Geometry source (Setup tab):

* **Parametric (conical):** the inputs above (`aeroflowsim.geometry.conical_nozzle`), sharp corners.
* **Custom profile (CSV):** a file with header `x_mm,r_mm` (axial position and wall **radius**
  in mm), x strictly increasing, r > 0, at least 5 points. `aeroflowsim/geometry.py` converts it to metres
  and interpolates with PCHIP (smooth, never overshoots, so the throat is never narrower than the
  data). The throat is the smallest given radius. A file that breaks a rule gives a message saying
  which line and what to fix. `examples/n2_conical_nozzle.csv` is the default cone sampled every
  0.01 mm plus all corner points (made with `aeroflowsim.geometry.write_profile_csv`). Because PCHIP
  rounds each corner only within one 0.01 mm interval, it gives the same answer as the parametric
  run within 0.2 %.

## Assumptions

* Quasi-1D: flow uniform over each cross-section, purely axial. There is **no divergence loss**,
  so the thrust is the ideal value. A real 15° cone loses the factor λ = (1 + cos 15°)/2 = 0.983 of
  its momentum thrust, so the ideal value is about 1.7 % above a real 15° cone.
* Inviscid and adiabatic: no boundary layers (which matter at this small size and low Reynolds
  number) and no heat transfer.
* Calorically perfect gas (N2: γ = 1.4, R = 296.8 J/(kg·K)). No condensation, although T_exit ≈
  70 K at 1 kPa back pressure is close to the N2 saturation line.
* Shocks outside the nozzle (over-expanded jet) are not modelled. The exit stays supersonic until
  the back pressure is high enough to push a normal shock inside.

## Derived design numbers (shown under the inputs, `derived()` in `case.py`)

Ideal isentropic nozzle theory, before any run: throat and exit area, area ratio, design exit Mach
number, pressure and temperature, choked mass flow, ideal vacuum thrust and Isp, the flow regime at
the chosen back pressure, and the two critical back pressures: p_b1 (above it the nozzle is not
choked) and p_b2 (normal shock exactly at the exit; below it the exit flow is supersonic).

## Validation (`test_case.py`, default geometry, p0 = 5 bar, T0 = 293.15 K)

1. p_back = 1 kPa: M_exit 3.99 (±2 %), p_exit 3.36 kPa (±5 %), ṁ 71.5 mg/s (±2 %),
   F_vacuum 50.8 mN (±2 %), throat Mach 1 (±3 %).
2. Mass flow at inlet, throat and exit equal within 0.5 %.
3. Back pressure = p0: velocity below 1e-8 m/s everywhere (well-balanced).
4. p_back = 2.5 bar: normal shock 0.32 mm after the throat (A/A* = 2.61, M1 = 2.49); solver within 2 cells.
5. CSV profile run = parametric run within 1 % (exit Mach, ṁ, thrust).
6. Residual drops by at least 6 orders of magnitude.

Also: the Mach number matches theory within 2 % downstream of the throat, and the Stop button ends a run.

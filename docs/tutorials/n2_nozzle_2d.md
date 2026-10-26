# Tutorial: 2D flow through my N2 nozzle

The default nozzle of AeroFlowSim is a small N2 cold-gas thruster: throat Ø 0.280 mm, 15° conical
divergent, exit Ø 0.911 mm (A_e/A_t = 10.59), fed at p0 = 5 bar and T0 = 293.15 K, exhausting into 1 kPa.
The quasi-1D template gives a vacuum Isp of 72.51 s. Here you solve the same nozzle as a 2D axisymmetric
flow and see what quasi-1D theory leaves out: the conical divergence and the curved sonic line at a sharp
throat. About 20 minutes, most of it waiting for the run.

1. **New project** from the template **Axisymmetric nozzle (2D Euler)** (`nozzle_axi`).
2. **Geometry step.** The default conical nozzle (sharp throat). The drawing shows the four named boundaries:
   `inlet`, `outlet`, `wall` and `axis` (r = 0).
3. **Mesh step.** Keep **Structured**, preset **Medium** (200 × 40 = 8,000 cells, clustered at the throat),
   **Generate mesh**. For a first look use **Coarse** (2,000 cells): it runs in about a minute and gives
   almost the same Isp.
4. **Setup step.**
   - **Gas** N2; **Operating conditions** p0 = 500 kPa, T0 = 293.15 K, back pressure 1 kPa;
     **Initial solution: Quasi-1D solution** (the isentropic flow of this wall as the start: the throat is
     already sonic, so the run only has to add the 2D effects).
   - **Boundary conditions:** `inlet` = Total-pressure inlet (500 kPa, 293.15 K, normal to the boundary),
     `outlet` = Pressure outlet (1 kPa; the exit flow is supersonic, so the solver ignores it there, as a real
     nozzle does), `wall` = Slip wall, `axis` = Axis. They follow the Operating conditions until you change a
     row yourself.
   - **Numerics:** the defaults (CFL 0.8, second order, Venkatakrishnan limiter frozen after 4 orders,
     residual tolerance 1e-6, thrust and mass flow settled to 1e-4 over 500 iterations).
5. **Run step → Run.** Watch the four residuals fall, and under them the thrust computed two ways and the
   mass flow in and out: they come together as the run converges. The Medium mesh needs 24,688
   iterations, 13 to 19 minutes in plain NumPy depending on the computer (Numba arrives in Prompt 8).
6. **Results step.**
   - **Key results:** mass flow, discharge coefficient, exit Mach number and pressure, vacuum thrust and
     thrust at the back pressure, vacuum Isp, and the Isp of the ideal quasi-1D nozzle of the same wall.
   - **Field: Mach number:** subsonic in the inlet (Mach 0.01), sonic at the throat, about 4 at the exit.
     The sharp throat corner turns the flow suddenly: the expansion fan starts at the corner, and the sonic
     line is curved, not the straight line quasi-1D theory assumes.
   - **Plot: Wall pressure p/p0 along x:** the dots (2D) follow the dashed quasi-1D line except just after
     the throat, where the flow over-expands round the corner and recompresses.
   - Click any cell: all its values are in Properties.
7. **Compare with theory.** On the Medium mesh: mass flow **67.21 mg/s**, discharge coefficient **0.940**,
   vacuum thrust **47.11 mN** (exit plane and wall + inlet agree to 0.0002 %), vacuum Isp **71.47 s**: 1.5 %
   below the ideal quasi-1D 72.53 s (the quasi-1D template: 72.51 s).
   A conical nozzle sends its gas out along spherical fronts, so only a fraction λ = (1 + cos 15°)/2 = 0.983 of
   the exit momentum is axial (Malina 1940): 72.53 s × 0.983 = 71.29 s. The 2D solver is 0.26 % above that
   estimate (λ is exact only for flow from a point source), on every mesh (71.43 to 71.48 s on six meshes).
   The mass flow is 6 % below the ideal choked mass flow (71.47 mg/s): with a sharp throat the sonic line bends
   upstream, so the effective throat is smaller than the geometric one.
8. **Check what the validity checks say:** convergence, mass balance, thrust two ways, monitors settled,
   positivity, gas checks (ideal gas, condensation margin at the cold exit, temperature range) and the total-
   pressure loss. The last one warns: the exit total pressure is about 2.5 % below p0. In an isentropic
   nozzle it would be zero; here it is numerical entropy made at the sharp throat corner.

**Things to try**

- **Rounded throat:** Rcu/Rt = `1.5`, Rcd/Rt = `0.4` (Geometry inputs). The discharge coefficient rises to
  about 0.99 and the total-pressure loss falls to about 1 %: the corner was the cause.
- **Triangles (Gmsh)** mesh type: the same Isp to 0.1 %, but the residual stalls near 1e-4 at the sharp throat
  (see the gap register); the run stops at the iteration limit and the Convergence check says so.
- **Stop and look:** press **Stop** at any time: the Results step shows the flow of that moment (marked
  *stopped*, not converged). The Run button then reads **Continue (from iteration N + 1)**: it carries on, with
  the residual and monitor curves continuing. **Start from scratch** begins again from the Initial solution.
- **Change an input and continue:** after a run, change for example the back pressure and press Continue: the run
  carries on from the current flow with the new value, much faster than from scratch. A new mesh always starts
  from scratch (the old flow does not fit it).
- **Save .vtu…** in the Results step writes every field and the velocity vector for ParaView.

The numbers of all six meshes (structured and triangles, three sizes each) are in `validation/report.md`
(case "N2 nozzle, 2D axisymmetric Euler").

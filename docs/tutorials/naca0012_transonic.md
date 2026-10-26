# Tutorial: NACA 0012 in transonic flow

Inviscid flow round a NACA 0012 at Mach 0.8 and 1.25 deg angle of attack has a shock on the upper surface (strong)
and the lower surface (weak). The grid-converged answer is known to about 1-2 %: Cl about 0.352 and Cd about 0.0225
(Vassberg and Jameson 2010, J. Aircraft 47(4), Table 11). You will set up a C-domain, watch Cl and Cd converge,
plot Cp and estimate the mesh error with the GCI tool. About 30 minutes plus run time.

1. **New project** from **Body in free stream (2D Euler)**. Shape **NACA 4-digit airfoil**, digits `0012`. For the
   reference's sharp-trailing-edge geometry use **Custom coordinates file** with
   `validation/euler2d_naca0012/naca0012_vassberg_jameson.dat`.
2. **C-domain.** In the Geometry step **History** tab suppress *Template far field*; **Enclosure... > C-domain**,
   radius `30`, downstream `30`.
3. **Mesh.** Wall size `0.005` (in chords), far-field size `2`, growth `1.15`, triangles. Generate.
4. **Setup.** Mach `0.8`, angle of attack `1.25` deg, air. The far-field boundary gets the free stream.
5. **Monitors.** Cl, Cd and Cm are built-in monitors. In **Results > Reports > Forces** you can keep them as report
   definitions; a definition used as convergence criterion makes the run wait until it has settled.
6. **Run.** The residual falls; the shock moves for a while and then settles; watch Cl.
7. **Cp plot.** **Results > Plots** chooses *Pressure coefficient*; the upper-surface shock is the jump near
   x = 0.6-0.65 c. For a custom plot use **XY plot**: field *Pressure coefficient*, surface *wall*, x axis
   *Position x*. The *Mach number normal to the pressure gradient* field shows the shocks as a jump through 1.
8. **Mesh study with the GCI tool.** Save a snapshot, halve the wall size, Run (the new mesh starts from the
   interpolated old solution), save a snapshot, halve again. With the three Cl values:

   ```python
   from aeroflowsim import gci
   g = gci.three_mesh(h=(h_fine, h_medium, h_coarse), phi=(cl_fine, cl_medium, cl_coarse))
   print(g.summary())          # observed order, extrapolated Cl, GCI of the fine mesh
   ```

   Use 1/sqrt(number of cells) as h. The validation case `validation/euler2d_naca0012` does exactly this.
9. **Mach 0.5.** Repeat at Mach 0.5: the flow is shock-free and the drag must fall towards zero as the mesh is
   refined (any drag left is numerical error).

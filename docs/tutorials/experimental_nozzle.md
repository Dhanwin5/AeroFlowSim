# Tutorial: comparing with an experiment (Back, Massier and Gier nozzle)

Back, Massier and Gier (JPL Technical Report 32-654, 1964) measured the wall pressure along conical nozzles. You will
build their 45-15 deg nozzle (throat radius 0.8 in, throat curvature radius 0.5 in), solve it with the 2D
axisymmetric Euler solver and plot the measured points on top of the computed wall pressure. About 20 minutes.

1. **New project** from **Axisymmetric nozzle (2D Euler)**.
2. **Geometry.** Geometry source **Custom profile (CSV)**, file `validation/bmg_nozzle/bmg_45_15_profile.csv`
   (columns x_mm, r_mm; made from the dimensions printed in the report, see `validation/bmg_nozzle/README.md`).
3. **Mesh.** Structured, preset Medium (200 x 40).
4. **Setup.** Gas air, p0 = 1034 kPa (150 psia), T0 = 833 K (1500 R), back pressure 1 kPa (the exit flow is
   supersonic).
5. **Run** and open **Results**.
6. **Measured data.** The digitized points are in `validation/bmg_nozzle/bmg_wall_pressure.csv` (z in inches). For
   the XY plot, make a CSV with x in metres (z x 0.0254) and p/p0, and choose it as *Reference data*; plot *Pressure
   ratio p/p0* along *wall* against *Position x*.
7. **What to expect.** Computed and measured p/p0 agree within about 0.03 at 8 of the 9 compared positions, and the
   2D solver reproduces the dip just downstream of the throat that one-dimensional theory misses (the report found
   up to 45 % deviation from 1D there). Just after the start of the throat arc (z = 2.24 in) the computed pressure is
   0.07 lower than measured; the wall pressure falls very steeply there, so a few hundredths of an inch of position
   uncertainty could account for it; the cause is not settled (see the validation report).
8. The automatic comparison with its tolerance band is the validation case `validation/bmg_nozzle`.

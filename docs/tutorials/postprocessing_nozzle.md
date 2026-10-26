# Tutorial: post-processing a nozzle

You will take the N2 nozzle example, look at its flow in several ways, measure the exit total pressure and the mass
flow on your own surfaces, watch them live during a run, use one as a convergence criterion, plot the wall pressure
against quasi-1D theory, and write the report. About 20 minutes; the run takes about a minute.

1. **Open the example.** On the start page double-click **N2 nozzle (2D axisymmetric, with its result)**. A copy
   opens from your projects folder; go to **Results**.
2. **Look at the flow.** In the **Display** panel:
   - Field *Mach number*, tick **Contour lines** (12 levels) and **Labels on the lines**.
   - Tick **Mirror about the axis / symmetry line**: the whole nozzle cross-section.
   - Tick **3D revolved view**: the nozzle as a surface of revolution; drag with the mouse to turn it.
     **Reset view** (right-click) brings back the 2D view; untick 3D.
   - Tick **Streamlines**, then right-click in the flow near the inlet and choose **Seed a streamline here** a few
     times. Field *Numerical schlieren* with *Cell values* shows the expansion round the sharp throat corner.
3. **Make surfaces.** In **Surfaces** press **Line by two clicks** and click across the nozzle at the throat (from
   the axis to beyond the wall: the line is cut at the wall). Press **New...**, type *Line x = constant*,
   x = 3 mm.
4. **Measure.** In **Reports > Surface**: surface *line*, operation *Mass flow rate*, **Compute**; then surface
   *outlet*: the two agree (the run is converged: mass is conserved). Operation *Mass-weighted average*, field
   *Total pressure* on *outlet*: the exit p0, a little below the inlet's 500 kPa (numerical loss, mostly at the sharp
   throat corner). **Fluxes** shows the mass and energy balance of every boundary (imbalance far below 0.01 %).
5. **Keep it.** With *Mass-weighted average of p0 on outlet* selected press **Keep as report definition...**, name
   it `p0 exit`. In **Definitions** select it, **Monitor settings...**: tick *Evaluate during the run* and *Use as a
   convergence criterion*, tolerance 1e-5 over 300 iterations.
6. **Run with the monitor.** In the Run step press **Start from scratch**. The new monitor appears under the
   residuals; `results/report_p0 exit.csv` grows while the run goes on. The run converges only when p0 exit has
   settled too. Stop it half-way and press **Continue**: the file continues at the next iteration.
7. **XY plot.** In **XY plot** choose field *Pressure ratio p/p0*... or *Pressure*, surface *wall*, x axis *Position
   x*, tick *Log y*, **Plot**. For your own measurements, *Reference data* reads a CSV with columns x [m], value
   [SI]. **Save picture...** writes it in the light paper style (PNG, SVG or PDF).
8. **Snapshot and compare.** **Snapshots > Save current...** `baseline`. Change the back pressure or p0 in Setup,
   Run, then **Compare with current**: four linked views (current, baseline, difference, current with lines) and a
   key-number table.
9. **Report.** Press **Report...** under the views. The HTML file opens in your browser: everything above, in your
   display units, with the fingerprints that identify the inputs.

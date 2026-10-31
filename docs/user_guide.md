# AeroFlowSim user guide

AeroFlowSim 0.2.0a1 (2D alpha). A GUI-first, open-source CFD solver for nozzle and propulsion aerodynamics, with
built-in validity checks and published validation. This guide shows how to install it, make a first project, use
every step page and the post-processing tools, write a report, and where your files live.

Contents: [Install](#install) · [First project](#first-project) · [The steps](#the-five-steps) ·
[Post-processing](#post-processing-the-results-step-for-2d-flows) · [Report](#the-automatic-report) ·
[Units](#units) · [Keyboard](#keyboard-shortcuts) · [Files](#where-files-live) ·
[Command line](#command-line-and-scripts) · [Troubleshooting](#troubleshooting)

## Install

**Windows installer.** Run `AeroFlowSim-0.2.0a1-setup.exe`. It installs for your user only (no administrator
rights) into `%LOCALAPPDATA%\Programs\AeroFlowSim`, adds AeroFlowSim to the Start menu and lets you open a project by
double-clicking the file `project.afsproj` inside its folder. Uninstall from Windows Settings > Apps, or the
"Uninstall AeroFlowSim" Start-menu entry; your projects are never deleted.

The installer is **not code-signed** yet. Windows SmartScreen may say "Windows protected your PC": click
*More info*, then *Run anyway*. The download size is about 400 MB (Qt, VTK, Gmsh, NumPy/SciPy are included).

**macOS installer** (Apple silicon: `AeroFlowSim-<version>-macOS-arm64.dmg`; Intel Macs: `...-macOS-x86_64.dmg`).
Open the .dmg and drag AeroFlowSim onto Applications. The app is **not signed by Apple** yet, so the first time
macOS says it cannot check it: right-click (or Control-click) AeroFlowSim in Applications, choose *Open*, then *Open*
again (on recent macOS: System Settings > Privacy & Security > *Open Anyway*). After that it opens normally. On Intel
Macs the solver runs without its compiled (Numba) kernels, which no longer support them: every feature works and the
results are the same, but runs take several times longer than on Apple silicon. Your
settings, log and own gases are in `~/Library/Application Support/AeroFlowSim`; projects in
`Documents/AeroFlowSim Projects`. Uninstall: drag AeroFlowSim from Applications to the Bin.

**Linux AppImage** (`AeroFlowSim-<version>-x86_64.AppImage`, for Ubuntu 22.04 and newer and similar systems): one
file, nothing to install. Make it runnable and start it:

```bash
chmod +x AeroFlowSim-*-x86_64.AppImage
./AeroFlowSim-*-x86_64.AppImage
```

If it says FUSE is missing, install `libfuse2` (Ubuntu: `sudo apt install libfuse2`) or start it with
`--appimage-extract-and-run`. The command line works the same: `./AeroFlowSim-...AppImage run "My nozzle.afsproj"`.

**With pip** (Windows, macOS or Linux, Python 3.13): everything, including the templates and example projects:

```bash
python3 -m venv aeroflowsim-env
source aeroflowsim-env/bin/activate        # Windows: aeroflowsim-env\Scripts\activate
pip install --pre aeroflowsim                 # --pre: the current versions are alphas
python -m aeroflowsim gui
```

On Linux the Gmsh mesher needs a few system libraries: `sudo apt install libglu1-mesa libxcursor1 libxft2
libxinerama1`.

**From the source code** (any system with Python 3.13):

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m aeroflowsim gui
```

## First project

1. Start AeroFlowSim. The start page offers the templates and the example projects (N2 nozzle, NACA 0012
   transonic, Mach 2 wedge, Sod shock tube).
2. **File > New project**, choose *Axisymmetric nozzle (2D Euler)*, give it a name. Projects are saved in
   `Documents\AeroFlowSim Projects` unless you choose another folder.
3. Press **Run** (F5). AeroFlowSim makes the mesh, then solves; the Run step shows the residuals and the monitors
   (thrust, mass flow) live. Stop keeps the flow of that moment; Run again continues from it.
4. Open **Results**: Mach contours, wall pressure against quasi-1D theory, key numbers (thrust, Isp, Cd).

## The five steps

The workflow strip at the bottom shows each step's status: green up to date, amber needs update (an input it depends
on changed), grey not started, red failed. A running job shows its progress and a cancel button in its chip.

- **Geometry** - the template's shape, or your own: import CSV / DAT / DXF / STEP / IGES, sketch with the mouse
  (lines, arcs, splines with snapping, constraints and dimensions), edit (move, rotate, fillet, trim, offset, ...),
  booleans, enclosures (far-field circle, box, C-domain, nozzle plume region), name boundaries by clicking, add
  refinement regions. Every edit can be undone.
- **Mesh** - structured or Gmsh meshes (triangles, quad-dominant, inflation layers); quality fields and checks;
  click a cell for its values.
- **Setup** - gas, operating conditions, the boundary-condition table (one row per named boundary), numerics.
  *Suggested numerics* proposes CFL, first-order start and initial solution, with reasons.
- **Run** - Run / Continue, Start from scratch, Stop. *Start options* holds the **patch regions** (boxes or circles
  with their own p, T, u, v on top of the Initial solution, for a start from scratch) and the switch for starting a
  run on a **new mesh from the old solution interpolated onto it** (on by default; the Run step says when it is
  used). Your **report definitions marked "monitor"** are plotted next to the built-in monitors and written to
  `results/report_<name>.csv` while the run goes on; a continued run continues the file, Start from scratch begins a
  new one.
- **Results** - for 1D flows: field plots against the exact solution, x-t diagram. For 2D flows: the
  post-processing workspace described next.

## Post-processing: the Results step for 2D flows

On the left are seven panels (tabs on the left edge); on the right one, two or four views of the flow (their cameras
are linked: pan or zoom one and the others follow), and under them the plots and the key numbers.

**Display** - per view: what it shows (the current result, a snapshot, or the difference current minus snapshot
with a blue-white-red colour map), the field (flow fields, derived fields such as Cp, schlieren, vorticity, the shock
indicator, mesh quality, the residual of the last iteration per cell, and your own fields), colouring (smooth from
node values, cell values, or bands), contour lines (number or typed levels, labels), colour map, range (automatic,
typed, over all snapshots, clipped), log scale, colour-bar position and number format, mesh edges, boundaries,
vectors (velocity or a gradient; size, density, equal length, colour by a field), streamlines (from a line or rake
surface or from clicked points, with arrow marks), mirror about the axis, and the 3D revolved view of axisymmetric
results (rotate it with the mouse; Reset view returns to 2D). **Saved scenes** keep all of this plus the camera in
the project; Restore brings a scene back in one click. **Picture**: PNG at 1-8 x the window resolution, transparent
background, paper style (light, whatever the theme); Copy puts it on the clipboard. **Histogram** shows the
distribution of the field (cell count or volume-weighted) with min / mean / max.

In the view: hover for the value under the mouse; click a cell to see all its values in Properties; right-click for
*Probe here*, *Pin a probe here* (a point surface), *Start a line surface here*, *Seed a streamline here*, *Zoom to
fit*, *Reset view*, *Save picture*.

**Surfaces** - named surfaces for plots and integrals: boundaries (always available), lines, rakes (lines with seed
points), points, iso-lines (where a field has a value) and lines x = c / y = c. Create them by typing values (in your
length unit) or by clicking: *Line by two clicks*, *Point by one click*. Rename, edit, delete, show or hide. Surfaces
are geometric, so they survive re-meshing.

**Reports** - *Surface*: area, integral, area- or mass-weighted average, mass flow, flux of mass / momentum / energy,
min, max, standard deviation on any surface (planar: per metre of depth; axisymmetric: the full circle). On a
boundary the mass flow uses the solver's own boundary fluxes, so it equals the solver's number. *Volume*: volume,
mass, volume-weighted average, min, max over the domain, a box or a circle. *Fluxes*: mass, momentum and energy
through every boundary and the net imbalance. *Forces*: pressure force and moment of any walls, body and wind axes,
coefficients with editable reference values, centre of pressure. *Definitions*: "Keep as report definition" turns
any of these into a named quantity of the project, evaluated after every run; *Monitor settings* makes it a live
monitor and, if wanted, a convergence criterion (settled within a tolerance over a window of iterations).

**XY plot** - any fields along one or more surfaces, against x, y, arc length or another field; reference data from
a CSV file (two columns x, y in SI units) as markers; snapshots overlaid as dashed lines; log axes; cell values as
steps. The plot appears in the Plots area; save it as PNG / SVG / PDF (paper style) or CSV, or keep its settings in
the project.

**Snapshots** - save the current result under a name (compressed, with its mesh), rename, delete (asked first),
restore as the current result (you are offered to save the current one first), compare with the current result (four
views: current, snapshot, difference, and a key-number table). The panel shows the project size and warns above
500 MB.

**Fields** - your own field functions: a name and a formula of fields and constants, e.g. `p / 1e5`,
`sqrt(u**2 + v**2)`, `rho * u`. Allowed: + - * / ** %, numbers, field names, `pi e g0 gamma R`, and functions such
as `sqrt exp log log10 abs sin cos tan minimum maximum`. The formula is checked as you type (unknown names, syntax,
adding different units); it can never run other code. Your fields are available everywhere a field is.

**Animation** - play back how the flow developed during the run. While the run is solving, AeroFlowSim keeps
*frames* of the flow (density, velocity and pressure in every cell); the last frame is the final result. For a
steady run the frames show the convergence in pseudo-time: the start-up transient (shocks forming and moving into
place) until the steady state. Press Play; the first / previous / next / last buttons and the slider step through the frames; the label shows
the iteration (or the time of a time-accurate run). Speed (2-30 frames per second), Loop, and the colour range:
*Fixed over all frames* (default: a colour means the same value in every frame) or *Per frame*. Every view that
shows the current result plays the frame with its own Display settings (field, colour map, contour lines, vectors,
streamlines, mirror), so you can watch Mach number and pressure side by side. Leaving the tab shows the final
result again. *Save GIF / MP4* writes the active view's field as an animated GIF (paper style, your units); MP4 is
offered when the ffmpeg program is installed. *Recording* (used by the next run): on by default, *Automatic* keeps
50 to 100 frames spread over the whole run whatever its length, or choose every N iterations. Run again continues
the run and adds frames to the earlier ones; Start from scratch records a new set; with recording off a run keeps
no frames. The frames are stored in `results/animation.npz` next to the result (a few MB) and are out of date
exactly when the result is. Projects run before this feature have no frames: run again to record them.

1D unsteady results (Sod shock tube) have the same playback bar under the field plot: it plays the stored
snapshots (the field against x at up to 200 moments).

**Export** (button under the views): fields as CSV (cell centres or nodes, in your display units), VTU for ParaView
(cell and node data, velocity vector) or Tecplot ASCII; *Save .vtu* is the quick ParaView export.

## The automatic report

**Results > Report...** or **Tools > Project report** writes `results/report/<project>_report.html` (one
self-contained file, pictures included, nothing fetched from the internet) and a PDF: project and fingerprints,
mesh picture and quality, boundary conditions, gas and its sources, numerics, convergence, key numbers, report
definitions, flux balance, validity checks, Mach and pressure pictures and your saved scenes, wall plots and saved
XY plots, comparison with quasi-1D theory (nozzles), snapshots, and how to reproduce the result. In the GUI the
numbers are in your display units; from the command line in SI (the report says which).

## Units

View > Units chooses the display units (default mm, kPa, mg/s, mN). Inputs, tables, plots, colour bars and GUI
exports follow it; everything stored in the project and computed stays SI, and so do the command line, the
validation report and `summary.yaml`.

## Structured grids and meshes from other programs

**Structured C/O-grids.** In the template *Body in free stream*, Mesh step, *Mesh type* **Structured C/O-grid** makes one block of
quadrilaterals that follows the body: a C-grid (wraps round the nose, runs back along the wake) for airfoils with a sharp trailing
edge, an O-grid for smooth closed bodies (cylinder, sphere). Choose Coarse / Medium / Fine or type the cell counts; the first layer height
you type is the exact height of the cell at the wall. A body that does not fit (blunt trailing edge, corners, a flat base) is refused with
the reason. Tutorial: `docs/tutorials/naca0012_c_grid.md`.

**A mesh from another program.** Template *Start from an existing mesh*: pick a Gmsh `.msh` (version 2 or 4), SU2 `.su2`, CGNS or Fluent ASCII
`.msh` file (2D, triangles and quadrilaterals), the unit of its coordinates, *Planar* or *Axisymmetric*, and say what each boundary name is
(`name: type`, types inlet, outlet, wall, axis, farfield, symmetry; names like "wall" or "farfield" need no entry). The numbers under the
inputs list the names found and the type each gets. Every boundary of the mesh must have a name.

**Convert or inspect from the command line:**

    python -m aeroflowsim mesh-info mesh.msh
    python -m aeroflowsim mesh-convert mesh.msh mesh.su2 --unit mm --map "outer: farfield, body: wall"

Export writes Gmsh (2.2 or 4.1), SU2 and CGNS, with the patch names as the boundary names, to run the same mesh in SU2 or OpenFOAM.

## Solver speed and Preferences

The 2D solver uses compiled kernels (Numba) on several CPU cores. **Tools > Preferences > Solver threads**: the default
is the number of physical cores minus one (at most 16), so the window stays responsive; choose fewer to keep cores
free for other work. The thread count changes only the speed, never the results, and applies from the next run
(Continue included). The Run step and the report say how a run was computed (e.g. "Numba, 15 threads").
The very first run on a computer compiles the kernels (about 20-40 s, once); later runs start at once.
On the command line: `python -m aeroflowsim run <case or project> --threads 8`. If Numba is missing, the solver
still works with plain NumPy (10-30 x slower, same results) and says so.

## Time stepping (Numerics)

Steady 2D runs use **Implicit LU-SGS** by default (since the speed stage (LU-SGS)): large time steps, so several times fewer
iterations than the explicit schemes, and the same converged result (the right-hand side is the same second-order
residual). The CFL number input is the START value: the CFL grows as the residual falls, up to 100, and falls again
if the residual rises; after an unphysical step the solver backs off by itself. **SSP-RK3** (explicit, the reference
of earlier versions) and **Jameson 4-stage** stay available; projects saved with them keep them. Continue carries on
with the CFL reached; Start from scratch starts the ramp again. Time-accurate runs (Sod) always use an explicit scheme.

## Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+N / Ctrl+O / Ctrl+S | New, open, save project |
| Ctrl+Z / Ctrl+Y | Undo / redo an input or geometry change |
| F5 / Shift+F5 | Run (continue) / stop |
| Ctrl+T | Light / dark theme |
| F | Fit the view |
| F1 | This user guide |

## Where files live

| What | Where |
|---|---|
| Your projects | `Documents\AeroFlowSim Projects\<name>.afsproj\` (one folder per project) |
| Inputs and settings of a project | `project.yaml` (inputs, surfaces, report definitions, scenes, ...) |
| Geometry, mesh, result | `geometry\`, `mesh\mesh.npz`, `results\run.npz` (exact result) |
| Snapshots | `results\snapshots\<name>\` |
| Report definitions monitored during a run | `results\report_<name>.csv` |
| Report | `results\report\` |
| Custom gases | `%APPDATA%\AeroFlowSim\gases` (copied into a project that uses them) |
| Log file | `%APPDATA%\AeroFlowSim\aeroflowsim.log` |

Zip a project folder to share it: it contains everything needed to reproduce its result exactly.

## Command line and scripts

```
AeroFlowSim.exe run "My nozzle.afsproj"            (from the source: python -m aeroflowsim run ...)
AeroFlowSim.exe run "My nozzle.afsproj" --fresh    start from scratch
AeroFlowSim.exe report "My nozzle.afsproj"
AeroFlowSim.exe export "My nozzle.afsproj" --format tecplot --fields p,M,p0
AeroFlowSim.exe export "My nozzle.afsproj" --surface wall --fields p,Cp
AeroFlowSim.exe export "My nozzle.afsproj" --definitions
AeroFlowSim.exe export "My nozzle.afsproj" --animation flow.gif --field M     (--fps 10, --per-frame-range)
AeroFlowSim.exe snapshot "My nozzle.afsproj" save baseline
```

From Python:

```python
from aeroflowsim.project import Project
from aeroflowsim import post
sol = post.Solution.from_project(Project.open("My nozzle.afsproj"))
print(post.surface_integral(sol, post.Surface.boundary("outlet"), "mass_flow"))      # (value, "kg/s")
print(post.surface_integral(sol, post.Surface.x_line(0.003), "mass_weighted", "p0"))
print(post.flux_balance(sol)["net"])
```

## The optional assistant (off by default)

The assistant turns a description in plain words into proposed values for the boxes of the **Setup** step. It is an
optional typing aid: AeroFlowSim works fully, and identically, with it off or not installed.

**Turn it on:** Tools > Assistant settings > *Turn the assistant on*. Then open the **Assistant** panel in the Setup step,
type for example `Mach 2.4 nitrogen over a 10 degree wedge, 300 bar chamber pressure, 5 bar back pressure`, and press
*Propose*. A table lists every proposed input with its current value, the new value, the unit and the reason. Tick the
rows you want and press *Apply ticked*: all ticked rows change as **one** step, and Ctrl+Z takes them all back. Nothing
changes before you press Apply.

**What it does:** fills inputs that exist in the template (it reads their names, units and ranges from the template, so a new
input is understood at once); checks every value (type, unit, range) before showing it and says why it refused a
proposal; picks a gas from the gas library when you name one ("nitrogen", "helium", "air", "CO2").

**What it never does:** change anything without your tick; touch files, results, settings or the boundary table; run the
solver; type gas properties (the gas comes from the library); put a pressure into a temperature box; invent a number
(a model's numbers must appear in your text); send anything anywhere unless you chose a local or online provider.

The first provider, **Rules (no AI)**, reads phrases such as `Mach 2.4`, `300 bar chamber pressure`, `5 bar back pressure`,
`10 degree wedge`, `angle of attack 4 degrees`, `throat diameter 2 mm`, `500 cells`, `nitrogen`. A pressure or temperature
with no label ("300 bar", "300 K") goes to the total (chamber) value, and the reason says so. Name a shape in full
(for example `wedge`). What it cannot place is listed under the table.

| Provider | Where your text goes | Needs |
|---|---|---|
| **Rules (no AI)** | Nowhere. It is parsed inside AeroFlowSim. | Nothing |
| **Local model** | To a server on THIS computer (for example Ollama on `localhost`). Other addresses are refused. | A model server you already run; its host, port and model name in the settings |
| **Online (your own key)** | Over the internet to the service address you type. Shown as "Online - text leaves this computer". | Its own opt-in tick in the settings, the secure (https) address and model of a service you use, your key (kept in the operating system's keyring, never in a project or a settings file), `pip install keyring` |

What is sent to a model: your description and the *definitions* of the template's inputs (names, units, ranges, help texts).
Never your project files, geometry, results or current input values. No usage statistics, no automatic upload.

**Command line:** `python -m aeroflowsim assist "300 bar chamber pressure, helium" --case "My Nozzle.afsproj" --dry-run`
prints the review table; `--apply` writes the values into the project (a template is read-only: the command then prints the
equivalent `--set` options for `run`). `--provider local --model NAME` and
`--provider online --allow-online --url ... --model ...` choose the other providers;
`python -m aeroflowsim assist-key set` stores the online key in the keyring.

Physics note: see the theory manual, section 15 ("it assists, it never replaces physics").

## Troubleshooting

- **The run does not converge / the residual stalls.** Look at the *Residual of the last iteration* field in the
  Results view: it shows where. On triangle meshes and at attached shocks the explicit solver can stall near
  1e-3-1e-4 while forces have settled (see the gap register; implicit time stepping comes in the speed stage). The
  "What to try" button lists fixes.
- **"Results of an older mesh"** - the mesh changed after the run: press Run (it starts from the interpolated old
  solution).
- **The 3D view is empty** - only axisymmetric results can be revolved.
- **SmartScreen warning** - see [Install](#install).
- **Reporting a problem** - Help > Copy diagnostic info copies the version, system, package versions and the last log
  lines (no personal data) for a bug report.

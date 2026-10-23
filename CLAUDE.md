# AeroFlowSim — project rules

## Mission

AeroFlowSim is a free, open-source CFD software for nozzle aerodynamics and propulsion, with a built-in GUI. Anyone - students, CubeSat teams, researchers, engineers - can set up, mesh, solve and analyse their own cases in one install, and trust the results, because the software checks its own validity and is validated against published benchmarks. Others can extend it, and publish work done with it.

Release claim: "A GUI-first, open-source CFD solver for nozzle and propulsion aerodynamics, with built-in validity checks and published validation."

Always write the name as one word: **AeroFlowSim** (never "AeroFlow Sim"). Python package: `aeroflowsim`.
Licence: GPL-3.0-or-later (`LICENSE`); every `.py` file starts with the 3-line licence header.

## The user
The user is new to programming but knows aerospace engineering and CFD theory:
explain plans, code and tools simply, in plain words; CFD concepts need no simplification.
Clarity matters more than speed.

## Architecture
- **Templates and projects.** A *template* (also called a case) is a folder under `cases/` with the
  physics; a *project* is the user's own work: a folder `<name>.afsproj/` (default in
  `Documents/AeroFlowSim Projects`, never in the code folder) with `project.yaml` (version, template,
  inputs, step records), `geometry/` (copied input files, relative paths), `mesh/` and `results/`
  (`run.npz` = exact results). A zipped project reproduces its results exactly (`aeroflowsim/project.py`).
  The GUI works on one project (one template) at a time.
- Every template has the same two files: `schema.toml` (name, description, steady flag and inputs —
  no code) and `case.py` (physics, contract in `aeroflowsim/case.py`). New templates are found
  automatically and never require changes to old ones. Each input has a workflow `step`
  (`geometry`, `mesh` or `setup`, default `setup`); shape-library inputs are `geometry`.
- **Desktop GUI:** Qt (PySide6) + PyVista/VTK in `aeroflowsim/gui/`, started with
  `python -m aeroflowsim gui`. Workflow steps **Geometry → Mesh → Setup → Run → Results**, shown as a
  *workflow strip* at the bottom (status colours: green up to date, amber needs update, grey not
  started, red error; a running job shows progress and ✕ Cancel in its chip; no status bar, no step
  tree - the GUI must not look like an ANSYS clone). Dockable panels: Inputs, Properties, Messages,
  Validity checks. Undo/redo of input changes. Architecture: `docs/developer_guide.md`.
- **Out-of-date status by fingerprints:** a mesh or run stores a SHA-256 of the inputs it depends on
  (+ input-file contents, template code, version); a changed upstream input marks everything
  downstream "needs update", and old results are always labelled out of date, never shown as current.
- **Geometry workspace** (Geometry step of 2D templates, `aeroflowsim/geometry_model/`): the geometry is a
  history of operations (template shape, import, sketch, transform, fillet, boolean, enclosure, boundary
  names, refinement regions, edit tools: split, trim, extend, offset, chamfer, pattern, fill, merge)
  replayed in OpenCASCADE (Gmsh `occ`, only in `kernel.py`); edge ids are
  stable across edits (lineage); saved as `geometry/history.json`; every edit is one undoable command.
  Unedited template geometry keeps the template's own mesher (`workspace_mesh.mesh_for`); edited geometry
  is meshed by `workspace_mesh.py` with boundary names as patches. A template joins with
  `workspace_settings(params, built)` (+ `size_inputs` for the suggested sizes). Page logic without Qt
  in `gui/geometry_logic.py`. Units in the workspace GUI: mm. Sketches are drawn with the mouse
  (`gui/sketch_tools.py`, one state machine per tool, no Qt) with inference snapping
  (`geometry_model/inference.py`) and may carry constraints and driving dimensions solved by
  least squares (`geometry_model/constraints.py`). The view (`gui/geometry_view.py`) has its own icons
  (`gui/icons.py`), an adaptive grid, an axes triad, box selection, right-click menus and a 3D
  revolve preview.
- The input panel is generated from `schema.toml`: the logic (`gui/panel_model.py`, no Qt) is separate
  from the drawing (`gui/panel.py`) — zero GUI code per template or shape.
- Solver code must **not depend on the GUI**: only `aeroflowsim/gui/` (and the old `app.py`) may import
  PySide6, PyVista, VTK or streamlit (tested); the command line works without Qt.
- **Long work never freezes the GUI:** meshing and solving run in a warm helper process
  (`aeroflowsim/tasks.py`, Qt side `gui/jobs.py`) with progress, Stop (clean, between iterations)
  and Cancel (terminates the helper, e.g. inside Gmsh).
- **One engine:** `aeroflowsim.run_case(case_folder, params)` is used by the GUI (via the helper
  process), the command line (templates and projects) and scripts, so all give identical results.
- The old **Streamlit** GUI (`app.py`, `gui/streamlit_panel.py`, `job.py`, `plots.py`, `settings.py`) stays
  until the user confirms the desktop GUI has full parity; then ask before deleting it.
- **Validity checks** (`aeroflowsim/checks.py`): one function per check, results shown in the
  Results tab, printed by the command line, stored in `summary.yaml`. Mesh checks run before the
  solver; an error-level mesh check (e.g. negative cell volume) stops the run.
- **One mesh format:** every 2D/3D generator produces the face-based `Mesh` of `aeroflowsim/mesh.py`
  (VTK cell types, OpenFOAM-style owner/neighbour faces) and every 2D/3D solver consumes it.
- A case may be **mesh-only** (`solver = false` + `solver_message` in `schema.toml`; no `run()`).
- **Gas library** (`aeroflowsim/gases/`): solvers get every gas property through the `GasModel`
  interface (R, cp, cv, gamma, sound speed, e(T) and T(e), mu, k, Pr, valid ranges; numbers or arrays)
  and never hard-code gamma or R. Now: `CaloricallyPerfectGas` (Sutherland / power laws); later models
  (NASA polynomials, mixtures, Peng-Robinson real gas) are new subclasses. One TOML per built-in gas, every
  value with its source, written by `tools/gas_data/make_gas_files.py` from NIST data. A case input of
  type `gas` holds a built-in id ("N2") or a custom gas file; custom gases live in the user's library
  (`%APPDATA%/AeroFlowSim/gases`) and are copied into `<project>/gases/`. A case with `gas(params)` gets
  the gas checks (ideal gas via Peng-Robinson Z, condensation, temperature range).

Layout:

```
app.py                     old Streamlit GUI (kept until the desktop GUI is approved)
aeroflowsim/               the Python package
    case.py                case contract + Case object (schema.toml + case.py)
    schema.py              reads schema.toml (tomllib)
    parameters.py          input types (float/int/bool/choice/file) and value checks
    engine.py              run_case(): the one run engine
    cli.py, __main__.py    python -m aeroflowsim run cases/<case_name> | run <project>.afsproj | list | gui
    project.py             projects: create/open/save/duplicate, fingerprints and step status
    result_io.py           exact save/load of a run (results/run.npz, no pickle)
    tasks.py               background Worker: warm helper process for mesh and run jobs (Stop, Cancel)
    geometry_preview.py    template geometry as named boundary curves (1D templates' Geometry step)
    geometry_model/        geometry workspace (no Qt): document.py (history, replay), operations.py,
                           kernel.py (OCC, stable edge ids), built.py, importers.py, healing.py,
                           boundaries.py, picking.py, snapping.py, export.py, edit_operations.py
                           (split/trim/extend/offset/chamfer/pattern/fill/merge), inference.py
                           (snapping while drawing), constraints.py (sketch constraint solver)
    workspace_mesh.py      mesh_for(): template mesher, or Gmsh mesh of an edited workspace geometry
    smart_rules.py         suggestions with reasons (sizes, enclosure); applied only by the user
    checks.py              validity checks (convergence, mass balance, ...)
    job.py                 old thread-based run for the Streamlit GUI
    runner.py              output files: CSV, YAML summary, PNG plots
    geometry.py            shared wall profiles (parametric, CSV) for nozzle/duct cases
    mesh.py                Mesh1D (1D cases) and the face-based Mesh (2D/axisymmetric/3D): nodes, cells,
                           faces with owner/neighbour, patches, geometry, save/load (.npz)
    mesh_quality.py        aspect ratio, non-orthogonality, volume ratio, cell size (per cell)
    nozzle_mesh.py         structured axisymmetric nozzle mesh (throat clustering, inflation layers)
    gmsh_mesh.py           optional Gmsh meshes (triangles / quad-dominant): external domain, nozzle
    inflation_layers.py    inflation layers grown from a wall for unstructured meshes
    shapes/                shape library: profile.py (ShapeProfile), registry, one .py + .toml per shape
    gases/                 gas library: model.py (GasModel, CaloricallyPerfectGas), data.py (TOML format,
                           saturation curves), library.py (built-in / user / project gases), real_gas.py
                           (Peng-Robinson Z), one <id>.toml per built-in gas
    vtk.py                 ParaView .vtu writer (any cell data); save_mesh_files()
    euler1d.py, quasi1d.py, gasdynamics.py, riemann_exact.py, results.py, plots.py, visualise.py
    gui/                   desktop GUI (the ONLY place with Qt / PyVista / VTK / streamlit):
        app.py, main_window.py   start-up, main window (menus, docks, jobs, undo)
        panel_model.py, panel.py input panel: logic (no Qt) + Qt drawing
        workflow_strip.py        step chips with status and progress
        steps/                   one page per step (geometry = the workspace, mesh, setup, run, results) + welcome
        geometry_logic.py, geometry_view.py, geometry_forms.py   workspace: logic (no Qt), view, dialogs
        sketch_tools.py, icons.py   mouse drawing tools (no Qt), the app's own icon set
        gas_logic.py, gas_dialog.py  gas dropdown / Details / custom-gas form: logic (no Qt) + dialogs
        vtk_view.py, figures.py  VTK view (meshes, picking), embedded matplotlib plots
        jobs.py, undo.py, logic.py, theme.py, widgets.py, dialogs.py, app_info.py
        streamlit_panel.py       old Streamlit input panel
cases/<case_name>/         one folder per case
    schema.toml            inputs (key, label, unit, type, default, min, max, group, step, help, show_if)
    case.py                build_mesh(), run() (+ optional reference, geometry, reference_lines)
    README.md              physics and assumptions
    test_case.py           pytest validation test
    mesh/                  generated mesh.npz + mesh.vtu (git-ignored)
cases/_template/           copy-me skeleton for a new case (ignored by discovery and pytest)
cases/external_2d/         body in a free stream (shape library + Gmsh), mesh only until Prompt 7
cases/geometry_2d/         custom 2D geometry from the workspace (import / sketch), mesh only until Prompt 7
docs/theory_manual.md      equations and methods, with references and where they are in the code
docs/developer_guide.md    how the desktop GUI is built (Qt, signals/slots, VTK view, jobs, projects)
docs/gap_register.md       living checklist of everything still missing (read at the start of every prompt)
docs/tutorials/            step-by-step tutorials (nozzle with plume region, airfoil in a C-domain)
spikes/                    throwaway proofs of concept (not part of the package)
tools/gas_data/            developer tool that writes aeroflowsim/gases/*.toml from NIST data (not packaged)
validation/<case_name>/    reference.toml (values, sources, tolerances) + validate.py
validation/run_all.py      runs all validation cases, writes validation/report.md
tests/                     tests for aeroflowsim/ (tests/gui/: pytest-qt tests of the desktop GUI)
run_case.py                old command line, thin wrapper around aeroflowsim.cli
results/<case_name>/       output of the command line (not committed)
pyproject.toml             package metadata, dependencies, pytest settings (marker "validation")
requirements.txt           exact versions used in .venv
.github/workflows/tests.yml  GitHub Actions: fast + validation tests on Windows and Ubuntu
```

Commands (from the project folder):
- Fast tests: `.venv\Scripts\python.exe -m pytest`
- Validation tests: `.venv\Scripts\python.exe -m pytest -m validation`
- Validation report: `.venv\Scripts\python.exe validation/run_all.py`
- Desktop GUI: `.venv\Scripts\python.exe -m aeroflowsim gui` (optionally followed by a project folder)
- Old Streamlit GUI: `.venv\Scripts\python.exe -m streamlit run app.py`
- Command line: `.venv\Scripts\python.exe -m aeroflowsim run cases/<case_name>`, or
  `... run "<path>/<name>.afsproj"` for a project (its inputs; mesh and results stored in it)

## Geometry input (all nozzle and duct cases)
- **Level 1:** built-in parametric geometry (diameters, angles, lengths typed in the Setup tab).
- **Level 2:** custom wall profile from a user-uploaded CSV.
  - Format: two columns, header `x_mm,r_mm` (axial position and wall radius, in millimetres).
  - Converted to SI metres inside the code.
- One shared module, `aeroflowsim/geometry.py`, reads, checks and interpolates profiles, so every case uses the same code.
- **Later:** Level 3 = 2D CAD import (DXF/IGES/STEP) meshed with Gmsh.
- Design so Level 3 can be added later **without rewriting the cases**: every geometry source
  (parametric, CSV, future CAD) produces the same wall-profile object (x [m], r [m]);
  cases only consume that object and never care where it came from.

## Rules
1. **SI units everywhere.** Write units in variable comments (e.g. `p0 = 101325.0  # Pa`).
2. **Solver code is face-based finite volume** and must not use 2D-only shortcuts: the same code
   must later run in 2D, axisymmetric and 3D.
3. Every new case gets a **`schema.toml`**, **tests** (pytest validation against theory or an exact
   solution) and a **validation case** in `validation/` where possible. A case is not finished until
   its tests pass.
4. **Never change validated results without saying so.** If a change alters any number in
   `validation/report.md` or a case's validated output, tell the user explicitly and why.
5. Work in **small steps**. Plan first, then code. **Explain plans simply** (the user is a beginner)
   and explain what was done in plain words after each step.
6. **Never edit another case's folder** when working on one case.
7. Keep code **simple and well commented**; prefer clarity over speed.
8. After each working step, make a **git commit** with a clear message.
9. Use a Python virtual environment in **`.venv`**; the project is installed into it with
   `pip install -e .`. Dependencies (pyproject.toml): numpy, scipy, matplotlib, plotly, streamlit,
   pyyaml, pytest, PySide6-Essentials, vtk, pyvista, pyvistaqt, pytest-qt, gmsh (meshes and the
   workspace's OpenCASCADE kernel; required since 6d), ezdxf (DXF files) - exact versions in
   requirements.txt. The old `pip install -e ".[mesh]"` still works (empty group).
10. Every `.py` file starts with the AeroFlowSim licence header (GPL-3.0-or-later).
11. Ask before deleting files or making changes that were not requested.
12. **Privacy:** the desktop GUI makes no network connections, contains no web addresses, opens only
    local files and collects no usage statistics (`tests/test_gui_privacy.py`); the old Streamlit GUI
    listens on localhost only without statistics (`.streamlit/config.toml`, tested). Never change
    this without asking. User data (results/,
    uploads/, cases/*/settings/, cases/*/mesh/) is git-ignored and must never be committed.
13. **Verification and validation:** every new numerical method gets a Method of Manufactured
    Solutions (MMS) order-of-accuracy test where possible, plus validation against theory or
    experiment.
14. **Speed:** steady cases must use local time stepping (and later implicit methods). Report
    iterations and wall-clock time in the Results tab and in validation reports.
15. **The user must understand the code:** at the end of every prompt, give a plain-language
    walkthrough of the most important new module (what it does, the key equations, where they are in
    the code), and add or update the matching section in `docs/theory_manual.md` with the equations
    and references.
16. **Best practice by default:** when there is a choice between a quick approach and the approach
    serious CFD codes use, choose the serious one, explain why in simple words, and only ask the user
    when the choice really changes what the software can do.
17. **Adding a shape** (shape library): two files in `aeroflowsim/shapes/` - `<name>.toml` (name,
    group, symmetry, inputs) and `<name>.py` (`profile(inputs) -> ShapeProfile`: closed,
    counter-clockwise, corners marked, reference length and area) - plus tests. No GUI or case code.
18. **Gap register:** read `docs/gap_register.md` at the start of every prompt. At the end, update it
    (status of the items that moved, new gaps found) and report both to the user.

## Intelligence
- **Principle:** intelligence assists, never replaces physics. Every suggestion is shown to the
  user, is editable, and is verified by the validity checks. The core software must work fully
  offline without any AI.
- **Smart rules:** setup suggestions (mesh size, inflation first-layer height from Re and target y+,
  suggested enclosure, CFL) from **Prompt 6d**; failure diagnosis with suggested fixes and result sanity
  checks against theory from **Prompt 7**. Each rule is one small function, like a check.
- **Adaptive mesh refinement:** **Prompt 8c**.
- **Optional AI assistant plugin:** **Prompt 7c** (natural-language setup and result explanation). It
  works only through the schema inputs (fills them, never runs its own code), so every new feature
  becomes available to it automatically; opt-in, with a local-model option for confidential designs.
- **Surrogate models and shape optimisation** (nozzle contour for maximum thrust/Isp, nose cone for
  minimum drag): **Phase 5** headline feature.

## Roadmap
- **Phase 1 - platform and 2D supersonic:**
  - 6c desktop GUI (Qt + PyVista), Workbench-style steps and status, projects, undo/redo, gap register (done).
  - 6d geometry workspace (clickable): import CSV/DAT, DXF and 2D STEP/IGES; shape templates; edit
    (move, rotate, scale, mirror, point table, drag points); sketch (line, arc, spline); enclosure tool
    (box, circle, C-shape around the body; inlet plenum and plume region for nozzles); booleans (Gmsh
    OpenCASCADE); name boundaries by clicking; refinement regions; smart rule: suggested enclosure and
    mesh sizes (done).
  - 6e remaining shapes (bell nozzle, ramp and spike intakes, biconvex, NACA 5-digit, ogive, von Karman,
    power-law, sphere, hemisphere-cylinder, sphere-cone); structured C-grid / O-grid meshes via Gmsh
    (transfinite); mesh import (Gmsh .msh, SU2, CGNS, Fluent .msh).
  - 6f materials: gas library + custom gas (designed for mixtures, real gas and liquids later); units
    system (SI, mm, imperial in the GUI; SI inside).
  - 7 2D Euler solver (2D + axisymmetric) with local time stepping; full boundary-condition set
    (total-pressure inlet, mass-flow inlet, pressure outlet, supersonic inlet/outlet, far-field, slip wall,
    symmetry, axis) taken from the named boundaries; initialisation options; live monitors (residuals,
    forces, mass flow); restart from a saved solution; carbuncle fix; thrust/Isp/Cf, Cp/Cl/Cd/Cm; smart
    rules for failure diagnosis.
  - 7b post-processing (contours, streamlines, line probes, surface plots such as Cp vs x, image/CSV/VTK
    export); validation suite + MMS verification; automatic report (HTML/PDF); first tutorials; Windows
    installer; then the 2D alpha release.
  - 7c AI assistant plugin v1 (opt-in; fills schema inputs only; local-model option).
- **Phase 2 - speed and all speeds:** 8 Numba + implicit time stepping (LU-SGS) + multi-core parallel;
  8b low-Mach preconditioning; 8c adaptive mesh refinement; 8d parametric studies and batch runs (lift
  polars, thrust vs back pressure); 8e unsteady flow (dual time stepping).
- **Phase 3 - 3D:** 9 3D geometry workspace (STEP) + 3D Gmsh meshes (tetrahedra, prism inflation);
  10 3D Euler; multiple zones.
- **Phase 4 - viscous and liquids:** laminar Navier-Stokes (with slip-wall option for rarefied
  micro-nozzles), Spalart-Allmaras, k-omega SST, wall heat flux; constant-density liquids
  (preconditioned) + classic cases (lid-driven cavity vs Ghia, backward-facing step, cylinder at
  Re = 100); cross-code comparison with SU2/OpenFOAM.
- **Phase 5 - advanced propulsion and version 1.0:** real-gas model (Peng-Robinson; for example
  R-236fa), multi-species and combustion (scramjet), high-temperature gas, surrogate models + shape
  optimisation (headline feature), GPU, GCI mesh-independence tool, full docs and tutorials, Zenodo
  DOI, JOSS paper. Later list: two-phase/condensation, cavitation, conjugate heat transfer, optional
  web demo.
- **Out of scope:** rotating machinery, free-surface flows, structures.

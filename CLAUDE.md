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
- Each simulation is a **case** in its own folder under `cases/`. The app runs **one case at a time**.
- Every case has the same two files: `schema.toml` (name, description, steady flag and inputs —
  no code) and `case.py` (physics, contract in `aeroflowsim/case.py`). New cases are found
  automatically and never require changes to old ones.
- GUI: **Streamlit** web app in `app.py` with tabs **Setup, Mesh, Run, Results**. The Setup input
  panel is generated from `schema.toml` by `aeroflowsim/gui/panel.py` — zero GUI code per case.
- Solver code must **not depend on the GUI**: only `app.py` and `aeroflowsim/gui/` may import
  streamlit (tested), so the GUI can later be swapped (e.g. Qt) without touching solvers.
- **One engine:** `aeroflowsim.run_case(case_folder, params)` is used by the GUI (via
  `aeroflowsim/job.py`), the command line and scripts, so all give identical results.
- **Validity checks** (`aeroflowsim/checks.py`): one function per check, results shown in the
  Results tab, printed by the command line, stored in `summary.yaml`. Mesh checks run before the
  solver; an error-level mesh check (e.g. negative cell volume) stops the run.
- **One mesh format:** every 2D/3D generator produces the face-based `Mesh` of `aeroflowsim/mesh.py`
  (VTK cell types, OpenFOAM-style owner/neighbour faces) and every 2D/3D solver consumes it.
- A case may be **mesh-only** (`solver = false` + `solver_message` in `schema.toml`; no `run()`).

Layout:

```
app.py                     Streamlit GUI (Setup / Mesh / Run / Results)
aeroflowsim/               the Python package
    case.py                case contract + Case object (schema.toml + case.py)
    schema.py              reads schema.toml (tomllib)
    parameters.py          input types (float/int/bool/choice/file) and value checks
    engine.py              run_case(): the one run engine
    cli.py, __main__.py    python -m aeroflowsim run cases/<case_name>  |  list
    checks.py              validity checks (convergence, mass balance, ...)
    job.py                 background run for the GUI (live progress, Stop)
    runner.py              output files: CSV, YAML summary, PNG plots
    geometry.py            shared wall profiles (parametric, CSV) for nozzle/duct cases
    mesh.py                Mesh1D (1D cases) and the face-based Mesh (2D/axisymmetric/3D): nodes, cells,
                           faces with owner/neighbour, patches, geometry, save/load (.npz)
    mesh_quality.py        aspect ratio, non-orthogonality, volume ratio, cell size (per cell)
    nozzle_mesh.py         structured axisymmetric nozzle mesh (throat clustering, inflation layers)
    vtk.py                 ParaView .vtu writer (any cell data); save_mesh_files()
    euler1d.py, quasi1d.py, gasdynamics.py, riemann_exact.py, results.py, plots.py, visualise.py
    gui/panel.py           auto-generated input panel (the GUI layer; only place with streamlit)
cases/<case_name>/         one folder per case
    schema.toml            inputs (key, label, unit, type, default, min, max, group, help, show_if)
    case.py                build_mesh(), run() (+ optional reference, geometry, reference_lines)
    README.md              physics and assumptions
    test_case.py           pytest validation test
    mesh/                  generated mesh.npz + mesh.vtu (git-ignored)
cases/_template/           copy-me skeleton for a new case (ignored by discovery and pytest)
validation/<case_name>/    reference.toml (values, sources, tolerances) + validate.py
validation/run_all.py      runs all validation cases, writes validation/report.md
tests/                     tests for aeroflowsim/
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
- GUI: `.venv\Scripts\python.exe -m streamlit run app.py`
- Command line: `.venv\Scripts\python.exe -m aeroflowsim run cases/<case_name>`

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
   pyyaml, pytest. Optional group `mesh` (Gmsh, from Prompt 6b).
10. Every `.py` file starts with the AeroFlowSim licence header (GPL-3.0-or-later).
11. Ask before deleting files or making changes that were not requested.
12. **Privacy:** the GUI listens on localhost only and sends no usage statistics
    (`.streamlit/config.toml`, tested). Never change this without asking. User data (results/,
    uploads/, cases/*/settings/, cases/*/mesh/) is git-ignored and must never be committed.

## Intelligence
- **Principle:** intelligence assists, never replaces physics. Every suggestion is shown to the
  user, is editable, and is verified by the validity checks. The core software must work fully
  offline without any AI.
- **Smart rules (from Prompt 7 onwards):** auto-setup (mesh size, inflation first layer height
  from Re and target y+, CFL), failure diagnosis with suggested fixes, and result sanity checks
  against theory. Each rule is one small function, like a check.
- **Adaptive mesh refinement:** after Prompt 8 (Numba).
- **Shape optimisation** (nozzle contour for maximum thrust/Isp, nose cone for minimum drag):
  Phase 5 headline feature.
- **Optional AI assistant** (natural-language setup and result explanation): Phase 5 plugin. It
  fills schema inputs only, never runs its own code, is opt-in, and has a local-model option for
  confidential designs.

## Roadmap
- **Phase 1 - 2D foundations and supersonic:**
  - 5.5 foundations (done);
  - 6 face-based mesh format + structured nozzle mesh with inflation controls + VTK export (done);
  - 6b Gmsh 2D mesh (optional install) + shape library (nozzles: conical, bell, CSV; intakes: ramp,
    spike; supersonic airfoils: wedge, diamond, biconvex; subsonic airfoils: NACA 4/5-digit,
    coordinate file; nose cones: conical, tangent ogive, von Karman, power-law; blunt bodies:
    cylinder, sphere, hemisphere-cylinder, sphere-cone);
  - 6c gas library + custom gas (designed so mixtures can be added later);
  - 7 Euler solver 2D + axisymmetric with carbuncle fix, far-field BC, thrust/Isp/Cf, Cp/Cl/Cd/Cm;
  - 7b validation (wedge, diamond airfoil, cone Taylor-Maccoll, cylinder bow shock stand-off,
    Back-Massier-Gier nozzle, NACA 0012 transonic).
- **Phase 2 - speed and all speeds:** 8 Numba; 8b low-Mach preconditioning.
- **Phase 3 - 3D:** 9 3D Gmsh mesh + STEP import; 10 3D Euler + ParaView export.
- **Phase 4 - viscous:** laminar NS, Spalart-Allmaras, k-omega SST (2D and 3D); wall heat flux.
- **Phase 5 - advanced and release:** high-temperature gas, GPU speed-up, GCI mesh-independence
  tool, docs and theory manual, GitHub release, Zenodo DOI, JOSS paper.

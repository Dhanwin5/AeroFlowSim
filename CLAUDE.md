# Flow Sim — project rules

A small **educational CFD software in Python**. Clarity matters more than speed.
The user is new to programming but knows aerospace engineering and CFD theory:
explain code and tools in plain words; CFD concepts need no simplification.

## Architecture
- Each simulation is a **case** in its own folder under `cases/`. The app runs **one case at a time**.
- Every case follows the **same template** (`case.py`), so new cases can be added without changing old ones.
- GUI: **Streamlit** web app in `app.py` with tabs **Setup, Mesh, Run, Results**.
- Solver code must **not depend on the GUI** (never import streamlit in solver/case code).
  Every case must also **run from the command line**.

Target layout:

```
app.py                   Streamlit GUI (Setup / Mesh / Run / Results)
run_case.py              command line: python run_case.py <case_name>  (or --list)
core/                    shared code: case contract, parameters, mesh, results, discovery, runner
core/geometry.py         shared geometry code used by all nozzle/duct cases (to be added)
cases/<case_name>/       one folder per case
    case.py              follows the contract in core/case_template.py
    README.md            physics and assumptions
    test_case.py         pytest validation test
cases/_template/         copy-me skeleton for a new case (ignored by discovery and pytest)
tests/                   tests for core/
results/<case_name>/     output of run_case.py (not committed)
requirements.txt
.venv/                   Python virtual environment (not committed)
```

Run tests with `.venv\Scripts\python.exe -m pytest` (settings in `pytest.ini`).

## Geometry input (all nozzle and duct cases)
- **Level 1:** built-in parametric geometry (diameters, angles, lengths typed in the Setup tab).
- **Level 2:** custom wall profile from a user-uploaded CSV.
  - Format: two columns, header `x_mm,r_mm` (axial position and wall radius, in millimetres).
  - Converted to SI metres inside the code.
- One shared module, `core/geometry.py`, reads, checks and interpolates profiles, so every case uses the same code.
- **Later (not now):** Level 3 = 2D CAD import (DXF/IGES/STEP) meshed with Gmsh.
- Design so Level 3 can be added later **without rewriting the cases**: every geometry source
  (parametric, CSV, future CAD) produces the same wall-profile object (x [m], r [m]);
  cases only consume that object and never care where it came from.

## Rules
1. **SI units everywhere.** Write units in variable comments (e.g. `p0 = 101325.0  # Pa`).
2. Every case needs a **validation test (pytest)** against theory or an exact solution.
   A case is not finished until its test passes.
3. Work in **small steps**. Plan first, then code. Explain what was done in plain words after each step.
4. **Never edit another case's folder** when working on one case.
5. Keep code **simple and well commented**; prefer clarity over speed.
6. After each working step, make a **git commit** with a clear message.
7. Use a Python virtual environment in **`.venv`**.
   Dependencies: numpy, scipy, matplotlib, plotly, streamlit, pyyaml, pytest.

## Not yet
- Level 3 CAD import / Gmsh meshing.

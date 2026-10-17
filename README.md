<p align="center"><img src="assets/logo.png" alt="AeroFlowSim" width="520"></p>

# AeroFlowSim

## Mission

AeroFlowSim is a free, open-source CFD software for nozzle aerodynamics and propulsion, with a built-in GUI. Anyone - students, CubeSat teams, researchers, engineers - can set up, mesh, solve and analyse their own cases in one install, and trust the results, because the software checks its own validity and is validated against published benchmarks. Others can extend it, and publish work done with it.

> **Release claim:** "A GUI-first, open-source CFD solver for nozzle and propulsion aerodynamics, with built-in validity checks and published validation."

## Status

**Pre-release, under development** (version 0.1.0.dev0). Inputs, file formats and results may
still change between versions. Not yet published on PyPI.

## What works now

| Case | Physics | Validated against |
|---|---|---|
| `demo_heat1d` | Steady 1D heat conduction with heat generation (demo of the case template) | Exact parabolic solution |
| `sod_shock_tube` | Unsteady 1D Euler equations, HLLC + MUSCL finite volumes | Exact Riemann solution (Toro, test 1) |
| `quasi1d_nozzle` | Steady quasi-1D Euler flow of N2 through a conical or CSV-profile nozzle | Isentropic area-Mach and normal-shock theory |

- **GUI** (Streamlit, in the web browser) with Setup, Mesh, Run and Results tabs. The input panel
  of each case is generated automatically from the case's `schema.toml`.
- **Validity checks** after every run (convergence, mass balance), shown in the Results tab.
- **Validation suite** with a pass/fail report: [validation/report.md](validation/report.md).
- **Command line and Python scripting** using the same engine as the GUI, so results are identical.
- Nozzle geometry: built-in parametric conical nozzle, or your own wall profile from a CSV file
  (`x_mm,r_mm`).

## Install

You need Python 3.13 and Git. In a terminal (PowerShell on Windows), from the project folder:

```bash
python -m venv .venv
```

Activate the virtual environment (Windows; on Linux/macOS use `source .venv/bin/activate`):

```bash
.venv\Scripts\activate
```

Install AeroFlowSim and its dependencies (`-e` = "editable": your edits take effect at once):

```bash
python -m pip install -e .
```

`requirements.txt` lists the exact versions used during development
(`python -m pip install -r requirements.txt`).

## Start the GUI

```bash
python -m streamlit run app.py
```

Your browser opens the app at `http://localhost:8501`. For privacy, `.streamlit/config.toml` makes
the GUI reachable **only from your own computer** (nobody else on your network can open it or run
cases on it) and turns off Streamlit's usage statistics. Choose a case in the sidebar, set the inputs in **Setup**, build the
mesh in **Mesh**, press **Run**, and look at the plots, key numbers and **Validity checks** in **Results**.

## Command line and scripts

```bash
python -m aeroflowsim list
```

```bash
python -m aeroflowsim run cases/quasi1d_nozzle
```

```bash
python -m aeroflowsim run cases/quasi1d_nozzle --set p_back=250000 --set n_cells=400
```

Results (CSV, YAML summary, PNG plots) are written to `results/<case_name>/`.
From a Python script:

```python
import aeroflowsim

out = aeroflowsim.run_case("cases/quasi1d_nozzle", {"p_back": 2.5e5, "max_iter": 30000})
print(out.result.key_numbers["x_shock"])          # (value, unit)
for check in out.checks:
    print(check.level, check.message)
```

## Tests and validation

Fast tests (a few minutes):

```bash
python -m pytest
```

Validation tests (slow: complete cases compared with published reference values):

```bash
python -m pytest -m validation
```

Run all validation cases and write `validation/report.md` (pass/fail table):

```bash
python validation/run_all.py
```

Tests run automatically on GitHub (Windows and Ubuntu) for every push and pull request
(`.github/workflows/tests.yml`).

## Roadmap

- **Phase 1 - 2D foundations and supersonic:** project foundations (done: 0.1); face-based mesh
  format and structured nozzle meshes with VTK export; Gmsh 2D meshing and a shape library
  (nozzles, intakes, airfoils, nose cones, blunt bodies); gas library; 2D and axisymmetric Euler
  solver with thrust/Isp/Cf and Cp/Cl/Cd/Cm; validation (wedge, diamond airfoil, cone, cylinder bow
  shock, Back-Massier-Gier nozzle, NACA 0012).
- **Phase 2 - speed and all speeds:** Numba acceleration; low-Mach preconditioning.
- **Phase 3 - 3D:** 3D Gmsh meshes and STEP import; 3D Euler solver with ParaView export.
- **Phase 4 - viscous:** laminar Navier-Stokes, Spalart-Allmaras, k-omega SST; wall heat flux.
- **Phase 5 - advanced and release:** high-temperature gas, GPU speed-up, GCI mesh-independence
  tool, documentation and theory manual, GitHub release, Zenodo DOI, JOSS paper.

## Contributing

New cases, shapes and gases are welcome - see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

AeroFlowSim is free software: you can redistribute it and/or modify it under the terms of the
GNU General Public License as published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version (`GPL-3.0-or-later`). See [LICENSE](LICENSE).
It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY.

## How to cite

If you use AeroFlowSim in your work, please cite it (details in [CITATION.cff](CITATION.cff);
GitHub shows a "Cite this repository" button for it). A DOI will follow with the first release.

> Mehta, D. (2026). *AeroFlowSim* (version 0.1.0.dev0) [Computer software].

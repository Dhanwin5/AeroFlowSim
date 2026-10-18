# Contributing to AeroFlowSim

Thank you for helping! AeroFlowSim aims to be CFD that people can **trust**, so every contribution
comes with tests, and every physics case with a validation against theory or published data.

## Set up and run everything locally

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
python -m pip install -e .
```

| What | Command |
|---|---|
| GUI | `python -m streamlit run app.py` |
| List cases | `python -m aeroflowsim list` |
| Run a case | `python -m aeroflowsim run cases/<case_name>` |
| Fast tests | `python -m pytest` |
| Validation tests | `python -m pytest -m validation` |
| Validation report | `python validation/run_all.py` (writes `validation/report.md`) |

## Rules for every contribution

1. **Tests:** new code comes with pytest tests. All fast tests **and** all validation tests must
   pass (`python -m pytest` and `python -m pytest -m validation`). GitHub runs both on Windows and
   Ubuntu for every pull request.
2. **Never change validated results silently.** If a change alters any number in
   `validation/report.md`, say so in the pull request and explain why.
3. **Solver code is face-based finite volume** and must not use 2D-only shortcuts: the same code
   must later run in 2D, axisymmetric and 3D.
4. **No GUI code in solvers.** Only `app.py` and `aeroflowsim/gui/` may import streamlit (a test
   checks this). Every case must run from the command line.
5. **SI units everywhere**, written in comments next to variables, e.g. `p0 = 101325.0  # Pa`.
6. **Licence header** at the top of every `.py` file (a test checks this):

   ```python
   # AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
   # Copyright (C) 2026 Dhanwin Mehta
   # SPDX-License-Identifier: GPL-3.0-or-later
   ```

   By contributing you agree that your contribution is licensed under GPL-3.0-or-later.

## Code style

- Clarity over speed: simple, well-commented code that a student can follow.
- Descriptive names; a docstring for every module and function; physics and assumptions in the
  case's `README.md`.
- Small, focused commits with clear messages.

## How to add a case

A case is a folder `cases/<case_name>/`. It is found automatically - no other file needs changing,
and the GUI panel is generated for you.

1. Copy `cases/_template/` to `cases/<case_name>/` (folders starting with `_` are ignored).
2. **`schema.toml`** - describe the case and its inputs (no code). The GUI builds the input panel
   from it, the command line takes the defaults from it:

   ```toml
   [case]
   name = "Quasi-1D nozzle"
   description = "Steady quasi-1D Euler flow ..."
   steady = true                  # true: marched to steady state; false: time-accurate

   [[input]]
   key = "d_throat"               # params["d_throat"] in case.py
   label = "Throat diameter"
   unit = "m"
   type = "float"                 # float, int, bool, choice (with options = [...]) or file
   default = 0.280e-3
   min = 1e-6
   max = 1.0
   group = "Geometry"             # heading in the GUI
   help = "Smallest diameter (sharp-cornered throat)."
   # show_if = { geometry_source = "Parametric (conical)" }   # optional
   ```

3. **`case.py`** - the physics: `build_mesh(params)` and `run(params, mesh, progress)`, plus optional
   `reference`, `geometry` and `reference_lines`. The full contract is in `aeroflowsim/case.py`.
   Return mass flows as key numbers `mdot_inlet` / `mdot_exit` [kg/s] to get the mass-balance check.
4. **`test_case.py`** - a pytest validation against theory or an exact solution.
5. **`README.md`** - equations, assumptions, numerics, what is validated and with which tolerance.
6. **Validation case** (where possible): `validation/<case_name>/reference.toml` with the published
   or exact reference values, each with its **source** and **tolerance**, and `validate.py` with a
   function `measure()` that runs the case with `aeroflowsim.run_case(...)` and returns the measured
   values. `python validation/run_all.py` picks it up automatically. See `validation/common.py`.

## How to add a shape

Shapes live in the shape library `aeroflowsim/shapes/`. A shape is **two files with the same name**
in that folder; the registry finds them automatically, so the Shape dropdown of every case that uses
the library (e.g. `cases/external_2d`) lists the new shape with its own input boxes. No GUI code
and no change to any case.

1. **`<name>.toml`** - what the shape is and its inputs (same `[[input]]` format as a case's
   `schema.toml`):

   ```toml
   [shape]
   name = "Wedge"                    # shown in the Shape dropdown
   group = "Supersonic airfoils"     # see GROUPS in aeroflowsim/shapes/__init__.py
   symmetry = "planar"               # planar, axisymmetric or either
   description = "Planar wedge with a sharp tip and a flat base."

   [[input]]
   key = "half_angle"                # inputs["half_angle"] in <name>.py
   label = "Wedge half-angle"
   unit = "deg"
   type = "float"
   default = 10.0
   min = 1.0
   max = 45.0
   help = "Angle between each wedge surface and the x axis."
   ```

2. **`<name>.py`** - one function `profile(inputs) -> ShapeProfile` (see
   `aeroflowsim/shapes/profile.py`). Return the **closed outline**: points (x, y) in metres, going
   round the body once **counter-clockwise**, last point not repeated, no crossings, enough points
   on curves. Mark the sharp corners (`corners=[...]`) and the leading/trailing edges
   (`refine=[...]`), and give the **reference length** and **reference area** (planar: length x 1 m;
   axisymmetric: base area pi R², with the full silhouette symmetric about y = 0):

   ```python
   def profile(inputs):
       L = inputs["length"]                                     # [m]
       h = L * math.tan(math.radians(inputs["half_angle"]))     # [m]
       return ShapeProfile([(0, 0), (L, -h), (L, h)], reference_length=L, reference_area=L,
                           corners=[0, 1, 2])
   ```

3. **Tests** in `tests/test_shapes.py`: the shape is checked automatically for being closed,
   counter-clockwise and free of crossings; add a test of its exact geometry (area, thickness,
   angles) and, where possible, a validation value in `validation/external_geometry`.

## How to add a gas (coming in Prompt 6c)

Gases will live in a gas library (`aeroflowsim/gases/`). The intended pattern:

- **one entry per gas** with its properties in SI units and their source (molar mass, R, gamma or
  cp(T), and later viscosity and conductivity);
- a "custom gas" entry built from user inputs;
- designed so that mixtures can be added later without changing the cases;
- tests against tabulated property data.

## Validity checks

A check is one function in `aeroflowsim/checks.py` with the signature
`check(case, params, mesh, result) -> CheckResult | None` (level `info`, `warning` or `error`,
a short message and a value), added to the `CHECKS` list. Planned: mesh quality, Knudsen number,
ideal-gas validity, y+.

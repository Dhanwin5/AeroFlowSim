# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The case "contract": what every cases/<name>/case.py must provide.

A case.py file must define:

    NAME          str   short human-readable name, e.g. "1D heat conduction (demo)"
    DESCRIPTION   str   one or two sentences describing the case

    parameters()                  -> list[Parameter]
        The inputs of the case (see aeroflowsim/parameters.py).

    build_mesh(params)            -> Mesh1D
        params is a dict {name: value}. Returns the mesh (see aeroflowsim/mesh.py).

    run(params, mesh, progress)   -> Result
        Solves the problem. While iterating it calls progress(iteration, residual)
        so the GUI or the command line can show how the solution is converging.
        Returns a Result (see aeroflowsim/results.py).

    reference(params, mesh)       -> dict[str, Field] or None      (optional)
        Theory or exact solution on the same mesh. Keys should match the keys of
        Result.fields so the two can be compared and plotted together.

    geometry(params)              -> WallProfile                    (optional)
        The duct / nozzle wall r(x) for these inputs (see aeroflowsim/geometry.py). The GUI shows it
        as a preview in the Setup tab; raise ValueError with a "what to fix" message if the
        inputs do not give a valid geometry (e.g. a bad CSV file).

    reference_lines(params, mesh) -> list[Line]                     (optional)
        Exact lines to draw on top of the x-t diagram, e.g. wave paths x = x0 + S t
        (see aeroflowsim/results.py). Kept apart from reference() because reference() returns
        fields only (they are compared value by value with the numerical fields).

Optional extras a case may put in its Result (the GUI then offers more "Contours" views):
    Result.snapshots   fields over time, for unsteady cases -> x-t diagram.
                       Collect them with aeroflowsim.results.SnapshotRecorder (at most ~200 kept).
    Result.shape       outline r(x) as a aeroflowsim.geometry.WallProfile -> shape view.
                       Without it the shape view uses a constant height.
    Result.shape_note  text under the shape view title, e.g. "quasi-1D: varies along x only".

A ready-to-copy skeleton lives in cases/_template/.
"""

# Names every case must define, and which of them must be functions.
REQUIRED_TEXT = ["NAME", "DESCRIPTION"]
REQUIRED_FUNCTIONS = ["parameters", "build_mesh", "run"]
OPTIONAL_FUNCTIONS = ["reference", "reference_lines", "geometry"]


def check_case(module) -> list[str]:
    """Return a list of problems with a loaded case module (empty list = valid case)."""
    problems = []
    for name in REQUIRED_TEXT:
        if not isinstance(getattr(module, name, None), str):
            problems.append(f"missing text constant {name}")
    for name in REQUIRED_FUNCTIONS:
        if not callable(getattr(module, name, None)):
            problems.append(f"missing function {name}()")
    for name in OPTIONAL_FUNCTIONS:
        if hasattr(module, name) and not callable(getattr(module, name)):
            problems.append(f"{name} exists but is not a function")
    return problems


def get_reference(module, params, mesh):
    """Call the case's reference() if it has one; otherwise return None."""
    if hasattr(module, "reference"):
        return module.reference(params, mesh)
    return None


def get_geometry(module, params):
    """Call the case's geometry() if it has one; otherwise return None."""
    if hasattr(module, "geometry"):
        return module.geometry(params)
    return None


def get_reference_lines(module, params, mesh):
    """Call the case's reference_lines() if it has one; otherwise return an empty list."""
    if hasattr(module, "reference_lines"):
        return module.reference_lines(params, mesh)
    return []

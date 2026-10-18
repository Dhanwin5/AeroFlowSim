# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The case "contract": what every case folder cases/<name>/ must provide, and the Case object.

A case folder holds two required files:

    schema.toml   name, description, steady flag and all inputs (see aeroflowsim/schema.py).
                  The GUI builds the input panel from it automatically.
    case.py       the physics, as plain functions:

    build_mesh(params)            -> Mesh1D or Mesh
        params is a dict {key: value} with the inputs of schema.toml. Returns the mesh
        (see aeroflowsim/mesh.py: Mesh1D for 1D cases, the face-based Mesh for 2D/3D cases).

    run(params, mesh, progress)   -> Result
        Solves the problem. While iterating it calls progress(iteration, residual)
        so the GUI or the command line can show how the solution is converging.
        Returns a Result (see aeroflowsim/results.py).
        Not needed when schema.toml says solver = false (a mesh-only case, e.g. before its
        solver exists); the GUI then shows solver_message instead of the Run button.

    reference(params, mesh)       -> dict[str, Field] or None      (optional)
        Theory or exact solution on the same mesh. Keys should match the keys of
        Result.fields so the two can be compared and plotted together.

    geometry(params)              -> WallProfile                    (optional)
        The duct / nozzle wall r(x) for these inputs (see aeroflowsim/geometry.py). The GUI shows it
        as a preview in the Setup tab; raise ValueError with a "what to fix" message if the
        inputs do not give a valid geometry (e.g. a bad CSV file).

    derived(params)               -> dict {label: (value, unit)}    (optional)
        Read-only numbers that follow from the inputs (e.g. the total inflation thickness).
        The GUI shows them under the input panel; they cannot be typed in.

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
    Result.key_numbers "mdot_inlet" and "mdot_exit" [kg/s] switch on the mass-balance check.

A ready-to-copy skeleton lives in cases/_template/.
"""

import importlib.util
from pathlib import Path

from aeroflowsim.schema import SCHEMA_FILE, Schema, load_schema

# Functions case.py must define, and optional ones.
REQUIRED_FUNCTIONS = ["build_mesh", "run"]
OPTIONAL_FUNCTIONS = ["reference", "reference_lines", "geometry", "derived"]


def check_module(module, has_solver=True) -> list[str]:
    """Return a list of problems with a loaded case.py module (empty list = valid).

    has_solver=False (schema.toml: solver = false): run() is not required.
    """
    problems = []
    for name in REQUIRED_FUNCTIONS:
        if name == "run" and not has_solver:
            continue
        if not callable(getattr(module, name, None)):
            problems.append(f"missing function {name}()")
    for name in OPTIONAL_FUNCTIONS:
        if hasattr(module, name) and not callable(getattr(module, name)):
            problems.append(f"{name} exists but is not a function")
    return problems


def _load_module(name: str, case_file: Path):
    """Import a case.py file directly from its path and return the module."""
    spec = importlib.util.spec_from_file_location(f"cases.{name}.case", case_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Case:
    """One case: its folder, its schema (from schema.toml) and its physics (from case.py).

    Use it like the case.py module itself: case.build_mesh(params), case.run(params, mesh, progress),
    and the optional case.reference(...), case.geometry(...) exist only if case.py defines them
    (so hasattr(case, "geometry") tells whether the case has a geometry preview).
    """

    def __init__(self, folder, schema: Schema, module):
        self.folder = Path(folder)   # e.g. .../cases/quasi1d_nozzle
        self.schema = schema
        self.module = module

    @classmethod
    def load(cls, folder) -> "Case":
        """Read schema.toml and import case.py of one case folder; ValueError if anything is wrong."""
        folder = Path(folder)
        schema = load_schema(folder / SCHEMA_FILE)
        try:
            module = _load_module(folder.name, folder / "case.py")
        except Exception as error:  # any error inside case.py
            raise ValueError(f"could not import case.py: {error!r}") from None
        problems = check_module(module, has_solver=schema.solver)
        if problems:
            raise ValueError("; ".join(problems))
        return cls(folder, schema, module)

    @property
    def name(self) -> str:
        """Folder name, e.g. "quasi1d_nozzle" (used in file names and on the command line)."""
        return self.folder.name

    @property
    def title(self) -> str:
        """Human-readable name from schema.toml, e.g. "Quasi-1D nozzle"."""
        return self.schema.title

    @property
    def description(self) -> str:
        return self.schema.description

    @property
    def steady(self) -> bool:
        """True if the case marches to a steady state (its residual must drop)."""
        return self.schema.steady

    @property
    def has_solver(self) -> bool:
        """False for a mesh-only case (schema.toml: solver = false)."""
        return self.schema.solver

    @property
    def solver_message(self) -> str:
        """Text shown instead of the Run button when the case has no solver."""
        return self.schema.solver_message

    def parameters(self):
        """The inputs of the case (list of Parameter), in schema.toml order."""
        return list(self.schema.inputs)

    def __getattr__(self, name):
        # Called only for names not found on the Case itself: pass them on to case.py,
        # e.g. case.run -> module.run. Missing optional functions raise AttributeError as usual.
        if name in ("module", "schema", "folder"):
            raise AttributeError(name)   # not set yet (during construction); avoid endless recursion
        return getattr(self.module, name)

    def __repr__(self):
        return f"Case({self.name!r})"


def get_reference(case, params, mesh):
    """Call the case's reference() if it has one; otherwise return None."""
    if hasattr(case, "reference"):
        return case.reference(params, mesh)
    return None


def get_geometry(case, params):
    """Call the case's geometry() if it has one; otherwise return None."""
    if hasattr(case, "geometry"):
        return case.geometry(params)
    return None


def get_derived(case, params):
    """Call the case's derived() if it has one; otherwise return an empty dict."""
    if hasattr(case, "derived"):
        return case.derived(params)
    return {}


def get_reference_lines(case, params, mesh):
    """Call the case's reference_lines() if it has one; otherwise return an empty list."""
    if hasattr(case, "reference_lines"):
        return case.reference_lines(params, mesh)
    return []

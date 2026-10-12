"""TEMPLATE - copy this whole folder to cases/<new_case_name>/ and fill in the parts marked TODO.

Folders starting with "_" are ignored by the app and by pytest, so this file is never run.
See core/case_template.py for the full description of each function.
"""

from core.mesh import Mesh1D
from core.parameters import Parameter
from core.results import Field, Result

NAME = "TODO short name"
DESCRIPTION = "TODO one or two sentences about the physics."


def parameters():
    """Inputs of this case (all SI). Parameter(name, label, unit, default, min, max, help)."""
    return [
        Parameter("L", "Length", "m", 1.0, 0.01, 10.0, "TODO help text"),
    ]


def build_mesh(params):
    """Return the mesh for these parameters."""
    raise NotImplementedError  # TODO return Mesh1D(x=...)


def run(params, mesh, progress):
    """Solve; call progress(iteration, residual) every iteration; return a Result."""
    # Optional Result extras (they unlock more views in the Results tab, "Contours"):
    #   snapshots=SnapshotRecorder(...).snapshots()   unsteady case -> x-t diagram
    #   shape=WallProfile(x=..., r=...)               outline r(x) -> shape view
    raise NotImplementedError  # TODO return Result(fields={...}, residuals=[...], ...)


def reference(params, mesh):
    """Optional: theory or exact solution as {field_name: Field}. Delete if there is none."""
    raise NotImplementedError


def reference_lines(params, mesh):
    """Optional: exact lines for the x-t diagram as a list of core.results.Line. Delete if none."""
    raise NotImplementedError

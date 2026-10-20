# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validity checks: after every run, the software checks whether its own result can be trusted.

Each check is ONE function with the same signature:

    def my_check(case, params, mesh, result) -> CheckResult | None

It returns a CheckResult (level "info" = fine, "warning" = be careful, "error" = do not trust
the result) or None when the check does not apply to this case (e.g. no mass flow to balance).
All checks are listed in CHECKS; run_checks() runs them all. To add a check later (Knudsen
number, ideal-gas validity, y+ ...), write one function and add it to CHECKS.

Mesh quality checks (MESH_CHECKS) only look at the mesh, so they can run BEFORE the solver:
run_mesh_checks() is called by the run engine, which refuses to start the solver when one of
them reports an error (e.g. a cell with zero or negative volume). They apply to face-based
meshes (aeroflowsim.mesh.Mesh) only; for 1D meshes they return None (= does not apply).

Geometry checks (GEOMETRY_CHECKS) look at the workspace geometry (aeroflowsim/geometry_model/)
BEFORE meshing; their signature is  def my_check(built, settings) -> CheckResult | None  (built: the
replayed geometry, settings: the GmshSettings or None). run_geometry_checks() runs them.

The GUI shows the results in the "Validity checks" box of the Results tab, the command line
prints them, and summary.yaml stores them. Nothing here depends on the GUI.
"""

import math
from dataclasses import dataclass

import numpy as np

from aeroflowsim import mesh_quality
from aeroflowsim.mesh import TRIANGLE, Mesh

LEVELS = ("info", "warning", "error")

MIN_RESIDUAL_DROP = 6.0      # orders of magnitude a steady case's residual should drop [-]
MAX_MASS_IMBALANCE = 0.5     # largest acceptable inlet/exit mass-flow difference [%]
NO_FLOW = 1e-15              # mass flows below this are treated as "no flow" [kg/s]
MAX_ASPECT_RATIO = 100.0     # largest cell aspect ratio without a warning (no inflation) [-]
MAX_NON_ORTHOGONALITY = 70.0 # largest angle between face normal and centre line [deg]
MAX_VOLUME_RATIO = 2.0       # largest volume ratio of two neighbouring cells, quad meshes [-]
MAX_VOLUME_RATIO_TRIANGLES = 4.0   # ... meshes with triangles: equal-sized triangles of different
                                   # shapes already differ about 2.5 times in area [-]
MAX_INFLATION_FRACTION = 0.5 # inflation thicker than this fraction of the throat radius: warning [-]
MAX_INFLATION_FRACTION_BODY = 0.1  # ... or of the reference length of a body in a free stream [-]
MIN_ANGLE_WARNING = 20.0     # smallest triangle angle below this: warning [deg]
MIN_ANGLE_ERROR = 5.0        # smallest triangle angle below this: error, the solver will not run [deg]
MAX_SKEWNESS = 0.85          # largest equiangle skewness without a warning [-]
MIN_CELLS_PER_FEATURE = 2.0  # the smallest wall feature should be at least this many surface cells long [-]
AXIS_TOLERANCE = 1e-9        # a point is below the axis if y < -this x geometry size [-]


@dataclass
class CheckResult:
    """The outcome of one validity check."""

    name: str              # short name, e.g. "Convergence"
    level: str             # "info", "warning" or "error"
    message: str           # one sentence for the user
    value: float | None = None   # the number the check is based on (None if there is none)
    unit: str = ""         # unit of value, e.g. "%" or "orders"

    def __post_init__(self):
        if self.level not in LEVELS:
            raise ValueError(f"Check level must be one of {LEVELS}, got '{self.level}'.")
        if self.value is not None:
            self.value = float(self.value)   # plain Python float (numpy numbers cannot go into YAML)

    def as_dict(self) -> dict:
        """Plain dictionary (for summary.yaml and reports)."""
        return {"name": self.name, "level": self.level, "message": self.message,
                "value": self.value, "unit": self.unit}


def convergence(case, params, mesh, result):
    """Steady cases: how many orders of magnitude the (normalised) residual has dropped."""
    residuals = list(result.residuals or [])
    if not residuals:
        return None
    if not getattr(case, "steady", True):
        return CheckResult("Convergence", "info",
                           "Time-accurate (unsteady) run to the end time: a residual drop is not expected.")
    first, last = residuals[0], residuals[-1]
    if not (math.isfinite(first) and math.isfinite(last)):
        return CheckResult("Convergence", "error", "The residual is not a finite number: the solution diverged.")
    if last == 0.0:
        return CheckResult("Convergence", "info",
                           "The residual is exactly zero (the initial state is already the steady solution).")
    if first <= 0.0:
        return None
    orders = math.log10(first / last)
    if orders < MIN_RESIDUAL_DROP:
        return CheckResult("Convergence", "warning",
                           f"The residual dropped only {orders:.1f} orders of magnitude (at least "
                           f"{MIN_RESIDUAL_DROP:g} expected for a steady case): the result may not be converged.",
                           orders, "orders")
    return CheckResult("Convergence", "info",
                       f"The residual dropped {orders:.1f} orders of magnitude.", orders, "orders")


def mass_balance(case, params, mesh, result):
    """Inlet vs exit mass flow, for cases that report key numbers mdot_inlet and mdot_exit [kg/s]."""
    numbers = result.key_numbers or {}
    if "mdot_inlet" not in numbers or "mdot_exit" not in numbers:
        return None
    m_in, m_out = numbers["mdot_inlet"][0], numbers["mdot_exit"][0]   # [kg/s]
    if not (math.isfinite(m_in) and math.isfinite(m_out)):
        return CheckResult("Mass balance", "error", "The mass flow is not a finite number.")
    mean = 0.5 * (abs(m_in) + abs(m_out))
    if mean < NO_FLOW:
        return CheckResult("Mass balance", "info", "No net flow through the duct (gas at rest).", 0.0, "%")
    imbalance = 100.0 * abs(m_in - m_out) / mean   # [%]
    if imbalance > MAX_MASS_IMBALANCE:
        return CheckResult("Mass balance", "warning",
                           f"Inlet and exit mass flow differ by {imbalance:.3g} % (more than "
                           f"{MAX_MASS_IMBALANCE:g} %): mass is not conserved well, the run may not be converged.",
                           imbalance, "%")
    return CheckResult("Mass balance", "info",
                       f"Inlet and exit mass flow agree within {imbalance:.2g} %.", imbalance, "%")


# ---- mesh quality (face-based meshes only) -----------------------------------------------------

def _face_mesh(mesh):
    """The mesh if it is a face-based Mesh, else None (the mesh checks then do not apply)."""
    return mesh if isinstance(mesh, Mesh) else None


def mesh_cell_volumes(case, params, mesh, result):
    """Every cell must have a positive volume; otherwise the solver must not run."""
    if _face_mesh(mesh) is None:
        return None
    bad = int(np.count_nonzero(mesh.cell_volumes <= 0.0))
    if bad:
        return CheckResult("Cell volumes", "error",
                           f"{bad} cell(s) have zero or negative volume (inverted or collapsed cells). "
                           "The solver will not run on this mesh: fix the geometry or the mesh settings.",
                           bad, "cells")
    return CheckResult("Cell volumes", "info", "All cell volumes are positive.", 0, "cells")


def mesh_aspect_ratio(case, params, mesh, result):
    """Largest cell aspect ratio; thin cells are expected (info only) inside inflation layers."""
    if _face_mesh(mesh) is None:
        return None
    worst = float(np.nanmax(mesh_quality.aspect_ratio(mesh)))
    if worst > MAX_ASPECT_RATIO and mesh.info.get("inflation"):
        return CheckResult("Aspect ratio", "info",
                           f"Largest aspect ratio {worst:.3g}: thin cells in the inflation layers are intended.",
                           worst, "-")
    if worst > MAX_ASPECT_RATIO:
        return CheckResult("Aspect ratio", "warning",
                           f"Largest aspect ratio {worst:.3g} (more than {MAX_ASPECT_RATIO:g}): very stretched "
                           "cells can slow convergence and reduce accuracy.", worst, "-")
    return CheckResult("Aspect ratio", "info", f"Largest aspect ratio {worst:.3g}.", worst, "-")


def mesh_non_orthogonality(case, params, mesh, result):
    """Largest angle between a face normal and the line joining the two cell centres."""
    if _face_mesh(mesh) is None:
        return None
    worst = float(mesh_quality.non_orthogonality(mesh).max())
    if worst > MAX_NON_ORTHOGONALITY:
        return CheckResult("Non-orthogonality", "warning",
                           f"Largest non-orthogonality {worst:.3g}° (more than {MAX_NON_ORTHOGONALITY:g}°): "
                           "gradients and diffusive fluxes become inaccurate.", worst, "deg")
    return CheckResult("Non-orthogonality", "info", f"Largest non-orthogonality {worst:.3g}°.", worst, "deg")


def _has_triangles(mesh):
    return bool(np.any(mesh.cell_types == TRIANGLE))


def mesh_volume_ratio(case, params, mesh, result):
    """Largest volume ratio of two neighbouring cells (a sudden jump in cell size)."""
    if _face_mesh(mesh) is None:
        return None
    worst = float(np.nanmax(mesh_quality.volume_ratio(mesh)))
    limit = MAX_VOLUME_RATIO_TRIANGLES if _has_triangles(mesh) else MAX_VOLUME_RATIO
    if worst > limit:
        hint = ""
        if mesh.info.get("inflation") and str(mesh.info.get("generator", "")).startswith("gmsh"):
            hint = (" With inflation layers the biggest jumps are where the thin layers meet the triangles and "
                    "at the corner fans: more layers or a larger growth rate give a smoother transition.")
        return CheckResult("Cell growth", "warning",
                           f"Two neighbouring cells differ {worst:.3g} times in volume (more than "
                           f"{limit:g}): sudden jumps in cell size cause numerical errors.{hint}", worst, "-")
    return CheckResult("Cell growth", "info",
                       f"Largest volume ratio of neighbouring cells {worst:.3g}.", worst, "-")


def mesh_inflation(case, params, mesh, result):
    """Inflation layers must be thin compared with the throat radius (or the body) and must not overlap."""
    if _face_mesh(mesh) is None or not mesh.info.get("inflation"):
        return None
    if "r_throat" not in mesh.info:      # a body in a free stream: compare with its reference length
        thickness, length = mesh.info["inflation_thickness"], mesh.info["reference_length"]   # [m]
        fraction = 100.0 * thickness / length                                                 # [%]
        if fraction > 100.0 * MAX_INFLATION_FRACTION_BODY:
            return CheckResult("Inflation layers", "warning",
                               f"The inflation layers are {fraction:.3g} % of the reference length thick (more "
                               f"than {100 * MAX_INFLATION_FRACTION_BODY:g} %): much thicker than a boundary layer.",
                               fraction, "%")
        return CheckResult("Inflation layers", "info",
                           f"The inflation layers are {thickness * 1e6:.4g} µm thick, {fraction:.3g} % of the "
                           "reference length.", fraction, "%")
    thickness, r_throat = mesh.info["inflation_thickness"], mesh.info["r_throat"]   # [m]
    fraction = 100.0 * thickness / r_throat                                         # [%]
    if thickness >= r_throat:
        return CheckResult("Inflation layers", "warning",
                           f"The inflation layers ({thickness * 1e3:.4g} mm) are thicker than the throat "
                           "radius: layers from the wall would overlap at the axis.", fraction, "%")
    if fraction > 100.0 * MAX_INFLATION_FRACTION:
        return CheckResult("Inflation layers", "warning",
                           f"The inflation layers are {fraction:.3g} % of the throat radius thick (more than "
                           f"{100 * MAX_INFLATION_FRACTION:g} %): they fill much of the throat. Use a smaller "
                           "first layer height, fewer layers or a smaller growth rate.", fraction, "%")
    return CheckResult("Inflation layers", "info",
                       f"The inflation layers are {thickness * 1e6:.4g} µm thick, {fraction:.3g} % of the "
                       "throat radius.", fraction, "%")


def mesh_min_angle(case, params, mesh, result):
    """Smallest corner angle of any triangle (meshes with triangles only)."""
    if _face_mesh(mesh) is None or not _has_triangles(mesh):
        return None
    smallest = float(np.nanmin(mesh_quality.min_angle(mesh)[mesh.cell_types == TRIANGLE]))   # [deg]
    if smallest < MIN_ANGLE_ERROR:
        return CheckResult("Smallest angle", "error",
                           f"A triangle has an angle of only {smallest:.3g}° (less than {MIN_ANGLE_ERROR:g}°): such "
                           "slivers make the solver fail. The solver will not run on this mesh: change the mesh "
                           "settings.", smallest, "deg")
    if smallest < MIN_ANGLE_WARNING:
        return CheckResult("Smallest angle", "warning",
                           f"A triangle has an angle of only {smallest:.3g}° (less than {MIN_ANGLE_WARNING:g}°): "
                           "gradients there are inaccurate.", smallest, "deg")
    return CheckResult("Smallest angle", "info", f"The smallest triangle angle is {smallest:.3g}°.", smallest, "deg")


def mesh_skewness(case, params, mesh, result):
    """Largest equiangle skewness (0 = perfect cell shapes, 1 = flat cells)."""
    if _face_mesh(mesh) is None:
        return None
    worst = float(np.nanmax(mesh_quality.equiangle_skewness(mesh)))
    if worst > MAX_SKEWNESS:
        return CheckResult("Skewness", "warning",
                           f"Largest equiangle skewness {worst:.3g} (more than {MAX_SKEWNESS:g}): strongly distorted "
                           "cells reduce accuracy and can slow convergence.", worst, "-")
    return CheckResult("Skewness", "info", f"Largest equiangle skewness {worst:.3g}.", worst, "-")


def mesh_smallest_cell(case, params, mesh, result):
    """The smallest cell size (it sets the time step of an explicit solver)."""
    if _face_mesh(mesh) is None:
        return None
    smallest = float(mesh_quality.cell_size(mesh).min())   # [m]
    return CheckResult("Smallest cell", "info", f"The smallest cell is {smallest * 1e6:.4g} µm thick.",
                       smallest, "m")


# Mesh-only checks: run before the solver, and shown with the other checks. Add new ones here.
MESH_CHECKS = [mesh_cell_volumes, mesh_aspect_ratio, mesh_non_orthogonality, mesh_volume_ratio,
               mesh_min_angle, mesh_skewness, mesh_inflation, mesh_smallest_cell]

# Every check, in the order shown. Add new checks here.
CHECKS = [convergence, mass_balance] + MESH_CHECKS


# ---- geometry checks (before meshing) ------------------------------------------------------------

def geometry_replay(built, settings):
    """Every step of the geometry history worked."""
    if built.failed_operation:
        return CheckResult("Geometry steps", "error", " ".join(built.errors()) or
                           f"Step {built.failed_operation} failed.")
    return CheckResult("Geometry steps", "info", "Every step of the geometry history worked.")


def geometry_closed_loops(built, settings):
    """Every curve belongs to a closed face (free curves are not meshed)."""
    free = [e for e in built.edges.values() if not e.faces]
    if free:
        return CheckResult("Closed loops", "warning", f"{len(free)} curve(s) are not part of a closed face, so they "
                           "are not meshed. Close them (sketch a line over the gap) or delete them.", len(free))
    return CheckResult("Closed loops", "info", "Every curve is part of a closed face.")


def geometry_self_intersections(built, settings):
    """No outline crosses itself."""
    from aeroflowsim.shapes.profile import count_self_intersections
    crossings = sum(count_self_intersections(built.loop_points(loop)) for f in built.faces.values() for loop in f.loops)
    if crossings:
        return CheckResult("Self-intersections", "error", f"Face outlines cross themselves ({crossings} crossing(s)); "
                           "such a face cannot be meshed.", crossings)
    branching = [t for level, t in built.messages if "cross or branch" in t or "crosses itself" in t]
    if branching:
        return CheckResult("Self-intersections", "error", branching[0])
    return CheckResult("Self-intersections", "info", "No outline crosses itself.")


def geometry_bodies_inside(built, settings):
    """Solid bodies are cut out of the fluid (inside an enclosure); left-over solid faces are not meshed."""
    from aeroflowsim.geometry_model import FLUID, SOLID
    solids, fluid = built.faces_with_role(SOLID), built.faces_with_role(FLUID)
    if not fluid:
        return CheckResult("Body inside the domain", "error", "There is no fluid region: add an enclosure around the "
                           "body, or mark a face as fluid.")
    if solids:
        return CheckResult("Body inside the domain", "warning", f"{len(solids)} solid face(s) are not cut out of the "
                           "fluid (outside the domain, or overlapping it without a boolean); they are not meshed.",
                           len(solids))
    return CheckResult("Body inside the domain", "info", "Every body is cut out of the fluid region.")


def geometry_boundary_names(built, settings):
    """Every boundary edge has a name and a type; a name has only one type."""
    from aeroflowsim.geometry_model.boundaries import boundary_problems
    problems = [text for level, text in boundary_problems(built) if level == "error" and "fluid region" not in text]
    if problems:
        return CheckResult("Boundary names", "error", " ".join(problems))
    return CheckResult("Boundary names", "info", f"All boundary edges are named ({len(built.patches())} boundaries).",
                       len(built.patches()))


def geometry_feature_size(built, settings):
    """The smallest wall feature is resolved by the surface cell size."""
    if settings is None:
        return None
    walls = [built.edges[e] for e in built.boundary_edges() if e in built.names and built.names[e].type == "wall"]
    if not walls:
        return None
    feature = min(e.length for e in walls)                      # [m]
    cells = feature / settings.surface_size
    text = (f"The smallest wall feature is {feature * 1e3:.4g} mm long: {cells:.3g} surface cells "
            f"of {settings.surface_size * 1e3:.4g} mm.")
    if cells < MIN_CELLS_PER_FEATURE:
        return CheckResult("Smallest feature", "warning", text + " Use smaller wall cells (see Suggestions) to "
                           "resolve it.", cells, "cells")
    return CheckResult("Smallest feature", "info", text, cells, "cells")


def geometry_axisymmetric(built, settings):
    """Axisymmetric geometry: y >= 0 everywhere and an axis boundary on y = 0."""
    if not built.axisymmetric:
        return None
    y_min = min((float(e.points[:, 1].min()) for e in built.edges.values()), default=0.0)
    if y_min < -AXIS_TOLERANCE * built.size:
        return CheckResult("Axisymmetric rules", "error", f"Part of the geometry is below the axis (y = "
                           f"{y_min * 1e3:.4g} mm); axisymmetric geometry must have y = r >= 0.", y_min, "m")
    axis = [e for e in built.boundary_edges() if e in built.names and built.names[e].type == "axis"]
    if built.faces and not axis:
        return CheckResult("Axisymmetric rules", "error", "An axisymmetric geometry needs a boundary of type axis "
                           "on y = 0.")
    return CheckResult("Axisymmetric rules", "info", "y >= 0 everywhere and the axis is on y = 0.")


GEOMETRY_CHECKS = [geometry_replay, geometry_closed_loops, geometry_self_intersections, geometry_bodies_inside,
                   geometry_boundary_names, geometry_feature_size, geometry_axisymmetric]


def run_geometry_checks(built, settings=None) -> list[CheckResult]:
    """Run the geometry checks on a replayed workspace geometry (settings: GmshSettings or None)."""
    results = []
    for check in GEOMETRY_CHECKS:
        try:
            outcome = check(built, settings)
        except Exception as error:
            outcome = CheckResult(check.__name__, "error", f"The check itself failed: {error!r}")
        if outcome is not None:
            results.append(outcome)
    return results


def run_checks(case, params, mesh, result, checks=None) -> list[CheckResult]:
    """Run every check that applies; a check that crashes is reported as an error, not raised.

    checks: the check functions to run (default: all of CHECKS).
    """
    results = []
    for check in CHECKS if checks is None else checks:
        try:
            outcome = check(case, params, mesh, result)
        except Exception as error:   # a broken check must never hide the solver's result
            outcome = CheckResult(check.__name__, "error", f"The check itself failed: {error!r}")
        if outcome is not None:
            results.append(outcome)
    return results


def run_mesh_checks(case, params, mesh) -> list[CheckResult]:
    """Run only the mesh quality checks (possible before the solver has run)."""
    return run_checks(case, params, mesh, None, checks=MESH_CHECKS)


def worst_level(results: list[CheckResult]) -> str:
    """The most serious level among the results ("info" if there are none)."""
    return max((r.level for r in results), key=LEVELS.index, default="info")

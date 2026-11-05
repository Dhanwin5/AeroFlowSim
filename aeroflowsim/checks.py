# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validity checks: after every run, the software checks whether its own result can be trusted.

Each check is ONE function with the same signature:

    def my_check(case, params, mesh, result) -> CheckResult | None

It returns a CheckResult (level "info" = fine, "warning" = be careful, "error" = do not trust
the result) or None when the check does not apply to this case (e.g. no mass flow to balance).
All checks are listed in CHECKS; run_checks() runs them all. To add a check later (Knudsen
number, y+ ...), write one function and add it to CHECKS.

Gas checks (ideal-gas validity, condensation risk, temperature range) apply to cases that say which
gas they use (case.gas(params), aeroflowsim/gases/) and return "T" [K] and "p" [Pa] fields; they also
look at the case's reservoir_state(params) (e.g. the chamber), if it has one.

Setup checks (SETUP_CHECKS) look at the inputs and the mesh before the solver starts, e.g. an angle of
attack on an axisymmetric mesh; an error-level setup check stops the run (run_setup_checks, engine).

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
from aeroflowsim.gases import peng_robinson_z
from aeroflowsim.mesh import TETRA, TRIANGLE, WEDGE, Mesh
from aeroflowsim.units import Quantity

LEVELS = ("info", "warning", "error")

MIN_RESIDUAL_DROP = 6.0      # orders of magnitude a steady case's residual should drop [-]
MAX_MASS_IMBALANCE = 0.5     # largest acceptable inlet/exit mass-flow difference [%]
NO_FLOW = 1e-15              # mass flows below this are treated as "no flow" [kg/s]
MAX_ASPECT_RATIO = 100.0     # largest cell aspect ratio without a warning (no inflation) [-]
MAX_NON_ORTHOGONALITY = 70.0 # largest angle between face normal and centre line [deg]
MAX_VOLUME_RATIO = 2.0       # largest volume ratio of two neighbouring cells, quad meshes [-]
MAX_VOLUME_RATIO_TETRAHEDRA = 10.0   # ... 3D meshes with tetrahedra: tetrahedra with equal edges differ up to
                             # about 5 times in volume at a skewness of 0.8, and the prism / tetrahedron transition adds 2 [-]
MAX_VOLUME_RATIO_TRIANGLES = 4.0   # ... meshes with triangles: equal-sized triangles of different
                                   # shapes already differ about 2.5 times in area [-]
MAX_INFLATION_FRACTION = 0.5 # inflation thicker than this fraction of the throat radius: warning [-]
MAX_INFLATION_FRACTION_BODY = 0.1  # ... or of the reference length of a body in a free stream [-]
MIN_ANGLE_WARNING = 20.0     # smallest triangle angle below this: warning [deg]
MIN_ANGLE_ERROR = 5.0        # smallest triangle angle below this: error, the solver will not run [deg]
MAX_SKEWNESS = 0.85          # largest equiangle skewness without a warning [-]
MAX_SKEWNESS_3D = 0.95       # largest skewness of a 3D mesh (equivolume for tetrahedra) without a warning [-]
MIN_DIHEDRAL_WARNING = 5.0   # smallest dihedral angle of a tetrahedron without a warning [deg]
FIRST_LAYER_TOLERANCE = 0.2  # measured first-layer height may differ this much from the requested one [-]
MIN_CELLS_PER_FEATURE = 2.0  # the smallest wall feature should be at least this many surface cells long [-]
AXIS_TOLERANCE = 1e-9        # a point is below the axis if y < -this x geometry size [-]
MAX_Z_DEVIATION = 2.0        # ideal-gas check: largest |Z - 1| without a warning [%]


@dataclass
class CheckResult:
    """The outcome of one validity check."""

    name: str              # short name, e.g. "Convergence"
    level: str             # "info", "warning" or "error"
    message: str           # one sentence for the user (with quantities: a template with {0}, {1}, ...)
    value: float | None = None   # the number the check is based on (None if there is none)
    unit: str = ""         # unit of value, e.g. "%" or "orders"
    quantities: tuple = () # dimensional numbers of the message (aeroflowsim.units.Quantity): the GUI shows
                           # them in the user's units, text() without preferences writes them in SI
    template: str = ""     # the message with {0}, {1}, ... in place of the quantities (set automatically)

    def __post_init__(self):
        if self.level not in LEVELS:
            raise ValueError(f"Check level must be one of {LEVELS}, got '{self.level}'.")
        if self.value is not None:
            self.value = float(self.value)   # plain Python float (numpy numbers cannot go into YAML)
        if self.quantities:
            self.quantities = tuple(Quantity(**q) if isinstance(q, dict) else q for q in self.quantities)
            if not self.template:
                self.template = self.message
            self.message = self.text()       # the SI text: command line, summary.yaml, reports

    def text(self, prefs=None) -> str:
        """The message, with its quantities in the user's units (prefs: UnitPreferences) or in SI."""
        if not self.quantities:
            return self.message
        return self.template.format(*(q.text(prefs) for q in self.quantities))

    def as_dict(self) -> dict:
        """Plain dictionary (for summary.yaml and reports)."""
        d = {"name": self.name, "level": self.level, "message": self.message, "value": self.value, "unit": self.unit}
        if self.quantities:
            d.update(quantities=[q.as_dict() for q in self.quantities], template=self.template)
        return d


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


# ---- gas validity (cases with case.gas(params) and T, p fields) -----------------------------------

def _gas_states(case, params, result):
    """(gas model, T [K] per cell, p [Pa] per cell, reservoir (p0, T0) or None), or None if the checks
    do not apply (no gas model, or no temperature / pressure fields)."""
    if not hasattr(case, "gas") or result is None:
        return None
    fields = result.fields or {}
    if "T" not in fields or "p" not in fields:
        return None
    gas = case.gas(params)
    T = np.asarray(fields["T"].values, dtype=float)
    p = np.asarray(fields["p"].values, dtype=float)
    reservoir = case.reservoir_state(params) if hasattr(case, "reservoir_state") else None
    return gas, T, p, reservoir


class _Numbers:
    """Collects the dimensional numbers of one message: q() returns the placeholder {i} for the template
    and remembers the Quantity, so the GUI can show it in the user's units (see CheckResult.text)."""

    def __init__(self):
        self.quantities = []

    def q(self, value, unit, digits=4, delta=False) -> str:
        self.quantities.append(Quantity(float(value), unit, digits, delta))
        return "{" + str(len(self.quantities) - 1) + "}"


def _literal(text) -> str:
    """Text put into a message template as it is (a custom gas name may contain braces)."""
    return str(text).replace("{", "{{").replace("}", "}}")


def _state(n, p, T) -> str:
    return f"{n.q(p, 'Pa')}, {n.q(T, 'K')}"


def ideal_gas_validity(case, params, mesh, result):
    """Is the ideal-gas law p = rho R T good enough? The compressibility factor Z (Peng-Robinson, from the
    gas's critical point) should stay within MAX_Z_DEVIATION % of 1 in every cell and in the reservoir."""
    states = _gas_states(case, params, result)
    if states is None:
        return None
    gas, T, p, reservoir = states
    data = gas.data
    if not data.has_critical_point:
        return CheckResult("Ideal gas", "info", f"Cannot run for {gas.name}: its critical temperature, critical "
                           "pressure and acentric factor are not known, and the compressibility estimate "
                           "(Peng-Robinson) needs all three. For a custom gas, add them in the custom-gas form "
                           "(Custom... next to the gas, or Tools > Gas library).")
    crit = (data.T_critical, data.p_critical, data.acentric_factor)
    deviation = 100.0 * np.abs(peng_robinson_z(p, T, *crit) - 1.0)     # [%] per cell
    i = int(np.argmax(deviation))
    flow, tank = _Numbers(), _Numbers()
    worst, where, n = deviation[i], f"in the flow ({_state(flow, p[i], T[i])})", flow
    if reservoir is not None:
        z0 = peng_robinson_z(reservoir[0], reservoir[1], *crit)
        if 100.0 * abs(z0 - 1.0) >= worst:
            worst, n = 100.0 * abs(z0 - 1.0), tank
            where = f"in the reservoir ({_state(tank, *reservoir)}, Z = {z0:.4f})"
    name = _literal(gas.name)
    if worst > MAX_Z_DEVIATION:
        return CheckResult("Ideal gas", "warning",
                           f"The compressibility factor Z differs from 1 by {worst:.3g} % {where}: the ideal-gas "
                           f"model of {name} is not accurate there (limit {MAX_Z_DEVIATION:g} %, Peng-Robinson "
                           "estimate). A real-gas model is planned (Phase 5).", worst, "%", n.quantities)
    return CheckResult("Ideal gas", "info", f"The ideal-gas law holds within {worst:.2g} % (largest |Z - 1|, "
                       f"Peng-Robinson estimate, {where}).", worst, "%", n.quantities)


def condensation_risk(case, params, mesh, result):
    """Does the gas cool below its saturation (or frost) temperature somewhere? Margin T - T_sat(p) [K]
    in every cell, reported at the exit (last cell) and where it is smallest."""
    states = _gas_states(case, params, result)
    if states is None:
        return None
    gas, T, p, reservoir = states
    curve = gas.data.vapour_pressure
    if curve is None:
        return CheckResult("Condensation", "info", f"No saturation curve stored for {gas.name}: the "
                           "condensation risk cannot be estimated.")
    T_sat = curve.T_sat(p)                                        # nan above the critical pressure
    margin = np.where(np.isnan(T_sat), T - curve.T_critical, T - T_sat)   # [K]
    i = int(np.argmin(margin))
    name = _literal(gas.name)
    n = _Numbers()
    estimate = (". Below the triple-point pressure the frost temperature is estimated by extending the "
                "vapour-pressure curve (Clausius-Clapeyron); the true frost point is somewhat higher (N2 at the "
                f"default exit: about {n.q(0.6, 'K', 2, delta=True)}), so read this margin as an upper limit"
                if np.any(p < curve.p[0]) else "")
    exit_text = (f"exit: T = {n.q(T[-1], 'K')} at {n.q(p[-1], 'Pa')}, saturation temperature "
                 f"{n.q(T[-1] - margin[-1], 'K')}, margin {n.q(margin[-1], 'K', 3, delta=True)}")
    if reservoir is not None:
        p0, T0 = reservoir
        if T0 < curve.T_critical and p0 > float(curve.p_sat(T0)):
            r = _Numbers()
            return CheckResult("Condensation", "warning",
                               f"The reservoir state ({_state(r, p0, T0)}) is a LIQUID for {name} (saturation "
                               f"pressure {r.q(curve.p_sat(T0), 'Pa')}): this gas model does not apply.",
                               float(margin[i]), "K", r.quantities)
    if margin[i] < 0.0:
        where = f"down to {n.q(-margin[i], 'K', 3, delta=True)} below, at {_state(n, p[i], T[i])}"
        return CheckResult("Condensation", "warning",
                           f"{name} is colder than its saturation temperature in {int(np.sum(margin < 0))} "
                           f"cell(s) ({where}): it may condense there, which this model does not include; "
                           f"{exit_text}{estimate}.", float(margin[i]), "K", n.quantities)
    smallest = n.q(margin[i], "K", 3, delta=True)
    return CheckResult("Condensation", "info", f"No condensation: smallest margin {smallest} to the "
                       f"saturation temperature; {exit_text}{estimate}.", float(margin[i]), "K", n.quantities)


def temperature_range(case, params, mesh, result):
    """Do all temperatures stay inside the range where the gas data are valid (constant cp and gamma for
    this calorically perfect gas)? Inviscid cases: thermodynamic range only."""
    states = _gas_states(case, params, result)
    if states is None:
        return None
    gas, T, p, reservoir = states
    lo, hi = gas.thermo_range
    T_all = np.append(T, reservoir[1]) if reservoir is not None else T
    T_min, T_max = float(T_all.min()), float(T_all.max())
    n = _Numbers()
    temperatures = f"{n.q(T_min, 'K')} to {n.q(T_max, 'K')}"
    name = _literal(gas.name)
    if not math.isfinite(hi):
        return CheckResult("Temperature range", "info", f"No valid temperature range stored for {name} "
                           f"(temperatures {temperatures}).", None, "", n.quantities)
    limits = f"{n.q(lo, 'K')} to {n.q(hi, 'K')}"
    if T_min < lo or T_max > hi:
        return CheckResult("Temperature range", "warning",
                           f"Temperatures {temperatures} leave the range {limits} of the gas data of {name} (where "
                           "its constant cp is within 2 % of the real cp; the lower end is often the triple point, "
                           "below which the source has no gas data).", T_min, "K", n.quantities)
    return CheckResult("Temperature range", "info", f"Temperatures {temperatures} are inside the valid range of "
                       f"the gas data ({limits}).", T_min, "K", n.quantities)


GAS_CHECKS = [ideal_gas_validity, condensation_risk, temperature_range]


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
    if np.any(mesh.cell_types == TETRA):
        limit = MAX_VOLUME_RATIO_TETRAHEDRA
    if worst > limit:
        hint = ""
        if mesh.info.get("inflation") and str(mesh.info.get("generator", "")).startswith(("gmsh", "workspace 3D")):
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
        return CheckResult("Inflation layers", "info", f"The inflation layers are {{0}} thick, {fraction:.3g} % "
                           "of the reference length.", fraction, "%", [Quantity(thickness, "m")])
    thickness, r_throat = mesh.info["inflation_thickness"], mesh.info["r_throat"]   # [m]
    fraction = 100.0 * thickness / r_throat                                         # [%]
    if thickness >= r_throat:
        return CheckResult("Inflation layers", "warning",
                           "The inflation layers ({0}) are thicker than the throat radius ({1}): layers from the "
                           "wall would overlap at the axis.", fraction, "%",
                           [Quantity(thickness, "m"), Quantity(r_throat, "m")])
    if fraction > 100.0 * MAX_INFLATION_FRACTION:
        return CheckResult("Inflation layers", "warning",
                           f"The inflation layers are {fraction:.3g} % of the throat radius thick (more than "
                           f"{100 * MAX_INFLATION_FRACTION:g} %): they fill much of the throat. Use a smaller "
                           "first layer height, fewer layers or a smaller growth rate.", fraction, "%")
    return CheckResult("Inflation layers", "info",
                       f"The inflation layers are {{0}} thick, {fraction:.3g} % of the throat radius.", fraction, "%",
                       [Quantity(thickness, "m")])


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
    """Largest equiangle skewness (0 = perfect cell shapes, 1 = flat cells); 3D: equivolume for tetrahedra."""
    if _face_mesh(mesh) is None:
        return None
    if mesh.dim == 3:
        worst = float(np.nanmax(mesh_quality.skewness(mesh)))
        if worst > MAX_SKEWNESS_3D:
            return CheckResult("Skewness", "warning",
                               f"Largest skewness {worst:.3g} (more than {MAX_SKEWNESS_3D:g}; equivolume for tetrahedra, "
                               "equiangle for the other cells): strongly distorted cells reduce accuracy and can slow "
                               "convergence.", worst, "-")
        return CheckResult("Skewness", "info", f"Largest skewness {worst:.3g} (equivolume for tetrahedra, equiangle for "
                           "the other cells).", worst, "-")
    worst = float(np.nanmax(mesh_quality.equiangle_skewness(mesh)))
    if worst > MAX_SKEWNESS:
        return CheckResult("Skewness", "warning",
                           f"Largest equiangle skewness {worst:.3g} (more than {MAX_SKEWNESS:g}): strongly distorted "
                           "cells reduce accuracy and can slow convergence.", worst, "-")
    return CheckResult("Skewness", "info", f"Largest equiangle skewness {worst:.3g}.", worst, "-")


def mesh_dihedral_angle(case, params, mesh, result):
    """Smallest dihedral angle of the tetrahedra of a 3D mesh (slivers: four corners almost in one plane)."""
    if _face_mesh(mesh) is None or mesh.dim != 3 or not np.any(mesh.cell_types == TETRA):
        return None
    smallest = float(np.nanmin(mesh_quality.min_dihedral_angle(mesh)))     # [deg]
    if smallest < MIN_DIHEDRAL_WARNING:
        return CheckResult("Dihedral angle", "warning",
                           f"A tetrahedron has a dihedral angle of only {smallest:.3g}° (less than "
                           f"{MIN_DIHEDRAL_WARNING:g}°): a nearly flat 'sliver' gives inaccurate gradients there.",
                           smallest, "deg")
    return CheckResult("Dihedral angle", "info", f"The smallest dihedral angle of the tetrahedra is {smallest:.3g}°.",
                       smallest, "deg")


def mesh_first_layer(case, params, mesh, result):
    """3D prism layers: the height of the first cell on the walls (volume / wall face area) against the requested one."""
    if _face_mesh(mesh) is None or mesh.dim != 3 or not mesh.info.get("first_layer_height"):
        return None
    wanted = float(mesh.info["first_layer_height"])                         # [m]
    walls = [p for p in mesh.patches if p.type == "wall"]
    faces = np.concatenate([p.faces for p in walls]) if walls else np.zeros(0, dtype=np.int64)
    faces = faces[mesh.cell_types[mesh.owner[faces]] == WEDGE]
    if not len(faces):
        return None
    height = float(np.mean(mesh.cell_volumes[mesh.owner[faces]] / mesh.face_areas[faces]))   # [m]
    error = 100.0 * (height - wanted) / wanted                               # [%]
    level = "warning" if abs(error) > 100.0 * FIRST_LAYER_TOLERANCE else "info"
    note = " (the layers were squeezed or stretched: check the wall corners)" if level == "warning" else ""
    return CheckResult("First layer height", level, "The first cells on the walls are {0} high on average (requested "
                       f"{{1}}, {error:+.2g} %){note}.", height, "m", [Quantity(height, "m"), Quantity(wanted, "m")])


def mesh_smallest_cell(case, params, mesh, result):
    """The smallest cell size (it sets the time step of an explicit solver)."""
    if _face_mesh(mesh) is None:
        return None
    smallest = float(mesh_quality.cell_size(mesh).min())   # [m]
    return CheckResult("Smallest cell", "info", "The smallest cell is {0} thick.", smallest, "m",
                       [Quantity(smallest, "m")])


# Mesh-only checks: run before the solver, and shown with the other checks. Add new ones here.
MEMORY_FRACTION = 0.7        # warn when a run needs more than this fraction of the free memory


def run_memory(case, params, mesh, result):
    """3D meshes: the memory the run will need (measured bytes per cell) against the free memory now; a warning above
    70 % of it (the computer would start swapping, or the run would fail part-way). 2D meshes: no check (small)."""
    if _face_mesh(mesh) is None or mesh.dim != 3:
        return None
    from aeroflowsim.compute import free_memory_bytes, run_memory_estimate
    need = run_memory_estimate(mesh.n_cells, 3)
    free = free_memory_bytes()
    gb = need / 1e9
    if free is not None and need > MEMORY_FRACTION * free:
        return CheckResult("Run memory", "warning",
                           f"The run needs about {gb:.1f} GB, more than 70 % of the {free / 1e9:.1f} GB free now: close "
                           "other programs, use a coarser mesh, or a half / quarter domain.", gb, "GB")
    note = "" if free is None else f" ({free / 1e9:.1f} GB free)"
    return CheckResult("Run memory", "info", f"The run needs about {gb:.2f} GB of memory{note}.", gb, "GB")


MESH_CHECKS = [mesh_cell_volumes, mesh_aspect_ratio, mesh_non_orthogonality, mesh_volume_ratio,
               mesh_min_angle, mesh_skewness, mesh_dihedral_angle, mesh_inflation, mesh_first_layer, mesh_smallest_cell,
               run_memory]


# ---- 2D/3D flow solver checks (results with Result.info, aeroflowsim/euler/) -----------------------

MAX_THRUST_DIFFERENCE = 0.5  # thrust from the exit plane vs from the wall: largest difference without a warning [%]
MAX_TOTAL_PRESSURE_LOSS = 0.5  # exit total-pressure loss of a shock-free nozzle without a warning [%]
SUBSONIC_SHOCK_FREE = 0.95   # largest Mach number below which an external flow cannot hold a shock [-]


def _info(result):
    return getattr(result, "info", None) or {}


def run_status(case, params, mesh, result):
    """2D runs: did the run end normally, or did the solution become unphysical (diverged)?"""
    info = _info(result)
    if "status" not in info:
        return None
    if info["status"] == "diverged":
        return CheckResult("Run status", "error",
                           f"The run diverged: {info.get('message', '')} The fields shown are the last good state; "
                           "do not use them. See the suggestions (Run step: What to try).")
    if info["status"] == "stopped":
        return CheckResult("Run status", "warning",
                           f"You stopped the run after {result.iterations:,} iterations, before it converged: the "
                           f"results show the flow of that moment. Press Run (Continue) to carry on from iteration "
                           f"{result.iterations + 1:,}.")
    return CheckResult("Run status", "info", f"The run ended normally ({info['status'].replace('_', ' ')}).")


def monitors_settled(case, params, mesh, result):
    """Steady 2D runs: have the convergence monitors (thrust, mass flow, Cd, Cl) stopped changing?"""
    info = _info(result)
    names = info.get("converge_on") or []
    series = getattr(result, "series", None) or {}
    window = int(info.get("monitor_window", 0))
    tol = float(info.get("monitor_tol", 0.0))
    if not names or not window or not getattr(case, "steady", True):
        return None
    worst, worst_name = 0.0, ""
    for name in names:
        values = np.asarray(series.get(f"monitor_{name}", ()), dtype=float)
        if len(values) < window:
            return CheckResult("Monitors settled", "warning",
                               f"The run is shorter than the monitor window ({window} iterations): it cannot be "
                               "judged whether the monitors have settled.")
        last = values[-window:]
        size = max(abs(float(last.mean())), 1e-300)
        if name in ("Cd", "Cl", "Cm"):
            size = max(size, 0.01)          # coefficients near zero (e.g. Cl at zero incidence)
        change = float(last.max() - last.min()) / size
        if change > worst:
            worst, worst_name = change, name
    labels = info.get("monitor_labels", {})
    label = labels.get(worst_name, [worst_name])[0] if worst_name else "every monitor"
    if worst > tol:
        return CheckResult("Monitors settled", "warning",
                           f"{label} still changed by {100 * worst:.3g} % over the last {window} iterations (allowed "
                           f"{100 * tol:.3g} %): the integrated results are not settled yet.", 100 * worst, "%")
    return CheckResult("Monitors settled", "info",
                       f"The monitors changed less than {100 * tol:.3g} % over the last {window} iterations "
                       f"(largest: {label}, {100 * worst:.2g} %).", 100 * worst, "%")


def positivity_events(case, params, mesh, result):
    """2D runs: faces where the reconstruction gave negative density or pressure (first-order fallback)."""
    info = _info(result)
    if "positivity_events" not in info:
        return None
    total, last = int(info["positivity_events"]), int(info.get("positivity_last", 0))
    if total == 0:
        return CheckResult("Positivity", "info", "The reconstruction never gave a negative density or pressure.", 0, "")
    if last > 0:
        return CheckResult("Positivity", "warning",
                           f"{last} faces still fall back to first order in the last iteration ({total:,} face events "
                           "in the whole run): the solution there is only first-order accurate. Usually a sign of a "
                           "very strong expansion or a too coarse mesh there.", total, "")
    return CheckResult("Positivity", "info",
                       f"{total:,} face events fell back to first order during the run (start-up transients), none "
                       "at the end.", total, "")


def cfl_reductions(case, params, mesh, result):
    """2D runs: how often the solver had to halve the CFL number to stay stable."""
    info = _info(result)
    if "cfl_reductions" not in info:
        return None
    n = int(info["cfl_reductions"])
    if n == 0:
        return CheckResult("CFL number", "info", f"No CFL reductions were needed (CFL {info.get('cfl_final', 0):g}).")
    return CheckResult("CFL number", "warning",
                       f"The solver halved the CFL number {n} times to stay stable (from {info.get('cfl', 0):g} to "
                       f"{info.get('cfl_final', 0):g}). Start the next run with CFL {info.get('cfl_final', 0):g}.", n, "")


def thrust_two_ways(case, params, mesh, result):
    """Nozzles: the thrust from the exit plane and from the wall pressure + inlet momentum must agree."""
    numbers = result.key_numbers or {} if result is not None else {}
    if "thrust_difference" not in numbers:
        return None
    diff = float(numbers["thrust_difference"][0])
    if diff > MAX_THRUST_DIFFERENCE:
        return CheckResult("Thrust two ways", "warning",
                           f"The exit-plane and wall-pressure thrusts differ by {diff:.3g} % (more than "
                           f"{MAX_THRUST_DIFFERENCE:g} %): momentum is not balanced yet, the run is not converged.",
                           diff, "%")
    return CheckResult("Thrust two ways", "info",
                       f"The exit-plane and wall-pressure thrusts agree within {diff:.2g} % (momentum balance).", diff, "%")


def total_pressure_loss(case, params, mesh, result):
    """Shock-free flows are isentropic: any total-pressure loss is numerical error (a classic accuracy check).

    Nozzle: the loss of the mass-flux-weighted total pressure at the exit, relative to the inlet total
    pressure (a shock in the nozzle would also show here). Body in a subsonic free stream (Mach < 0.95
    everywhere): the largest loss anywhere. Supersonic external flows have shocks, where a loss is physical.
    """
    info = _info(result)
    if result is None or "p0" not in (result.fields or {}) or "kind" not in info:
        return None
    p0 = result.fields["p0"].values
    if info["kind"] == "nozzle":
        bcs = info.get("boundaries", {})
        p0_in = next((b["p0"] for b in bcs.values() if b.get("type") == "total_pressure_inlet"), None)
        exit_p0 = result.key_numbers.get("p0_exit", (None,))[0]
        if p0_in is None or exit_p0 is None:
            return None
        loss = 100.0 * (1.0 - exit_p0 / p0_in)
        level = "warning" if loss > MAX_TOTAL_PRESSURE_LOSS else "info"
        extra = (" This is numerical (or a shock in the nozzle): refine the mesh, especially at the throat."
                 if level == "warning" else "")
        return CheckResult("Total-pressure loss", level,
                           f"The exit total pressure is {loss:.3g} % below the inlet total pressure (an isentropic "
                           f"nozzle loses nothing).{extra}", loss, "%")
    mach = result.fields["M"].values if "M" in result.fields else None
    if mach is None or float(mach.max()) >= SUBSONIC_SHOCK_FREE:
        return CheckResult("Total-pressure loss", "info",
                           "The flow reaches Mach 0.95 or more, so it may contain shocks: a total-pressure loss is "
                           "physical there and is not checked.")
    loss = 100.0 * (1.0 - float(p0.min()) / float(np.median(p0)))
    level = "warning" if loss > MAX_TOTAL_PRESSURE_LOSS else "info"
    return CheckResult("Total-pressure loss", level,
                       f"Largest total-pressure loss {loss:.3g} % in a shock-free flow (should be close to zero: it "
                       "is numerical error).", loss, "%")


FREE_STREAM_TYPES = ("far_field", "supersonic_inlet")   # boundary conditions that carry a free-stream angle


def axisymmetric_incidence(case, params, mesh, result):
    """An axisymmetric flow is the same at every angle round the axis, so its free stream must be parallel
    to the axis: an angle of attack (template input or a far-field / supersonic-inlet row of the boundary
    table) on an axisymmetric mesh is an error. It is known before the run, so it is also a setup check."""
    if not isinstance(mesh, Mesh) or not mesh.axisymmetric:
        return None
    angles = []
    if params.get("alpha"):
        angles.append(f"angle of attack {params['alpha']:g}°")
    for name, entry in (params.get("boundaries") or {}).items():
        if isinstance(entry, dict) and entry.get("type") in FREE_STREAM_TYPES and entry.get("flow_angle"):
            angles.append(f"boundary '{name}' at {entry['flow_angle']:g}°")
    if not angles:
        return CheckResult("Axisymmetric free stream", "info",
                           "The free stream is parallel to the axis, as an axisymmetric flow needs.") \
            if "alpha" in params else None
    return CheckResult("Axisymmetric free stream", "error",
                       f"The mesh is axisymmetric (a body of revolution), but the free stream is at an angle "
                       f"({'; '.join(angles)}). An axisymmetric flow is the same all round the axis, so it cannot "
                       "have an angle of attack. Set the angle to 0, or use a planar (2D) body for incidence.")


def wall_y_plus(case, params, mesh, result):
    """Viscous runs: y+ of the first cells. The low-Re wall treatment (no wall functions) needs y+ about 1; above 2
    the wall shear and heat flux of a turbulent boundary layer are not resolved."""
    from aeroflowsim.euler.viscous import TURBULENT_MODELS, is_viscous
    from aeroflowsim.smart_rules import MAX_WALL_Y_PLUS
    numbers = (result.key_numbers or {}) if result is not None else {}
    if not is_viscous(params.get("flow_model")) or "y_plus_max" not in numbers:
        return None
    yp = float(numbers["y_plus_max"][0])
    turbulent = params.get("flow_model") in TURBULENT_MODELS
    if yp > MAX_WALL_Y_PLUS:
        return CheckResult("Wall y+", "warning" if turbulent else "info",
                           f"y+ of the first cell reaches {yp:.3g} (above {MAX_WALL_Y_PLUS:g}). "
                           + ("The turbulence model has a low-Re wall treatment only (no wall functions): re-mesh with a "
                              "first layer for y+ about 1 (Mesh step, inflation layers; the smart rule suggests the "
                              "height)." if turbulent else
                              "For laminar flow this is acceptable while about 10 cells span the boundary layer; for "
                              "accurate wall shear and heat flux use a first layer for y+ about 1."), yp, "-")
    return CheckResult("Wall y+", "info", f"y+ of the first cell is at most {yp:.3g} (wall-resolved).", yp, "-")


def slip_walls_in_viscous_flow(case, params, mesh, result):
    """A viscous flow model with a wall the user set to 'slip wall': allowed (e.g. a far wall), but worth a note."""
    from aeroflowsim.euler.viscous import is_viscous
    if not is_viscous(params.get("flow_model")):
        return None
    table = params.get("boundaries") or {}
    slip = [name for name, bc in table.items() if isinstance(bc, dict) and bc.get("type") == "slip_wall"]
    if not slip:
        return None
    return CheckResult("Slip walls in viscous flow", "warning",
                       f"The flow model is {params['flow_model']}, but {', '.join(slip)} is set to 'Slip wall' (no "
                       "friction there). Set it to 'No-slip wall' unless that is intended.", float(len(slip)), "")


SETUP_CHECKS = [axisymmetric_incidence, slip_walls_in_viscous_flow]   # checks of the inputs and the mesh, before the solver starts

FLOW_CHECKS = [run_status, monitors_settled, thrust_two_ways, total_pressure_loss, positivity_events, cfl_reductions,
               wall_y_plus]

# Every check, in the order shown. Add new checks here.
CHECKS = [convergence, mass_balance] + FLOW_CHECKS + SETUP_CHECKS + GAS_CHECKS + MESH_CHECKS


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
    text = f"The smallest wall feature is {{0}} long: {cells:.3g} surface cells of {{1}}."
    sizes = [Quantity(feature, "m"), Quantity(settings.surface_size, "m")]
    if cells < MIN_CELLS_PER_FEATURE:
        return CheckResult("Smallest feature", "warning", text + " Use smaller wall cells (see Suggestions) to "
                           "resolve it.", cells, "cells", sizes)
    return CheckResult("Smallest feature", "info", text, cells, "cells", sizes)


def geometry_axisymmetric(built, settings):
    """Axisymmetric geometry: y >= 0 everywhere and an axis boundary on y = 0."""
    if not built.axisymmetric:
        return None
    y_min = min((float(e.points[:, 1].min()) for e in built.edges.values()), default=0.0)
    if y_min < -AXIS_TOLERANCE * built.size:
        return CheckResult("Axisymmetric rules", "error", "Part of the geometry is below the axis (y = {0}); "
                           "axisymmetric geometry must have y = r >= 0.", y_min, "m", [Quantity(y_min, "m")])
    axis = [e for e in built.boundary_edges() if e in built.names and built.names[e].type == "axis"]
    if built.faces and not axis:
        return CheckResult("Axisymmetric rules", "error", "An axisymmetric geometry needs a boundary of type axis "
                           "on y = 0.")
    return CheckResult("Axisymmetric rules", "info", "y >= 0 everywhere and the axis is on y = 0.")


GEOMETRY_CHECKS = [geometry_replay, geometry_closed_loops, geometry_self_intersections, geometry_bodies_inside,
                   geometry_boundary_names, geometry_feature_size, geometry_axisymmetric]


# ---- 3D geometry (BuiltGeometry3D, aeroflowsim/geometry_model/built3d.py) ---------------------------

def geometry_3d_bodies(built, settings):
    """3D: there is a fluid body, and the solid bodies are cut out of it (left-over solids are not meshed)."""
    from aeroflowsim.geometry_model import FLUID, SOLID
    solids, fluid = built.bodies_with_role(SOLID), built.bodies_with_role(FLUID)
    if not fluid:
        return CheckResult("Body inside the domain", "error", "There is no fluid body: add an enclosure around the "
                           "solid bodies, or mark a body as fluid.")
    if solids:
        return CheckResult("Body inside the domain", "warning", f"{len(solids)} solid body(ies) are not cut out of the "
                           "fluid (no enclosure after them, or outside it); they are not meshed.", len(solids))
    return CheckResult("Body inside the domain", "info", "Every solid body is cut out of the fluid.")


def geometry_3d_names(built, settings):
    """3D: every boundary face of the fluid has a name and a type; a name has only one type."""
    faces = built.boundary_faces()
    unnamed = [f for f in faces if f not in built.names]
    types = {}
    for f in faces:
        if f in built.names:
            types.setdefault(built.names[f].name, set()).add(built.names[f].type)
    mixed = [n for n, t in types.items() if len(t) > 1]
    if unnamed:
        return CheckResult("Boundary names", "error", f"{len(unnamed)} boundary face(s) have no name; name them in the "
                           "Boundaries tab (they become mesh patches).", len(unnamed))
    if mixed:
        return CheckResult("Boundary names", "error", f"The boundary name(s) {', '.join(mixed)} have faces of different "
                           "types; one name, one type.")
    return CheckResult("Boundary names", "info", f"All boundary faces are named ({len(types)} boundaries).", len(types))


def geometry_3d_feature_size(built, settings):
    """3D: the shortest edge of the walls is resolved by the surface cell size."""
    if settings is None:
        return None
    walls = {f for f in built.boundary_faces() if f in built.names and built.names[f].type == "wall"}
    edges = [e for e in built.edges.values() if walls & set(e.faces) and e.length > 1e-9 * built.size]   # (not the
    # degenerate edges at the poles of a sphere or the tip of a cone)
    if not edges:
        return None
    feature = min(e.length for e in edges)                      # [m]
    cells = feature / settings.surface_size
    text = f"The shortest wall edge is {{0}} long: {cells:.3g} surface cells of {{1}}."
    sizes = [Quantity(feature, "m"), Quantity(settings.surface_size, "m")]
    if cells < MIN_CELLS_PER_FEATURE:
        return CheckResult("Smallest feature", "warning", text + " Use smaller wall cells to resolve it.", cells,
                           "cells", sizes)
    return CheckResult("Smallest feature", "info", text, cells, "cells", sizes)


GEOMETRY_CHECKS_3D = [geometry_replay, geometry_3d_bodies, geometry_3d_names, geometry_3d_feature_size]


def run_geometry_checks(built, settings=None) -> list[CheckResult]:
    """Run the geometry checks on a replayed workspace geometry (settings: GmshSettings / MeshSettings3D or None)."""
    results = []
    for check in GEOMETRY_CHECKS_3D if getattr(built, "dimension", 2) == 3 else GEOMETRY_CHECKS:
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


def run_setup_checks(case, params, mesh) -> list[CheckResult]:
    """Run the setup checks (inputs + mesh, before the solver starts; an error stops the run)."""
    return run_checks(case, params, mesh, None, checks=SETUP_CHECKS)


def worst_level(results: list[CheckResult]) -> str:
    """The most serious level among the results ("info" if there are none)."""
    return max((r.level for r in results), key=LEVELS.index, default="info")

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Decisions of the step pages that need no window (no Qt import), so they are unit-tested directly."""

import math

import numpy as np

from aeroflowsim.mesh import Mesh, Mesh1D, Mesh2D
from aeroflowsim.results import Field
from aeroflowsim.runner import max_errors
from aeroflowsim.units import SCALABLE_UNITS, prefixed

AUTO_REBUILD_CELLS = 50_000   # rebuild the mesh after every input change only below this size [cells]

# Key results shown as tiles at the top of the Results step, when a template reports them
# (key_numbers of its Result). Nozzle templates use these names; other templates show only the run
# status there (picking "some" key numbers would mix computed and exact values, e.g. for Sod).
KEY_RESULTS = (("M_exit", "Exit Mach number"), ("p_exit", "Exit pressure"), ("mdot", "Mass flow"),
               ("discharge_coefficient", "Discharge coefficient"),
               ("F_vacuum", "Thrust (vacuum)"), ("F_at_p_back", "Thrust at back pressure"),
               ("Isp_vacuum", "Specific impulse (vacuum)"), ("Isp_quasi1D", "Isp of the ideal quasi-1D nozzle"),
               ("Cl", "Lift coefficient Cl"), ("Cd", "Drag coefficient Cd"), ("Cm", "Moment coefficient Cm"))
LENGTH_UNITS = ("m", "m²")                                     # only these in the full-precision tables


def readable(value, unit, digits=4, units=SCALABLE_UNITS, prefs=None):
    """(value text, unit) with an SI prefix that keeps the number between 1 and 1000, e.g.
    3369.88 Pa -> ("3.37", "kPa"), 7.16e-5 kg/s -> ("71.6", "mg/s"), 2.8e-4 m -> ("280", "µm"),
    6.16e-8 m² -> ("0.06158", "mm²"). digits = significant digits; units = which units may be scaled
    (other values keep their SI unit). Never changes a value, only how it is written.
    prefs: the user's UnitPreferences (aeroflowsim/units.py): numbers of a quantity that has a chosen
    unit (length, pressure, temperature, mass flow, force, area, velocity) are shown in that unit."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value), unit
    value = float(value)
    if prefs is not None and prefs.unit_for(unit) is not None and math.isfinite(value):
        shown, name = prefs.display(value, unit)
        return f"{shown:.{digits}g}", name
    return prefixed(value, unit, digits, units)


def key_result_tiles(result, prefs=None):
    """[(title, value text, unit)] for the summary card: the nozzle key results the template reports
    (an empty list for other templates; their numbers are in the Key numbers table)."""
    numbers = result.key_numbers
    return [(title, *readable(*numbers[key], prefs=prefs)) for key, title in KEY_RESULTS if key in numbers]


def history_extras(result) -> dict:
    """The per-equation residuals and monitors of a finished 2D result, as residual_figure() wants them
    (an empty dict for 1D results)."""
    series = getattr(result, "series", None) or {}
    names = [k for k in series if k.startswith("residual_")]
    if not names:
        return {}
    eq = np.column_stack([series[k] for k in names])
    monitors = {k[len("monitor_"):]: series[k] for k in series if k.startswith("monitor_")}
    return {"equation_residuals": eq, "equations": [k[len("residual_"):] for k in names], "monitors": monitors}


def display_field(field, prefs=None):
    """The Field with its values in the user's unit for its quantity (a copy; the SI field is unchanged)."""
    if prefs is None or prefs.unit_for(field.unit) is None:
        return field
    values, unit = prefs.display(field.values, field.unit)
    return Field(values=np.asarray(values), unit=unit, label=field.label)


def run_status_text(result, run_s=None):
    """One line about the run, e.g. 'Converged after 44,600 iterations in 14.2 s'."""
    info = getattr(result, "info", None) or {}
    state = "Converged" if result.converged else "NOT converged"
    if info.get("status") == "diverged":
        state = "DIVERGED (the last good state is shown)"
    text = f"{state} after {result.iterations:,} iterations"
    return text + (f" in {run_s:.3g} s" if run_s is not None else "")


def cell_value_rows(result, mesh, cell, prefs=None):
    """[(quantity, value text, unit)] of every field in one cell of a 2D result (Properties panel)."""
    c = mesh.cell_centres[cell]
    rows = [("centre x", *readable(c[0], "m", 6, prefs=prefs)), ("centre y", *readable(c[1], "m", 6, prefs=prefs))]
    rows += [(f.label, *readable(float(f.values[cell]), f.unit, 6, prefs=prefs)) for f in result.fields.values()]
    return rows


def flow_plots(result) -> list:
    """Names of the plots under a 2D field view, for what the result holds."""
    series = getattr(result, "series", None) or {}
    plots = []
    if "wall_p_over_p0" in series:
        plots.append("Wall pressure p/p0 along x")
    if "wall_Cp" in series:
        plots.append("Pressure coefficient Cp along the wall")
    if any(k.startswith("residual_") for k in series):
        plots.append("Convergence history")
    return plots


def estimated_cells(case, params):
    """The case's own quick cell-count estimate, or None if it has none (or cannot tell)."""
    if not hasattr(case, "estimated_cells"):
        return None
    try:
        return int(case.estimated_cells(params))
    except ValueError:
        return None


def auto_rebuild(estimate) -> bool:
    """True if a mesh of about `estimate` cells may be rebuilt automatically after an input change."""
    return estimate is None or estimate <= AUTO_REBUILD_CELLS


def progress_fraction(params, iteration, residual):
    """Rough 0..1 progress of a run: the further of 'iterations used' and 'orders of magnitude converged'."""
    fraction = 0.0
    if params.get("max_iter"):
        fraction = iteration / params["max_iter"]
    tol = params.get("tol")
    if tol and 0.0 < tol < 1.0 and residual > 0.0:
        fraction = max(fraction, math.log10(residual) / math.log10(tol))
    return min(max(fraction, 0.0), 1.0)


def available_views(result, mesh):
    """The colour-picture views a result supports, in the order offered."""
    views = []
    if isinstance(mesh, Mesh1D):
        views.append("Shape view")      # every 1D result (constant height if no shape)
    if result.snapshots is not None:
        views.append("x-t diagram")     # unsteady cases that stored snapshots
    if isinstance(mesh, Mesh2D):
        views.append("2D contour")
    return views


def key_number_rows(result, reference, run_s=None, prefs=None):
    """[(quantity, value text, unit)] for the Key numbers table (same rows as the old GUI)."""
    rows = [("converged", "yes" if result.converged else "no", ""),
            ("iterations", f"{result.iterations:,}", "-"),
            ("final residual", f"{result.residuals[-1]:.3e}" if len(result.residuals) else "-", "-")]
    if run_s is not None:
        rows.append(("run time", f"{run_s:.3g}", "s"))
    rows += [(name, *readable(value, unit, 6, LENGTH_UNITS, prefs)) for name, (value, unit) in result.key_numbers.items()]
    for name, (err, unit) in max_errors(result, reference).items():       # a difference: no offset (K = degC)
        shown = prefs.unit_for(unit) if prefs is not None else None
        if shown is not None:
            err, unit = err * shown.divide / shown.scale, shown.name
        rows.append((f"max |{name} − {name}_exact|", f"{err:.3e}", unit))
    return rows


def mesh_summary_rows(mesh, quality, prefs=None):
    """[(label, value text)] summarising a face-based mesh; quality = mesh_quality.quality_summary(mesh);
    lengths and areas in the user's units (prefs)."""
    rows = [("cells", f"{mesh.n_cells:,}"), ("faces", f"{mesh.n_faces:,}"), ("nodes", f"{mesh.n_nodes:,}"),
            ("memory", f"{mesh.memory_bytes() / 1e6:.3g} MB"),
            ("smallest cell", " ".join(readable(quality["min_cell_size"], "m", prefs=prefs))),
            ("max aspect ratio", f"{quality['max_aspect_ratio']:.3g}"),
            ("max non-orthogonality", f"{quality['max_non_orthogonality']:.3g}°"),
            ("max volume ratio", f"{quality['max_volume_ratio']:.3g}"),
            ("smallest angle", f"{quality['min_angle']:.3g}°"),
            ("max skewness", f"{quality['max_skewness']:.3g}")]
    for key in ("reference_length", "reference_area"):
        if key in mesh.info:
            unit = "m" if key == "reference_length" else "m²"
            rows.append((key.replace("_", " "), " ".join(readable(mesh.info[key], unit, prefs=prefs))))
    return rows


def mesh_1d_rows(mesh, prefs=None):
    rows = [("nodes", f"{mesh.n_nodes:,}"), ("cells", f"{mesh.n_cells:,}")]
    if len(mesh.x) > 1:
        rows += [("smallest spacing", " ".join(readable(mesh.dx.min(), "m", prefs=prefs))),
                 ("largest spacing", " ".join(readable(mesh.dx.max(), "m", prefs=prefs)))]
    return rows


def is_face_mesh(mesh) -> bool:
    return isinstance(mesh, Mesh)

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Decisions of the step pages that need no window (no Qt import), so they are unit-tested directly."""

import math

from aeroflowsim.mesh import Mesh, Mesh1D, Mesh2D
from aeroflowsim.runner import max_errors

AUTO_REBUILD_CELLS = 50_000   # rebuild the mesh after every input change only below this size [cells]


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


def key_number_rows(result, reference, run_s=None):
    """[(quantity, value text, unit)] for the Key numbers table (same rows as the old GUI)."""
    rows = [("converged", "yes" if result.converged else "no", ""),
            ("iterations", f"{result.iterations:,}", "-"),
            ("final residual", f"{result.residuals[-1]:.3e}" if len(result.residuals) else "-", "-")]
    if run_s is not None:
        rows.append(("run time", f"{run_s:.3g}", "s"))
    rows += [(name, f"{value:.6g}", unit) for name, (value, unit) in result.key_numbers.items()]
    rows += [(f"max |{name} − {name}_exact|", f"{err:.3e}", unit)
             for name, (err, unit) in max_errors(result, reference).items()]
    return rows


def mesh_summary_rows(mesh, quality):
    """[(label, value text)] summarising a face-based mesh; quality = mesh_quality.quality_summary(mesh)."""
    rows = [("cells", f"{mesh.n_cells:,}"), ("faces", f"{mesh.n_faces:,}"), ("nodes", f"{mesh.n_nodes:,}"),
            ("memory", f"{mesh.memory_bytes() / 1e6:.3g} MB"),
            ("smallest cell", f"{quality['min_cell_size'] * 1e6:.4g} µm"),
            ("max aspect ratio", f"{quality['max_aspect_ratio']:.3g}"),
            ("max non-orthogonality", f"{quality['max_non_orthogonality']:.3g}°"),
            ("max volume ratio", f"{quality['max_volume_ratio']:.3g}"),
            ("smallest angle", f"{quality['min_angle']:.3g}°"),
            ("max skewness", f"{quality['max_skewness']:.3g}")]
    for key in ("reference_length", "reference_area"):
        if key in mesh.info:
            unit = "m" if key == "reference_length" else "m²"
            rows.append((key.replace("_", " "), f"{mesh.info[key]:.4g} {unit}"))
    return rows


def mesh_1d_rows(mesh):
    rows = [("nodes", f"{mesh.n_nodes:,}"), ("cells", f"{mesh.n_cells:,}")]
    if len(mesh.x) > 1:
        rows += [("smallest spacing", f"{mesh.dx.min():.4g} m"), ("largest spacing", f"{mesh.dx.max():.4g} m")]
    return rows


def is_face_mesh(mesh) -> bool:
    return isinstance(mesh, Mesh)

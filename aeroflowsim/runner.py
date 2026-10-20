# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Output files of a run: CSV tables, a YAML summary and PNG plots.

save_outputs() writes everything for one run (called by aeroflowsim.run_case when out_dir is given,
e.g. from the command line). The GUI reuses the CSV/PNG writers and max_errors for its downloads.
"""

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files only, never open a window
import matplotlib.pyplot as plt
import numpy as np
import yaml

# Plot colours (numerical, reference, muted grid/axes) and axis style are shared with visualise.py
from aeroflowsim.visualise import (COLOR_MUTED, COLOR_NUMERICAL, COLOR_REFERENCE, figure_png, length_axes,
                                   shape_view, style_axes, xt_diagram)

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"   # default output folder


def save_outputs(out_dir, output) -> Path:
    """Write the files of one run (a RunOutput from aeroflowsim.run_case) into out_dir; return it."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    case, mesh, result, reference = output.case, output.mesh, output.result, output.reference
    errors = max_errors(result, reference)
    save_fields_csv(out_dir / "fields.csv", mesh, result, reference)
    save_residuals_csv(out_dir / "residuals.csv", result)
    save_summary_yaml(out_dir / "summary.yaml", case.name, case, case.parameters(), output.params,
                      result, errors, output.checks)
    plot_fields(out_dir / "fields.png", case, mesh, result, reference)
    plot_residuals(out_dir / "residuals.png", case, result)
    if result.snapshots is not None:
        # Unsteady case: x-t diagram of the first field, with the exact lines (if any) on top.
        save_xt_diagram(out_dir, mesh, result, output.reference_lines)
    if result.shape is not None:
        # Duct / nozzle case: the first field drawn inside the wall outline.
        save_shape_view(out_dir, mesh, result)
    return out_dir


def max_errors(result, reference):
    """Largest absolute difference between numerical and reference fields: {key: (error, unit)}."""
    if not reference:
        return {}
    errors = {}
    for key, ref in reference.items():
        if key in result.fields:
            err = float(np.max(np.abs(result.fields[key].values - ref.values)))
            errors[key] = (err, ref.unit)
    return errors


def save_fields_csv(path, mesh, result, reference):
    """Write x and every field (and reference field) as columns of a CSV file.

    path may be a file name or an open text buffer (e.g. io.StringIO, used by the GUI download).
    The x column holds the nodes or the cell centres, whichever the fields are stored on.
    """
    first = next(iter(result.fields.values()))
    columns = [mesh.positions(len(first.values))]
    header = ["x_m"]
    for key, f in result.fields.items():
        columns.append(f.values)
        header.append(f"{key}_{f.unit}")
    for key, f in (reference or {}).items():
        columns.append(f.values)
        header.append(f"{key}_exact_{f.unit}")
    np.savetxt(path, np.column_stack(columns), delimiter=",", header=",".join(header), comments="")


def fields_csv_text(mesh, result, reference) -> str:
    """Same content as save_fields_csv, returned as text instead of written to disk."""
    buffer = io.StringIO()
    save_fields_csv(buffer, mesh, result, reference)
    return buffer.getvalue()


def save_residuals_csv(path, result):
    """Write the residual history: iteration, residual."""
    iterations = np.arange(1, len(result.residuals) + 1)
    np.savetxt(path, np.column_stack([iterations, result.residuals]), delimiter=",",
               header="iteration,residual", comments="", fmt=["%d", "%.6e"])


def save_summary_yaml(path, name, case, param_list, values, result, errors, checks=()):
    """Write inputs, convergence info, key numbers, errors and validity checks to a readable YAML file."""
    summary = {
        "case": name,
        "description": case.description,
        "parameters": {p.name: {"value": values[p.name], "unit": p.unit, "label": p.label}
                       for p in param_list},
        "converged": bool(result.converged),
        "iterations": int(result.iterations),
        "final_residual": float(result.residuals[-1]),
        "key_numbers": {k: {"value": float(v), "unit": u} for k, (v, u) in result.key_numbers.items()},
        "max_error_vs_reference": {k: {"value": e, "unit": u} for k, (e, u) in errors.items()},
        "checks": [c.as_dict() for c in checks],
    }
    with open(path, "w", encoding="utf-8") as file:
        yaml.safe_dump(summary, file, sort_keys=False, allow_unicode=True)


def save_xt_diagram(out_dir, mesh, result, lines):
    """Save the x-t diagram of the first field as xt_<field>.png; return the file path."""
    key, f = next(iter(result.snapshots.fields.items()))
    x = mesh.positions(f.values.shape[1])  # nodes or cell centres [m]
    fig = xt_diagram(x, result.snapshots.times, f.values, f.label, f.unit, lines=lines)
    path = Path(out_dir) / f"xt_{key}.png"
    path.write_bytes(figure_png(fig))
    return path


def save_shape_view(out_dir, mesh, result):
    """Save the shape view (wall outline coloured by the first field) as shape_<field>.png."""
    key, f = next(iter(result.fields.items()))
    x = mesh.positions(len(f.values))      # [m]
    fig = shape_view(x, result.shape.radius_at(x), f.values, f.label, f.unit, note=result.shape_note)
    path = Path(out_dir) / f"shape_{key}.png"
    path.write_bytes(figure_png(fig))
    return path


def plot_fields(path, case, mesh, result, reference, keys=None):
    """One plot per field: numerical solution (line + dots) and reference (dashed line).

    keys: list of field names to plot (default: all fields).
    path may be a file name or an open binary buffer (e.g. io.BytesIO, used by the GUI download).
    """
    keys = list(result.fields) if keys is None else list(keys)
    n = len(keys)
    fig, axes = plt.subplots(n, 1, figsize=(7, 3.5 * n), squeeze=False)
    for ax, key in zip(axes[:, 0], keys):
        f = result.fields[key]
        x = mesh.positions(len(f.values))  # nodes or cell centres [m]
        ax.plot(x, f.values, color=COLOR_NUMERICAL, linewidth=2, marker="o",
                markersize=4, label="numerical")
        if reference and key in reference:
            ax.plot(x, reference[key].values, color=COLOR_REFERENCE, linewidth=2,
                    linestyle="--", label="exact")
            ax.legend(frameon=False)
        length_axes(ax, x[-1] - x[0], "x")
        ax.set_ylabel(f"{f.label} [{f.unit}]")
        ax.set_title(f"{case.title}: {f.label}")
        style_axes(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=120, format="png")
    plt.close(fig)


def plot_residuals(path, case, result):
    """Residual history on a log scale."""
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.semilogy(np.arange(1, len(result.residuals) + 1), result.residuals,
                color=COLOR_NUMERICAL, linewidth=2)
    ax.set_xlabel("iteration [-]")
    ax.set_ylabel("normalised residual [-]")
    ax.set_title(f"{case.title}: convergence history")
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)

"""Run one case from start to finish and save the results to disk.

Used by run_case.py (command line); the GUI reuses the CSV/PNG writers and max_errors.
Steps: load case -> parameters -> mesh -> solve -> reference -> save CSV, YAML and PNG.
"""

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files only, never open a window
import matplotlib.pyplot as plt
import numpy as np
import yaml

from core.case_template import get_reference, get_reference_lines
from core.discovery import CASES_DIR, load_case
from core.parameters import defaults, validate
# Plot colours (numerical, reference, muted grid/axes) and axis style are shared with visualise.py
from core.visualise import (COLOR_MUTED, COLOR_NUMERICAL, COLOR_REFERENCE, figure_png,
                            shape_view, style_axes, xt_diagram)

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def run_case(name, params=None, out_dir=None, cases_dir=CASES_DIR, print_every=1000):
    """Run case `name` and save everything to out_dir (default results/<name>/).

    params: dict of parameter values; missing ones take their default value.
    Returns (result, reference, out_dir).
    """
    case = load_case(name, cases_dir)
    param_list = case.parameters()
    values = defaults(param_list)
    values.update(params or {})
    values = validate(param_list, values)

    print(f"Case: {name} - {case.NAME}")
    for p in param_list:
        value = values[p.name]
        text = f"{value:>12g}" if p.kind == "number" else f"{value}"
        print(f"  {p.label:<35} {text} {p.unit}")

    mesh = case.build_mesh(values)
    print(f"Mesh: {mesh.n_nodes} nodes")

    def progress(iteration, residual):
        """Print the convergence status every `print_every` iterations."""
        if iteration == 1 or iteration % print_every == 0:
            print(f"  iteration {iteration:>7d}   residual {residual:.3e}")

    result = case.run(values, mesh, progress)
    reference = get_reference(case, values, mesh)

    status = "converged" if result.converged else "NOT converged"
    print(f"Finished: {status} after {result.iterations} iterations, "
          f"final residual {result.residuals[-1]:.3e}")

    out_dir = Path(out_dir) if out_dir else RESULTS_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    errors = max_errors(result, reference)
    save_fields_csv(out_dir / "fields.csv", mesh, result, reference)
    save_residuals_csv(out_dir / "residuals.csv", result)
    save_summary_yaml(out_dir / "summary.yaml", name, case, param_list, values, result, errors)
    plot_fields(out_dir / "fields.png", case, mesh, result, reference)
    plot_residuals(out_dir / "residuals.png", case, result)
    if result.snapshots is not None:
        # Unsteady case: x-t diagram of the first field, with the exact lines (if any) on top.
        save_xt_diagram(out_dir, mesh, result, get_reference_lines(case, values, mesh))
    if result.shape is not None:
        # Duct / nozzle case: the first field drawn inside the wall outline.
        save_shape_view(out_dir, mesh, result)

    for key, (value, unit) in result.key_numbers.items():
        print(f"  {key:<12} = {value:.6g} {unit}")
    for key, (value, unit) in errors.items():
        print(f"  max |{key} - {key}_exact| = {value:.3e} {unit}")
    print(f"Results saved to {out_dir}")
    return result, reference, out_dir


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


def save_summary_yaml(path, name, case, param_list, values, result, errors):
    """Write inputs, convergence info, key numbers and errors to a readable YAML file."""
    summary = {
        "case": name,
        "description": case.DESCRIPTION,
        "parameters": {p.name: {"value": values[p.name], "unit": p.unit, "label": p.label}
                       for p in param_list},
        "converged": bool(result.converged),
        "iterations": int(result.iterations),
        "final_residual": float(result.residuals[-1]),
        "key_numbers": {k: {"value": float(v), "unit": u} for k, (v, u) in result.key_numbers.items()},
        "max_error_vs_reference": {k: {"value": e, "unit": u} for k, (e, u) in errors.items()},
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
        ax.set_xlabel("x [m]")
        ax.set_ylabel(f"{f.label} [{f.unit}]")
        ax.set_title(f"{case.NAME}: {f.label}")
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
    ax.set_title(f"{case.NAME}: convergence history")
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)

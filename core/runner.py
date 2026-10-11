"""Run one case from start to finish and save the results to disk.

Used by run_case.py (command line) now, and reusable by the GUI later.
Steps: load case -> parameters -> mesh -> solve -> reference -> save CSV, YAML and PNG.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files only, never open a window
import matplotlib.pyplot as plt
import numpy as np
import yaml

from core.case_template import get_reference
from core.discovery import CASES_DIR, load_case
from core.parameters import defaults, validate

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

# Plot colours: numerical solution, reference solution, grid/axes (muted)
COLOR_NUMERICAL = "#2a78d6"
COLOR_REFERENCE = "#eb6834"
COLOR_MUTED = "#898781"


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
        print(f"  {p.label:<35} {values[p.name]:>12g} {p.unit}")

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
    """Write x and every field (and reference field) as columns of a CSV file."""
    columns = [mesh.x]
    header = ["x_m"]
    for key, f in result.fields.items():
        columns.append(f.values)
        header.append(f"{key}_{f.unit}")
    for key, f in (reference or {}).items():
        columns.append(f.values)
        header.append(f"{key}_exact_{f.unit}")
    np.savetxt(path, np.column_stack(columns), delimiter=",", header=",".join(header), comments="")


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


def _style_axes(ax):
    """Light grid and muted axes so the data stands out."""
    ax.grid(True, color=COLOR_MUTED, alpha=0.3, linewidth=0.5)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(COLOR_MUTED)


def plot_fields(path, case, mesh, result, reference):
    """One plot per field: numerical solution (line + dots) and reference (dashed line)."""
    n = len(result.fields)
    fig, axes = plt.subplots(n, 1, figsize=(7, 3.5 * n), squeeze=False)
    for ax, (key, f) in zip(axes[:, 0], result.fields.items()):
        ax.plot(mesh.x, f.values, color=COLOR_NUMERICAL, linewidth=2, marker="o",
                markersize=4, label="numerical")
        if reference and key in reference:
            ax.plot(mesh.x, reference[key].values, color=COLOR_REFERENCE, linewidth=2,
                    linestyle="--", label="exact")
            ax.legend(frameon=False)
        ax.set_xlabel("x [m]")
        ax.set_ylabel(f"{f.label} [{f.unit}]")
        ax.set_title(f"{case.NAME}: {f.label}")
        _style_axes(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_residuals(path, case, result):
    """Residual history on a log scale."""
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.semilogy(np.arange(1, len(result.residuals) + 1), result.residuals,
                color=COLOR_NUMERICAL, linewidth=2)
    ax.set_xlabel("iteration [-]")
    ax.set_ylabel("normalised residual [-]")
    ax.set_title(f"{case.NAME}: convergence history")
    _style_axes(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)

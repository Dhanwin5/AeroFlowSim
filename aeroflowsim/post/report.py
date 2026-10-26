# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Automatic report of a project: one self-contained HTML file (pictures embedded as base64, no external links,
privacy rule 12) and a PDF made with matplotlib (PdfPages: text pages with tables, and the figures). No Qt.

Sections: title (project, template, date, version, fingerprints), geometry / mesh picture, mesh statistics and
quality, boundary conditions, gas and its sources, numerics, convergence history, key numbers and report
definitions, flux balance, validity checks, contour pictures (Mach, pressure, saved scenes), wall plots and saved
XY plots, comparison with the reference (quasi-1D for nozzles), snapshots, how to reproduce.
Numbers are in the user's display units when the GUI passes them (prefs), SI from the command line; each page says
which.
"""

import base64
import datetime
import html
import io
import textwrap
from pathlib import Path

import numpy as np

from aeroflowsim import __version__
from aeroflowsim.units import prefixed

SECTIONS = ("Project", "Geometry and mesh", "Boundary conditions", "Gas", "Numerics", "Convergence",
            "Key numbers", "Report definitions", "Flux balance", "Validity checks", "Flow pictures", "Plots",
            "Comparison with the reference", "Snapshots", "How to reproduce")


def _value(v, unit, prefs):
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not np.isfinite(v):
        return str(v), unit
    if prefs is not None and prefs.unit_for(unit) is not None:
        shown, name = prefs.display(float(v), unit)
        return f"{shown:.5g}", name
    return prefixed(float(v), unit, 5)


class _Doc:
    """Collects sections as (title, blocks); blocks are ("text", str), ("table", header, rows), ("figure", Figure)."""

    def __init__(self):
        self.sections = []

    def section(self, title):
        self.sections.append((title, []))

    def text(self, s):
        self.sections[-1][1].append(("text", s))

    def table(self, header, rows):
        self.sections[-1][1].append(("table", list(header), [[str(c) for c in r] for r in rows]))

    def figure(self, fig):
        self.sections[-1][1].append(("figure", fig))


def build(project, prefs=None, snapshots=True):
    """The report content (_Doc) of a project with a result."""
    from aeroflowsim.checks import CheckResult  # noqa: F401
    from aeroflowsim.mesh_quality import quality_summary
    from aeroflowsim.post.definitions import definitions_from, evaluate_definitions
    from aeroflowsim.post.fields import FieldError
    from aeroflowsim.post.integrals import flux_balance
    from aeroflowsim.post.pictures import field_picture, mesh_picture
    from aeroflowsim.post.solution import Solution
    from aeroflowsim.post.surfaces import surfaces_from

    payload = project.load_results()
    if payload is None:
        raise ValueError(f"The project '{project.name}' has no result yet: run it first.")
    result = payload["result"]
    mesh = project.load_mesh()
    two_d = mesh is not None and hasattr(mesh, "patches") and "rho" in result.fields and \
        len(result.fields["rho"].values) == mesh.n_cells
    sol = Solution.from_project(project) if two_d else None
    units_text = "the display units chosen in the GUI (View > Units)" if prefs is not None else "SI units"
    convert = (lambda v, u: (np.asarray(prefs.unit_for(u).from_si(v)) if prefs.unit_for(u) else v,
                             prefs.unit_for(u).name if prefs.unit_for(u) else u)) if prefs is not None else None
    d = _Doc()

    d.section("Project")
    run = project.steps.get("run") or {}
    meshrec = project.steps.get("mesh") or {}
    d.table(["Item", "Value"], [
        ("Project", project.name), ("Folder", project.folder.name), ("Template", f"{project.case.title} "
                                                                          f"({Path(project.case.folder).name})"),
        ("Report date", datetime.date.today().isoformat()), ("AeroFlowSim version", __version__),
        ("Run finished", run.get("time", "")), ("Run status", run.get("status", "converged" if result.converged else "")),
        ("Iterations", f"{result.iterations:,}"), ("Mesh fingerprint", str(meshrec.get("fingerprint", ""))[:16]),
        ("Run fingerprint", str(run.get("fingerprint", ""))[:16]),
        ("Results up to date", "yes" if project.status("run") == "ok" else "NO (inputs changed since the run)")])
    d.text(f"All numbers are in {units_text}.")

    d.section("Geometry and mesh")
    if two_d:
        d.figure(mesh_picture(mesh))
        q = quality_summary(mesh)
        rows = [("Cells", f"{mesh.n_cells:,}"), ("Nodes", f"{mesh.n_nodes:,}"), ("Faces", f"{mesh.n_faces:,}"),
                ("Axisymmetric", "yes" if mesh.axisymmetric else "no")]
        for key, unit in (("min_cell_size", "m"), ("max_aspect_ratio", "-"), ("max_non_orthogonality", "deg"),
                          ("max_volume_ratio", "-"), ("min_angle", "deg"), ("max_skewness", "-")):
            rows.append((key.replace("_", " "), " ".join(_value(q[key], unit, prefs))))
        d.table(["Mesh", "Value"], rows)
    else:
        d.text("One-dimensional mesh.")

    d.section("Boundary conditions")
    bcs = result.info.get("boundaries") or {}
    if bcs:
        rows = []
        for name, bc in bcs.items():
            vals = ", ".join(f"{k} = {v:g}" if isinstance(v, (int, float)) else f"{k}: {v}"
                             for k, v in bc.items() if k != "type")
            rows.append((name, bc["type"].replace("_", " "), vals or "-"))
        d.table(["Boundary", "Type", "Values (SI)"], rows)
    else:
        d.text("This template has no boundary-condition table.")

    d.section("Gas")
    gas_id = payload["params"].get("gas")
    if gas_id:
        try:
            from aeroflowsim.gases.library import gas_data
            g = gas_data(gas_id, base=project.folder)
            d.table(["Property", "Value"], [("Gas", g.name), ("R [J/(kg K)]", f"{g.R:.6g}"),
                                            ("gamma", f"{g.gamma:.6g}" if hasattr(g, "gamma") else "")])
            if g.sources:
                d.table(["Data", "Source"], list(g.sources.items()))
        except Exception as exc:     # noqa: BLE001
            d.text(f"Gas '{gas_id}' (details not available: {exc}).")
    else:
        d.text("No gas input.")

    d.section("Numerics")
    params = payload["params"]
    keys = [p for p in project.case.parameters() if p.group == "Numerics"]
    d.table(["Input", "Value"], [(p.label, f"{params.get(p.name)} {p.unit if p.unit not in ('', '-') else ''}")
                                 for p in keys] or [("-", "-")])

    d.section("Convergence")
    d.figure(_convergence_figure(result))
    d.text(f"Status: {result.info.get('status', 'converged' if result.converged else 'not converged')} after "
           f"{result.iterations:,} iterations; wall-clock time {result.info.get('wall_time_s', 0):.0f} s.")

    d.section("Key numbers")
    d.table(["Quantity", "Value", "Unit"], [(k, *_value(v, u, prefs)) for k, (v, u) in result.key_numbers.items()])

    d.section("Report definitions")
    defs = definitions_from(project.post["report_definitions"])
    if defs and sol is not None:
        vals = evaluate_definitions(sol, defs, surfaces_from(project.post["surfaces"]))
        d.table(["Name", "Definition", "Value", "Unit"],
                [(x.name, x.describe(), *_value(*vals[x.name], prefs)) for x in defs])
    else:
        d.text("No report definitions in this project.")

    d.section("Flux balance")
    if sol is not None:
        try:
            fb = flux_balance(sol)
            d.table(fb["columns"], [(r[0], r[1], *[f"{v:.6g}" for v in r[2:]]) for r in fb["rows"]]
                    + [("Net", "", *[f"{v:.6g}" for v in fb["net"]])])
            d.text(f"Relative imbalance: mass {100 * fb['relative']['mass']:.3g} %, energy "
                   f"{100 * fb['relative']['energy']:.3g} % (SI units, outward positive). {fb['note']}")
        except ValueError as exc:
            d.text(str(exc))
    else:
        d.text("Not available for one-dimensional results.")

    d.section("Validity checks")
    checks = payload.get("checks") or []
    d.table(["Level", "Check", "Message"], [(c.level.upper(), c.name, c.message) for c in checks] or [("-", "-", "-")])

    d.section("Flow pictures")
    if sol is not None:
        mirror = sol.axisymmetric
        for name, cmap in (("M", "turbo"), ("p", "viridis")):
            d.figure(field_picture(sol, name, cmap, mirror=mirror, unit_convert=convert))
        for scene_name, sc in project.post["scenes"].items():
            try:
                d.figure(field_picture(sol, sc.get("field", "M"), sc.get("cmap", "turbo"), mirror=sc.get("mirror", False),
                                       title=f"Scene: {scene_name}", unit_convert=convert))
            except (FieldError, ValueError):
                d.text(f"Scene '{scene_name}' could not be drawn on this result.")
    else:
        d.text("See the field plots in the GUI (one-dimensional result).")

    d.section("Plots")
    fig = _wall_figure(result)
    if fig is not None:
        d.figure(fig)
    if sol is not None and project.post["xy_plots"]:
        from aeroflowsim.post.surfaces import default_surfaces
        from aeroflowsim.post.xy import XYPlot, axis_label, curves, xy_figure
        surfaces = {s.name: s for s in surfaces_from(project.post["surfaces"]) + default_surfaces(sol)}
        for name, data in project.post["xy_plots"].items():
            plot = XYPlot.from_dict(data)
            try:
                c = curves(sol, plot, surfaces)
                d.figure(xy_figure(c, axis_label(sol, plot.x_axis), axis_label(sol, plot.fields[0]), plot.log_x,
                                   plot.log_y, title=name))
            except (ValueError, KeyError, IndexError) as exc:
                d.text(f"XY plot '{name}' could not be drawn: {exc}")

    d.section("Comparison with the reference")
    k = result.key_numbers
    if "Isp_quasi1D" in k and "Isp_vacuum" in k:
        d.table(["Quantity", "2D Euler", "Ideal quasi-1D", "Ratio"],
                [("Vacuum Isp [s]", f"{k['Isp_vacuum'][0]:.4f}", f"{k['Isp_quasi1D'][0]:.4f}",
                  f"{k['Isp_vacuum'][0] / k['Isp_quasi1D'][0]:.4f}"),
                 ("Mass flow [kg/s]", f"{k['mdot'][0]:.5g}", f"{k['mdot_1D'][0]:.5g}",
                  f"{k['discharge_coefficient'][0]:.4f}")])
        d.text("The 2D nozzle loses Isp to the divergence of the exit flow and passes less mass than 1D theory "
               "(curved sonic line); the wall-pressure plot shows the quasi-1D isentropic pressure of the same wall.")
    elif payload.get("reference"):
        d.text("The template's exact or theoretical solution is drawn with the field plots in the GUI.")
    else:
        d.text("This template has no built-in reference; see the validation report for validated cases.")

    d.section("Snapshots")
    from aeroflowsim.post.snapshots import list_snapshots
    snaps = list_snapshots(project)
    if snaps and snapshots and sol is not None:
        from aeroflowsim.post.compare import key_number_table
        rows = []
        for s in snaps:
            try:
                other = Solution.from_project(project, snapshot=s["name"])
                for key, a, b, unit, change in key_number_table(sol, other)[:6]:
                    rows.append((s["name"], key, f"{a:.6g}", f"{b:.6g}", unit, f"{change:+.3f}"))
            except (ValueError, OSError):
                rows.append((s["name"], "(could not be read)", "", "", "", ""))
        d.table(["Snapshot", "Key number", "Current", "Snapshot", "Unit (SI)", "Change %"], rows)
    else:
        d.text("No snapshots.")

    d.section("How to reproduce")
    d.text(f"Open the project folder in AeroFlowSim {__version__} and press Run, or from a command prompt in the "
           "AeroFlowSim folder:")
    d.text(f'python -m aeroflowsim run "{project.folder.name}" --fresh')
    d.text("The project folder holds every input (project.yaml), the geometry files, the mesh and the exact result "
           "(results/run.npz); the fingerprints above identify the mesh and the inputs of the run.")
    d.table(["Input", "Value"], [(name, str(v)[:80]) for name, v in project.values.items()])
    return d


def _convergence_figure(result):
    from matplotlib.figure import Figure
    fig = Figure(figsize=(7, 3.2), dpi=110, layout="constrained")
    ax = fig.add_subplot()
    s = result.series or {}
    names = [k for k in s if k.startswith("residual_")]
    if names:
        for n in names:
            ax.semilogy(np.arange(1, len(s[n]) + 1), np.maximum(s[n], 1e-300), lw=1, label=n[len("residual_"):])
        ax.legend(fontsize=7)
    elif result.residuals:
        ax.semilogy(np.arange(1, len(result.residuals) + 1), np.maximum(result.residuals, 1e-300), lw=1)
    ax.set_xlabel("iteration")
    ax.set_ylabel("normalised residual")
    ax.set_title("Convergence history")
    ax.grid(True, lw=0.4)
    return fig


def _wall_figure(result):
    from matplotlib.figure import Figure
    s = result.series or {}
    if "wall_x" not in s:
        return None
    fig = Figure(figsize=(7, 3.2), dpi=110, layout="constrained")
    ax = fig.add_subplot()
    x = np.asarray(s["wall_x"])
    o = np.argsort(x)
    if "wall_p_over_p0" in s:
        ax.semilogy(x[o], np.asarray(s["wall_p_over_p0"])[o], ".", ms=3, label="2D Euler (wall)")
        ax.set_ylabel("p / p0")
        ax.set_title("Wall pressure")
    else:
        ax.plot(x[o], np.asarray(s["wall_Cp"])[o], ".", ms=3, label="wall")
        ax.invert_yaxis()
        ax.set_ylabel("Cp")
        ax.set_title("Pressure coefficient along the wall")
    ax.set_xlabel("x [m]")
    ax.grid(True, lw=0.4)
    ax.legend(fontsize=7)
    return fig


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor="white")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def html_text(doc, title):
    css = ("body{font-family:Segoe UI,Arial,sans-serif;max-width:960px;margin:2em auto;color:#111}"
           "table{border-collapse:collapse;margin:.6em 0;font-size:13px}td,th{border:1px solid #bbb;padding:3px 8px;"
           "text-align:left}th{background:#eef}h1{font-size:26px}h2{border-bottom:2px solid #ccd;margin-top:1.6em}"
           "img{max-width:100%}nav a{margin-right:.8em}")
    out = [f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
           f"<style>{css}</style></head><body><h1>{html.escape(title)}</h1><nav>"]
    out += [f"<a href='#s{i}'>{html.escape(t)}</a>" for i, (t, _) in enumerate(doc.sections)]
    out.append("</nav>")
    for i, (t, blocks) in enumerate(doc.sections):
        out.append(f"<h2 id='s{i}'>{html.escape(t)}</h2>")
        for b in blocks:
            if b[0] == "text":
                out.append(f"<p>{html.escape(b[1])}</p>")
            elif b[0] == "table":
                out.append("<table><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in b[1]) + "</tr>")
                out += ["<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in b[2]]
                out.append("</table>")
            else:
                out.append(f"<img alt='figure' src='data:image/png;base64,{_png(b[1])}'>")
    out.append(f"<p><small>Made by AeroFlowSim {__version__}.</small></p></body></html>")
    return "\n".join(out)


def write_pdf(doc, path, title):
    """Text pages (tables written as aligned text) and one page per figure, A4 portrait."""
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure
    with PdfPages(path) as pdf:
        lines = [(title, 16, "bold"), ("", 10, "normal")]

        def flush():
            if len(lines) <= 0:
                return
            fig = Figure(figsize=(8.27, 11.69))
            y = 0.96
            for text, size, weight in lines:
                fig.text(0.07, y, text, fontsize=size, weight=weight, family="monospace" if size == 7 else None,
                         va="top")
                y -= (size + 4) / 11.69 / 72
            pdf.savefig(fig)
            lines.clear()

        def add(text, size=9, weight="normal"):
            if sum((s + 4) for _, s, _ in lines) / 72 > 10.6:
                flush()
            lines.append((text, size, weight))

        for t, blocks in doc.sections:
            add("", 6)
            add(t, 13, "bold")
            for b in blocks:
                if b[0] == "text":
                    for w in textwrap.wrap(b[1], 105) or [""]:
                        add(w)
                elif b[0] == "table":
                    widths = [min(max(len(r[i]) for r in [b[1]] + b[2]), 42) for i in range(len(b[1]))]
                    for r in [b[1]] + b[2]:
                        add("  ".join(c[:42].ljust(widths[i]) for i, c in enumerate(r))[:150], 7)
                else:
                    flush()
                    pdf.savefig(b[1])
        flush()
    return path


def write_report(project, out_dir=None, formats=("html", "pdf"), prefs=None):
    """Write the report; returns the paths. Default folder: <project>/results/report/."""
    out = Path(out_dir) if out_dir else project.results_dir / "report"
    out.mkdir(parents=True, exist_ok=True)
    doc = build(project, prefs)
    title = f"AeroFlowSim report: {project.name}"
    paths = []
    stem = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in project.name).strip() or "report"
    if "html" in formats:
        p = out / f"{stem}_report.html"
        p.write_text(html_text(doc, title), encoding="utf-8")
        paths.append(p)
    if "pdf" in formats:
        paths.append(write_pdf(doc, out / f"{stem}_report.pdf", title))
    return paths

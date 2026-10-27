# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Command line:  python -m aeroflowsim <command>

    python -m aeroflowsim list                            show all available cases
    python -m aeroflowsim run cases/quasi1d_nozzle        run a case with its default inputs
    python -m aeroflowsim run cases/quasi1d_nozzle --set p_back=250000 --set n_cells=400
                                                          change some inputs (the others keep their default)
    python -m aeroflowsim run cases/sod_shock_tube --out my_results/sod
                                                          save the files somewhere else
    python -m aeroflowsim run "C:/Users/me/Documents/AeroFlowSim Projects/My Nozzle.afsproj"
                                                          run a project (made in the GUI): its inputs
                                                          are used, mesh and results are saved in it
    python -m aeroflowsim gui                             start the desktop GUI
    python -m aeroflowsim report "My Nozzle.afsproj"      write the HTML and PDF report of a project
    python -m aeroflowsim export "My Nozzle.afsproj" --format tecplot --fields p,M,p0
                                                          export fields (csv, vtu, tecplot), --surface NAME for
                                                          the data along a surface, --definitions for the
                                                          report definitions table
    python -m aeroflowsim snapshot "My Nozzle.afsproj" save baseline
                                                          snapshots: save, list, rename, restore, delete

Results of a case are saved to results/<case_name>/ unless --out is given; results of a project
go into its own results/ folder (and --set changes are saved in the project). The run itself is done by
aeroflowsim.run_case(), the same function the GUI uses, so both give identical numbers.
Exit code: 0 = finished (and converged), 1 = error in the inputs, 2 = finished but not converged.
"""

import argparse
import sys

from aeroflowsim import __version__
from aeroflowsim.discovery import find_cases, load_case
from aeroflowsim.engine import run_case
from aeroflowsim.parameters import defaults, parse_value, validate
from aeroflowsim.checks import run_mesh_checks
from aeroflowsim.project import Project, build_project_mesh, is_project, run_project
from aeroflowsim.runner import RESULTS_DIR, max_errors

LEVEL_MARK = {"info": "OK  ", "warning": "WARN", "error": "FAIL"}


def parse_settings(case, assignments):
    """Turn ["name=value", ...] into {name: value} with the right types for the case's inputs."""
    param_list = {p.name: p for p in case.parameters()}
    values = {}
    for text in assignments:
        name, sep, value = text.partition("=")
        name = name.strip()
        if not sep or name not in param_list:
            raise ValueError(f"--set {text}: use NAME=VALUE with NAME one of {', '.join(param_list)}.")
        try:
            values[name] = parse_value(param_list[name], value.strip())
        except ValueError:
            kind = "true or false" if param_list[name].type == "bool" else "a number"
            raise ValueError(f"--set {text}: '{value}' is not {kind}.") from None
    return values


def print_progress_every(n):
    """A progress callback that prints the residual at iteration 1 and every n iterations."""
    def progress(iteration, residual, info=None):
        if iteration == 1 or iteration % n == 0:
            print(f"  iteration {iteration:>7d}   residual {residual:.3e}", flush=True)
    return progress


def command_list():
    cases, problems = find_cases()
    print("Available cases (run with: python -m aeroflowsim run cases/<name>):")
    for name, case in cases.items():
        print(f"  {name:<20} {case.description}")
    for name, problem in problems.items():
        print(f"  {name:<20} BROKEN: {problem}")
    return 0


def print_inputs(case, params):
    print(f"AeroFlowSim {__version__}")
    print(f"Case: {case.name} - {case.title}")
    for p in case.parameters():
        text = f"{params[p.name]:>12g}" if p.is_number else f"{params[p.name]}"
        print(f"  {p.label:<35} {text} {p.unit}")


def command_run(args):
    if is_project(args.case):
        return command_run_project(args)
    try:
        case = load_case(args.case)
        param_list = case.parameters()
        params = validate(param_list, {**defaults(param_list), **parse_settings(case, args.set)})
    except ValueError as error:
        print(f"Error: {error}")
        return 1

    print_inputs(case, params)
    try:
        out = run_case(case, params, progress=print_progress_every(args.print_every),
                       out_dir=args.out or RESULTS_DIR / case.name)
    except ValueError as error:    # e.g. a bad geometry file, found while building the mesh
        print(f"Error: {error}")
        return 1
    return print_report(out)


def command_run_project(args):
    """Run a project folder: same engine, its own inputs; mesh and results are stored in the project."""
    if args.out:
        print("Error: --out cannot be used with a project (its results go into its results/ folder).")
        return 1
    try:
        project = Project.open(args.case)
        for warning in project.warnings:
            print(f"Note: {warning}")
        for name, value in parse_settings(project.case, args.set).items():
            project.set_value(name, value)
        params = project.params()
        if project.dirty:
            project.save()
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    print(f"Project: {project.folder}")
    print_inputs(project.case, params)
    try:
        if not project.case.has_solver:          # mesh-only template: make the mesh, nothing to solve
            mesh = build_project_mesh(project)
            print(f"Mesh: {mesh.n_cells} cells, saved to {project.mesh_dir}. {project.case.solver_message}")
            for check in run_mesh_checks(project.case, params, mesh):
                print(f"  [{LEVEL_MARK[check.level]}] {check.name}: {check.message}")
            return 0
        if not args.fresh:
            _path, done = project.continuation(project.load_mesh() if project.status("mesh") == "ok" else None)
            if done:
                print(f"Continuing the saved run from iteration {done + 1:,} (use --fresh to start from scratch).")
        out = run_project(project, progress=print_progress_every(args.print_every), fresh=args.fresh)
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    return print_report(out)


def command_gui(project=None):
    """Start the desktop GUI (imported only here, so the command line works without Qt)."""
    try:
        from aeroflowsim.gui.app import main as gui_main
    except ImportError as error:
        print(f"Error: the desktop GUI needs PySide6 and PyVista ({error}). Install with: pip install -e .")
        return 1
    return gui_main(["aeroflowsim"] + ([project] if project else []))


def print_report(out):
    """Print the outcome of a run (key numbers, errors vs reference, validity checks); return the exit code."""
    result = out.result
    status = "converged" if result.converged else "NOT converged"
    print(f"Mesh: {out.mesh.n_nodes} nodes. Finished: {status} after {result.iterations} iterations, "
          f"final residual {result.residuals[-1]:.3e}")
    for key, (value, unit) in result.key_numbers.items():
        print(f"  {key:<20} = {value:.6g} {unit}")
    for key, (value, unit) in max_errors(result, out.reference).items():
        print(f"  max |{key} - {key}_exact| = {value:.3e} {unit}")
    report_values = (getattr(result, "info", None) or {}).get("report_values") or {}
    if report_values:
        print("Report definitions:")
        for key, (value, unit) in report_values.items():
            print(f"  {key:<20} = {value:.6g} {unit}")
    print("Validity checks:")
    for check in out.checks:
        print(f"  [{LEVEL_MARK[check.level]}] {check.name}: {check.message}")
    print(f"Results saved to {out.out_dir}")
    return 0 if result.converged else 2


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m aeroflowsim",
                                     description="AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion.")
    parser.add_argument("--version", action="version", version=f"AeroFlowSim {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="list the available cases")
    run = commands.add_parser("run", help="run a case and save its results")
    run.add_argument("case", help="case folder, e.g. cases/quasi1d_nozzle (or just its name), "
                                  "or a project folder (*.afsproj)")
    run.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                     help="change one input (may be repeated)")
    run.add_argument("--out", default=None, help="output folder (default: results/<case_name>/)")
    run.add_argument("--print-every", type=int, default=1000, metavar="N",
                     help="print the residual every N iterations (default 1000)")
    run.add_argument("--fresh", action="store_true",
                     help="projects: start the run from scratch instead of carrying on from the saved result")
    gui = commands.add_parser("gui", help="start the desktop GUI")
    gui.add_argument("project", nargs="?", default=None, help="project folder to open (optional)")
    report = commands.add_parser("report", help="write the automatic HTML / PDF report of a project")
    report.add_argument("project", help="project folder (*.afsproj)")
    report.add_argument("--out", default=None, help="output folder (default: the project's results/report/)")
    report.add_argument("--format", choices=("html", "pdf", "both"), default="both")
    export = commands.add_parser("export", help="export fields, surface data or report definitions of a project")
    export.add_argument("project", help="project folder (*.afsproj)")
    export.add_argument("--format", choices=("csv", "vtu", "tecplot"), default="csv")
    export.add_argument("--fields", default="rho,u,v,p,T,M,p0,T0,s", help="comma-separated field names")
    export.add_argument("--nodes", action="store_true", help="CSV: node values instead of cell-centre values")
    export.add_argument("--surface", default=None, help="data along this named surface (CSV)")
    export.add_argument("--definitions", action="store_true", help="the report definitions table (CSV)")
    export.add_argument("--snapshot", default=None, help="export a snapshot instead of the current result")
    export.add_argument("--out", default=None, help="output file (default: in the project's results/exports/)")
    snap = commands.add_parser("snapshot", help="save, list, rename, restore or delete solution snapshots")
    snap.add_argument("project", help="project folder (*.afsproj)")
    snap.add_argument("action", choices=("save", "list", "rename", "restore", "delete"))
    snap.add_argument("name", nargs="?", default=None)
    snap.add_argument("new_name", nargs="?", default=None, help="rename: the new name")
    info = commands.add_parser("mesh-info", help="show what a mesh file holds (Gmsh, SU2, CGNS, Fluent): cells, size, boundary names")
    info.add_argument("file", help="mesh file (.msh, .su2, .cgns)")
    convert = commands.add_parser("mesh-convert", help="convert a mesh file to Gmsh (.msh, version 2.2 or 4.1), SU2 or CGNS")
    convert.add_argument("source", help="mesh file to read (.msh, .su2, .cgns)")
    convert.add_argument("target", help="file to write; the ending chooses the format (.msh, .su2, .cgns)")
    convert.add_argument("--unit", default="m", choices=("m", "mm", "cm", "in", "ft"),
                         help="length unit of the source file (written in metres; default m)")
    convert.add_argument("--axisymmetric", action="store_true", help="the mesh is axisymmetric about y = 0")
    convert.add_argument("--map", default="", metavar="NAME:TYPE,...", help="boundary types, e.g. 'outer: farfield, body: wall'")
    convert.add_argument("--gmsh-version", choices=("2.2", "4.1"), default="2.2", help="version of a .msh target (default 2.2)")
    args = parser.parse_args(argv)
    if args.command == "mesh-info":
        return command_mesh_info(args)
    if args.command == "mesh-convert":
        return command_mesh_convert(args)
    if args.command == "list":
        return command_list()
    if args.command == "gui":
        return command_gui(args.project)
    if args.command == "report":
        return command_report(args)
    if args.command == "export":
        return command_export(args)
    if args.command == "snapshot":
        return command_snapshot(args)
    return command_run(args)


def command_mesh_info(args):
    """Print what a mesh file holds: format, cells, size and every boundary name with the type it would get."""
    from aeroflowsim import mesh_io
    try:
        raw = mesh_io.read_mesh_file(args.file)
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    print(f"{raw.source}: {raw.format}, {raw.n_cells} cells, {len(raw.points)} points")
    print(f"  size in the file's unit: {mesh_io.size_text(raw)}")
    for row in mesh_io.tag_table(raw):
        print(f"  boundary '{row['name']}': {row['edges']} edges, type {row['guess'] or '(not guessed: give one)'}")
    return 0


def command_mesh_convert(args):
    """Read a mesh file, check it, write it in another format (the boundary names stay)."""
    from pathlib import Path
    from aeroflowsim import mesh_io
    target = Path(args.target)
    writers = {".msh": lambda m, p: mesh_io.write_gmsh(m, p, args.gmsh_version), ".su2": mesh_io.write_su2,
               ".cgns": mesh_io.write_cgns}
    try:
        if target.suffix.lower() not in writers:
            raise ValueError(f"'{target.suffix}' is not a format AeroFlowSim writes. Use .msh, .su2 or .cgns.")
        mesh = mesh_io.import_mesh(args.source, args.unit, args.axisymmetric, mesh_io.parse_tag_map(args.map))
        writers[target.suffix.lower()](mesh, target)
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    print(f"{mesh.n_cells} cells, patches {', '.join(f'{p.name} ({p.type})' for p in mesh.patches)} written to {target}")
    return 0


def _open_project(path):
    if not is_project(path):
        raise ValueError(f"{path} is not an AeroFlowSim project folder (*.afsproj with a project.yaml).")
    return Project.open(path)


def command_report(args):
    """Write the report (no Qt; SI units, stated on every page)."""
    from aeroflowsim.post.report import write_report
    try:
        project = _open_project(args.project)
        paths = write_report(project, args.out, formats=("html", "pdf") if args.format == "both" else (args.format,))
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    for p in paths:
        print(f"Report written: {p}")
    return 0


def command_export(args):
    from pathlib import Path

    from aeroflowsim.post import export
    from aeroflowsim.post.definitions import definitions_from, evaluate_definitions
    from aeroflowsim.post.solution import Solution
    from aeroflowsim.post.surfaces import default_surfaces, surfaces_from
    try:
        project = _open_project(args.project)
        sol = Solution.from_project(project, snapshot=args.snapshot)
        fields = tuple(f.strip() for f in args.fields.split(",") if f.strip())
        folder = project.results_dir / "exports"
        name = (args.snapshot or "current").replace(" ", "_")
        if args.definitions:
            defs = definitions_from(project.post["report_definitions"])
            if not defs:
                raise ValueError("The project has no report definitions.")
            path = export.definitions_csv(evaluate_definitions(sol, defs, surfaces_from(project.post["surfaces"])),
                                          Path(args.out or folder / f"report_definitions_{name}.csv"), defs)
        elif args.surface:
            surfaces = {s.name: s for s in surfaces_from(project.post["surfaces"]) + default_surfaces(sol)}
            if args.surface not in surfaces:
                raise ValueError(f"There is no surface '{args.surface}'; surfaces: {', '.join(surfaces)}.")
            path = export.surface_csv(sol, surfaces[args.surface], Path(args.out or folder / f"surface_{args.surface}_{name}.csv"),
                                      fields)
        elif args.format == "vtu":
            path = export.fields_vtu(sol, Path(args.out or folder / f"fields_{name}.vtu"), fields)
        elif args.format == "tecplot":
            path = export.fields_tecplot(sol, Path(args.out or folder / f"fields_{name}.dat"), fields)
        else:
            location = "node" if args.nodes else "cell"
            path = export.fields_csv(sol, Path(args.out or folder / f"fields_{location}_{name}.csv"), fields, location)
    except (ValueError, KeyError) as error:
        print(f"Error: {error}")
        return 1
    print(f"Exported: {path}")
    return 0


def command_snapshot(args):
    from aeroflowsim.post import snapshots
    try:
        project = _open_project(args.project)
        if args.action == "list":
            items = snapshots.list_snapshots(project)
            if not items:
                print("No snapshots.")
            for s in items:
                print(f"  {s['name']:<24} saved {s['saved']}  iterations {s['iterations']}  {snapshots.size_text(s['size'])}")
            return 0
        if not args.name:
            raise ValueError(f"snapshot {args.action} needs a NAME.")
        if args.action == "save":
            snapshots.save_snapshot(project, args.name)
            print(f"Snapshot '{args.name}' saved.")
        elif args.action == "rename":
            if not args.new_name:
                raise ValueError("snapshot rename needs the old and the new name.")
            snapshots.rename_snapshot(project, args.name, args.new_name)
            print(f"Snapshot '{args.name}' renamed to '{args.new_name}'.")
        elif args.action == "restore":
            snapshots.restore_snapshot(project, args.name)
            print(f"Snapshot '{args.name}' is the current result again.")
        else:
            snapshots.delete_snapshot(project, args.name)
            print(f"Snapshot '{args.name}' deleted.")
        warning = snapshots.size_warning(project)
        if warning:
            print(f"Note: {warning}")
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

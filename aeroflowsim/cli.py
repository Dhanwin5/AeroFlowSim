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
    def progress(iteration, residual):
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
        out = run_project(project, progress=print_progress_every(args.print_every))
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    return print_report(out)


def command_gui():
    """Start the desktop GUI (imported only here, so the command line works without Qt)."""
    try:
        from aeroflowsim.gui.app import main as gui_main
    except ImportError as error:
        print(f"Error: the desktop GUI needs PySide6 and PyVista ({error}). Install with: pip install -e .")
        return 1
    return gui_main()


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
    commands.add_parser("gui", help="start the desktop GUI")
    args = parser.parse_args(argv)
    if args.command == "list":
        return command_list()
    if args.command == "gui":
        return command_gui()
    return command_run(args)


if __name__ == "__main__":
    sys.exit(main())

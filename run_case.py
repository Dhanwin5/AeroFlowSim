"""Command-line runner.

Usage:
    python run_case.py <case_name>     run a case with default settings, save to results/<case_name>/
    python run_case.py <case_name> --set p_back=250000 --set "geometry_source=Custom profile (CSV)"
                                       change some inputs (the others keep their default value)
    python run_case.py --list          show all available cases
"""

import argparse
import sys

from core.discovery import find_cases, load_case
from core.parameters import parse_value
from core.runner import run_case


def parse_settings(case_name, assignments):
    """Turn ["name=value", ...] into {name: value} with the right types for the case's inputs."""
    param_list = {p.name: p for p in load_case(case_name).parameters()}
    values = {}
    for text in assignments:
        name, sep, value = text.partition("=")
        name = name.strip()
        if not sep or name not in param_list:
            raise ValueError(f"--set {text}: use NAME=VALUE with NAME one of {', '.join(param_list)}.")
        try:
            values[name] = parse_value(param_list[name], value.strip())
        except ValueError:
            raise ValueError(f"--set {text}: '{value}' is not a number.") from None
    return values


def main():
    parser = argparse.ArgumentParser(description="Run a Flow Sim case (default settings unless --set).")
    parser.add_argument("case_name", nargs="?", help="folder name of the case in cases/")
    parser.add_argument("--list", action="store_true", help="list the available cases and exit")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                        help="change one input (may be repeated)")
    args = parser.parse_args()

    if args.list or not args.case_name:
        cases, problems = find_cases()
        print("Available cases:")
        for name, case in cases.items():
            print(f"  {name:<20} {case.DESCRIPTION}")
        for name, problem in problems.items():
            print(f"  {name:<20} BROKEN: {problem}")
        return 0

    try:
        result, _, _ = run_case(args.case_name, parse_settings(args.case_name, args.set))
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    return 0 if result.converged else 2


if __name__ == "__main__":
    sys.exit(main())

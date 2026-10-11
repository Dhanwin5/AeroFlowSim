"""Command-line runner.

Usage:
    python run_case.py <case_name>     run a case with default settings, save to results/<case_name>/
    python run_case.py --list          show all available cases
"""

import argparse
import sys

from core.discovery import find_cases
from core.runner import run_case


def main():
    parser = argparse.ArgumentParser(description="Run a nozzle-cfd case with default settings.")
    parser.add_argument("case_name", nargs="?", help="folder name of the case in cases/")
    parser.add_argument("--list", action="store_true", help="list the available cases and exit")
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
        result, _, _ = run_case(args.case_name)
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    return 0 if result.converged else 2


if __name__ == "__main__":
    sys.exit(main())

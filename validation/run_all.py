# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run every validation case and write validation/report.md.

    python validation/run_all.py                 full set (all meshes; about 3 hours)
    python validation/run_all.py --quick         quick set (coarse meshes; under 10 minutes)
    python validation/run_all.py wedge cone      only the folders whose names contain these words

Prints one line per compared quantity and ends with exit code 0 if everything passes, 1 if not.
"""

import os
import sys
from pathlib import Path

# Started as a script, Python only knows this folder; add the project folder so that
# "import validation" works (aeroflowsim itself is installed with pip install -e .).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validation.common import SET_VARIABLE, validate_folder, validation_folders, write_report  # noqa: E402


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--quick" in argv:
        argv.remove("--quick")
        os.environ[SET_VARIABLE] = "quick"
    folders = [f for f in validation_folders() if not argv or any(word in f.name for word in argv)]
    validations = []
    for folder in folders:
        print(f"Validating {folder.name} ...", flush=True)
        v = validate_folder(folder)
        for c in v.comparisons:
            r = c.reference
            print(f"  {'PASS' if c.passed else 'FAIL'}  {r.quantity:<58} ref {r.value:<10.6g} "
                  f"AeroFlowSim {c.measured:<10.6g} {r.unit:<6} error {c.error_percent:.3f} % (tolerance {r.tolerance:g} %)")
        validations.append(v)
    passed = all(v.passed for v in validations)
    if argv:
        print("Only some cases were run: the report file is not rewritten.")
    else:
        print(f"Report written to {write_report(validations)}")
    print("ALL VALIDATION CASES PASS" if passed else "SOME VALIDATION CASES FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

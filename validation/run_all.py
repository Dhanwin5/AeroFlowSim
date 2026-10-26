# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run every validation case and write validation/report.md.

    python validation/run_all.py                 full set (all meshes; about 3 hours)
    python validation/run_all.py --quick         quick set (coarse meshes; under 10 minutes)
    python validation/run_all.py wedge cone      only the folders whose names contain these words
    python validation/run_all.py --jobs 6        run up to 6 cases at the same time (each in its own process;
                                                 the default uses about a third of the processor cores)

Prints one line per compared quantity and ends with exit code 0 if everything passes, 1 if not.
"""

import os
import sys
from pathlib import Path

# Started as a script, Python only knows this folder; add the project folder so that
# "import validation" works (aeroflowsim itself is installed with pip install -e .).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validation.common import SET_VARIABLE, validate_folder, validation_folders, write_report  # noqa: E402


def _validate(folder):
    """One case in a worker process (returns the CaseValidation and the wall-clock time)."""
    import time
    t0 = time.perf_counter()
    return validate_folder(folder), time.perf_counter() - t0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--quick" in argv:
        argv.remove("--quick")
        os.environ[SET_VARIABLE] = "quick"
    jobs = 1                       # cases run one after another (the MMS case uses all cores by itself)
    if "--jobs" in argv:
        i = argv.index("--jobs")
        jobs = int(argv[i + 1])
        del argv[i:i + 2]
    folders = [f for f in validation_folders() if not argv or any(word in f.name for word in argv)]
    validations = []
    results = {}
    if jobs == 1:
        for f in folders:
            print(f"Validating {f.name} ...", flush=True)
            results[f.name] = _validate(f)
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(min(jobs, len(folders))) as pool:
            futures = {f.name: pool.submit(_validate, f) for f in folders}
            for name, future in futures.items():
                results[name] = future.result()
    for folder in folders:
        v, seconds = results[folder.name]
        print(f"Validated {folder.name} ({seconds:.0f} s)", flush=True)
        for c in v.comparisons:
            r = c.reference
            print(f"  {c.status:<9} {r.quantity:<58} ref {r.value:<10.6g} "
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

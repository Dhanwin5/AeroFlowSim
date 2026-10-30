# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""MMS order of accuracy with the Venkatakrishnan limiter ACTIVE (not frozen, not off), for a sweep of K.

    python tools/limiter_order.py [--levels 16,32,64,128] [--k 1,5,20] [--out table.md]

Each run: implicit LU-SGS from the exact solution, residual drop 8 orders (or 30,000 iterations), limiter never
frozen. Prints the L2 error of p and rho on every level and the observed order between levels (Prompt 8-2, part 3).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aeroflowsim.euler.solver import LUSGS  # noqa: E402
from aeroflowsim.mms import observed_orders, run_level  # noqa: E402


def study(kind, levels, K, limiter="Venkatakrishnan"):
    import aeroflowsim.mms as mms
    from aeroflowsim.euler import solver as S
    original = S.Numerics.__init__

    def numerics(self, *args, **kwargs):                  # run_level builds its own Numerics: add K and LU-SGS
        original(self, *args, **kwargs)
        self.venkat_k, self.time_scheme, self.freeze_limiter_orders = K, LUSGS, 0.0

    S.Numerics.__init__ = numerics
    try:
        runs = [mms.run_level(kind, n, limiter=limiter, residual_drop=8.0, max_iterations=30000) for n in levels]
    finally:
        S.Numerics.__init__ = original
    return runs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="16,32,64,128")
    ap.add_argument("--k", default="1,5,20")
    ap.add_argument("--kinds", default="quads,triangles")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    levels = [int(v) for v in a.levels.split(",")]
    lines = ["| Mesh | K | " + " | ".join(f"L2(p) {n}" for n in levels) + " | " +
             " | ".join(f"order {levels[i]}-{levels[i + 1]}" for i in range(len(levels) - 1)) + " | converged |",
             "|---|---:|" + "---:|" * (2 * len(levels))]
    for kind in a.kinds.split(","):
        for K in [float(v) for v in a.k.split(",")]:
            runs = study(kind, levels, K)
            orders = observed_orders(runs)
            conv = "/".join("y" if r.residual <= 1e-8 * 1.0001 else f"{r.residual:.0e}" for r in runs)
            lines.append(f"| {kind} | {K:g} | " + " | ".join(f"{r.errors['L2'][3]:.3e}" for r in runs) + " | "
                         + " | ".join(f"{o[3]:.2f}" for o in orders) + f" | {conv} |")
            print(lines[-1], flush=True)
    if a.out:
        Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Full 3D release stage, Part 3: is the laminar square-duct error (1.7 % / 2.3 % from the series solution with 12 cells
per half side) resolution? The validation case validation/viscous_square_duct run with 24 cells per half side (the
same solver settings, the same duct; only the cross-section cells doubled), printed next to the series values.

    python tools/duct_resolution.py [cells per half side, default 24]
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(n=24):
    from validation.viscous_square_duct import validate as v
    original = v.box_mesh_3d

    def finer(nx, kind, lo, hi, ny=12, nz=12):
        return original(nx, kind, lo=lo, hi=hi, ny=n, nz=n)

    v.box_mesh_3d = finer
    out = v.run_duct(8, 64, 6, "")
    ratio, fre = v.series()
    row = {"cells_per_half_side": n, **out, "series_umax_over_umean": ratio, "series_fRe": fre,
           "error_ratio_percent": 100 * (out["umax_over_umean"] / ratio - 1), "error_fRe_percent":
           100 * (out["fRe"] / fre - 1), "timing": v.TIMING.get("run")}
    path = ROOT / "validation" / "results" / "duct_resolution.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
    print(json.dumps(row, default=str))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 24)

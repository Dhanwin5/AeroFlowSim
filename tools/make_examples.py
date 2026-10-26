# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Make the example projects shipped with AeroFlowSim (examples/<name>.afsproj).

    python tools/make_examples.py

N2 nozzle: the default N2 nozzle, coarse structured mesh, solved (its result is shipped, so the Results step works
at once). NACA 0012 transonic, Mach 2 wedge and Sod shock tube: set up, not solved (Run makes the result).
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EXAMPLES = {
    "N2 nozzle": ("nozzle_axi", {"mesh_preset": "Coarse"}, True),
    "NACA 0012 transonic": ("external_2d", {"shape": "NACA 4-digit airfoil", "mach": 0.8, "alpha": 1.25,
                                            "surface_size": 0.005, "farfield_size": 2.0}, False),
    "Mach 2 wedge": ("external_2d", {"shape": "Wedge", "wedge.half_angle": 10.0, "half_domain": True,
                                     "domain_shape": "Rectangle", "upstream": 0.5, "downstream": 0.5, "height": 1.5,
                                     "surface_size": 0.02, "farfield_size": 0.05, "mach": 2.0,
                                     "first_order_iterations": 200}, False),
    "Sod shock tube": ("sod_shock_tube", {}, True),
}


def main():
    from aeroflowsim.post.definitions import ReportDefinition
    from aeroflowsim.project import Project, run_project
    out = ROOT / "examples"
    out.mkdir(exist_ok=True)
    for name, (template, values, solve) in EXAMPLES.items():
        folder = out / f"{name}.afsproj"
        if folder.exists():
            shutil.rmtree(folder)
        project = Project.create(template, folder, values)
        if template == "nozzle_axi":
            project.set_post("report_definitions", [
                ReportDefinition("exit p0 (mass-weighted)", "surface", "outlet", "mass_weighted", "p0").to_dict()])
            project.save()
        if solve:
            print(f"Solving {name} ...", flush=True)
            run_project(project)
        print(f"Made {folder}")


if __name__ == "__main__":
    main()

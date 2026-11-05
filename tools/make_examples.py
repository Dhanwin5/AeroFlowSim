# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Make the example projects shipped with AeroFlowSim (examples/<name>.afsproj).

    python tools/make_examples.py                  (all)
    python tools/make_examples.py "N2 nozzle 3D"   (only the named ones)

N2 nozzle: the default N2 nozzle, coarse structured mesh, solved (its result is shipped, so the Results step works
at once). NACA 0012 transonic, Mach 2 wedge and Sod shock tube: set up, not solved (Run makes the result).
N2 nozzle 3D: the example STEP nozzle (cases/external_3d/examples/conical_nozzle.step, the same gas volume) imported as a
fluid body in the 3D template, boundary names accepted from the suggestions, solved (implicit LU-SGS, Green-Gauss gradients: converged).
Sphere at Mach 3 (3D): quarter domain (two symmetry planes), set up, not solved.
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
    "N2 nozzle laminar": ("nozzle_axi", {"mesh_preset": "Coarse", "flow_model": "Laminar"}, False),
    "NACA 0012 turbulent (SA)": ("external_2d", {"shape": "NACA 4-digit airfoil", "mach": 0.15, "alpha": 0.0,
                                                 "p_inf": 101325.0 * 6e6 / 7.0e6, "mesh_type": "Structured C/O-grid",
                                                 "grid_first_height": 2e-6, "flow_model": "Spalart-Allmaras",
                                                 "max_iter": 40000}, False),
    "Sphere at Mach 3 (3D)": ("external_3d", {"body_shape": "Sphere", "diameter": 0.1, "mach": 3.0, "half_domain": True,
                                              "quarter_domain": True, "upstream": 2.0, "downstream": 3.0,
                                              "lateral": 2.0, "surface_size": 0.04, "farfield_size": 0.5,
                                              "max_iter": 8000}, False),
    "N2 nozzle 3D": ("external_3d", {"gas": "N2", "surface_size": 0.03, "farfield_size": 0.06, "curvature_cells": 24,
                                     "max_iter": 20000,
                                     "boundaries": {"inlet": {"type": "total_pressure_inlet", "p0": 500000.0,
                                                              "T0": 293.15},
                                                    "outlet": {"type": "pressure_outlet", "p": 1000.0}}}, True),
}


def _step_nozzle(project):
    """The 3D workspace of "N2 nozzle 3D": the template geometry suppressed, the STEP nozzle imported as fluid, its
    faces named by the suggestions (inlet, outlet, wall)."""
    from aeroflowsim.geometry_model import replay
    from aeroflowsim.geometry_model.operations3d import ImportSolid
    from aeroflowsim.gui.geometry_logic import accept_suggestions_3d
    rel = project.import_file(ROOT / "cases" / "external_3d" / "examples" / "conical_nozzle.step")
    doc = project.geometry_document()
    for op in doc.operations:
        op.suppressed = True
    doc.add(ImportSolid(file=rel, role="fluid"))
    doc = accept_suggestions_3d(doc, replay(doc, project.replay_context(), triangulate=False))
    project.set_geometry_document(doc)
    project.save()


def main():
    from aeroflowsim.post.definitions import ReportDefinition
    from aeroflowsim.project import Project, run_project
    out = ROOT / "examples"
    out.mkdir(exist_ok=True)
    only = set(sys.argv[1:])
    for name, (template, values, solve) in EXAMPLES.items():
        if only and name not in only:
            continue
        folder = out / f"{name}.afsproj"
        if folder.exists():
            shutil.rmtree(folder)
        project = Project.create(template, folder, values)
        if template == "nozzle_axi":
            project.set_post("report_definitions", [
                ReportDefinition("exit p0 (mass-weighted)", "surface", "outlet", "mass_weighted", "p0").to_dict()])
            project.save()
        if template == "external_3d":            # no recorded animation: it would be most of the example's size
            project.set_post("animation", {"record": False, "every": 0})
            project.save()
        if name == "N2 nozzle 3D":
            _step_nozzle(project)
        if solve:
            print(f"Solving {name} ...", flush=True)
            run_project(project)
            if template == "external_3d":        # 3D: ship only what the project needs (exports are re-made on demand)
                for extra in ("results/fields.csv", "results/solution.vtu", "mesh/mesh.vtu"):
                    (folder / extra).unlink(missing_ok=True)
        print(f"Made {folder}")


if __name__ == "__main__":
    main()

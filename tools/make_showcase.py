# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pictures for the README and docs (docs/showcase/), in the light paper style, and a note with the key numbers.

    python tools/make_showcase.py

N2 nozzle (examples/N2 nozzle.afsproj, solved by tools/make_examples.py): Mach contours mirrored about the axis, a 3D
revolved view (VTK, off screen), wall pressure against quasi-1D theory. NACA 0012 at Mach 0.8, alpha 1.25 deg (solved
here on a 0.005 c C-domain-free mesh of the template): Mach contours and Cp along the wall. Mach 2 wedge: pressure
with contour lines. The validation table is copied from validation/report.md. Facts only.
"""

import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "showcase"


def revolved_png(sol, path):
    import pyvista as pv
    from aeroflowsim.post.fields import node_values
    pv.OFF_SCREEN = True
    mesh = sol.mesh
    counts = (mesh.cell_nodes >= 0).sum(axis=1)
    cells = np.column_stack([counts, mesh.cell_nodes])[np.column_stack([np.ones(len(counts), bool),
                                                                         mesh.cell_nodes >= 0])]
    grid = pv.UnstructuredGrid(cells.astype(np.int64), mesh.cell_types.astype(np.uint8), mesh.nodes)
    grid.point_data["M"] = node_values(sol, "M")
    surf = grid.extract_surface(algorithm="dataset_surface")
    edges = surf.extract_feature_edges(boundary_edges=True, feature_edges=False, manifold_edges=False,
                                       non_manifold_edges=False)
    wall = edges.extract_points(edges.points[:, 1] > 1e-12, adjacent_cells=False)
    swept = wall.extract_surface(algorithm="dataset_surface").extrude_rotate(resolution=90, angle=270.0,
                                                                              rotation_axis=(1, 0, 0), capping=False)
    p = pv.Plotter(off_screen=True, window_size=(1600, 900))
    p.set_background("white")
    p.add_mesh(grid, scalars="M", cmap="turbo", show_scalar_bar=False)
    p.add_mesh(grid.rotate_x(270.0, point=(0, 0, 0), inplace=False), scalars="M", cmap="turbo", show_scalar_bar=False)
    p.add_mesh(swept, scalars="M", cmap="turbo", smooth_shading=True,
               scalar_bar_args={"title": "Mach number", "color": "black", "vertical": False})
    p.view_isometric()
    p.camera.zoom(1.3)
    p.screenshot(str(path))
    p.close()


def main():
    from aeroflowsim.post.pictures import field_picture
    from aeroflowsim.post.solution import Solution
    from aeroflowsim.project import Project
    import aeroflowsim
    from aeroflowsim import gasdynamics as gd
    OUT.mkdir(parents=True, exist_ok=True)
    notes = ["# Showcase: key numbers", "", "All numbers from the projects and validation report named here (SI units).", ""]

    noz = Project.open(ROOT / "examples" / "N2 nozzle.afsproj")
    sol = Solution.from_project(noz)
    field_picture(sol, "M", "turbo", mirror=True, title="N2 nozzle: Mach number (2D axisymmetric Euler)",
                  size=(8, 3.6)).savefig(OUT / "n2_nozzle_mach_mirrored.png", dpi=160)
    revolved_png(sol, OUT / "n2_nozzle_mach_revolved.png")
    from matplotlib.figure import Figure
    s = sol.series
    x = np.asarray(s["wall_x"])
    o = np.argsort(x)
    r = np.asarray(s["wall_y"])[o]
    g = sol.info.get("gamma", 1.4)
    i_t = int(np.argmin(r))
    M1d = [gd.mach_from_area_ratio(max((ri / r[i_t]) ** 2, 1 + 1e-9), g, k > i_t) for k, ri in enumerate(r)]
    fig = Figure(figsize=(8, 3.6), dpi=160, layout="constrained")
    ax = fig.add_subplot()
    ax.semilogy(1e3 * x[o], np.asarray(s["wall_p_over_p0"])[o], ".", ms=3, label="2D Euler, wall")
    ax.semilogy(1e3 * x[o], 1 / gd.p0_over_p(np.asarray(M1d), g), "--", label="quasi-1D isentropic, same wall")
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("p / p0")
    ax.set_title("N2 nozzle: wall pressure")
    ax.grid(True, lw=0.4)
    ax.legend()
    fig.savefig(OUT / "n2_nozzle_wall_pressure.png")
    k = sol.key_numbers
    notes += [f"N2 nozzle ({sol.mesh.n_cells:,} cells, structured): vacuum Isp {k['Isp_vacuum'][0]:.3f} s (2D Euler) vs "
              f"{k['Isp_quasi1D'][0]:.3f} s (ideal quasi-1D), ratio {k['Isp_2D_over_quasi1D'][0]:.4f}; mass flow "
              f"{1e6 * k['mdot'][0]:.3f} mg/s, discharge coefficient {k['discharge_coefficient'][0]:.4f}; vacuum thrust "
              f"{1e3 * k['F_vacuum'][0]:.3f} mN; exit Mach {k['M_exit'][0]:.3f}.", ""]

    out = aeroflowsim.run_case("cases/external_2d", {"shape": "NACA 4-digit airfoil", "mach": 0.8, "alpha": 1.25,
                                                      "surface_size": 0.005, "farfield_size": 2.0, "max_iter": 20000})
    naca = Solution.from_result(out.mesh, out.result, out.params, case=out.case)
    fig = field_picture(naca, "M", "turbo", title="NACA 0012, Mach 0.8, alpha 1.25 deg: Mach number", size=(8, 4))
    fig.axes[0].set_xlim(-0.5, 1.6)
    fig.axes[0].set_ylim(-0.6, 0.7)
    fig.savefig(OUT / "naca0012_mach.png", dpi=160)
    fig = Figure(figsize=(8, 3.6), dpi=160, layout="constrained")
    ax = fig.add_subplot()
    wx, wy, cp = (np.asarray(out.result.series[n]) for n in ("wall_x", "wall_y", "wall_Cp"))
    up = wy >= 0
    ax.plot(wx[up], cp[up], ".", ms=3, label="upper surface")
    ax.plot(wx[~up], cp[~up], ".", ms=3, label="lower surface")
    ax.invert_yaxis()
    ax.set_xlabel("x / c")
    ax.set_ylabel("Cp")
    ax.set_title("NACA 0012, Mach 0.8, alpha 1.25 deg: pressure coefficient")
    ax.grid(True, lw=0.4)
    ax.legend()
    fig.savefig(OUT / "naca0012_cp.png")
    kn = out.result.key_numbers
    notes += [f"NACA 0012, Mach 0.8, alpha 1.25 deg (template mesh, wall 0.005 c, {out.mesh.n_cells:,} cells, "
              f"{'converged' if out.result.converged else 'not converged'} after {out.result.iterations:,} iterations): "
              f"Cl {kn['Cl'][0]:.4f}, Cd {kn['Cd'][0]:.5f}. Grid-converged reference (Vassberg and Jameson 2010, "
              "Table 11): Cl 0.348-0.356, Cd 0.02245-0.02268.", ""]

    w = aeroflowsim.run_case("cases/external_2d", {"shape": "Wedge", "wedge.half_angle": 10.0, "half_domain": True,
                                                   "domain_shape": "Rectangle", "upstream": 0.5, "downstream": 0.5,
                                                   "height": 1.5, "surface_size": 0.01, "farfield_size": 0.025,
                                                   "mach": 2.0, "first_order_iterations": 200})
    wedge = Solution.from_result(w.mesh, w.result, w.params, case=w.case)
    field_picture(wedge, "p", "viridis", levels=list(np.linspace(1.1e5, 1.8e5, 8)),
                  title="Mach 2 flow over a 10 deg wedge: pressure", size=(7, 4.5)).savefig(OUT / "wedge_pressure.png",
                                                                                          dpi=160)
    report = (ROOT / "validation" / "report.md").read_text(encoding="utf-8")
    (OUT / "validation_summary.md").write_text(report.split("\n## ")[0] + "\n", encoding="utf-8")
    notes += ["Validation: see validation/report.md (summary copied to docs/showcase/validation_summary.md)."]
    (OUT / "README.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
    print("\n".join(notes))


if __name__ == "__main__":
    main()

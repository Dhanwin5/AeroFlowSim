# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""3D post-processing (aeroflowsim/post/view3d.py): slices, iso-surfaces, wall surfaces, probes, streamlines."""

import numpy as np
import pytest

from aeroflowsim.post import view3d
from aeroflowsim.simple_meshes import BOX_KINDS, box_mesh_3d


def _area(s):
    p = s.points[s.triangles]
    return 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1).sum()


@pytest.mark.parametrize("kind", BOX_KINDS)
def test_a_slice_of_the_unit_box_has_its_exact_area_and_linear_values(kind):
    mesh = box_mesh_3d(4, kind, warp=0.03)
    x = mesh.nodes[:, 0]
    s = view3d.slice_plane(mesh, 3.0 * x, (0.37, 0, 0), (1, 0, 0))
    assert _area(s) == pytest.approx(1.0, rel=1e-9)
    assert np.allclose(s.values, 3 * 0.37) and np.allclose(s.points[:, 0], 0.37)
    tilted = view3d.slice_plane(mesh, x, (0.5, 0.5, 0.5), (1, 1, 0))
    assert _area(tilted) == pytest.approx(np.sqrt(2.0), rel=1e-9)        # the diagonal plane through the box


def test_only_the_cells_on_the_surface_are_split():
    mesh = box_mesh_3d(10, "tetrahedra")
    s_node = mesh.nodes[:, 2] - 0.55
    assert len(view3d._straddling(mesh, s_node)) == 6 * 100                # one layer of cubes


def test_iso_surface_of_a_linear_field_is_a_plane():
    mesh = box_mesh_3d(5, "hex-prism", warp=0.02)
    f = mesh.nodes @ np.array([1.0, 2.0, 0.0])
    s = view3d.iso_surface(mesh, f, 1.2)
    assert np.allclose(s.points @ [1.0, 2.0, 0.0], 1.2) and s.n_triangles > 0


def test_patch_surface_probe_and_streamline():
    mesh = box_mesh_3d(4, "prisms")
    s = view3d.patch_surface(mesh, ["xmin"], mesh.nodes[:, 1])
    assert _area(s) == pytest.approx(1.0) and np.allclose(s.points[:, 0], 0.0)
    out = view3d.probe(mesh, (0.9, 0.1, 0.1), {"x": mesh.cell_centres[:, 0]})
    assert out["x"] > 0.75
    vel = np.zeros((3, mesh.n_cells))
    vel[0] = 100.0
    line = view3d.streamlines(mesh, vel, [(0.05, 0.5, 0.5)])[0]
    assert np.allclose(line[:, 1:], 0.5) and line[-1, 0] > 1.0


def test_3d_node_values_of_pressure_use_the_pressure_on_the_boundary():
    """Bug found in the 3D validation: boundary node values of p took row 3 (w in 3D) of the face states."""
    from aeroflowsim.euler.boundary import BoundaryCondition
    from aeroflowsim.gases import gas_model
    from aeroflowsim.post.fields import node_values
    from aeroflowsim.post.solution import Solution
    mesh = box_mesh_3d(3, "tetrahedra", kinds={k: "wall" for k in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")})
    n = mesh.n_cells
    fields = {"rho": np.full(n, 1.2), "u": np.full(n, 10.0), "v": np.zeros(n), "w": np.full(n, 3.0),
              "p": np.full(n, 1e5)}
    sol = Solution(mesh, fields, gas_model("air"), {p.name: BoundaryCondition("slip_wall") for p in mesh.patches})
    assert np.allclose(node_values(sol, "p"), 1e5) and np.allclose(node_values(sol, "rho"), 1.2)

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests of the ParaView .vtu writer (aeroflowsim/vtk.py): valid XML with the right numbers."""

import xml.etree.ElementTree as ET

import numpy as np
import pytest

from aeroflowsim.mesh import QUAD, TRIANGLE, Mesh
from aeroflowsim.vtk import mesh_cell_data, vtu_text, write_vtu


def small_mesh():
    nodes = [[0, 0], [0.5, 0], [1, 0], [1, 1], [0.5, 1], [0, 1]]
    cells = [[0, 1, 4, 5], [1, 2, 3, -1], [1, 3, 4, -1]]
    boundary = {"bottom": ("wall", [[0, 1], [1, 2]]), "rest": ("farfield", [[2, 3], [3, 4], [4, 5], [5, 0]])}
    return Mesh.from_cells(nodes, [QUAD, TRIANGLE, TRIANGLE], cells, boundary)


def numbers(element):
    return np.array(element.text.split(), dtype=float)


def test_vtu_file_has_points_cells_and_any_cell_data(tmp_path):
    mesh = small_mesh()
    velocity = np.arange(9.0).reshape(3, 3)
    path = write_vtu(tmp_path / "mesh.vtu", mesh, {**mesh_cell_data(mesh), "U": velocity})
    root = ET.parse(path).getroot()
    piece = root.find("UnstructuredGrid/Piece")
    assert (piece.get("NumberOfPoints"), piece.get("NumberOfCells")) == ("6", "3")
    arrays = {a.get("Name"): a for a in piece.iter("DataArray")}
    assert numbers(arrays["Points"]).reshape(-1, 3)[3].tolist() == [1, 1, 0]
    assert numbers(arrays["connectivity"]).tolist() == [0, 1, 4, 5, 1, 2, 3, 1, 3, 4]
    assert numbers(arrays["offsets"]).tolist() == [4, 7, 10]
    assert numbers(arrays["types"]).tolist() == [QUAD, TRIANGLE, TRIANGLE]
    assert numbers(arrays["cell_volume"]) == pytest.approx([0.5, 0.25, 0.25])
    assert arrays["U"].get("NumberOfComponents") == "3"
    assert numbers(arrays["U"]).reshape(3, 3).tolist() == velocity.tolist()
    assert set(numbers(arrays["patch_marker"])) <= {0, 1, 2}


def test_cell_data_of_the_wrong_length_is_refused():
    with pytest.raises(ValueError, match="one value"):
        vtu_text(small_mesh(), {"p": np.ones(5)})

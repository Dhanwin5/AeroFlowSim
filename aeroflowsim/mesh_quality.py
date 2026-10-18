# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh quality numbers of a face-based Mesh (aeroflowsim/mesh.py), one value per cell.

They work for any cell type, in 2D and 3D, because they only use faces, owner and neighbour:

    aspect_ratio        largest / smallest face area of the cell. A 2D rectangle a x b gives a/b,
                        a 3D box a x b x c gives (longest edge) / (shortest edge). 1 = square cell.
    non_orthogonality   angle [deg] between a face normal and the line joining the two cell centres.
                        0 = the line crosses the face at right angles (best for gradients).
                        Per cell: the worst of its faces.
    volume_ratio        larger / smaller volume of two neighbouring cells (sudden growth = jump).
                        Per cell: the worst of its neighbours. 1 = equal sizes.
    cell_size           smallest "thickness" of the cell = volume / largest face area [m]
                        (a 2D rectangle a x b gives min(a, b)).

The validity checks (aeroflowsim/checks.py) and the GUI's Mesh tab use these numbers.
"""

import numpy as np


def _per_cell_max(mesh, face_values, interior_only=False):
    """For every cell, the largest value of face_values over its faces."""
    out = np.full(mesh.n_cells, -np.inf)
    faces = np.arange(mesh.n_interior_faces) if interior_only else np.arange(mesh.n_faces)
    np.maximum.at(out, mesh.owner[faces], face_values[faces])
    inner = faces[mesh.neighbour[faces] >= 0]
    np.maximum.at(out, mesh.neighbour[inner], face_values[inner])
    return out


def aspect_ratio(mesh) -> np.ndarray:
    """(C,) largest / smallest face area of every cell [-]."""
    largest = _per_cell_max(mesh, mesh.face_areas)
    smallest = -_per_cell_max(mesh, -mesh.face_areas)
    return largest / np.where(smallest > 0.0, smallest, np.nan)


def face_non_orthogonality(mesh) -> np.ndarray:
    """(F,) angle between the face normal and the owner->neighbour line [deg]; 0 on boundary faces."""
    d = mesh.face_deltas
    length = np.linalg.norm(d, axis=1)
    cosine = np.einsum("ij,ij->i", mesh.face_normals, d) / np.where(length > 0.0, length, 1.0)
    angle = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
    angle[mesh.neighbour < 0] = 0.0    # boundary faces have no neighbour centre
    return angle


def non_orthogonality(mesh) -> np.ndarray:
    """(C,) worst non-orthogonality angle of the faces of every cell [deg]."""
    return np.maximum(_per_cell_max(mesh, face_non_orthogonality(mesh)), 0.0)


def volume_ratio(mesh) -> np.ndarray:
    """(C,) largest volume ratio between the cell and any of its neighbours [-] (1 if it has none)."""
    n = mesh.n_interior_faces
    v_own, v_nb = mesh.cell_volumes[mesh.owner[:n]], mesh.cell_volumes[mesh.neighbour[:n]]
    small = np.minimum(np.abs(v_own), np.abs(v_nb))
    ratio = np.maximum(np.abs(v_own), np.abs(v_nb)) / np.where(small > 0.0, small, np.nan)
    face_ratio = np.ones(mesh.n_faces)
    face_ratio[:n] = ratio
    return np.maximum(_per_cell_max(mesh, face_ratio, interior_only=True), 1.0)


def cell_size(mesh) -> np.ndarray:
    """(C,) smallest thickness of every cell = volume / largest face area [m]."""
    return mesh.cell_volumes / _per_cell_max(mesh, mesh.face_areas)


def quality_summary(mesh) -> dict:
    """The key quality numbers of the whole mesh {name: value}."""
    return {
        "min_volume": float(mesh.cell_volumes.min()),                    # [m³]
        "max_aspect_ratio": float(np.nanmax(aspect_ratio(mesh))),        # [-]
        "max_non_orthogonality": float(non_orthogonality(mesh).max()),   # [deg]
        "max_volume_ratio": float(np.nanmax(volume_ratio(mesh))),        # [-]
        "min_cell_size": float(cell_size(mesh).min()),                   # [m]
    }

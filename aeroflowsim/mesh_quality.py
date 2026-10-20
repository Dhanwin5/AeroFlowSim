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
    min_angle           smallest inner corner angle of the cell [deg] (60 for an equilateral triangle).
    equiangle_skewness  how far the corner angles are from the perfect shape's, 0 (perfect) to 1 (flat).
                        These two use the cell's corners (2D) or the corners of its faces (3D).

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


def _polygon_angles(nodes, polygons, counts):
    """Inner corner angles [deg] of polygons (M, 4) with `counts` corners each; padding -> NaN."""
    angles = np.full(polygons.shape, np.nan)
    for k in range(polygons.shape[1]):
        use = k < counts
        if not np.any(use):
            continue
        rows = np.flatnonzero(use)
        n = counts[rows]
        here = nodes[polygons[rows, k]]
        before = nodes[polygons[rows, (k - 1) % n]]
        after = nodes[polygons[rows, (k + 1) % n]]
        a, b = before - here, after - here
        cosine = np.einsum("ij,ij->i", a, b) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1),
                                                          1e-300)
        angles[rows, k] = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
    return angles


def _polygon_skewness(angles, counts):
    """Equiangle skewness of polygons from their corner angles (see equiangle_skewness)."""
    ideal = np.where(counts == 3, 60.0, 90.0)          # equilateral triangle / square [deg]
    largest, smallest = np.nanmax(angles, axis=1), np.nanmin(angles, axis=1)
    return np.maximum((largest - ideal) / (180.0 - ideal), (ideal - smallest) / ideal)


def _cell_polygons(mesh):
    """The polygons whose angles describe the cells: 2D = the cells, 3D = their faces.

    Returns (polygons (M, 4) of node numbers, number of corners of each (M,)).
    """
    if mesh.dim == 2:
        polygons = mesh.cell_nodes[:, :4]
    else:
        polygons = mesh.face_nodes
    counts = np.count_nonzero(polygons >= 0, axis=1)
    return np.maximum(polygons, 0), counts


def min_angle(mesh) -> np.ndarray:
    """(C,) smallest inner corner angle of every cell [deg] (3D: of any of its faces).

    A triangle with a very small angle (a "sliver") gives inaccurate gradients and fluxes.
    """
    polygons, counts = _cell_polygons(mesh)
    smallest = np.nanmin(_polygon_angles(mesh.nodes, polygons, counts), axis=1)
    if mesh.dim == 2:
        return smallest
    return -_per_cell_max(mesh, -smallest)


def equiangle_skewness(mesh) -> np.ndarray:
    """(C,) equiangle skewness of every cell [-]: 0 = perfect shape, 1 = completely flat.

        skewness = max( (theta_max - theta_e) / (180 - theta_e), (theta_e - theta_min) / theta_e )
    with theta_min / theta_max the smallest / largest corner angle and theta_e the angle of the
    perfect shape: 60 deg for a triangle, 90 deg for a quad. In 3D the worst face of the cell counts.
    """
    polygons, counts = _cell_polygons(mesh)
    skew = _polygon_skewness(_polygon_angles(mesh.nodes, polygons, counts), counts)
    if mesh.dim == 2:
        return skew
    return _per_cell_max(mesh, skew)


def quality_summary(mesh) -> dict:
    """The key quality numbers of the whole mesh {name: value}."""
    return {
        "min_volume": float(mesh.cell_volumes.min()),                    # [m³]
        "max_aspect_ratio": float(np.nanmax(aspect_ratio(mesh))),        # [-]
        "max_non_orthogonality": float(non_orthogonality(mesh).max()),   # [deg]
        "max_volume_ratio": float(np.nanmax(volume_ratio(mesh))),        # [-]
        "min_cell_size": float(cell_size(mesh).min()),                   # [m]
        "min_angle": float(np.nanmin(min_angle(mesh))),                  # [deg]
        "max_skewness": float(np.nanmax(equiangle_skewness(mesh))),      # [-]
    }


# Per-cell quality fields a GUI can colour the cells by: {name: (function(mesh) -> values, unit)}
QUALITY_COLORINGS = {
    "Aspect ratio": (aspect_ratio, "-"),
    "Non-orthogonality": (non_orthogonality, "deg"),
    "Neighbour volume ratio": (volume_ratio, "-"),
    "Cell size": (cell_size, "m"),
    "Smallest angle": (min_angle, "deg"),
    "Equiangle skewness": (equiangle_skewness, "-"),
}

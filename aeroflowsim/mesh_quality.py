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

Tetrahedra (3D) have two more, the measures 3D meshers report for them:
    equivolume_skewness 1 - V / V_ideal, with V_ideal the volume of the regular tetrahedron that has the same
                        circumsphere (radius R): V_ideal = 8 / (9 sqrt 3) R³. 0 = regular, 1 = flat "sliver".
                        (The skewness Fluent reports for tetrahedra.)
    min_dihedral_angle  smallest angle between two faces of the tetrahedron [deg] (70.5 for a regular one);
                        a sliver has all four corners almost in one plane and a dihedral angle near 0.
    skewness            equivolume skewness for tetrahedra, equiangle skewness for every other cell (so in 2D it
                        is the equiangle skewness).

The validity checks (aeroflowsim/checks.py) and the GUI's Mesh tab use these numbers.
"""

import numpy as np

from aeroflowsim.mesh import TETRA


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


def _tetrahedra(mesh):
    """(indices of the tetrahedra, their corner points (n, 4, 3))."""
    ids = np.flatnonzero(mesh.cell_types == TETRA)
    return ids, mesh.nodes[mesh.cell_nodes[ids, :4]]


def equivolume_skewness(mesh) -> np.ndarray:
    """(C,) equivolume skewness of the tetrahedra [-] (NaN for other cells): 1 - V / V_ideal(circumradius)."""
    out = np.full(mesh.n_cells, np.nan)
    ids, p = _tetrahedra(mesh)
    if len(ids):
        u, v, w = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0], p[:, 3] - p[:, 0]
        six_v = np.einsum("ij,ij->i", u, np.cross(v, w))                    # 6 x signed volume [m³]
        centre = (np.einsum("ij,ij->i", u, u)[:, None] * np.cross(v, w) + np.einsum("ij,ij->i", v, v)[:, None] *
                  np.cross(w, u) + np.einsum("ij,ij->i", w, w)[:, None] * np.cross(u, v))
        radius = np.linalg.norm(centre, axis=1) / np.where(six_v != 0.0, 2.0 * np.abs(six_v), np.inf)   # [m]
        ideal = 8.0 / (9.0 * np.sqrt(3.0)) * radius ** 3                     # regular tetrahedron in that sphere
        out[ids] = np.clip(1.0 - np.abs(six_v) / 6.0 / np.where(ideal > 0.0, ideal, np.inf), 0.0, 1.0)
    return out


def min_dihedral_angle(mesh) -> np.ndarray:
    """(C,) smallest dihedral angle of the tetrahedra [deg] (NaN for other cells)."""
    out = np.full(mesh.n_cells, np.nan)
    ids, p = _tetrahedra(mesh)
    if len(ids):
        faces = ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1))                 # face k lies opposite corner k
        normals = []
        for k, (a, b, c) in enumerate(faces):
            n = np.cross(p[:, b] - p[:, a], p[:, c] - p[:, a])
            n *= -np.sign(np.einsum("ij,ij->i", n, p[:, k] - p[:, a]))[:, None]   # point away from corner k
            normals.append(n / np.maximum(np.linalg.norm(n, axis=1), 1e-300)[:, None])
        angles = [np.pi - np.arccos(np.clip(np.einsum("ij,ij->i", normals[i], normals[j]), -1.0, 1.0))
                  for i in range(4) for j in range(i + 1, 4)]
        out[ids] = np.degrees(np.min(angles, axis=0))
    return out


def skewness(mesh) -> np.ndarray:
    """(C,) equivolume skewness for tetrahedra, equiangle skewness for the other cells [-]."""
    skew = equiangle_skewness(mesh)
    tets = mesh.cell_types == TETRA
    if np.any(tets):
        skew[tets] = equivolume_skewness(mesh)[tets]
    return skew


def quality_summary(mesh) -> dict:
    """The key quality numbers of the whole mesh {name: value}."""
    out = {
        "min_volume": float(mesh.cell_volumes.min()),                    # [m³]
        "max_aspect_ratio": float(np.nanmax(aspect_ratio(mesh))),        # [-]
        "max_non_orthogonality": float(non_orthogonality(mesh).max()),   # [deg]
        "max_volume_ratio": float(np.nanmax(volume_ratio(mesh))),        # [-]
        "min_cell_size": float(cell_size(mesh).min()),                   # [m]
        "min_angle": float(np.nanmin(min_angle(mesh))),                  # [deg]
        "max_skewness": float(np.nanmax(skewness(mesh))),                # [-] (2D: equiangle, as before)
    }
    if np.any(mesh.cell_types == TETRA):
        out["min_dihedral_angle"] = float(np.nanmin(min_dihedral_angle(mesh)))   # [deg]
    return out


# Per-cell quality fields a GUI can colour the cells by: {name: (function(mesh) -> values, unit)}
QUALITY_COLORINGS = {
    "Aspect ratio": (aspect_ratio, "-"),
    "Non-orthogonality": (non_orthogonality, "deg"),
    "Neighbour volume ratio": (volume_ratio, "-"),
    "Cell size": (cell_size, "m"),
    "Smallest angle": (min_angle, "deg"),
    "Equiangle skewness": (equiangle_skewness, "-"),
}
# ... and the extra ones of 3D meshes with tetrahedra
QUALITY_COLORINGS_3D = {
    "Skewness (equivolume for tetrahedra)": (skewness, "-"),
    "Smallest dihedral angle": (min_dihedral_angle, "deg"),
}


def colorings(mesh) -> dict:
    """The quality fields that apply to this mesh (2D: QUALITY_COLORINGS; 3D: also QUALITY_COLORINGS_3D)."""
    return {**QUALITY_COLORINGS, **(QUALITY_COLORINGS_3D if mesh.dim == 3 else {})}

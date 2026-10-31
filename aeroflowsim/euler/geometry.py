# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The numbers the solver needs from a Mesh, computed once before the first iteration.

Planar 2D (and 3D later): a face's flux area is its area, a cell's volume its volume.
Axisymmetric (per radian): flux area = face area x r of the face centre, volume = cell volume x r of the
centroid (mesh.axi_face_areas, mesh.axi_cell_volumes; exact for straight edges, Pappus). Faces on the
axis have r = 0 and so zero flux area: nothing flows through the axis, without a special case.

The solver also needs, per cell, the list of its faces ("slots", padded to the largest number of faces
of any cell). With these padded arrays a sum or minimum over a cell's faces is one NumPy call, and the
same arrays can be handed to Numba later (Speed stage) unchanged.

Sums over faces use sparse matrices: `scatter` (cells x faces) has +1 at (owner, face) and -1 at
(neighbour, face). The net outflow of every cell is then  scatter @ (flux x area)  in one call.
"""

import numpy as np
from scipy import sparse


class FVGeometry:
    """Mesh numbers for the finite-volume solver (see the module docstring)."""

    def __init__(self, mesh):
        self.mesh = mesh
        dim = mesh.dim
        self.dim = dim
        self.axisymmetric = mesh.axisymmetric
        self.n_cells, self.n_faces = mesh.n_cells, mesh.n_faces
        self.n_interior = mesh.n_interior_faces
        self.owner = mesh.owner.copy()
        self.neighbour = mesh.neighbour[:self.n_interior].copy()        # interior faces only
        self.boundary_faces = np.arange(self.n_interior, self.n_faces)
        self.boundary_owner = mesh.owner[self.n_interior:]
        self.n_boundary = len(self.boundary_faces)

        self.normals = mesh.face_normals[:, :dim].copy()                # (F, dim) unit vectors
        self.planar_areas = mesh.face_areas.copy()                     # [m²] (2D: edge length x 1 m)
        self.planar_volumes = mesh.cell_volumes.copy()                 # [m³]
        if mesh.axisymmetric:
            self.flux_areas = mesh.axi_face_areas.copy()               # [m³ per radian]
            self.volumes = mesh.axi_cell_volumes.copy()                # [m⁴ per radian]
        else:
            self.flux_areas = self.planar_areas.copy()
            self.volumes = self.planar_volumes.copy()
        self.cell_centres = mesh.cell_centres[:, :dim].copy()          # [m]
        self.face_centres = mesh.face_centres[:, :dim].copy()          # [m]
        self.cell_size = np.abs(self.planar_volumes) ** (1.0 / dim)   # typical cell width h [m]

        # owner/neighbour scatter matrix: (cells x faces), +1 owner, -1 neighbour
        rows = np.concatenate([self.owner, self.neighbour])
        cols = np.concatenate([np.arange(self.n_faces), np.arange(self.n_interior)])
        vals = np.concatenate([np.ones(self.n_faces), -np.ones(self.n_interior)])
        self.scatter = sparse.csr_matrix((vals, (rows, cols)), shape=(self.n_cells, self.n_faces))

        # Discrete "geometric source" G_i = sum over the faces of n A_flux (outward). For a closed planar
        # cell it is zero; for an axisymmetric cell its radial part is exactly the planar cell volume
        # (sum n_r r_f L_f = area for straight edges), which is the pressure source of the r-momentum
        # equation. The solver uses this identity to be well-balanced (see solver.py).
        self.geometric_source = (self.scatter @ (self.normals * self.flux_areas[:, None])).T   # (dim, C)

        self._cell_slots()
        self.patch_faces = {p.name: np.arange(p.start, p.start + p.count) for p in mesh.patches}
        self.patch_types = {p.name: p.type for p in mesh.patches}

    def _cell_slots(self):
        """Per cell, its faces padded to the largest face count k_max (padding: face -1)."""
        cells = np.concatenate([self.owner, self.neighbour])
        faces = np.concatenate([np.arange(self.n_faces), np.arange(self.n_interior)])
        sign = np.concatenate([np.ones(self.n_faces), -np.ones(self.n_interior)])   # +1: normal points out
        order = np.argsort(cells, kind="stable")
        cells, faces, sign = cells[order], faces[order], sign[order]
        counts = np.bincount(cells, minlength=self.n_cells)
        k_max = int(counts.max())
        start = np.concatenate([[0], np.cumsum(counts)[:-1]])
        slot = np.arange(len(cells)) - start[cells]                  # position of each face in its cell
        self.k_max = k_max
        self.slot_face = np.full((self.n_cells, k_max), -1, dtype=np.int64)
        self.slot_sign = np.zeros((self.n_cells, k_max))
        self.slot_face[cells, slot] = faces
        self.slot_sign[cells, slot] = sign
        self.slot_used = self.slot_face >= 0
        # Slot of each face in its owner and (interior faces) in its neighbour
        self.owner_slot = np.empty(self.n_faces, dtype=np.int64)
        self.neighbour_slot = np.empty(self.n_interior, dtype=np.int64)
        is_owner = sign > 0
        self.owner_slot[faces[is_owner]] = slot[is_owner]
        self.neighbour_slot[faces[~is_owner]] = slot[~is_owner]

        # The value on the other side of each slot, as an index into [cell values, boundary face values]:
        # interior face -> the other cell; boundary face -> n_cells + its boundary number. Padding -> the
        # cell itself (so it never changes a minimum or maximum).
        f = np.where(self.slot_used, self.slot_face, 0)
        interior = f < self.n_interior
        own = self.owner[f]
        nb = np.where(interior, self.mesh.neighbour[f], -1)
        cell_ids = np.broadcast_to(np.arange(self.n_cells)[:, None], f.shape)
        other = np.where(interior, np.where(own == cell_ids, nb, own), self.n_cells + (f - self.n_interior))
        self.slot_other = np.where(self.slot_used, other, cell_ids)
        # Vector from the cell centre to each of its face centres [m] (zero for padding)
        self.slot_offset = np.where(self.slot_used[..., None],
                                    self.face_centres[f] - self.cell_centres[:, None, :], 0.0)
        self.slot_normal = np.where(self.slot_used[..., None], self.normals[f] * self.slot_sign[..., None], 0.0)
        self.slot_planar_area = np.where(self.slot_used, self.planar_areas[f], 0.0)
        # The same vectors component by component, (dim, C, k_max): a dot product with a per-cell vector is
        # then dim multiply-adds of whole arrays (much faster than einsum for 2 or 3 components)
        self.slot_offset_by_axis = np.ascontiguousarray(self.slot_offset.transpose(2, 0, 1))
        self.slot_normal_by_axis = np.ascontiguousarray(self.slot_normal.transpose(2, 0, 1))

    def change_to_faces(self, grad):
        """grad . r_f for every cell and each of its faces: (n_vars, dim, C) -> (n_vars, C, k_max)."""
        out = grad[:, 0, :, None] * self.slot_offset_by_axis[0]
        for k in range(1, self.dim):
            out += grad[:, k, :, None] * self.slot_offset_by_axis[k]
        return out

    def sum_over_faces(self, face_values):
        """Net outward sum per cell of face values (n_vars, F) -> (n_vars, C): owner +, neighbour -."""
        return (self.scatter @ face_values.T).T

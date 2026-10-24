# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cell gradients of the primitive variables: weighted least squares (default) or Green-Gauss.

Weighted least squares (Blazek 2015, sec. 5.3.3; Mavriplis 2003): in cell i, find the gradient g that
best predicts the values next door,
    phi_j - phi_i  ~  g . (x_j - x_i)      for every face neighbour j,
by minimising  sum_j w_j² (g . d_j - (phi_j - phi_i))²  with weights w_j = 1 / |d_j| (inverse
distance, so near neighbours count more). The solution is  g = A⁻¹ sum_j w_j² d_j (phi_j - phi_i)  with
the small dim x dim matrix  A = sum_j w_j² d_j d_jᵀ.  A depends only on the mesh, so every coefficient
c_j = A⁻¹ w_j² d_j is computed once; each iteration is then one sparse matrix product. A linear field is
reproduced exactly on any cell shape (tested). At a boundary face the "neighbour" is the boundary
value at the face centre (from the boundary condition).

Green-Gauss (option): g = (1/V) sum_f phi_f n_f A_f with phi_f the mean of the two cells (or the
boundary value). Simpler, but exact for linear fields only on regular meshes.
"""

import numpy as np
from scipy import sparse

LEAST_SQUARES, GREEN_GAUSS = "least squares", "Green-Gauss"
METHODS = (LEAST_SQUARES, GREEN_GAUSS)


class Gradients:
    """Precomputed gradient operator: gradient(Wc, Wb) -> (n_vars, dim, C).

    Wc: cell values (n_vars, C); Wb: boundary face values (n_vars, n_boundary_faces).
    """

    def __init__(self, geom, method=LEAST_SQUARES):
        if method not in METHODS:
            raise ValueError(f"Unknown gradient method '{method}'; use one of {', '.join(METHODS)}.")
        self.geom, self.method = geom, method
        self.matrix = self._least_squares(geom) if method == LEAST_SQUARES else self._green_gauss(geom)

    @staticmethod
    def _least_squares(g):
        """Sparse (dim*C) x (C + B) matrix M with  gradient = M @ [cell values, boundary values]."""
        C, B, dim = g.n_cells, g.n_boundary, g.dim
        own_i, nb_i = g.owner[:g.n_interior], g.neighbour
        own_b = g.boundary_owner
        # Each "pair" is (cell, other value column, offset d = x_other - x_cell)
        cells = np.concatenate([own_i, nb_i, own_b])
        others = np.concatenate([nb_i, own_i, C + np.arange(B)])
        d_int = g.cell_centres[nb_i] - g.cell_centres[own_i]
        d_bnd = g.face_centres[g.boundary_faces] - g.cell_centres[own_b]
        d = np.concatenate([d_int, -d_int, d_bnd])                  # (P, dim) [m]
        w2 = 1.0 / np.einsum("pk,pk->p", d, d)                       # inverse-distance weights squared
        A = np.zeros((C, dim, dim))
        for a in range(dim):
            for b in range(dim):
                A[:, a, b] = np.bincount(cells, w2 * d[:, a] * d[:, b], minlength=C)
        coeff = np.einsum("pab,pb->pa", np.linalg.inv(A)[cells], w2[:, None] * d)   # (P, dim) [1/m]
        rows, cols, vals = [], [], []
        for k in range(dim):
            rows += [k * C + cells, k * C + cells]
            cols += [others, cells]
            vals += [coeff[:, k], -coeff[:, k]]
        return sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                                 shape=(dim * C, C + B))

    @staticmethod
    def _green_gauss(g):
        """Sparse matrix of the Green-Gauss gradient with face value = mean of the two cells."""
        C, B, dim = g.n_cells, g.n_boundary, g.dim
        nI = g.n_interior
        own_i, nb_i = g.owner[:nI], g.neighbour
        S = g.normals * g.planar_areas[:, None]                      # area vectors [m²]
        V = g.planar_volumes
        rows, cols, vals = [], [], []
        for k in range(dim):
            si = S[:nI, k]
            for cell, sign in ((own_i, 1.0), (nb_i, -1.0)):          # face value 0.5 (phi_o + phi_n)
                for other in (own_i, nb_i):
                    rows.append(k * C + cell)
                    cols.append(other)
                    vals.append(sign * 0.5 * si / V[cell])
            rows.append(k * C + g.boundary_owner)
            cols.append(C + np.arange(B))
            vals.append(S[nI:, k] / V[g.boundary_owner])
        return sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                                 shape=(dim * C, C + B))

    def gradient(self, Wc, Wb):
        """Gradients (n_vars, dim, C) [unit of W per m] of cell values Wc with boundary values Wb."""
        X = np.concatenate([Wc, Wb], axis=1)                         # (n_vars, C + B)
        G = self.matrix @ X.T                                        # (dim*C, n_vars)
        return G.reshape(self.geom.dim, self.geom.n_cells, -1).transpose(2, 0, 1)

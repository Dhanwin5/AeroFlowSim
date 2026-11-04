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
GREEN_GAUSS_NODES = "Green-Gauss (node values)"
METHODS = (LEAST_SQUARES, GREEN_GAUSS, GREEN_GAUSS_NODES)


class Gradients:
    """Precomputed gradient operator: gradient(Wc, Wb) -> (n_vars, dim, C).

    Wc: cell values (n_vars, C); Wb: boundary face values (n_vars, n_boundary_faces).
    """

    def __init__(self, geom, method=LEAST_SQUARES):
        if method not in METHODS:
            raise ValueError(f"Unknown gradient method '{method}'; use one of {', '.join(METHODS)}.")
        self.geom, self.method = geom, method
        self.matrix = {LEAST_SQUARES: self._least_squares, GREEN_GAUSS: self._green_gauss,
                       GREEN_GAUSS_NODES: self._green_gauss_nodes}[method](geom)

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

    @staticmethod
    def _green_gauss_nodes(g):
        """Green-Gauss with NODE-averaged face values (Barth 1991; Mavriplis 2003): the value of a face is the mean of
        its nodes, a node's value the inverse-distance mean of the cells around it (boundary nodes: of the boundary
        face values around them). Every cell sharing a node with cell i enters its gradient (a vertex-neighbour
        stencil: about 20 cells for a tetrahedron instead of 4), which is what makes it smooth on tetrahedra.
        One sparse matrix (dim*C) x (C + B), like the other methods."""
        mesh = g.mesh
        C, B, dim, nI = g.n_cells, g.n_boundary, g.dim, g.n_interior
        N = len(mesh.nodes)
        k = 3 if dim == 3 else 2
        # (node, value column, point) triples: every cell around a node, and for boundary nodes the boundary faces
        cn = mesh.cell_nodes
        cells, slots = np.nonzero(cn >= 0)
        pn, pc, px = [cn[cells, slots]], [cells], [mesh.cell_centres[cells, :k]]
        fn = mesh.face_nodes[g.boundary_faces]
        bf, bs = np.nonzero(fn >= 0)
        pn.append(fn[bf, bs])
        pc.append(C + bf)
        px.append(mesh.face_centres[g.boundary_faces[bf], :k])
        pn, pc, px = np.concatenate(pn), np.concatenate(pc), np.concatenate(px)
        # node value = a of the weighted linear fit phi ~ a + b . (x - x_node) through those points (exact for linear
        # fields; the pseudo-Laplacian idea of Holmes & Connell 1989), weights 1 / distance
        d = px - mesh.nodes[pn, :k]
        w = 1.0 / np.maximum(np.linalg.norm(d, axis=1), 1e-300)
        P = np.column_stack([np.ones(len(pn)), d])                       # (n, k + 1)
        M = np.zeros((N, k + 1, k + 1))
        for i in range(k + 1):
            for j in range(k + 1):
                M[:, i, j] = np.bincount(pn, w * P[:, i] * P[:, j], minlength=N)
        # a node with too few or coplanar points (a corner): fall back to the weighted mean (first row only)
        good = np.linalg.cond(M) < 1e10
        Minv = np.zeros_like(M)
        Minv[good] = np.linalg.inv(M[good])
        coef = np.einsum("nj,nj->n", Minv[pn, 0, :], w[:, None] * P)    # weight of each point in its node's a
        bad = ~good[pn]
        wsum = np.bincount(pn, w, minlength=N)
        coef[bad] = (w / wsum[pn])[bad]
        node_op = sparse.csr_matrix((coef, (pn, pc)), shape=(N, C + B))
        # The flux of phi through a face, sum over its triangles t of (mean of phi on t) S_t, from the node values:
        # 2D: the edge mean times its area vector; 3D: the face's own triangles round its node mean m (as in
        # mesh._face_geometry), each (p, q, m) with its own area vector S_t, so it is exact for linear fields also on
        # non-planar quad faces. One operator per component k: (F x N) node weights times S_t,k.
        fall = mesh.face_nodes
        counts = np.count_nonzero(fall >= 0, axis=1)
        S = g.normals * g.planar_areas[:, None]
        rows, cols, vals = [], [], [[] for _ in range(dim)]
        for kk in np.unique(counts).tolist():
            sel = np.flatnonzero(counts == kk)
            nodes_f = fall[sel, :kk]
            weight = np.zeros((len(sel), kk, dim))
            if kk == 2:
                weight[:] = 0.5 * S[sel][:, None, :]
            else:
                pts = mesh.nodes[nodes_f]
                mid = pts.mean(axis=1)
                for i in range(kk):
                    St = 0.5 * np.cross(pts[:, i] - mid, pts[:, (i + 1) % kk] - mid)[:, :dim]   # triangle (i, i+1, m)
                    weight[:, i] += St / 3.0
                    weight[:, (i + 1) % kk] += St / 3.0
                    weight += (St / (3.0 * kk))[:, None, :]          # the mean node m shares among all nodes
            for i in range(kk):
                rows.append(sel)
                cols.append(nodes_f[:, i])
                for kd in range(dim):
                    vals[kd].append(weight[:, i, kd])
        rows, cols = np.concatenate(rows), np.concatenate(cols)
        V = g.planar_volumes
        own = sparse.csr_matrix((1.0 / V[g.owner], (g.owner, np.arange(g.n_faces))), shape=(C, g.n_faces))
        nbr = sparse.csr_matrix((-1.0 / V[g.neighbour], (g.neighbour, np.arange(nI))), shape=(C, g.n_faces))
        cell_sum = (own + nbr).tocsr()                               # + owner, - neighbour, divided by the volume
        blocks = []
        for kd in range(dim):
            flux = sparse.csr_matrix((np.concatenate(vals[kd]), (rows, cols)), shape=(g.n_faces, N))
            blocks.append(cell_sum @ flux @ node_op)
        return sparse.vstack(blocks).tocsr()

    def gradient(self, Wc, Wb):
        """Gradients (n_vars, dim, C) [unit of W per m] of cell values Wc with boundary values Wb."""
        X = np.concatenate([Wc, Wb], axis=1)                         # (n_vars, C + B)
        G = self.matrix @ X.T                                        # (dim*C, n_vars)
        return G.reshape(self.geom.dim, self.geom.n_cells, -1).transpose(2, 0, 1)

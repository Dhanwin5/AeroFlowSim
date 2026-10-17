# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh containers.

Mesh1D: a list of node positions along x (used by all current cases).
Mesh2D: a structured grid of nodes (not used by any case yet; it exists so the GUI
        can already draw 2D meshes when the first 2D case is added).
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class Mesh1D:
    """A 1D mesh: node positions along the axis."""

    x: np.ndarray  # node positions [m], increasing

    @property
    def n_nodes(self) -> int:
        """Number of nodes."""
        return len(self.x)

    @property
    def n_cells(self) -> int:
        """Number of cells (intervals between neighbouring nodes)."""
        return len(self.x) - 1

    @property
    def dx(self) -> np.ndarray:
        """Spacing between neighbouring nodes [m] (length n_nodes - 1)."""
        return np.diff(self.x)

    @property
    def xc(self) -> np.ndarray:
        """Cell centres [m] (length n_nodes - 1), halfway between neighbouring nodes.

        Finite-volume cases store one value per cell; the nodes are then the cell faces.
        """
        return 0.5 * (self.x[:-1] + self.x[1:])

    def positions(self, n_values: int) -> np.ndarray:
        """x positions [m] for a field with n_values entries: nodes or cell centres.

        Lets plots and CSV files handle node-based fields (e.g. the heat demo) and
        cell-based fields (finite-volume cases) with the same code.
        """
        if n_values == self.n_nodes:
            return self.x
        if n_values == self.n_cells:
            return self.xc
        raise ValueError(f"A field with {n_values} values does not fit this mesh "
                         f"({self.n_nodes} nodes, {self.n_cells} cells).")


@dataclass
class Mesh2D:
    """A structured 2D mesh: node coordinates stored as 2D arrays of shape (ni, nj).

    Node (i, j) sits at (x[i, j], y[i, j]). Grid lines run along i (fixed j) and along j (fixed i).
    For an axisymmetric nozzle, x is the axial position and y the radius.
    """

    x: np.ndarray  # node x coordinates [m], shape (ni, nj)
    y: np.ndarray  # node y coordinates [m], shape (ni, nj)

    @property
    def n_nodes(self) -> int:
        """Number of nodes."""
        return self.x.size

    @property
    def n_cells(self) -> int:
        """Number of quadrilateral cells."""
        ni, nj = self.x.shape
        return (ni - 1) * (nj - 1)

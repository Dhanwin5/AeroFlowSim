"""Mesh containers.

For now there is only a 1D mesh (a list of node positions along x).
A 2D mesh class will be added here when a 2D case needs it.
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
    def dx(self) -> np.ndarray:
        """Spacing between neighbouring nodes [m] (length n_nodes - 1)."""
        return np.diff(self.x)

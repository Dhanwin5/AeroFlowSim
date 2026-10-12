"""Shared geometry code for nozzle and duct cases.

Every geometry source produces the same object, a WallProfile: the wall radius r(x) along
the axis, in SI metres. Cases only use that object and never care where it came from.

    Level 1 (now):   built-in parametric shapes, made by each case from its Setup inputs.
    Level 2 (later): wall profile read from a user CSV file (x_mm, r_mm) - will be added here.
    Level 3 (later): 2D CAD import meshed with Gmsh - will also produce a WallProfile.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class WallProfile:
    """Wall radius along the axis: r(x). Also used for the "shape view" of 1D results."""

    x: np.ndarray  # axial positions [m], strictly increasing
    r: np.ndarray  # wall radius at those positions [m], >= 0

    def __post_init__(self):
        self.x = np.asarray(self.x, dtype=float)
        self.r = np.asarray(self.r, dtype=float)
        if self.x.ndim != 1 or self.x.shape != self.r.shape or len(self.x) < 2:
            raise ValueError("A wall profile needs two equally long lists x and r (at least 2 points).")
        if np.any(np.diff(self.x) <= 0.0):
            raise ValueError("The x positions of a wall profile must be strictly increasing.")
        if np.any(self.r < 0.0):
            raise ValueError("A wall radius cannot be negative.")

    def radius_at(self, x):
        """Wall radius [m] at positions x [m], by linear interpolation."""
        return np.interp(x, self.x, self.r)

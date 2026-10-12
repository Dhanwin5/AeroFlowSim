"""Shared geometry code for nozzle and duct cases.

Every geometry source produces the same object, a WallProfile: the wall radius r(x) along
the axis, in SI metres. Cases only use that object and never care where it came from.

    Level 1 (now):   built-in parametric shapes, e.g. conical_nozzle() below.
    Level 2 (now):   wall profile read from a user CSV file (x_mm, r_mm): read_profile_csv().
    Level 3 (later): 2D CAD import meshed with Gmsh - will also produce a WallProfile.
"""

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator

CSV_HEADER = ["x_mm", "r_mm"]  # required first line of a profile CSV file
CSV_MIN_POINTS = 5             # fewer points cannot describe a nozzle sensibly


@dataclass
class WallProfile:
    """Wall radius along the axis: r(x). Also used for the "shape view" of 1D results.

    interpolation: how r is computed between the given points
        "linear"  straight lines (exact for cones and cylinders; corners stay sharp)
        "pchip"   smooth monotone cubic (PCHIP): passes through every point and never
                  overshoots, i.e. never goes below the smallest or above the largest
                  neighbouring radius - so the throat is never narrower than the data says.
    """

    x: np.ndarray  # axial positions [m], strictly increasing
    r: np.ndarray  # wall radius at those positions [m], >= 0
    interpolation: str = "linear"

    def __post_init__(self):
        self.x = np.asarray(self.x, dtype=float)
        self.r = np.asarray(self.r, dtype=float)
        if self.x.ndim != 1 or self.x.shape != self.r.shape or len(self.x) < 2:
            raise ValueError("A wall profile needs two equally long lists x and r (at least 2 points).")
        if np.any(np.diff(self.x) <= 0.0):
            raise ValueError("The x positions of a wall profile must be strictly increasing.")
        if np.any(self.r < 0.0):
            raise ValueError("A wall radius cannot be negative.")
        if self.interpolation not in ("linear", "pchip"):
            raise ValueError(f"Unknown interpolation '{self.interpolation}' (use 'linear' or 'pchip').")
        self._pchip = PchipInterpolator(self.x, self.r) if self.interpolation == "pchip" else None

    def radius_at(self, x):
        """Wall radius [m] at positions x [m] (inside [x_start, x_end])."""
        if self._pchip is not None:
            return self._pchip(np.clip(x, self.x[0], self.x[-1]))
        return np.interp(x, self.x, self.r)

    def area_at(self, x):
        """Cross-section area pi r² [m²] at positions x [m]."""
        return math.pi * self.radius_at(x) ** 2

    @property
    def x_throat(self) -> float:
        """Position [m] of the smallest radius (the first one, if several are equal)."""
        return float(self.x[np.argmin(self.r)])

    @property
    def r_throat(self) -> float:
        """Smallest radius [m]. Both interpolations never undershoot, so it is a data point."""
        return float(self.r.min())

    @property
    def length(self) -> float:
        """Axial length [m]."""
        return float(self.x[-1] - self.x[0])


# ---- Level 1: parametric shapes --------------------------------------------------------------

def conical_nozzle(d_inlet, L_inlet, half_angle_conv, d_throat, half_angle_div, d_exit):
    """Conical converging-diverging nozzle with a straight inlet and a sharp throat.

    d_inlet, d_throat, d_exit   diameters [m]
    L_inlet                     length of the straight inlet section [m] (may be 0)
    half_angle_conv/div         cone half-angles [rad]
    The cone lengths follow from the diameters and angles. Starts at x = 0.
    """
    if not d_throat < d_inlet:
        raise ValueError("The throat diameter must be smaller than the inlet diameter.")
    if not d_throat < d_exit:
        raise ValueError("The throat diameter must be smaller than the exit diameter.")
    if not (0.0 < half_angle_conv < 0.5 * math.pi and 0.0 < half_angle_div < 0.5 * math.pi):
        raise ValueError("The cone half-angles must be between 0 and 90 degrees.")
    r_in, r_t, r_e = 0.5 * d_inlet, 0.5 * d_throat, 0.5 * d_exit   # [m]
    L_conv = (r_in - r_t) / math.tan(half_angle_conv)               # [m]
    L_div = (r_e - r_t) / math.tan(half_angle_div)                  # [m]
    x = [0.0, L_inlet, L_inlet + L_conv, L_inlet + L_conv + L_div]
    r = [r_in, r_in, r_t, r_e]
    if L_inlet <= 0.0:                                              # no straight inlet section
        x, r = x[1:], r[1:]
    return WallProfile(x=x, r=r, interpolation="linear")


# ---- Level 2: profile from a CSV file ---------------------------------------------------------

def read_profile_csv(path):
    """Read a wall profile from a CSV file with header "x_mm,r_mm" (millimetres) -> WallProfile [m].

    The values are checked; any problem raises ValueError with a message that says what to fix.
    Interpolation between the points is PCHIP (smooth, no overshoot).
    """
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Profile file not found: {path}. Check the file name or upload the file again.")
    with open(path, newline="", encoding="utf-8-sig") as file:   # utf-8-sig: ignore an Excel BOM
        rows = [row for row in csv.reader(file) if any(cell.strip() for cell in row)]
    return profile_from_rows(rows, source=path.name)


def profile_from_rows(rows, source="the file"):
    """Check CSV rows (header first) and turn them into a PCHIP WallProfile in metres."""
    if not rows:
        raise ValueError(f"{source} is empty. It needs a header line 'x_mm,r_mm' and at least "
                         f"{CSV_MIN_POINTS} rows of numbers.")
    header = [cell.strip() for cell in rows[0]]
    if header != CSV_HEADER:
        raise ValueError(f"The first line of {source} must be exactly 'x_mm,r_mm' "
                         f"(found '{','.join(rows[0])}'). Put the axial position in mm in the first "
                         "column and the wall radius (not the diameter) in mm in the second.")
    x_mm, r_mm = [], []
    for line_number, row in enumerate(rows[1:], start=2):           # line 1 is the header
        if len(row) != 2:
            raise ValueError(f"Line {line_number} of {source} has {len(row)} values; every line "
                             "needs exactly two: x_mm,r_mm.")
        try:
            x, r = float(row[0]), float(row[1])
        except ValueError:
            raise ValueError(f"Line {line_number} of {source} ('{','.join(row)}') is not two numbers. "
                             "Use a dot as decimal separator and a comma between the columns.") from None
        if not (math.isfinite(x) and math.isfinite(r)):
            raise ValueError(f"Line {line_number} of {source} contains an infinite or NaN value.")
        if r <= 0.0:
            raise ValueError(f"Line {line_number} of {source}: radius r = {r:g} mm. Every radius must "
                             "be larger than 0 (the wall cannot touch or cross the axis).")
        if x_mm and x <= x_mm[-1]:
            raise ValueError(f"Line {line_number} of {source}: x = {x:g} mm is not larger than the "
                             f"previous line (x = {x_mm[-1]:g} mm). The x_mm column must increase "
                             "from top to bottom: sort the rows and remove duplicate x values.")
        x_mm.append(x)
        r_mm.append(r)
    if len(x_mm) < CSV_MIN_POINTS:
        raise ValueError(f"{source} has only {len(x_mm)} data points; at least {CSV_MIN_POINTS} "
                         "are needed to describe the nozzle.")
    return WallProfile(x=np.array(x_mm) * 1e-3, r=np.array(r_mm) * 1e-3, interpolation="pchip")


def write_profile_csv(path, profile, x_values):
    """Write r(x) at the positions x_values [m] as a profile CSV file (x_mm,r_mm)."""
    x_values = np.asarray(x_values, dtype=float)
    data = np.column_stack([x_values * 1e3, profile.radius_at(x_values) * 1e3])
    np.savetxt(path, data, delimiter=",", header=",".join(CSV_HEADER), comments="", fmt="%.6f")


# ---- key numbers of a profile -----------------------------------------------------------------

def profile_summary(profile) -> dict:
    """Key geometry numbers {name: (value, unit)} of a (nozzle) wall profile."""
    d_throat = 2.0 * profile.r_throat   # [m]
    d_exit = 2.0 * float(profile.r[-1])  # [m]
    return {
        "d_inlet": (2.0 * float(profile.r[0]), "m"),
        "d_throat": (d_throat, "m"),
        "d_exit": (d_exit, "m"),
        "area_ratio": ((d_exit / d_throat) ** 2, "-"),
        "length": (profile.length, "m"),
        "x_throat": (profile.x_throat, "m"),
    }

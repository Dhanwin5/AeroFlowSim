# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Any body outline from a coordinates file.

Accepted files (any unit; the outline is scaled to the chosen reference length):
    Selig .dat     line 1 = name; then "x y" per line, going round the body once (usually from the
                   trailing edge over the upper surface to the leading edge and back below).
    Lednicer .dat  line 1 = name; line 2 = the number of upper and lower points (e.g. "61. 61.");
                   then the upper surface from the leading to the trailing edge, then the lower one.
    CSV / text     two columns x, y separated by a comma, semicolon, tab or spaces; an optional
                   header line (any text) is skipped.

What is done with the points, in this order:
    1. repeated neighbouring points are removed;
    2. axisymmetric bodies given as only their r >= 0 half are mirrored about the axis;
    3. an open outline is closed with a straight segment (e.g. a blunt trailing edge) - with a note;
    4. the outline is made counter-clockwise, moved so that it starts at x = 0, and scaled so that
       its length along x is the reference length;
    5. sharp corners (the outline turns by more than 30 degrees) are found, the leading and
       trailing edges (smallest / largest x) are marked for refinement;
    6. a crossing outline (self-intersection) gives a warning; such a body cannot be meshed.
"""

import math
import re
from pathlib import Path

import numpy as np

from aeroflowsim.shapes.profile import CLOSE_TOLERANCE, ShapeProfile, turning_corners

PROJECT_DIR = Path(__file__).resolve().parents[2]   # relative file names start here
MIN_POINTS = 3


def _numbers(line):
    """The numbers on one line (separated by commas, semicolons, tabs or spaces), or None if it has text."""
    parts = [p for p in re.split(r"[,;\s]+", line.strip()) if p]
    try:
        return [float(p) for p in parts]
    except ValueError:
        return None


def read_coordinates(path):
    """Read a coordinates file -> (points (N, 2) as given, format name). ValueError with a clear message."""
    path = Path(path)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    if not path.is_file():
        raise ValueError(f"Coordinates file not found: {path}. Check the name or upload the file again.")
    lines = [line for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if line.strip()]
    rows = []
    for number, line in enumerate(lines, start=1):
        values = _numbers(line)
        if values is None:
            if rows:
                raise ValueError(f"Line {number} of {path.name} ('{line.strip()}') is not two numbers. "
                                 "Only the first line may be a name or header.")
            continue                                   # name / header line before the numbers
        if len(values) != 2:
            raise ValueError(f"Line {number} of {path.name} has {len(values)} numbers; every line needs "
                             "exactly two: x y.")
        rows.append(values)
    if len(rows) < MIN_POINTS:
        raise ValueError(f"{path.name} has only {len(rows)} coordinate lines; at least {MIN_POINTS} are needed.")
    rows = np.array(rows)
    # Lednicer: the first number line holds the point counts of the two surfaces (whole numbers > 1).
    n_up, n_low = rows[0]
    if n_up > 1.0 and n_low > 1.0 and n_up == int(n_up) and n_low == int(n_low) and \
            int(n_up) + int(n_low) == len(rows) - 1:
        upper, lower = rows[1:1 + int(n_up)], rows[1 + int(n_up):]
        return np.vstack([upper[::-1], lower[1:]]), "Lednicer"   # TE -> upper -> LE -> lower -> TE
    return rows, "Selig/CSV"


def profile(inputs):
    points, kind = read_coordinates(inputs["file"])
    axisymmetric = inputs["body_type"] == "Axisymmetric"
    notes = []
    size = float(np.ptp(points, axis=0).max())
    if size <= 0.0:
        raise ValueError("All points in the coordinates file are the same.")
    step = np.linalg.norm(np.diff(points, axis=0), axis=1)
    points = points[np.r_[True, step > CLOSE_TOLERANCE * size]]          # 1. no repeated neighbours

    if axisymmetric and points[:, 1].min() >= -1e-9 * size:              # 2. only the r >= 0 half given
        if abs(points[0, 1]) > 1e-6 * size or abs(points[-1, 1]) > 1e-6 * size:
            raise ValueError("An axisymmetric half outline (r >= 0) must start and end on the axis (r = 0), "
                             "from the nose to the base.")
        points[[0, -1], 1] = 0.0
        points = np.vstack([points, points[-2:0:-1] * [1.0, -1.0]])     # add the mirrored lower half
        notes.append("Only the r >= 0 half was given: it was mirrored about the axis.")

    gap = float(np.linalg.norm(points[-1] - points[0]))                  # 3. close the outline
    if gap <= CLOSE_TOLERANCE * size:
        points = points[:-1]
    else:
        notes.append(f"The outline was open (gap {100 * gap / size:.3g} % of its size between the first "
                     "and last point): it was closed with a straight segment.")

    x0, x1 = points[:, 0].min(), points[:, 0].max()                      # 4. move and scale
    if x1 - x0 <= 0.0:
        raise ValueError("The outline has no length along x.")
    L = inputs["reference_length"]                                       # [m]
    points = (points - [x0, 0.0]) * (L / (x1 - x0))

    corners = turning_corners(points)                                    # 5. corners, LE and TE
    refine = np.zeros(len(points), dtype=bool)
    refine[[int(np.argmin(points[:, 0])), int(np.argmax(points[:, 0]))]] = True
    if axisymmetric:
        area = math.pi * float(np.abs(points[:, 1]).max()) ** 2           # largest cross-section [m²]
    else:
        area = L * 1.0                                                   # [m²] per metre depth
    outline = ShapeProfile(points, reference_length=L, reference_area=area, axisymmetric=axisymmetric,
                           corners=corners, refine=refine,
                           name=f"{Path(inputs['file']).stem} ({kind}, {len(points)} points)", warnings=notes)
    crossings = outline.self_intersections()                             # 6. crossing outline
    if crossings:
        outline.warnings.append(f"The outline crosses itself ({crossings} crossing(s)). Such a body cannot be "
                                "meshed: check the order of the points in the file.")
    return outline

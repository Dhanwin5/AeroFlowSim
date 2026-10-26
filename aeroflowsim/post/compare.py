# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Two results compared: difference fields, key-number tables, XY overlays.

difference(a, b, field) = field of A minus field of B, per cell of A's mesh. On the same mesh (same mesh
fingerprint) it is exact; on different meshes B is interpolated onto A's cell centres first (inverse distance,
post/sampling.py), and the result says so, because a difference then also contains interpolation error.
"""

from dataclasses import dataclass

import numpy as np

from aeroflowsim.post.fields import field_info, field_values
from aeroflowsim.post.sampling import interpolate_cells


def same_mesh(a, b) -> bool:
    if a.mesh is b.mesh:
        return True
    from aeroflowsim.euler.setup import mesh_signature
    return a.mesh.n_cells == b.mesh.n_cells and mesh_signature(a.mesh) == mesh_signature(b.mesh)


@dataclass
class Difference:
    values: np.ndarray       # (C_A,) A - B [SI]
    unit: str
    label: str
    interpolated: bool       # True if B was interpolated onto A's mesh
    largest: float           # max |A - B|
    rms: float               # volume-weighted RMS of A - B


def difference(a, b, name) -> Difference:
    """A - B of one field on A's mesh (see the module docstring)."""
    fa = field_values(a, name)
    fb = field_values(b, name)
    interpolated = not same_mesh(a, b)
    if interpolated:
        fb = interpolate_cells(b.geom.cell_centres, fb[None, :], a.geom.cell_centres)[0]
    d = fa - fb
    V = a.geom.volumes
    info = field_info(a, name)
    return Difference(d, info.unit, f"{info.label}: {a.name} - {b.name}", interpolated, float(np.abs(d).max()),
                      float(np.sqrt(np.sum(d * d * V) / np.sum(V))))


def key_number_table(a, b) -> list:
    """[(name, value A, value B, unit, change %)] of the key numbers both results have."""
    rows = []
    for k, (va, unit) in a.key_numbers.items():
        if k in b.key_numbers:
            vb = b.key_numbers[k][0]
            change = 100.0 * (va - vb) / abs(vb) if vb else float("nan")
            rows.append((k, float(va), float(vb), unit, change))
    return rows

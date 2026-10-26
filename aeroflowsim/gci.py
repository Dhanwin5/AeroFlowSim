# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Grid Convergence Index (GCI): how far a result on a finite mesh is from the mesh-independent answer.

Roache's method (Roache 1994, J. Fluids Eng. 116; Roache 1998, "Verification and Validation in
Computational Science and Engineering"), in the form of the ASME V&V 20 / Celik et al. (2008, J. Fluids
Eng. 130, 078001) procedure. Three meshes with cell sizes h1 < h2 < h3 (fine, medium, coarse) give a
quantity phi1, phi2, phi3. With refinement ratios r21 = h2/h1, r32 = h3/h2 and e21 = phi2 - phi1,
e32 = phi3 - phi2:

    observed order   p = | ln|e32/e21| + q(p) | / ln r21,    q(p) = ln((r21^p - s) / (r32^p - s)),  s = sign(e32/e21)
                     (for a constant ratio r21 = r32, q = 0 and p = ln|e32/e21| / ln r)
    extrapolated     phi_ext = (r21^p phi1 - phi2) / (r21^p - 1)                 (Richardson)
    GCI fine         GCI21 = Fs |e21 / phi1| / (r21^p - 1)        Fs = 1.25 (safety factor for 3 meshes)
    GCI coarse       GCI32 = Fs |e32 / phi2| / (r32^p - 1)
    asymptotic range GCI32 / (r21^p GCI21) ~ 1

Oscillatory convergence (s < 0) is reported as such: the order then means little and the GCI is a rough bound.
With only two meshes, an assumed (formal) order replaces the observed one (two_mesh()).
"""

import math
from dataclasses import dataclass

SAFETY_THREE_MESHES = 1.25   # Fs for three or more meshes (Roache 1998)
SAFETY_TWO_MESHES = 3.0      # Fs for two meshes and an assumed order


@dataclass
class GCIResult:
    """The outcome of a three-mesh (or two-mesh) study."""

    p: float                     # observed (or assumed) order of accuracy [-]
    extrapolated: float          # Richardson-extrapolated value (same unit as phi)
    gci_fine: float              # GCI of the finest mesh [fraction, 0.01 = 1 %]
    gci_coarse: float | None     # GCI of the medium mesh [fraction] (None for two meshes)
    asymptotic_ratio: float | None   # ~1 in the asymptotic range (None for two meshes)
    oscillatory: bool            # True if the changes alternate in sign
    r21: float
    r32: float | None
    phi: tuple                   # (fine, medium[, coarse]) values

    @property
    def in_asymptotic_range(self) -> bool:
        """True if GCI32 / (r^p GCI21) lies within 10 % of 1 (and the convergence is monotone)."""
        return (self.asymptotic_ratio is not None and not self.oscillatory
                and abs(self.asymptotic_ratio - 1.0) <= 0.1)

    def summary(self, unit="") -> str:
        """One line in plain words."""
        u = f" {unit}" if unit else ""
        text = (f"observed order {self.p:.2f}, extrapolated value {self.extrapolated:.6g}{u}, "
                f"GCI fine {100 * self.gci_fine:.3g} %")
        if self.gci_coarse is not None:
            text += f", GCI coarse {100 * self.gci_coarse:.3g} %"
        if self.asymptotic_ratio is not None:
            text += f", asymptotic ratio {self.asymptotic_ratio:.3f}"
        if self.oscillatory:
            text += " (oscillatory convergence)"
        return text


def _order(e21, e32, r21, r32, iterations=100):
    """Observed order p by fixed-point iteration of Celik et al. (2008) eq. 3-5."""
    s = 1.0 if e32 / e21 > 0 else -1.0
    p = abs(math.log(abs(e32 / e21))) / math.log(r21)
    for _ in range(iterations):
        q = math.log((r21**p - s) / (r32**p - s)) if (r21**p - s) > 0 and (r32**p - s) > 0 else 0.0
        p_new = abs(math.log(abs(e32 / e21)) + q) / math.log(r21)
        if abs(p_new - p) < 1e-12:
            return p_new
        p = p_new
    return p


def three_mesh(h, phi, safety=SAFETY_THREE_MESHES):
    """GCI study from three meshes. h = (h_fine, h_medium, h_coarse) cell sizes (or 1/sqrt(cells) in 2D),
    phi = the quantity on each, in the same order."""
    h1, h2, h3 = (float(v) for v in h)
    f1, f2, f3 = (float(v) for v in phi)
    if not h1 < h2 < h3:
        raise ValueError("Give the cell sizes from fine to coarse: h_fine < h_medium < h_coarse.")
    r21, r32 = h2 / h1, h3 / h2
    e21, e32 = f2 - f1, f3 - f2
    if e21 == 0.0 or e32 == 0.0:
        raise ValueError("The quantity did not change between two meshes: no order can be computed.")
    p = _order(e21, e32, r21, r32)
    ext = (r21**p * f1 - f2) / (r21**p - 1.0)
    gci21 = safety * abs(e21 / f1) / (r21**p - 1.0)
    gci32 = safety * abs(e32 / f2) / (r32**p - 1.0)
    return GCIResult(p, ext, gci21, gci32, gci32 / (r21**p * gci21), e32 / e21 < 0, r21, r32, (f1, f2, f3))


def two_mesh(h, phi, p, safety=SAFETY_TWO_MESHES):
    """GCI from two meshes with an assumed order p (e.g. the formal order 2): h = (fine, coarse)."""
    h1, h2 = (float(v) for v in h)
    f1, f2 = (float(v) for v in phi)
    r21 = h2 / h1
    ext = (r21**p * f1 - f2) / (r21**p - 1.0)
    gci = safety * abs((f2 - f1) / f1) / (r21**p - 1.0)
    return GCIResult(p, ext, gci, None, None, False, r21, None, (f1, f2))


def observed_order(h, errors):
    """Observed order between consecutive meshes from KNOWN errors (e.g. MMS): ln(e_c/e_f) / ln(h_c/h_f).
    h and errors listed from coarse to fine; returns one order per pair."""
    return [math.log(errors[i] / errors[i + 1]) / math.log(h[i] / h[i + 1]) for i in range(len(h) - 1)]

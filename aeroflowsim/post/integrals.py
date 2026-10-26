# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Surface and volume integrals, flux balance, forces and moments.

Surface element dA: planar 2D results are per metre of depth (dA = dl x 1 m); axisymmetric results are taken
round the whole circle (dA = 2 pi r dl). Each segment of a SurfaceData is integrated with 2-point Gauss
quadrature of the linear reconstruction (exact for linear fields, also with the 2 pi r weight); on a boundary the
value is the boundary condition's face state (constant per face).

Surface operations (f = the chosen field, n = the surface normal, V = velocity):
    area            A = int dA                                      [m²]
    integral        int f dA                                        [unit m²]
    area_weighted   int f dA / A
    mass_weighted   int f rho |V.n| dA / int rho |V.n| dA           (Fluent's definition: |V.n|, so a surface
                                                                     with flow in both directions still averages)
    mass_flow       int rho V.n dA                                  [kg/s], positive along the normal
    flux            int F_q . n dA of a conserved quantity q = mass, x_momentum, y_momentum, energy
    min, max        smallest / largest sample value
    std_dev         area-weighted standard deviation sqrt(int (f - f_avg)² dA / A)
On a BOUNDARY, mass_flow and flux use the solver's own numerical boundary fluxes (Solution.boundary_flux), so
the report equals the solver's mass flow to round-off.

Volume operations over a region (whole domain, box, circle, polygon such as a workspace face; cells whose
centroid is inside): volume [m³] (planar per metre of depth, axisymmetric full circle), mass [kg],
volume_weighted average, min, max.
"""

import math

import numpy as np

from aeroflowsim.post.fields import FieldError, boundary_face_values, field_info, field_values
from aeroflowsim.post.sampling import values_at
from aeroflowsim.post.surfaces import evaluate_surface

SURFACE_OPERATIONS = {
    "area": "Area", "integral": "Integral", "area_weighted": "Area-weighted average",
    "mass_weighted": "Mass-weighted average", "mass_flow": "Mass flow rate", "flux": "Flux of a conserved quantity",
    "min": "Minimum", "max": "Maximum", "std_dev": "Standard deviation",
}
VOLUME_OPERATIONS = {"volume": "Volume", "mass": "Mass", "volume_weighted": "Volume-weighted average",
                     "min": "Minimum", "max": "Maximum"}
CONSERVED = {"mass": (0, "kg/s"), "x_momentum": (1, "N"), "y_momentum": (2, "N"), "energy": (3, "W")}
NEEDS_FIELD = {"integral", "area_weighted", "mass_weighted", "min", "max", "std_dev", "volume_weighted"}
GAUSS = (0.5 - 0.5 / math.sqrt(3.0), 0.5 + 0.5 / math.sqrt(3.0))


def _quadrature(sol, data):
    """Gauss points: (points (2n, 2), cells (2n,), weights dA (2n,), segment index (2n,))."""
    pts, w = [], []
    L = data.lengths
    for t in GAUSS:
        p = data.a + t * (data.b - data.a)
        pts.append(p)
        dA = 0.5 * L * (2.0 * math.pi * np.abs(p[:, 1]) if sol.axisymmetric else 1.0)
        w.append(dA)
    seg = np.concatenate([np.arange(data.n)] * 2)
    return np.concatenate(pts), np.concatenate([data.cells] * 2), np.concatenate(w), seg


def _surface_values(sol, data, name, pts, cells, seg):
    """Field values at the quadrature points: boundary faces use the face state, lines the reconstruction."""
    if data.on_boundary:
        return boundary_face_values(sol, name)[data.faces][seg]
    return values_at(sol, name, pts, cells)


def _velocity_normal(sol, data, pts, cells, seg):
    rho = _surface_values(sol, data, "rho", pts, cells, seg)
    u = _surface_values(sol, data, "u", pts, cells, seg)
    v = _surface_values(sol, data, "v", pts, cells, seg)
    n = data.normals[seg]
    return rho, u * n[:, 0] + v * n[:, 1]


def surface_integral(sol, surface, operation, field=None, quantity="mass"):
    """Value of a surface operation (see the module docstring) in SI units, and its unit: (value, unit)."""
    if operation not in SURFACE_OPERATIONS:
        raise ValueError(f"Unknown surface operation '{operation}'; use one of {', '.join(SURFACE_OPERATIONS)}.")
    if operation in NEEDS_FIELD and not field:
        raise ValueError(f"'{SURFACE_OPERATIONS[operation]}' needs a field.")
    data = evaluate_surface(sol, surface)
    if surface.type == "point":
        if operation in ("min", "max", "area_weighted", "mass_weighted", "integral"):
            v = values_at(sol, field, data.seeds, data.cells)[0]
            return float(v), field_info(sol, field).unit
        raise ValueError(f"'{SURFACE_OPERATIONS[operation]}' needs a line or boundary, not a point.")
    if data.n == 0:
        raise ValueError(f"Surface '{surface.name}' does not cross the mesh.")
    unit = field_info(sol, field).unit if field else ""
    if operation in ("mass_flow", "flux") and data.on_boundary:
        k, flux_unit = CONSERVED["mass" if operation == "mass_flow" else quantity]
        flux = sol.boundary_flux[k, data.faces] * sol.full_circle
        return float(flux.sum()), flux_unit
    pts, cells, w, seg = _quadrature(sol, data)
    if operation == "area":
        return float(w.sum()), "m²"
    if operation in ("mass_flow", "flux"):
        rho, un = _velocity_normal(sol, data, pts, cells, seg)
        if operation == "mass_flow" or quantity == "mass":
            return float(np.sum(rho * un * w)), "kg/s"
        k, flux_unit = CONSERVED[quantity]
        n = data.normals[seg]
        p = _surface_values(sol, data, "p", pts, cells, seg)
        if quantity == "x_momentum":
            u = _surface_values(sol, data, "u", pts, cells, seg)
            q = rho * u * un + p * n[:, 0]
        elif quantity == "y_momentum":
            v = _surface_values(sol, data, "v", pts, cells, seg)
            q = rho * v * un + p * n[:, 1]
        else:
            h0 = _surface_values(sol, data, "h0", pts, cells, seg)
            q = rho * un * h0
        return float(np.sum(q * w)), flux_unit
    f = _surface_values(sol, data, field, pts, cells, seg)
    if operation == "min":
        return float(np.nanmin(f)), unit
    if operation == "max":
        return float(np.nanmax(f)), unit
    if operation == "integral":
        return float(np.sum(f * w)), _times_area(unit)
    if operation == "area_weighted":
        return float(np.sum(f * w) / np.sum(w)), unit
    if operation == "std_dev":
        mean = np.sum(f * w) / np.sum(w)
        return float(np.sqrt(np.sum((f - mean) ** 2 * w) / np.sum(w))), unit
    rho, un = _velocity_normal(sol, data, pts, cells, seg)
    m = rho * np.abs(un) * w
    if np.sum(m) <= 0.0:
        raise ValueError(f"No mass flows through '{surface.name}': a mass-weighted average is not defined there.")
    return float(np.sum(f * m) / np.sum(m)), unit


def _times_area(unit):
    if unit in ("", "-"):
        return "m²"
    return f"{unit} m²"


# ---- volume -----------------------------------------------------------------------------------------

def region_cells(sol, region=None) -> np.ndarray:
    """Boolean (C,) mask of the cells whose centroid is inside the region.

    region: None / {"type": "domain"}; {"type": "box", "min": (x, y), "max": (x, y)};
    {"type": "circle", "centre": (x, y), "radius": r}; {"type": "polygon", "points": [(x, y), ...]} [m].
    """
    c = sol.geom.cell_centres[:, :2]
    if not region or region.get("type", "domain") == "domain":
        return np.ones(len(c), dtype=bool)
    kind = region["type"]
    if kind == "box":
        lo, hi = np.asarray(region["min"], float), np.asarray(region["max"], float)
        return np.all((c >= np.minimum(lo, hi)) & (c <= np.maximum(lo, hi)), axis=1)
    if kind == "circle":
        return np.linalg.norm(c - np.asarray(region["centre"], float), axis=1) <= float(region["radius"])
    if kind == "polygon":
        from matplotlib.path import Path as MplPath
        return MplPath(np.asarray(region["points"], float)).contains_points(c)
    raise ValueError(f"Unknown region type '{kind}'; use domain, box, circle or polygon.")


def cell_volumes(sol) -> np.ndarray:
    """(C,) volume of every cell [m³]: planar per metre of depth, axisymmetric round the full circle."""
    return sol.geom.volumes * sol.full_circle


def volume_integral(sol, operation, field=None, region=None):
    """(value, unit) of a volume operation over a region (see region_cells)."""
    if operation not in VOLUME_OPERATIONS:
        raise ValueError(f"Unknown volume operation '{operation}'; use one of {', '.join(VOLUME_OPERATIONS)}.")
    mask = region_cells(sol, region)
    if not mask.any():
        raise ValueError("The region contains no cell centre.")
    V = cell_volumes(sol)[mask]
    if operation == "volume":
        return float(V.sum()), "m³"
    if operation == "mass":
        return float(np.sum(sol.fields["rho"][mask] * V)), "kg"
    if not field:
        raise ValueError(f"'{VOLUME_OPERATIONS[operation]}' needs a field.")
    f = field_values(sol, field)[mask]
    unit = field_info(sol, field).unit
    if operation == "min":
        return float(f.min()), unit
    if operation == "max":
        return float(f.max()), unit
    return float(np.sum(f * V) / V.sum()), unit


# ---- flux balance and forces ------------------------------------------------------------------------

def flux_balance(sol) -> dict:
    """Mass, momentum and energy through every boundary (outward positive) and the net imbalance (Fluent "Fluxes").

    Returns {"rows": [(patch, type, mass [kg/s], x-momentum [N], y-momentum [N], energy [W])], "net": (...),
             "relative": {mass, energy: |net| / largest inflow}, "pressure_source": axisymmetric radial pressure
             source [N] (it balances the radial momentum), "note": text}.
    Momentum fluxes include the pressure force p n A, so at a steady state the x-momentum sum is the force of the
    walls on the gas.
    """
    F = sol.boundary_flux * sol.full_circle
    rows = []
    for p in sol.mesh.patches:
        local = sol.patch_faces(p.name)
        bc = sol.conditions.get(p.name)
        rows.append((p.name, bc.label if bc else p.type, *[float(F[k, local].sum()) for k in range(4)]))
    net = tuple(float(F[k].sum()) for k in range(4))
    inflow_mass = float(-F[0][F[0] < 0].sum()) or 1.0
    inflow_energy = float(-F[3][F[3] < 0].sum()) or 1.0
    source = 0.0
    note = ""
    if sol.axisymmetric:
        source = float(np.sum(sol.W[3] * sol.geom.geometric_source[1]) * sol.full_circle)
        note = ("Axisymmetric: the radial momentum is balanced by the pressure source int p dA of the r-momentum "
                "equation (shown separately); only mass, x-momentum and energy should sum to zero over the walls' "
                "forces.")
    return {"rows": rows, "net": net, "relative": {"mass": abs(net[0]) / inflow_mass,
                                                   "energy": abs(net[3]) / inflow_energy},
            "pressure_source": source, "note": note,
            "columns": ("Boundary", "Type", "Mass [kg/s]", "x-momentum [N]", "y-momentum [N]", "Energy [W]")}


def forces_and_moments(sol, walls, moment_point=(0.0, 0.0), p_ref=None, q_ref=None, A_ref=1.0, L_ref=1.0,
                       angle_deg=None, mirror=1.0) -> dict:
    """Pressure force and moment of a set of walls (from the solver's wall fluxes p n A).

    p_ref: subtracted from the wall pressure (default: free-stream pressure for external flows, 0 otherwise);
    q_ref, A_ref, L_ref: reference values of the coefficients; angle_deg: free-stream direction for wind axes
    (default: the run's angle of attack); mirror = 2 for a half body on a symmetry plane.
    Returns body-axis forces Fx, Fy, wind-axis drag D and lift L, moment M (nose-up positive about moment_point),
    coefficients Cx, Cy, Cd, Cl, Cm and the centre of pressure x_cp on the line y = moment_point y (planar only).
    Viscous forces are zero (inviscid solver); they will be added with the Navier-Stokes solver (Phase 4).
    """
    if not walls:
        raise ValueError("Choose at least one wall.")
    p_inf, q_inf, _ = sol.reference_pressure()
    if p_ref is None:
        p_ref = p_inf if sol.kind == "external" else 0.0
    if q_ref is None:
        q_ref = q_inf if sol.kind == "external" else 1.0
    if angle_deg is None:
        angle_deg = float(sol.params.get("alpha", 0.0))
    g = sol.geom
    F = np.zeros(2)
    M = 0.0
    for name in walls:
        local = sol.patch_faces(name)
        n = g.normals[g.n_interior + local][:, :2]
        A = g.flux_areas[g.n_interior + local] * sol.full_circle
        mom = sol.boundary_flux[1:3, local].T * sol.full_circle
        f = mom - p_ref * n * A[:, None]
        F += f.sum(axis=0)
        if not sol.axisymmetric:
            r = g.face_centres[g.n_interior + local][:, :2] - np.asarray(moment_point, float)
            M -= float(np.sum(r[:, 0] * f[:, 1] - r[:, 1] * f[:, 0]))
    if sol.axisymmetric:
        F[1] = 0.0
    if mirror != 1.0:
        F = np.array([F[0] * mirror, 0.0])
        M = 0.0
    a = math.radians(angle_deg)
    drag_dir, lift_dir = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
    D, L = float(F @ drag_dir), float(F @ lift_dir)
    qA = q_ref * A_ref
    x_cp = None
    if not sol.axisymmetric and abs(F[1]) > 1e-12 * max(1.0, abs(F[0])):
        x_cp = float(moment_point[0] - M / F[1])     # where the normal force acts (M = -(x_cp - x_ref) Fy)
    unit = "N" if sol.axisymmetric else "N/m"
    return {"Fx": float(F[0]), "Fy": float(F[1]), "D": D, "L": L, "M": M, "Cx": F[0] / qA, "Cy": F[1] / qA,
            "Cd": D / qA, "Cl": L / qA, "Cm": M / (qA * L_ref), "x_cp": x_cp, "force_unit": unit,
            "moment_unit": "N m" if sol.axisymmetric else "N m/m"}


__all__ = ["SURFACE_OPERATIONS", "VOLUME_OPERATIONS", "CONSERVED", "surface_integral", "volume_integral",
           "region_cells", "cell_volumes", "flux_balance", "forces_and_moments", "FieldError"]

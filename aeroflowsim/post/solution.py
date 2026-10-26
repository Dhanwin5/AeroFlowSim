# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""One 2D / axisymmetric result, ready for post-processing: mesh, cell fields, gas and boundary conditions.

A Solution holds the cell values exactly as the solver left them (SI units) and computes, once and on
demand, what most tools need:
    geom              the solver's FVGeometry (centroids, face normals, flux areas, ...)
    W                 the primitive state [rho, u, v, p] per cell
    boundary_values   the state at every boundary face centre: the mean of the inside cell and the ghost
                      state of the boundary condition (exactly what the solver's gradients use), so wall
                      and axis values are the boundary condition's
    boundary_flux     the numerical flux x area of every boundary face for this state (the same numbers the
                      solver's mass flows and forces come from, so balances close as in the solver)
    gradients         least-squares gradients of the primitive variables (euler/gradients.py)
"""

from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import numpy as np

PRIMITIVES = ("rho", "u", "v", "p")


@dataclass
class Solution:
    """A result on a face-based mesh (see the module docstring)."""

    mesh: object                         # aeroflowsim.mesh.Mesh (2D, planar or axisymmetric)
    fields: dict                         # {name: (C,) cell values, SI}; needs rho, u, v, p
    gas: object                          # GasModel
    conditions: dict = field(default_factory=dict)   # {patch name: BoundaryCondition}
    params: dict = field(default_factory=dict)       # the inputs of the run (SI)
    info: dict = field(default_factory=dict)         # Result.info of the run
    key_numbers: dict = field(default_factory=dict)  # {name: (value, unit)}
    series: dict = field(default_factory=dict)       # residual and monitor histories, wall distributions
    custom_fields: dict = field(default_factory=dict)  # {name: {"formula": ..., "label": ...}} of the project
    name: str = "current"                # "current" or a snapshot name
    units: dict = field(default_factory=dict)        # {name: unit} of the stored fields
    labels: dict = field(default_factory=dict)       # {name: label} of the stored fields

    def __post_init__(self):
        missing = [k for k in PRIMITIVES if k not in self.fields]
        if missing:
            raise ValueError(f"A 2D result needs the fields {', '.join(PRIMITIVES)}; missing: {', '.join(missing)}.")
        self.fields = {k: np.asarray(v, dtype=float) for k, v in self.fields.items()}
        self._cache = {}

    # ---- building ---------------------------------------------------------------------------------

    @classmethod
    def from_result(cls, mesh, result, params, gas=None, case=None, base=None, name="current", custom_fields=None):
        """From a Result (aeroflowsim/results.py) of a 2D run and its inputs."""
        from aeroflowsim.euler.boundary import BoundaryCondition
        fields = {k: f.values for k, f in result.fields.items()}
        if len(fields.get("rho", ())) != mesh.n_cells:
            raise ValueError("These results do not belong to this mesh (different number of cells).")
        if gas is None:
            gas = _gas_of(params, case, base, fields)
        bcs = {k: BoundaryCondition.from_dict(v) for k, v in (result.info.get("boundaries") or {}).items()}
        return cls(mesh, fields, gas, bcs, dict(params), dict(result.info), dict(result.key_numbers),
                   dict(result.series), dict(custom_fields or {}), name,
                   {k: f.unit for k, f in result.fields.items()}, {k: f.label for k, f in result.fields.items()})

    @classmethod
    def from_payload(cls, mesh, payload, case=None, base=None, name="current", custom_fields=None):
        """From a loaded run file (aeroflowsim.result_io.load_run)."""
        return cls.from_result(mesh, payload["result"], payload["params"], case=case, base=base, name=name,
                               custom_fields=custom_fields)

    @classmethod
    def from_project(cls, project, snapshot=None):
        """The project's current result (or a named snapshot) on its current mesh."""
        from aeroflowsim.result_io import load_run
        mesh = project.load_mesh()
        if snapshot:
            from aeroflowsim.post.snapshots import snapshot_path
            payload = load_run(snapshot_path(project, snapshot))
        else:
            payload = project.load_results()
        if payload is None or mesh is None:
            raise ValueError(f"The project '{project.name}' has no 2D result to post-process yet: run it first.")
        return cls.from_payload(mesh, payload, case=project.case, base=project.folder, name=snapshot or "current",
                                custom_fields=getattr(project, "custom_fields", {}))

    def with_fields(self, fields, name=None):
        """A copy with other cell fields on the same mesh (e.g. a snapshot)."""
        series = {k: v for k, v in self.series.items() if k not in ("boundary_flux", "limiter_frozen")}
        return Solution(self.mesh, fields, self.gas, self.conditions, self.params, self.info, self.key_numbers,
                        series, self.custom_fields, name or self.name, self.units, self.labels)

    # ---- shared numbers ---------------------------------------------------------------------------

    @property
    def axisymmetric(self) -> bool:
        return bool(self.mesh.axisymmetric)

    @property
    def full_circle(self) -> float:
        """2 pi for axisymmetric results (whole circle), 1 for planar (per metre of depth)."""
        return 2.0 * np.pi if self.axisymmetric else 1.0

    @cached_property
    def geom(self):
        from aeroflowsim.euler.geometry import FVGeometry
        return FVGeometry(self.mesh)

    @cached_property
    def W(self) -> np.ndarray:
        """Primitive state (4, C)."""
        return np.array([self.fields[k] for k in PRIMITIVES])

    @cached_property
    def _solver(self):
        """An EulerSolver for this mesh and these conditions (ghost states and boundary fluxes), or None if the
        result carries no boundary conditions (then boundary values are the inside cell values)."""
        from aeroflowsim.euler.solver import EulerSolver, Numerics
        if not self.conditions or any(p.name not in self.conditions for p in self.mesh.patches):
            return None
        numerics = Numerics()
        if "cfl" in self.params and "limiter" in self.params:
            from aeroflowsim.euler.setup import numerics as numerics_of
            try:
                numerics = numerics_of(self.params)
            except (KeyError, ValueError):
                pass
        solver = EulerSolver(self.mesh, self.gas, self.conditions, numerics, L_ref=self.info.get("L_ref", 1.0),
                             scales=self.info.get("scales"))
        frozen = self.series.get("limiter_frozen")
        if frozen is not None and np.shape(frozen) == (4, self.mesh.n_cells):
            solver.psi_frozen = np.asarray(frozen, dtype=float)
        return solver

    @cached_property
    def ghost_states(self) -> np.ndarray:
        """Ghost state (4, B) of every boundary face (first-order, from the inside cell values)."""
        g = self.geom
        Wb = self.W[:, g.boundary_owner]
        return Wb.copy() if self._solver is None else self._solver.ghosts(Wb)

    @cached_property
    def boundary_values(self) -> np.ndarray:
        """State (4, B) at every boundary face centre: mean of the inside cell and the ghost state."""
        return 0.5 * (self.W[:, self.geom.boundary_owner] + self.ghost_states)

    @cached_property
    def gradients(self) -> np.ndarray:
        """Least-squares gradients (4, dim, C) of rho, u, v, p [unit per m]."""
        from aeroflowsim.euler.gradients import LEAST_SQUARES, Gradients
        return Gradients(self.geom, LEAST_SQUARES).gradient(self.W, self.boundary_values)

    def gradient_of(self, values, boundary=None) -> np.ndarray:
        """Least-squares gradient (dim, C) of any cell field; boundary face values default to the owner cell's."""
        from aeroflowsim.euler.gradients import LEAST_SQUARES, Gradients
        key = "_gradient_operator"
        if key not in self._cache:
            self._cache[key] = Gradients(self.geom, LEAST_SQUARES)
        if boundary is None:
            boundary = values[self.geom.boundary_owner]
        return self._cache[key].gradient(values[None, :], boundary[None, :])[0]

    @cached_property
    def boundary_flux(self) -> np.ndarray:
        """Numerical flux x flux area (4, B) of every boundary face for this state (second order, as the solver's
        final evaluation). Per radian for axisymmetric meshes (multiply by full_circle)."""
        from aeroflowsim.euler.state import primitive_to_conserved
        stored = self.series.get("boundary_flux")
        if stored is not None and np.shape(stored) == (4, self.geom.n_boundary):
            return np.asarray(stored, dtype=float)      # the solver's own final fluxes (saved with the run)
        if self._solver is None:
            raise ValueError("This result has no boundary conditions stored: boundary fluxes cannot be computed.")
        s = self._solver
        second = self.params.get("order", "Second order") != "First order"
        s.residual(primitive_to_conserved(self.W, self.gas), second, self.W)
        return s.boundary_flux.copy()

    @cached_property
    def cell_residual(self) -> np.ndarray:
        """Residual dU/dt (4, C) of this state, per cell, from one evaluation of the solver's residual."""
        from aeroflowsim.euler.state import primitive_to_conserved
        if self._solver is None:
            raise ValueError("This result has no boundary conditions stored: the residual cannot be computed.")
        second = self.params.get("order", "Second order") != "First order"
        R, _ = self._solver.residual(primitive_to_conserved(self.W, self.gas), second, self.W)
        return R

    def patch_faces(self, name) -> np.ndarray:
        """Boundary-local indices (into the B boundary faces) of a patch."""
        p = self.mesh.patch(name)
        return np.arange(p.start, p.start + p.count) - self.geom.n_interior

    # ---- reference values --------------------------------------------------------------------------

    @property
    def kind(self) -> str:
        return self.info.get("kind", "external" if "mach" in self.params else "nozzle")

    def reference_pressure(self) -> tuple:
        """(p_ref, q_ref, text): Cp = (p - p_ref) / q_ref. External: free stream; internal: p / p0 (q_ref = p0,
        p_ref = 0) with p0 of the first total-pressure inlet."""
        if self.kind == "external" and {"mach", "p_inf", "T_inf"} <= set(self.params):
            M, p, T = self.params["mach"], self.params["p_inf"], self.params["T_inf"]
            g = float(self.gas.gamma(T))
            return p, 0.5 * g * p * M * M, "Cp = (p - p_inf) / q_inf"
        p0 = None
        for bc in self.conditions.values():
            if bc.type == "total_pressure_inlet":
                p0 = bc.values["p0"]
                break
        if p0 is None:
            p0 = self.params.get("p0", float(np.max(self.fields.get("p0", self.fields["p"]))))
        return 0.0, float(p0), "p / p0 (inlet total pressure)"


def _gas_of(params, case, base, fields):
    """The GasModel of a run: the case's gas(params), else the 'gas' input, else a perfect gas fitted to the fields."""
    if case is not None and getattr(case, "gas", None) is not None:
        try:
            return case.gas(params)
        except Exception:      # noqa: BLE001 - fall back below (e.g. a custom gas file that moved)
            pass
    from aeroflowsim.gases.library import gas_model
    if "gas" in params:
        try:
            return gas_model(params["gas"], base=Path(base) if base else None)
        except Exception:      # noqa: BLE001
            pass
    return gas_model("air")

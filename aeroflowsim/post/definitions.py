# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Report definitions: named quantities of a result, evaluated after every run and (as monitors) during it.

Fluent's best idea, made simpler. A report definition is
    (where, operation, field)    e.g. "mass-weighted average of total pressure on outlet"
where "where" is a named surface (surface operations), a volume region (volume operations) or a set of walls
(force and moment coefficients). Definitions are stored in the project (key `report_definitions`).

A definition marked `monitor` is also evaluated during the run, every iteration: the Run page plots it next to
the built-in monitors and the values are written to results/report_<name>.csv (continued when a run is
continued, started again by "Start from scratch"). A monitor marked `converge` must also have settled for the
run to count as converged: it changed less than `tolerance` (relative) over the last `window` iterations, the
same rule as the built-in monitors (euler/solver.py).
"""

import dataclasses
from dataclasses import dataclass

import numpy as np

from aeroflowsim.post.integrals import (SURFACE_OPERATIONS, VOLUME_OPERATIONS, forces_and_moments,
                                        surface_integral, volume_integral)
from aeroflowsim.post.surfaces import Surface, default_surfaces

KINDS = ("surface", "volume", "force")
FORCE_QUANTITIES = {"Cd": "Drag coefficient", "Cl": "Lift coefficient", "Cm": "Moment coefficient",
                    "D": "Drag", "L": "Lift", "Fx": "Force x", "Fy": "Force y", "M": "Moment"}


@dataclass
class ReportDefinition:
    """A named quantity (see the module docstring)."""

    name: str
    kind: str = "surface"                      # surface, volume or force
    surface: str = ""                          # surface name (kind surface)
    operation: str = "area_weighted"           # SURFACE_OPERATIONS or VOLUME_OPERATIONS key
    field: str = ""                            # field name (operations that need one)
    quantity: str = "mass"                     # conserved quantity of the "flux" operation
    region: dict = dataclasses.field(default_factory=dict)  # volume region (integrals.region_cells); {} = whole domain
    walls: list = dataclasses.field(default_factory=list)  # kind force: wall patches
    force: str = "Cd"                          # kind force: one of FORCE_QUANTITIES
    moment_point: tuple = (0.0, 0.0)           # kind force [m]
    monitor: bool = False                      # evaluate during the run
    converge: bool = False                     # ... and require it to settle for convergence
    tolerance: float = 1e-4                    # relative change allowed over the window
    window: int = 500                          # iterations

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"'{self.kind}' is not a report-definition kind; use surface, volume or force.")
        self.moment_point = tuple(float(v) for v in self.moment_point)
        self.walls = [str(w) for w in self.walls]

    def to_dict(self) -> dict:
        d = {"name": self.name, "kind": self.kind, "monitor": self.monitor, "converge": self.converge,
             "tolerance": self.tolerance, "window": self.window}
        if self.kind == "surface":
            d.update(surface=self.surface, operation=self.operation, field=self.field, quantity=self.quantity)
        elif self.kind == "volume":
            d.update(operation=self.operation, field=self.field, region=dict(self.region))
        else:
            d.update(walls=list(self.walls), force=self.force, moment_point=list(self.moment_point))
        return d

    @classmethod
    def from_dict(cls, d) -> "ReportDefinition":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in dict(d).items() if k in known})

    def describe(self) -> str:
        if self.kind == "surface":
            what = SURFACE_OPERATIONS.get(self.operation, self.operation)
            if self.operation == "flux":
                what += f" ({self.quantity.replace('_', ' ')})"
            elif self.field:
                what += f" of {self.field}"
            return f"{what} on {self.surface}"
        if self.kind == "volume":
            what = VOLUME_OPERATIONS.get(self.operation, self.operation)
            where = (self.region or {}).get("type", "domain")
            return f"{what}{' of ' + self.field if self.field else ''} over {'the whole domain' if where == 'domain' else 'a ' + where}"
        return f"{FORCE_QUANTITIES.get(self.force, self.force)} of {', '.join(self.walls)}"


def find_surface(name, surfaces, sol) -> Surface:
    """The named surface among the project's surfaces and the default boundary surfaces."""
    for s in list(surfaces or []) + default_surfaces(sol):
        if s.name == name:
            return s
    raise ValueError(f"There is no surface called '{name}'.")


def evaluate(sol, definition, surfaces=()) -> tuple:
    """(value, unit) of one report definition on a Solution."""
    d = definition
    if d.kind == "surface":
        return surface_integral(sol, find_surface(d.surface, surfaces, sol), d.operation, d.field or None, d.quantity)
    if d.kind == "volume":
        return volume_integral(sol, d.operation, d.field or None, d.region or None)
    out = forces_and_moments(sol, d.walls, d.moment_point)
    unit = {"Cd": "-", "Cl": "-", "Cm": "-", "M": out["moment_unit"]}.get(d.force, out["force_unit"])
    return float(out[d.force]), unit


def evaluate_definitions(sol, definitions, surfaces=()) -> dict:
    """{name: (value, unit) or (nan, problem text)} of every definition; one broken definition never stops the rest."""
    out = {}
    for d in definitions:
        try:
            out[d.name] = evaluate(sol, d, surfaces)
        except (ValueError, KeyError) as exc:
            out[d.name] = (float("nan"), f"cannot be evaluated: {exc}")
    return out


def definitions_from(dicts) -> list:
    out = []
    for d in dicts or []:
        try:
            out.append(ReportDefinition.from_dict(d))
        except (TypeError, ValueError):
            continue
    return out


class MonitorEvaluator:
    """Evaluates the monitor report definitions during a run (built once per run; each call is cheap).

    The geometric work (surfaces cut through the mesh, gradient operator, point location) is done on the first
    call and kept; each iteration only the flow state changes. The boundary fluxes are the solver's own of that
    iteration (solver.stage0_boundary_flux), so boundary mass flows equal the built-in monitors."""

    def __init__(self, mesh, gas, conditions, params, definitions, surfaces=()):
        from aeroflowsim.post.solution import Solution
        self.definitions = [d for d in definitions if d.monitor]
        self.surfaces = list(surfaces)
        n = mesh.n_cells
        zeros = np.ones(n)
        self.sol = Solution(mesh, {"rho": zeros, "u": zeros * 0, "v": zeros * 0, "p": zeros}, gas, dict(conditions),
                            dict(params), {"kind": params.get("_kind", "")})
        self._keep = ("geom", "_solver")

    def __call__(self, solver, W):
        sol = self.sol
        for key in ("W", "ghost_states", "boundary_values", "gradients", "cell_residual", "boundary_flux"):
            sol.__dict__.pop(key, None)
        for key in ("fields", "gradients_of"):
            sol._cache.pop(key, None)
        sol.fields = {"rho": W[0], "u": W[1], "v": W[2], "p": W[-1]}
        sol.__dict__["_solver"] = solver
        sol.__dict__["geom"] = solver.geom
        flux = getattr(solver, "stage0_boundary_flux", None)
        if flux is not None:
            sol.__dict__["boundary_flux"] = flux
        values = {}
        for d in self.definitions:
            try:
                values["user_" + d.name] = evaluate(sol, d, self.surfaces)[0]
            except (ValueError, KeyError):
                values["user_" + d.name] = float("nan")
        return values


def report_file_name(name) -> str:
    """results/report_<name>.csv with a file-system-safe name."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name).strip("_") or "report"
    return f"report_{safe}.csv"


class ReportFileWriter:
    """Writes the monitor report definitions to results/report_<name>.csv WHILE the run goes on (flushed every
    FLUSH_EVERY iterations), one row per iteration. A continued run (restart with its histories) first writes the
    earlier iterations, so the file always holds the whole run; a start from scratch begins a new file."""

    FLUSH_EVERY = 50

    def __init__(self, folder, names, restart=None):
        from pathlib import Path
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        self.names = list(names)
        self.files = {}
        series = (restart or {}).get("series") if isinstance(restart, dict) else None
        for name in self.names:
            f = open(folder / report_file_name(name), "w", encoding="utf-8", newline="\n")
            f.write(f"iteration,{name} (SI)\n")
            old = None if series is None else series.get("monitor_user_" + name)
            if old is not None:
                for i, v in enumerate(np.asarray(old, dtype=float), start=1):
                    f.write(f"{i},{v:.10g}\n")
            self.files[name] = f
        self.count = 0

    def add(self, iteration, monitors):
        for name, f in self.files.items():
            v = monitors.get("user_" + name)
            if v is not None:
                f.write(f"{iteration},{float(v):.10g}\n")
        self.count += 1
        if self.count % self.FLUSH_EVERY == 0:
            for f in self.files.values():
                f.flush()

    def close(self):
        for f in self.files.values():
            f.close()

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Save a finished run to one file and read it back exactly, so a project shows its results after reopening.

File: <project>/results/run.npz (NumPy's zip of arrays). Numbers that are arrays (fields, residuals,
snapshots, wall profile, reference lines) are stored as arrays; everything else (labels, units,
key numbers, checks, parameters) as one JSON text inside the same file. No pickle is used, so
opening a project shared by someone else can never run code hidden in it.
"""

import json
from pathlib import Path

import numpy as np

from aeroflowsim.checks import CheckResult
from aeroflowsim.geometry import WallProfile
from aeroflowsim.mesh import Mesh1D
from aeroflowsim.results import Field, Line, Result, Snapshots

RUN_FILE = "run.npz"
RUN_FORMAT_VERSION = 1


def _fields_out(prefix, fields, arrays):
    """Store a {key: Field} dict: arrays under '<prefix>/<key>', labels and units in the returned dict."""
    if fields is None:
        return None
    meta = {}
    for key, f in fields.items():
        arrays[f"{prefix}/{key}"] = np.asarray(f.values)
        meta[key] = {"unit": f.unit, "label": f.label}
    return meta


def _fields_in(prefix, meta, data):
    if meta is None:
        return None
    return {key: Field(values=data[f"{prefix}/{key}"], unit=m["unit"], label=m["label"]) for key, m in meta.items()}


def save_run(folder, payload, mesh=None) -> Path:
    """Write the outputs of a run (the 'done' payload of aeroflowsim.tasks) to <folder>/run.npz.

    mesh: the mesh used; a 1D mesh is stored too (2D meshes live in the project's mesh/ folder).
    """
    result = payload["result"]
    arrays = {"residuals": np.asarray(result.residuals, dtype=float)}
    meta = {
        "format_version": RUN_FORMAT_VERSION,
        "params": payload["params"],
        "run_s": payload.get("run_s"),
        "fields": _fields_out("fields", result.fields, arrays),
        "key_numbers": {k: [float(v), u] for k, (v, u) in result.key_numbers.items()},
        "iterations": int(result.iterations),
        "converged": bool(result.converged),
        "shape_note": result.shape_note,
        "reference": _fields_out("reference", payload.get("reference"), arrays),
        "checks": [c.as_dict() for c in payload.get("checks", [])],
        "lines": [],
        "snapshots": None,
        "shape": None,
        "series": sorted(result.series),          # 2D solvers: histories, wall distributions
        "info": result.info,                      # 2D solvers: status, positivity events, ...
    }
    for key, values in result.series.items():
        arrays[f"series/{key}"] = np.asarray(values)
    if result.snapshots is not None:
        arrays["snapshots/times"] = np.asarray(result.snapshots.times)
        meta["snapshots"] = _fields_out("snapshots", result.snapshots.fields, arrays)
    if result.shape is not None:
        arrays["shape/x"], arrays["shape/r"] = result.shape.x, result.shape.r
        meta["shape"] = {"interpolation": result.shape.interpolation,
                         "marks": [[label, float(x), float(r)] for label, x, r in result.shape.marks]}
    for i, line in enumerate(payload.get("reference_lines") or []):
        arrays[f"lines/{i}/x"], arrays[f"lines/{i}/y"] = np.asarray(line.x), np.asarray(line.y)
        meta["lines"].append({"label": line.label, "style": line.style})
    if isinstance(mesh, Mesh1D):
        arrays["mesh1d/x"] = np.asarray(mesh.x)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / RUN_FILE
    np.savez_compressed(path, meta=np.array(json.dumps(meta)), **arrays)
    return path


def load_run(path) -> dict:
    """Read run.npz back into the same payload dict save_run was given (+ 'mesh1d' if stored)."""
    with np.load(path, allow_pickle=False) as data:
        meta = json.loads(str(data["meta"]))
        if meta.get("format_version", 0) > RUN_FORMAT_VERSION:
            raise ValueError(f"{path} was written by a newer AeroFlowSim; please update to open it.")
        snapshots = None
        if meta["snapshots"] is not None:
            snapshots = Snapshots(times=data["snapshots/times"], fields=_fields_in("snapshots", meta["snapshots"], data))
        shape = None
        if meta["shape"] is not None:
            shape = WallProfile(data["shape/x"], data["shape/r"], meta["shape"]["interpolation"],
                                [tuple(m) for m in meta["shape"]["marks"]])
        result = Result(fields=_fields_in("fields", meta["fields"], data), residuals=data["residuals"].tolist(),
                        key_numbers={k: (v, u) for k, (v, u) in meta["key_numbers"].items()},
                        iterations=meta["iterations"], converged=meta["converged"], snapshots=snapshots,
                        shape=shape, shape_note=meta["shape_note"],
                        series={k: data[f"series/{k}"] for k in meta.get("series", [])},
                        info=meta.get("info", {}))
        lines = [Line(label=m["label"], x=data[f"lines/{i}/x"], y=data[f"lines/{i}/y"], style=m["style"])
                 for i, m in enumerate(meta["lines"])]
        payload = {"result": result, "reference": _fields_in("reference", meta["reference"], data),
                   "reference_lines": lines, "checks": [CheckResult(**c) for c in meta["checks"]],
                   "params": meta["params"], "run_s": meta["run_s"]}
        if "mesh1d/x" in data:
            payload["mesh1d"] = Mesh1D(data["mesh1d/x"])
    return payload

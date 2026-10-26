# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Projects: the user's own work, saved in a folder that can be zipped and shared.

A *template* is a case folder (cases/<name>/: schema.toml + case.py): the physics, the same for
everyone. A *project* is one user's use of a template, in its own folder, e.g.

    Documents/AeroFlowSim Projects/My Nozzle.afsproj/
        project.yaml     AeroFlowSim version, template name, every input value, step records
        geometry/        copies of input files (CSV profiles, coordinate files, CAD files) - paths stored
                         relative - and history.json, the geometry workspace history (only once the
                         geometry has been edited in the workspace; see aeroflowsim/geometry_model/)
        gases/           copies of the custom gases the project uses (built-in gases are referred to
                         by their id, e.g. "N2"; see aeroflowsim/gases/)
        mesh/            mesh.npz (exact mesh), mesh.vtu (ParaView)
        results/         run.npz (exact results, reopened by the GUI) + the command line's files
                         (fields.csv, residuals.csv, summary.yaml, PNG plots)

Because input files are copied in and stored with relative paths, someone who opens a zipped
copy gets exactly the same inputs and therefore exactly the same results.

Up-to-date status ("fingerprints"): when a mesh or a run is produced, the project stores a short
code (SHA-256) made from every input it depends on, the contents of the input files and the
template's code. The status of a step compares that code with today's:
    "ok"        produced from exactly the current inputs              (green)
    "outdated"  produced, but an input it depends on changed since    (amber)
    "none"      never produced                                        (grey)
    "error"     the last attempt with the current inputs failed, or the inputs are invalid (red)
    "disabled"  the template has no solver (mesh-only)
Geometry inputs feed the mesh and the run; mesh inputs feed the run; so a geometry change marks
Mesh, Run and Results "outdated" automatically, and old results are never shown as current.

No GUI code here: the command line uses projects too (python -m aeroflowsim run "<folder>").
"""

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from aeroflowsim import __version__
from aeroflowsim.discovery import CASES_DIR, PROJECT_DIR, load_case
from aeroflowsim.gases import PROJECT_GAS_DIR, builtin_gas, is_builtin
from aeroflowsim.mesh import Mesh, Mesh1D
from aeroflowsim.parameters import STEPS as INPUT_STEPS
from aeroflowsim.parameters import check_values, defaults, validate
from aeroflowsim.result_io import RUN_FILE, load_run, save_run

SUFFIX = ".afsproj"
PROJECT_FILE = "project.yaml"
FORMAT_VERSION = 1
GEOMETRY_DIR, MESH_DIR, RESULTS_DIR = "geometry", "mesh", "results"
WORKFLOW = ("geometry", "mesh", "setup", "run", "results")   # the steps of the workflow strip, in order
MESH_1D_FILE = "mesh1d.npz"

# Which input steps each product depends on.
DEPENDS_ON = {"geometry": ("geometry",), "mesh": ("geometry", "mesh"), "run": INPUT_STEPS}


POST_DEFAULTS = {
    "surfaces": [],              # named surfaces (aeroflowsim/post/surfaces.py), geometric: survive re-meshing
    "report_definitions": [],    # aeroflowsim/post/definitions.py
    "custom_fields": {},         # {name: {"formula": text, "label": text}}
    "scenes": {},                # {name: view settings of the Results step}
    "xy_plots": {},              # {name: XY plot settings}
    "init_patches": [],          # patch regions for a fresh start (aeroflowsim/euler/setup.py apply_patches)
    "interpolate_new_mesh": True,   # a run on a new mesh starts from the old solution interpolated onto it
}


def default_post() -> dict:
    """A fresh copy of the post-processing settings of a new project."""
    import copy
    return copy.deepcopy(POST_DEFAULTS)


def default_projects_dir() -> Path:
    """Where new projects go by default: Documents/AeroFlowSim Projects (never the code folder)."""
    return Path.home() / "Documents" / "AeroFlowSim Projects"


def folder_for(name, parent=None) -> Path:
    """Project folder for a name typed by the user, e.g. 'My Nozzle' -> .../My Nozzle.afsproj."""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not clean:
        raise ValueError("Please give the project a name.")
    if clean.lower().endswith(SUFFIX):
        clean = clean[: -len(SUFFIX)]
    return Path(parent or default_projects_dir()) / f"{clean}{SUFFIX}"


def is_project(path) -> bool:
    return (Path(path) / PROJECT_FILE).is_file()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _file_bytes(path) -> bytes:
    """File contents with Windows line endings made Unix-like, so a project checked out on another
    system has the same fingerprints."""
    return Path(path).read_bytes().replace(b"\r\n", b"\n")


def template_fingerprint(case) -> str:
    """SHA-256 of the template's schema.toml and case.py: a code change makes old results outdated."""
    h = hashlib.sha256()
    for name in ("schema.toml", "case.py"):
        h.update(_file_bytes(Path(case.folder) / name))
    return h.hexdigest()


class Project:
    """One project folder: inputs, step records and the files produced."""

    def __init__(self, folder, case, values, steps=None, created=None, modified=None, warnings=None):
        self.folder = Path(folder)
        self.case = case
        self.values = dict(values)          # {input name: value}, file paths relative to the folder
        self.steps = dict(steps or {})      # {"mesh": {...}, "run": {...}}: what was produced from what
        self.created = created or _now()
        self.modified = modified or self.created
        self.warnings = list(warnings or [])   # shown to the user after opening
        self.dirty = False                  # inputs changed since the last save
        self._history, self._history_loaded = None, False   # workspace history (see edited_geometry)
        self.post = default_post()          # post-processing settings (surfaces, report definitions, ...)

    # ---- creating, opening, saving -------------------------------------------------------------

    @classmethod
    def create(cls, template, folder, values=None) -> "Project":
        """New project from a template (case name or folder). The folder must not exist yet (or be empty)."""
        folder = Path(folder)
        if folder.exists() and any(folder.iterdir()):
            raise ValueError(f"The folder {folder} already exists and is not empty; choose another name.")
        case = load_case(template)
        project = cls(folder, case, defaults(case.parameters()))
        folder.mkdir(parents=True, exist_ok=True)
        for sub in (GEOMETRY_DIR, MESH_DIR, RESULTS_DIR):
            (folder / sub).mkdir(exist_ok=True)
        for p in case.parameters():         # copy the template's example files in: the project is self-contained
            if p.type == "file":
                source = project._absolute(project.values[p.name], base=PROJECT_DIR)
                if source.is_file():
                    project.values[p.name] = project.import_file(source)
        if values:
            project.values.update(values)
        project.save()
        return project

    @classmethod
    def open(cls, folder) -> "Project":
        folder = Path(folder)
        path = folder / PROJECT_FILE
        if not path.is_file():
            raise ValueError(f"{folder} is not an AeroFlowSim project (no {PROJECT_FILE}).")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("format_version", 0) > FORMAT_VERSION:
            raise ValueError(f"{folder.name} was saved by a newer AeroFlowSim ({data.get('aeroflowsim_version')}); "
                             "please update AeroFlowSim to open it.")
        template = data.get("template")
        if (CASES_DIR / str(template)).is_dir():
            case = load_case(CASES_DIR / template)
        else:
            raise ValueError(f"{folder.name} uses the template '{template}', which is not installed.")
        warnings = []
        if data.get("template_fingerprint") not in (None, template_fingerprint(case)):
            warnings.append(f"The template '{case.title}' has changed since this project was saved; "
                            "results made before may differ from a new run.")
        values = defaults(case.parameters())
        saved = data.get("inputs") or {}
        unknown = sorted(set(saved) - set(values))
        if unknown:
            warnings.append(f"Inputs no longer used by the template were ignored: {', '.join(unknown)}.")
        missing = sorted(set(values) - set(saved))
        if missing:
            warnings.append(f"New inputs got their default values: {', '.join(missing)}.")
        values.update({k: v for k, v in saved.items() if k in values})
        project = cls(folder, case, values, data.get("steps"), data.get("created"), data.get("modified"), warnings)
        for key, default in default_post().items():     # older projects have none of these: the defaults
            value = data.get(key)
            if isinstance(value, type(default)):
                project.post[key] = value
        project._convert_old_gas_inputs(saved)
        project._convert_old_restart_input()
        return project

    def _convert_old_restart_input(self):
        """Projects from before Run carried on by itself (Prompt 7) may have Initial solution = 'Previous result
        (restart)'. That option is gone: Run now continues the current solution by default. It becomes the
        template's default start (used only when starting from scratch)."""
        from aeroflowsim.euler.initial import RESTART
        for p in self.case.parameters():
            if p.name == "initialisation" and self.values.get(p.name) == RESTART and RESTART not in p.options:
                self.values[p.name] = p.default
                self.warnings.append(f"Initial solution 'Previous result (restart)' is no longer needed: Run carries on "
                                     f"from the current solution by itself. For a start from scratch it is now "
                                     f"'{p.default}'.")
                self.dirty = True

    def _convert_old_gas_inputs(self, saved):
        """Projects from before the gas library (6f) stored gamma and R as numbers. 1.4 and 296.8 (the old
        default) become the built-in N2; other values become a custom gas inside the project."""
        gas_inputs = [p for p in self.case.parameters() if p.type == "gas"]
        if not gas_inputs or gas_inputs[0].name in saved or not {"gamma", "R"} <= set(saved):
            return
        name = gas_inputs[0].name
        gamma, R = float(saved["gamma"]), float(saved["R"])
        if (gamma, R) == (1.4, 296.8):
            self.values[name] = "N2"
            self.warnings = [w for w in self.warnings if "gamma" not in w]
            self.warnings.append("The gas inputs gamma = 1.4 and R = 296.8 J/(kg K) of this older project now "
                                 "use the built-in gas N2 (same values).")
        else:
            from aeroflowsim.gases import custom_gas_toml
            gas_name = f"Gas of {self.name} (gamma {gamma:g}, R {R:g})"
            text = custom_gas_toml(gas_name, "custom", R=R, gamma=gamma, prandtl=0.71,
                                   viscosity={"law": "sutherland", "ref": 1.716e-5, "T_ref": 273.15, "S": 110.4},
                                   note="Made from the gamma and R of an older project; viscosity and Prandtl "
                                        "number are those of air (not used by inviscid solvers).")
            folder = self.folder / PROJECT_GAS_DIR
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "converted gas.toml").write_text(text, encoding="utf-8")
            self.values[name] = f"{PROJECT_GAS_DIR}/converted gas.toml"
            self.warnings.append(f"This older project used gamma = {gamma:g} and R = {R:g} J/(kg K); they are now "
                                 f"the custom gas '{gas_name}' (gases/converted gas.toml).")
        self.dirty = True

    def to_dict(self) -> dict:
        return {
            "format_version": FORMAT_VERSION,
            "aeroflowsim_version": __version__,
            "template": Path(self.case.folder).name,
            "template_title": self.case.title,
            "template_fingerprint": template_fingerprint(self.case),
            "created": self.created,
            "modified": self.modified,
            "inputs": self.values,
            "steps": self.steps,
            **self.post,
        }

    def save(self):
        """Write project.yaml (the produced files are already in the folder)."""
        self.modified = _now()
        self.folder.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True)
        tmp = self.folder / (PROJECT_FILE + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.folder / PROJECT_FILE)    # never a half-written project.yaml
        if self._history_loaded:                   # the workspace history, if the geometry was edited
            if self._history is None:
                self.history_path.unlink(missing_ok=True)
            else:
                self._history.save(self.history_path)
        self.dirty = False

    def duplicate(self, new_folder) -> "Project":
        """A full copy (inputs, files, mesh, results) in new_folder; this project stays as it is."""
        new_folder = Path(new_folder)
        if new_folder.exists():
            raise ValueError(f"{new_folder} already exists; choose another name.")
        shutil.copytree(self.folder, new_folder, ignore=shutil.ignore_patterns("*.tmp"))
        copy = Project(new_folder, self.case, self.values, json.loads(json.dumps(self.steps)), _now())
        copy.post = json.loads(json.dumps(self.post))
        copy.set_geometry_document(self.edited_geometry)      # unsaved geometry edits go with the copy
        copy.save()
        return copy

    def save_as(self, new_folder):
        """Copy everything to new_folder and continue working there (the old folder stays as saved)."""
        copy = self.duplicate(new_folder)
        self.folder, self.created, self.modified = copy.folder, copy.created, copy.modified
        self.save()

    @property
    def name(self) -> str:
        return self.folder.name[: -len(SUFFIX)] if self.folder.name.endswith(SUFFIX) else self.folder.name

    # ---- inputs ----------------------------------------------------------------------------------

    def set_value(self, name, value):
        if self.values.get(name) != value or type(self.values.get(name)) is not type(value):
            self.values[name] = value
            self.dirty = True

    def _absolute(self, value, base=None) -> Path:
        path = Path(str(value))
        return path if path.is_absolute() else Path(base or self.folder) / path

    def import_file(self, source) -> str:
        """Copy a chosen input file into geometry/ and return its relative path (stored in the inputs)."""
        source = Path(source)
        target_dir = self.folder / GEOMETRY_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        if source.resolve() == target.resolve():
            return f"{GEOMETRY_DIR}/{target.name}"
        stem, n = target.stem, 2
        while target.exists() and _file_bytes(target) != _file_bytes(source):   # same name, other content
            target = target_dir / f"{stem}_{n}{source.suffix}"
            n += 1
        if not target.exists():
            shutil.copy2(source, target)
        return f"{GEOMETRY_DIR}/{target.name}"

    def import_gas(self, source) -> str:
        """Copy a custom gas file into gases/ and return its relative path (stored in the inputs), so a
        zipped project carries its gas with it."""
        source = Path(source)
        target_dir = self.folder / PROJECT_GAS_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        if source.resolve() != target.resolve():
            stem, n = target.stem, 2
            while target.exists() and _file_bytes(target) != _file_bytes(source):   # same name, other gas
                target = target_dir / f"{stem}_{n}{source.suffix}"
                n += 1
            if not target.exists():
                shutil.copy2(source, target)
        return f"{PROJECT_GAS_DIR}/{target.name}"

    def resolved_values(self) -> dict:
        """The inputs with file paths made absolute (what the case code and the engine receive)."""
        values = dict(self.values)
        for p in self.case.parameters():
            if p.type in ("file", "gas") and isinstance(values.get(p.name), str) and values[p.name].strip()                     and not (p.type == "gas" and is_builtin(values[p.name])):
                values[p.name] = str(self._absolute(values[p.name]))
        return values

    def params(self) -> dict:
        """Validated inputs ready for the engine (ValueError naming the first problem)."""
        return validate(self.case.parameters(), self.resolved_values())

    def params_for(self, steps) -> dict:
        """Validated inputs of the given steps; any OTHER input that is invalid gets its default.

        Lets a page work while an unrelated input is being typed (e.g. the geometry drawing stays
        while a solver tolerance is half-typed). ValueError if an input of these steps is invalid.
        """
        values = self.resolved_values()
        problems = check_values(self.case.parameters(), values)
        own = [p for p in self.case.parameters() if p.step in steps and p.name in problems]
        if own:
            raise ValueError(problems[own[0].name])
        base = defaults(self.case.parameters())
        fixed = {name: (base[name] if name in problems else value) for name, value in values.items()}
        return validate(self.case.parameters(), fixed)

    def problems(self, steps=INPUT_STEPS) -> dict:
        """{input: message} for every bad value among the inputs of the given steps."""
        chosen = [p for p in self.case.parameters() if p.step in steps]
        return check_values(chosen, self.resolved_values())

    # ---- geometry workspace ----------------------------------------------------------------------

    @property
    def history_path(self) -> Path:
        from aeroflowsim.geometry_model import HISTORY_FILE
        return self.folder / GEOMETRY_DIR / HISTORY_FILE

    @property
    def edited_geometry(self):
        """The workspace history if the geometry has been edited (a GeometryDocument), else None.

        Kept in memory like the inputs: geometry/history.json is read on first use and written by
        save(), so "discard changes" also discards geometry edits.
        """
        if not self._history_loaded:
            from aeroflowsim.geometry_model import GeometryDocument
            self._history = GeometryDocument.load(self.history_path) if self.history_path.is_file() else None
            self._history_loaded = True
        return self._history

    def geometry_document(self):
        """A copy of the workspace history: the edited one, or the template's own geometry (then
        everything works exactly as before the workspace existed)."""
        from aeroflowsim.geometry_model import template_document
        edited = self.edited_geometry
        return edited.copy() if edited is not None else template_document(self.case)

    def set_geometry_document(self, document):
        """Use this workspace history; None (or the unedited template geometry) means "not edited"."""
        from aeroflowsim.geometry_model import template_document
        template = template_document(self.case)
        if document is None or (document.is_template_only() and
                                document.to_dict()["operations"] == template.to_dict()["operations"]):
            new = None
        else:
            new = document.copy()
        if new != self.edited_geometry:
            self._history, self._history_loaded = new, True
            self.dirty = True

    def geometry_files(self) -> list:
        """Project-relative paths of the files imported by workspace operations (their contents
        are part of the fingerprints)."""
        edited = self.edited_geometry
        if edited is None:
            return []
        return sorted({op.params["file"] for op in edited.operations if op.params.get("file")})

    def replay_context(self, params=None):
        """What a replay of the workspace history needs: template, its geometry inputs, the folder."""
        from aeroflowsim.geometry_model import ReplayContext
        if params is None:
            params = self.params_for(("geometry",))
        return ReplayContext(self.case, params, self.folder)

    # ---- fingerprints and status -----------------------------------------------------------------

    def fingerprint(self, product) -> str:
        """SHA-256 of everything a product ('geometry', 'mesh' or 'run') depends on."""
        h = hashlib.sha256()
        h.update(f"{template_fingerprint(self.case)}|{__version__}|{product}".encode())
        if self.edited_geometry is not None:      # only then: old projects keep their fingerprints
            h.update(b"history|" + self.edited_geometry.to_json().encode())
            for name in self.geometry_files():
                path = self.folder / name
                h.update(name.encode() + (_file_bytes(path) if path.is_file() else b"<missing file>"))
        resolved = self.resolved_values()
        for p in self.case.parameters():
            if p.step not in DEPENDS_ON[product]:
                continue
            h.update(json.dumps([p.name, self.values.get(p.name)], sort_keys=True, default=str).encode())
            if p.type == "file":
                path = Path(str(resolved.get(p.name, "")))
                h.update(_file_bytes(path) if path.is_file() else b"<missing file>")
            if p.type == "gas":                   # the gas data itself: a changed gas file makes results old
                value = resolved.get(p.name, "")
                path = builtin_gas(value).path if is_builtin(value) else Path(str(value))
                h.update(_file_bytes(path) if path.is_file() else b"<missing gas file>")
        return h.hexdigest()

    def status(self, step) -> str:
        """'ok', 'outdated', 'none', 'error' or 'disabled' for a workflow step (see the module text)."""
        if step == "geometry":
            return "error" if self.problems(("geometry",)) else "ok"
        if step == "setup":
            return "error" if self.problems(("setup",)) else "ok"
        product = "run" if step in ("run", "results") else "mesh"
        if product == "run" and not self.case.has_solver:
            return "disabled"
        record = self.steps.get(product) or {}
        current = self.fingerprint(product)
        if record.get("error") and record.get("error_fingerprint") == current:
            return "error"
        if not record.get("fingerprint"):
            return "none"
        return "ok" if record["fingerprint"] == current else "outdated"

    def statuses(self) -> dict:
        return {step: self.status(step) for step in WORKFLOW}

    # ---- produced files --------------------------------------------------------------------------

    @property
    def mesh_dir(self) -> Path:
        return self.folder / MESH_DIR

    @property
    def results_dir(self) -> Path:
        return self.folder / RESULTS_DIR

    def record_mesh(self, mesh, info=None, fingerprint=None):
        """Remember that the mesh files in mesh/ were made from the current inputs.

        fingerprint: the mesh fingerprint taken when the job was SENT (the GUI lets the user keep
        editing while a job runs, so the inputs may have changed since). Default: current inputs.
        """
        if isinstance(mesh, Mesh1D):
            self.mesh_dir.mkdir(parents=True, exist_ok=True)
            np.savez(self.mesh_dir / MESH_1D_FILE, x=mesh.x)
        cells = mesh.n_cells
        self.steps["mesh"] = {"fingerprint": fingerprint or self.fingerprint("mesh"), "time": _now(), "cells": int(cells),
                              **(info or {})}
        self.save()

    def record_failure(self, product, message, fingerprint=None):
        """Remember that making a product failed with these inputs (status 'error' while they stay)."""
        record = dict(self.steps.get(product) or {})
        record.update(error=str(message), error_fingerprint=fingerprint or self.fingerprint(product),
                      error_time=_now())
        self.steps[product] = record
        self.save()

    def record_run(self, payload, mesh, fingerprint=None):
        """Save a finished run (results/run.npz) and remember which inputs it came from
        (fingerprint taken when the run was sent; default: current inputs)."""
        save_run(self.results_dir, payload, mesh)
        result = payload["result"]
        self.steps["run"] = {"fingerprint": fingerprint or self.fingerprint("run"), "time": _now(),
                             "converged": bool(result.converged), "iterations": int(result.iterations),
                             "run_s": payload.get("run_s")}
        status = (getattr(result, "info", None) or {}).get("status")
        if status:                               # 2D runs: converged, max_iterations, stopped or diverged
            self.steps["run"]["status"] = status
        self.save()

    def load_mesh(self):
        """The saved mesh (Mesh or Mesh1D), or None if there is none."""
        if (self.mesh_dir / "mesh.npz").is_file():
            return Mesh.load(self.mesh_dir / "mesh.npz")
        if (self.mesh_dir / MESH_1D_FILE).is_file():
            with np.load(self.mesh_dir / MESH_1D_FILE) as data:
                return Mesh1D(data["x"])
        return None

    def continuation(self, mesh, results=None):
        """(results/run.npz, iterations done) when a run can carry on from the saved result on this mesh (a 2D
        result with one value per cell of the mesh), else (None, 0): then the run starts from scratch.
        results: the loaded payload if the caller has it (saves reading the file again)."""
        from aeroflowsim.result_io import can_continue
        path = self.results_dir / RUN_FILE
        if not path.is_file() or mesh is None:
            return None, 0
        try:
            payload = results if results is not None else load_run(path)
        except (OSError, ValueError, KeyError):
            return None, 0
        result = payload["result"]
        return (path, int(result.iterations)) if can_continue(result, mesh) else (None, 0)

    def load_results(self):
        """The saved run payload (result, reference, checks, ...), or None if there is none."""
        path = self.results_dir / RUN_FILE
        return load_run(path) if path.is_file() else None

    # ---- post-processing settings ----------------------------------------------------------------

    @property
    def custom_fields(self) -> dict:
        return self.post["custom_fields"]

    def set_post(self, key, value):
        """Change one post-processing setting (surfaces, report_definitions, custom_fields, scenes, xy_plots,
        init_patches, interpolate_new_mesh); marks the project as changed."""
        if key not in POST_DEFAULTS:
            raise KeyError(f"'{key}' is not a post-processing setting.")
        self.post[key] = value
        self.dirty = True

    def interpolation_source(self, mesh):
        """{"centres", "W"} of the saved result when it belongs to a DIFFERENT mesh than `mesh` and the project allows
        starting from it ("interpolate_new_mesh", default on); else None (the run starts from the Initial solution)."""
        if not self.post.get("interpolate_new_mesh", True) or mesh is None:
            return None
        try:
            payload = self.load_results()
        except (OSError, ValueError, KeyError):
            return None
        if payload is None:
            return None
        from aeroflowsim.result_io import can_continue
        result = payload["result"]
        centres = (result.series or {}).get("cell_centres")
        if centres is None or can_continue(result, mesh) or not {"rho", "u", "v", "p"} <= set(result.fields):
            return None
        W = np.array([np.asarray(result.fields[k].values, dtype=float) for k in ("rho", "u", "v", "p")])
        if W.shape[1] != len(centres):
            return None
        return {"centres": np.asarray(centres, dtype=float), "W": W}

    def run_extras(self, mesh=None, fresh=False) -> dict:
        """The post-processing settings a run needs (aeroflowsim.engine.run_case(extras=...)): report definitions and
        surfaces (monitors), custom fields, patch regions, and the previous solution to interpolate when the mesh has
        changed (only for a start that does not continue the current result; never with "Start from scratch")."""
        extras = {k: self.post[k] for k in ("report_definitions", "surfaces", "custom_fields", "init_patches")}
        if not fresh:
            source = self.interpolation_source(mesh)
            if source is not None:
                extras["interpolate"] = source
        return extras

    # ---- old settings files ----------------------------------------------------------------------

    @classmethod
    def from_old_settings(cls, settings_file, folder) -> "Project":
        """Turn an old cases/<case>/settings/<name>.yaml file (Streamlit GUI) into a project."""
        data = yaml.safe_load(Path(settings_file).read_text(encoding="utf-8")) or {}
        project = cls.create(data.get("case") or Path(settings_file).parents[1].name, folder)
        saved = data.get("parameters") or {}
        for p in project.case.parameters():
            if p.name not in saved:
                continue
            value = saved[p.name]
            if p.type == "file":
                source = project._absolute(value, base=PROJECT_DIR)
                value = project.import_file(source) if source.is_file() else value
            project.values[p.name] = value
        project.save()
        return project


def old_settings_files() -> list[Path]:
    """Every cases/*/settings/*.yaml file left by the Streamlit GUI."""
    return sorted(CASES_DIR.glob("*/settings/*.yaml")) + sorted(CASES_DIR.glob("*/settings/*.yml"))


def build_project_mesh(project):
    """Build the mesh from the current inputs, save it in mesh/ and record it (command line).

    The GUI does the same in its background worker (aeroflowsim/tasks.py, _mesh_job).
    """
    from aeroflowsim.vtk import mesh_cell_data, write_vtu

    from aeroflowsim.workspace_mesh import mesh_for
    mesh = mesh_for(project.case, project.params(), project.edited_geometry, project.folder)
    if isinstance(mesh, Mesh):
        project.mesh_dir.mkdir(parents=True, exist_ok=True)
        mesh.save(project.mesh_dir / "mesh.npz")
        write_vtu(project.mesh_dir / "mesh.vtu", mesh, mesh_cell_data(mesh))
    project.record_mesh(mesh)
    return mesh


def run_project(project, progress=None, fresh=False):
    """Mesh (if needed) and solve a project with the one engine; store mesh and results in it.

    Like the GUI's Run, a 2D run carries on from the project's saved result on the same mesh (iteration 159 after
    158); fresh=True starts from scratch (the Initial solution input). Used by the command line; the GUI does the
    same steps in its background worker.
    """
    from aeroflowsim.engine import run_case

    params = project.params()
    mesh = project.load_mesh() if project.status("mesh") == "ok" else None
    if mesh is None:
        mesh = build_project_mesh(project)
    restart = None
    if not fresh:                                 # carry on from the saved result, as the GUI's Run does
        from aeroflowsim.result_io import continuation_data
        path, _done = project.continuation(mesh)
        restart = None if path is None else continuation_data(path)
    extras = project.run_extras(mesh, fresh=fresh or restart is not None)
    output = run_case(project.case, params, mesh=mesh, progress=progress, out_dir=project.results_dir,
                      restart=restart, extras=extras)
    payload = {"result": output.result, "reference": output.reference, "reference_lines": output.reference_lines,
               "checks": output.checks, "params": output.params}
    project.record_run(payload, mesh)
    return output

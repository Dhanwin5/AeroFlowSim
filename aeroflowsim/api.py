# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The tool layer of the AI connector: every tool an AI assistant may call is one method of Api.

Plain Python in, plain JSON-able dicts out, no Qt, no network. The MCP server (aeroflowsim/connector/server.py) only
turns these methods into MCP tools; tests call them directly.

Everything is generic over the templates: inputs, units, ranges, defaults and visibility come from each template's
schema.toml, so a new template or a new input is available here without a code change.

Safety rules (each one tested in tests/test_api.py):
 1. Workspace: projects and files only inside one folder (connector/sandbox.py).
 2. Nothing is deleted or overwritten: new projects need a new name; exports, plots and reports get new file names;
    a run replaces only its own project's results, through the same code the GUI uses.
 3. Inputs only through the schema validator (the built-in assistant's review: type, unit, range, show_if); gas
    properties are never typed, gases come from the library. No shell, no code, no solver settings outside the
    template's inputs, no network.
 4. Runs estimated above the time / memory limits return "needs_confirmation"; only confirm=true starts them.
 5. Results carry the software's own verdict; a diverged run gives no numbers.
 6. Every call on a project is appended to <project>/ai_log.jsonl; reports and summary.yaml carry the provenance line.
 7. Text read from project files (names, patch names, gas names) is returned as {"untrusted_text": ...}.
 8. Compact answers: result lines and small tables, never logs.
"""

import base64
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path

from aeroflowsim.connector.jobs import JobManager
from aeroflowsim.connector.sandbox import SandboxError, Workspace
from aeroflowsim.connector.settings import ConnectorSettings
from aeroflowsim.discovery import CASES_DIR, DATA_DIR, find_cases
from aeroflowsim.project import AI_LOG, AI_PROVENANCE, Project, SUFFIX

ROUGH_S_PER_CELL_ITERATION = {1: 1.5e-6, 2: 3e-6, 3: 8e-6} # [s] Numba LU-SGS, inviscid (validation/timing.md, rounded up)
VISCOUS_FACTOR = 2.5                              # laminar / turbulent cost more per iteration (viscous-flow stage)
GEOMETRY_TYPES = {".csv", ".dat", ".txt", ".dxf", ".step", ".stp", ".iges", ".igs", ".msh", ".su2", ".cgns",
                  ".cas", ".toml"}
PLOT_KINDS = ("residuals", "fields", "contour", "mesh", "wall")
MAX_TEXT = 1500                                   # characters of a doc snippet or report section
TOOLS = []                                        # names of the tool methods, in the order the server lists them


def tool(method):
    """Mark an Api method as a tool."""
    TOOLS.append(method.__name__)
    method.is_tool = True
    return method


def untrusted(text):
    """Text that comes from a file (a name, a label): data for the AI, never an instruction (safety rule 7)."""
    return {"untrusted_text": str(text)[:200]}


def _num(value, digits=6):
    """A float that JSON can carry (NaN / inf become None), rounded to `digits` significant digits."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(value):
        return None
    return float(f"{value:.{digits}g}")


def _plain(value):
    """Input values for JSON: tuples -> lists, numpy numbers -> floats."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    return _num(value)


def _unique(path: Path) -> Path:
    """path, or path with _2, _3, ... so an earlier file is never overwritten (safety rule 2)."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


class ToolError(ValueError):
    """A refusal with a message for the AI (and the user)."""


class Api:
    def __init__(self, settings: ConnectorSettings | None = None, workspace=None, cases_dir=None):
        self.settings = settings or ConnectorSettings()
        self.workspace = Workspace(workspace or self.settings.workspace_path())
        self.cases_dir = Path(cases_dir or CASES_DIR)
        self.jobs = JobManager(self.settings.one_job_at_a_time, self.settings.max_job_hours)

    # ---- plumbing -------------------------------------------------------------------------------

    def call(self, name, /, **arguments) -> dict:
        """Run one tool by name; errors become {"ok": false, "error": text}; calls on a project are logged."""
        method = getattr(self, name, None)
        if name not in TOOLS or method is None:
            return {"ok": False, "error": f"Unknown tool '{name}'."}
        try:
            out = method(**arguments)
            out = {"ok": True, **out}
        except TypeError as error:
            out = {"ok": False, "error": f"Wrong arguments for {name}: {error}"}
        except (SandboxError, ToolError, ValueError, KeyError, RuntimeError, FileNotFoundError) as error:
            text = error.args[0] if isinstance(error, KeyError) and error.args else str(error)
            out = {"ok": False, "error": str(text)}
        except Exception as error:      # noqa: BLE001 - an unexpected failure is reported, never hides as success
            out = {"ok": False, "error": f"{type(error).__name__}: {error}"[:600]}
        self._log(name, arguments, out)
        return out

    def _log(self, name, arguments, out):
        project = arguments.get("project") or (arguments.get("name") if name == "create_project" else None)
        if not isinstance(project, str):
            return
        try:
            folder = self.workspace.project_path(project)
        except SandboxError:
            return
        if not (folder / "project.yaml").is_file():
            return
        summary = {k: v for k, v in out.items() if k in ("ok", "error", "status", "verdict", "job_id", "applied",
                                                         "rejected", "cells", "path", "paths")}
        line = {"time": datetime.now().isoformat(timespec="seconds"), "tool": name,
                "arguments": json.loads(json.dumps(arguments, default=str)),
                "result": json.loads(json.dumps(summary, default=str))}
        with open(folder / AI_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False)[:20000] + "\n")

    def _cases(self):
        return find_cases(self.cases_dir)[0]

    def _case(self, template):
        cases = self._cases()
        if template not in cases:
            raise ToolError(f"There is no template '{template}'. Templates: {', '.join(cases)}.")
        return cases[template]

    def _open(self, project) -> Project:
        return Project.open(self.workspace.existing_project(project))

    def _not_running(self, project):
        name = self.workspace.existing_project(project).name[: -len(SUFFIX)]
        job = self.jobs.running_for(name)
        if job is not None:
            raise ToolError(f"Project '{project}' is running ({job.id}); stop it or wait before changing it.")

    def _limits(self, case) -> list:
        """Rows of the gap register that are not done and name this template (its known limits)."""
        path = DATA_DIR / "docs" / "gap_register.md"
        if not path.is_file():
            return []
        keys = {Path(case.folder).name.lower()}
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 3 or cells[1].lower().startswith(("done", "status", "---")):
                continue
            if any(k in line.lower() for k in keys):
                out.append(f"{cells[0]} ({cells[1]})"[:240])
        return out[:8]

    # ---- templates, gases, shapes ------------------------------------------------------------------

    @tool
    def list_templates(self) -> dict:
        """Every template (case) installed: name, title, what it solves, steady or not, has a solver."""
        return {"templates": [{"template": n, "title": c.title, "description": " ".join(c.description.split())[:300],
                               "steady": c.steady, "has_solver": c.has_solver}
                              for n, c in self._cases().items()]}

    @tool
    def describe_template(self, template: str) -> dict:
        """What a template solves and every input (unit, range, default, options, when it is shown)."""
        case = self._case(template)
        inputs = []
        for p in case.parameters():
            item = {"key": p.name, "label": p.label, "type": p.type, "step": p.step, "group": p.group}
            if p.is_number:
                item.update(unit=p.unit or "-", min=_plain(p.min), max=_plain(p.max))
            if p.type == "choice":
                item["options"] = list(p.options)
            if p.type == "gas":
                from aeroflowsim.gases import builtin_ids
                item["options"] = list(builtin_ids())
            item["default"] = _plain(p.default)
            if p.show_if is not None:
                item["only_if"] = {p.show_if[0]: _plain(p.show_if[1])}
            if p.help:
                item["help"] = " ".join(p.help.split())[:300]
            inputs.append({k: v for k, v in item.items() if v not in (None, "")})
        readme = Path(case.folder) / "README.md"
        about = " ".join(readme.read_text(encoding="utf-8").split())[:MAX_TEXT] if readme.is_file() else ""
        return {"template": template, "title": case.title, "description": case.description, "steady": case.steady,
                "has_solver": case.has_solver, "solver_message": "" if case.has_solver else case.solver_message,
                "about": about, "known_limits": self._limits(case), "inputs": inputs,
                "note": "Shape inputs are '<shape key>.<input>' and shown only for the chosen shape; use list_shapes "
                        "and set_geometry for them. Boundary tables and files are set with import_geometry or in "
                        "the desktop app."}

    @tool
    def list_gases(self) -> dict:
        """The built-in gas library (choose a gas by its id; never type gas properties)."""
        from aeroflowsim.gases import builtin_gas, builtin_ids
        return {"gases": [{"id": g, "name": builtin_gas(g).name} for g in builtin_ids()]}

    @tool
    def describe_gas(self, gas: str) -> dict:
        """Properties of a built-in gas at 300 K, with the source of the data (from the gas library)."""
        from aeroflowsim.gases import builtin_gas, builtin_ids, gas_model
        if gas not in builtin_ids():
            raise ToolError(f"There is no built-in gas '{gas}'. Gases: {', '.join(builtin_ids())}.")
        data, model = builtin_gas(gas), gas_model(gas)
        props = {"R [J/(kg K)]": _num(model.R), "gamma at 300 K": _num(model.gamma(300.0)),
                 "cp at 300 K [J/(kg K)]": _num(model.cp(300.0)), "mu at 300 K [Pa s]": _num(model.mu(300.0)),
                 "Pr": _num(model.prandtl(300.0)) if hasattr(model, "prandtl") else None}
        sources = []
        for attr in ("sources", "source", "references"):
            value = getattr(data, attr, None)
            if value:
                if isinstance(value, dict):
                    sources = [f"{k}: {v}" for k, v in value.items()]
                else:
                    sources = list(value) if isinstance(value, (list, tuple)) else [value]
                break
        return {"id": gas, "name": data.name, "properties": {k: v for k, v in props.items() if v is not None},
                "sources": [str(s)[:200] for s in sources][:10]}

    @tool
    def list_shapes(self) -> dict:
        """The shape library (bodies and nozzles) with each shape's inputs."""
        from aeroflowsim.shapes import find_shapes
        out = []
        for s in find_shapes().values():
            out.append({"shape": s.key, "name": s.name, "group": s.group, "symmetry": s.symmetry,
                        "description": " ".join(s.description.split())[:200],
                        "inputs": [{"key": p.name, "label": p.label, "unit": p.unit or "-", "default": _plain(p.default),
                                    **({"options": list(p.options)} if p.type == "choice" else {})}
                                   for p in s.inputs]})
        return {"shapes": out, "templates_with_shapes": [n for n, c in self._cases().items()
                                                         if any(p.name == "shape" for p in c.parameters())]}

    # ---- projects ---------------------------------------------------------------------------------

    @tool
    def create_project(self, template: str, name: str) -> dict:
        """A new project from a template, in the workspace. Refused if the name is taken (nothing is overwritten)."""
        case = self._case(template)
        folder = self.workspace.project_path(name)
        if folder.exists():
            raise ToolError(f"A project or folder '{folder.name}' already exists; choose another name.")
        self.workspace.ensure()
        project = Project.create(case.folder, folder)
        (project.folder / AI_LOG).touch()
        return {"project": folder.name[: -len(SUFFIX)], "template": template,
                "statuses": project.statuses(), "next": "get_inputs, then set_inputs"}

    @tool
    def list_projects(self) -> dict:
        """Projects in the workspace with their template and step status."""
        out = []
        for folder in self.workspace.projects():
            try:
                p = Project.open(folder)
                out.append({"project": untrusted(folder.name[: -len(SUFFIX)]), "template": Path(p.case.folder).name,
                            "statuses": p.statuses()})
            except ValueError as error:
                out.append({"project": untrusted(folder.name[: -len(SUFFIX)]), "error": str(error)[:200]})
        return {"workspace": str(self.workspace.root), "projects": out}

    @tool
    def get_inputs(self, project: str) -> dict:
        """The project's inputs that are in use now (value with unit), and the step statuses."""
        from aeroflowsim.parameters import is_shown
        p = self._open(project)
        params = p.case.parameters()
        inputs = {}
        for q in params:
            if not is_shown(q, p.values, params):
                continue
            value = p.values.get(q.name)
            if q.type in ("file", "text"):
                value = untrusted(value)
            elif q.type == "boundaries":
                value = {str(k): _plain(v) for k, v in (value or {}).items()}
                value = untrusted(json.dumps(value)[:600])
            else:
                value = _plain(value)
            inputs[q.name] = {"value": value, **({"unit": q.unit or "-"} if q.is_number else {})}
        return {"project": project, "template": Path(p.case.folder).name, "inputs": inputs,
                "statuses": p.statuses(), "warnings": [untrusted(w) for w in p.warnings]}

    @tool
    def set_inputs(self, project: str, inputs: dict) -> dict:
        """Change inputs: {key: {"value": v, "unit": "bar"}} (or a bare value for unitless inputs). Every value is
        checked against the template's schema; refused ones come back with the reason."""
        from aeroflowsim.assistant.context import SchemaContext
        from aeroflowsim.assistant.proposal import Proposal
        from aeroflowsim.assistant.review import _is_gas_property, review_proposals
        self._not_running(project)
        if not isinstance(inputs, dict) or not inputs:
            raise ToolError('inputs must be {"key": {"value": ..., "unit": ...}, ...}.')
        p = self._open(project)
        params = p.case.parameters()
        known = {q.name: q for q in params}
        proposals, rejected = [], []
        for key, spec in inputs.items():
            value, unit = (spec.get("value"), str(spec.get("unit", "") or "")) if isinstance(spec, dict) else (spec, "")
            q = known.get(key)
            if q is not None and q.is_number and not unit and q.unit not in ("", "-"):
                unit = q.unit                        # a bare number means the schema's own unit
            if q is not None and q.type == "choice" and isinstance(value, str) and value not in q.options:
                starts = [o for o in q.options if o.lower().startswith(value.strip().lower())]
                if len(starts) == 1:                 # "External" -> "External (body in a free stream)"
                    value = starts[0]
            if q is not None and _is_gas_property(q):
                rejected.append({"key": key, "reason": "gas properties come from the gas library: choose the gas"})
                continue
            proposals.append(Proposal(str(key), value, unit, "AI connector"))
        review = review_proposals(SchemaContext(params, dict(p.values)), proposals)
        rejected += [{"key": r.proposal.field, "reason": r.message} for r in review.rejected]
        applied = {}
        for row in review.rows:
            p.set_value(row.name, row.new)
            applied[row.name] = {"value": _plain(row.new), **({"unit": row.unit} if row.unit else {})}
        if applied:
            p.save()
        return {"applied": applied, "unchanged": review.unchanged, "rejected": rejected,
                "hints": self._hints(p), "statuses": p.statuses()}

    def _hints(self, p, mesh=None) -> list:
        """Smart-rule suggestions (shown, never applied)."""
        from aeroflowsim.smart_rules import numerics_suggestions
        try:
            return [{"title": s.title, "suggest": s.text, "why": s.reason[:300], "inputs": _plain(s.inputs)}
                    for s in numerics_suggestions(p.case, p.params(), mesh)][:6]
        except Exception:                            # noqa: BLE001 - a hint must never break a tool
            return []

    @tool
    def set_geometry(self, project: str, shape: str, params: dict | None = None) -> dict:
        """Choose a library shape (key or name, see list_shapes) and its inputs {input: {value, unit}}."""
        from aeroflowsim.shapes import find_shapes
        p = self._open(project)
        keys = {q.name for q in p.case.parameters()}
        if "shape" not in keys:
            raise ToolError(f"The template '{Path(p.case.folder).name}' has no shape library input.")
        shapes = find_shapes()
        found = shapes.get(shape) or next((s for s in shapes.values() if s.name.lower() == str(shape).lower()), None)
        if found is None:
            raise ToolError(f"There is no shape '{shape}' (list_shapes shows them).")
        inputs = {"shape": found.name}
        for k, v in (params or {}).items():
            inputs[k if k in keys else f"{found.key}.{k}"] = v
        out = self.set_inputs(project, inputs)
        return {"shape": found.key, **out}

    @tool
    def import_geometry(self, project: str, path: str, input: str | None = None, enclosure: str | None = None,
                        axisymmetric: bool | None = None) -> dict:
        """Copy a file from the workspace (CSV / DAT wall profile or coordinates, DXF, STEP, IGES, mesh file) into the
        project. Templates with a file input: that input is set to it. Templates with a geometry workspace and no
        file input (geometry_2d): the file is imported as in the GUI's Geometry step; enclosure = circle /
        rectangle / c_domain (fluid round a solid body) or plume / plenum (added to a nozzle); suggested boundary
        names are accepted; boundary_problems lists what is still missing."""
        self._not_running(project)
        p = self._open(project)
        source = self.workspace.path(path)
        if not source.is_file():
            raise ToolError(f"There is no file '{path}' in the workspace.")
        if source.suffix.lower() not in GEOMETRY_TYPES:
            raise ToolError(f"'{source.suffix}' files cannot be imported ({', '.join(sorted(GEOMETRY_TYPES))}).")
        files = [q for q in p.case.parameters() if q.type == "file"]
        from aeroflowsim.geometry_model.document import has_workspace
        if not files and input is None and has_workspace(p.case):
            return self._import_into_workspace(p, source, enclosure, axisymmetric)
        if input is not None:
            files = [q for q in files if q.name == input]
        elif len(files) > 1:
            fitting = [q for q in files if not q.file_types or source.suffix.lower().lstrip(".") in
                       [t.lower().lstrip(".*") for t in q.file_types]]
            files = fitting or files
        if not files:
            raise ToolError("This template has no file input" + (f" '{input}'." if input else "."))
        if len(files) > 1:
            raise ToolError(f"Say which input with input=: {', '.join(q.name for q in files)}.")
        rel = p.import_file(source)
        p.set_value(files[0].name, rel)
        problems = p.problems()
        p.save()
        return {"input": files[0].name, "stored_as": untrusted(rel),
                "problems": {k: str(v)[:300] for k, v in problems.items()}, "statuses": p.statuses()}

    def _import_into_workspace(self, p, source, enclosure, axisymmetric) -> dict:
        """The GUI's Import (gui/steps/geometry.py) + optional Enclosure + Accept suggestions, as workspace operations."""
        from aeroflowsim.geometry_model.boundaries import boundary_problems, suggestions
        from aeroflowsim.geometry_model.document import replay
        from aeroflowsim.geometry_model.importers import file_format, read_coordinate_points, read_wall_profile_points
        from aeroflowsim.geometry_model.operations import Enclosure, ImportFile, NameBoundary
        fmt = file_format(source)
        if fmt == "coordinates":
            op = ImportFile(format=fmt, source=source.name, points=read_coordinate_points(source).tolist())
        elif fmt == "wall_profile":
            op = ImportFile(format=fmt, source=source.name, unit="mm", points=read_wall_profile_points(source).tolist())
        else:
            op = ImportFile(format=fmt, source=source.name, file=p.import_file(source))
        doc = p.geometry_document()
        if axisymmetric is not None:
            doc.axisymmetric = bool(axisymmetric)
        doc.add(op)
        if enclosure:
            if enclosure not in Enclosure.KINDS:
                raise ToolError(f"enclosure must be one of {', '.join(Enclosure.KINDS)}.")
            doc.add(Enclosure(kind=enclosure))
        built = replay(doc, p.replay_context())
        groups = {}
        for edge_id, b in suggestions(built).items():
            groups.setdefault((b.name, b.type), []).append(edge_id)
        for (name, kind), edges in sorted(groups.items()):
            doc.add(NameBoundary(edges=sorted(edges), name=name, kind=kind))
        built = replay(doc, p.replay_context())
        p.set_geometry_document(doc)
        p.save()
        names = sorted({b.name for b in built.names.values()}) if hasattr(built, "names") else []
        return {"format": fmt, "boundaries": [untrusted(n) for n in names],
                "boundary_problems": [{"level": lv, "message": t[:300]} for lv, t in boundary_problems(built)],
                "messages": [(m[1] if isinstance(m, tuple) else str(m))[:200] for m in getattr(built, "messages", [])][:8], "statuses": p.statuses(),
                "note": "Edges without a suggested name (e.g. inlet / outlet of a planar duct) must be named in the "
                        "desktop app's Geometry step."}

    # ---- mesh, checks, estimate -----------------------------------------------------------------

    @tool
    def mesh(self, project: str, preset: str | None = None) -> dict:
        """Build the mesh now (preset Coarse / Medium / Fine where the template has one) and return its size and
        quality checks."""
        from aeroflowsim.checks import run_mesh_checks
        from aeroflowsim.project import build_project_mesh
        self._not_running(project)
        p = self._open(project)
        if preset:
            q = next((q for q in p.case.parameters() if q.step == "mesh" and q.type == "choice"
                      and q.name.endswith("preset")), None)
            if q is None:
                raise ToolError("This template has no mesh preset; set its mesh-size inputs with set_inputs.")
            option = next((o for o in q.options if o.lower() == preset.lower()), None)
            if option is None:
                raise ToolError(f"Preset must be one of {', '.join(q.options)}.")
            p.set_value(q.name, option)
            p.save()
        started = time.perf_counter()
        mesh = build_project_mesh(p)
        p.save()
        checks = run_mesh_checks(p.case, p.params(), mesh)
        return {**self._mesh_stats(mesh), "seconds": _num(time.perf_counter() - started, 3),
                "checks": [self._check(c) for c in checks], "statuses": p.statuses()}

    @staticmethod
    def _mesh_stats(mesh) -> dict:
        out = {"cells": int(getattr(mesh, "n_cells", 0) or len(getattr(mesh, "x", []) or [])),
               "dimension": int(getattr(mesh, "dim", 1))}
        if hasattr(mesh, "cell_types"):
            from aeroflowsim.mesh import CELL_TYPES
            import numpy as np
            types, counts = np.unique(mesh.cell_types, return_counts=True)
            out["cell_types"] = {getattr(CELL_TYPES.get(int(t)), "name", str(int(t))): int(n)
                                 for t, n in zip(types, counts)}
        if hasattr(mesh, "patches"):
            out["patches"] = [{"name": untrusted(pt.name), "faces": int(pt.count)} for pt in mesh.patches]
        return out

    @staticmethod
    def _check(c) -> dict:
        out = {"check": c.name, "level": c.level, "message": " ".join(str(c.message).split())[:400]}
        if c.value is not None:
            out["value"] = _num(c.value, 4)
        return out

    def _estimate(self, p, mesh) -> dict:
        """Rough wall time and memory of a run (shown to the user before long runs)."""
        from aeroflowsim.compute import free_memory_bytes, run_memory_estimate
        cells = int(getattr(mesh, "n_cells", 0) or 0)
        dim = int(getattr(mesh, "dim", 1))
        iterations = p.values.get("max_iter")
        out = {"cells": cells, "max_iterations": iterations}
        if dim in ROUGH_S_PER_CELL_ITERATION and iterations:
            per = ROUGH_S_PER_CELL_ITERATION[dim]
            if p.values.get("flow_model", "Euler") != "Euler":
                per *= VISCOUS_FACTOR
            out["minutes_at_most"] = _num(cells * int(iterations) * per / 60.0, 3)
            out["note"] = "rough upper estimate: max iterations x cells x measured cost; converged runs stop earlier"
        if dim == 3 and cells:
            need, free = run_memory_estimate(cells, 3), free_memory_bytes()
            out["memory_GB"] = _num(need / 1e9, 3)
            if free:
                out["free_memory_GB"] = _num(free / 1e9, 3)
                out["memory_share"] = _num(need / free, 3)
        out["needs_confirmation"] = bool(out.get("minutes_at_most", 0) > self.settings.confirm_minutes
                                         or out.get("memory_share", 0) > self.settings.memory_fraction)
        return out

    @tool
    def check(self, project: str) -> dict:
        """Mesh and setup checks before a run, what to try, smart-rule suggestions and the run estimate."""
        from aeroflowsim.checks import run_mesh_checks, run_setup_checks
        p = self._open(project)
        problems = {k: str(v)[:300] for k, v in p.problems().items()}
        if p.status("mesh") != "ok":
            return {"problems": problems, "statuses": p.statuses(),
                    "message": "No up-to-date mesh: call mesh first (the checks and the estimate need it)."}
        mesh = p.load_mesh()
        checks = run_mesh_checks(p.case, p.params(), mesh) + run_setup_checks(p.case, p.params(), mesh)
        return {"problems": problems, "checks": [self._check(c) for c in checks],
                "hints": self._hints(p, mesh), "estimate": self._estimate(p, mesh), "statuses": p.statuses(),
                "ready": not problems and not any(c.level == "error" for c in checks)}

    # ---- runs -------------------------------------------------------------------------------------

    @tool
    def run(self, project: str, confirm: bool = False, fresh: bool = False) -> dict:
        """Start a run in the background (returns a job id). Like the GUI's Run it carries on from the saved
        result on the same mesh; fresh=true starts from scratch. Long or memory-heavy runs first return
        status "needs_confirmation": ask the user, then call again with confirm=true."""
        from aeroflowsim.project import build_project_mesh
        self._not_running(project)
        p = self._open(project)
        if not p.case.has_solver:
            raise ToolError(p.case.solver_message or "This template has no solver (mesh only).")
        problems = p.problems()
        if problems:
            raise ToolError("Fix these inputs first: " + "; ".join(f"{k}: {v}" for k, v in problems.items())[:600])
        mesh = p.load_mesh() if p.status("mesh") == "ok" else None
        if mesh is None:
            mesh = build_project_mesh(p)
            p.save()
        estimate = self._estimate(p, mesh)
        if estimate["needs_confirmation"] and not confirm:
            return {"status": "needs_confirmation", "estimate": estimate,
                    "message": "This run may be long or memory-heavy. ASK THE USER before calling run again with "
                               "confirm=true."}
        p = self._open(project)                       # a fresh object for the run thread
        job = self.jobs.start(p, fresh=fresh, on_done=self._after_run)
        return {"status": "started", "job_id": job.id, "estimate": estimate,
                "next": "job_status(job_id) every few seconds to minutes; get_results when it has ended"}

    def _after_run(self, job, output):
        """Provenance in summary.yaml of the run (safety rule 6)."""
        try:
            folder = self.workspace.existing_project(job.project)
        except SandboxError:
            return
        summary = folder / "results" / "summary.yaml"
        if summary.is_file():
            with open(summary, "a", encoding="utf-8") as f:
                f.write(f"provenance: \"{AI_PROVENANCE}\"\n")
        with open(folder / AI_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "event": "run ended",
                                "job_id": job.id, "status": job.status, "error": job.error[:300]}) + "\n")

    @tool
    def continue_run(self, project: str, confirm: bool = False) -> dict:
        """Carry on from the project's saved (e.g. stopped) result."""
        p = self._open(project)
        if p.load_results() is None:
            raise ToolError("The project has no result to continue from: use run.")
        return self.run(project, confirm=confirm, fresh=False)

    @tool
    def job_status(self, job_id: str) -> dict:
        """Progress of a run: status, iteration, residual drop, latest monitor values, time, rough ETA."""
        job = self.jobs.get(job_id)
        out = {"job_id": job.id, "project": job.project, "status": job.status, "elapsed_s": _num(job.elapsed_s(), 4)}
        if job.iterations:
            it = job.iterations[-1]
            out.update(iteration=it, residual=_num(job.residuals[-1], 4))
            first = max(job.residuals[0], 1e-300)
            out["residual_drop_orders"] = _num(math.log10(first / max(job.residuals[-1], 1e-300)), 3)
            out["monitors"] = {k: _num(v[-1], 6) for k, v in list(job.monitors.items())[:8]}
            if job.running and job.max_iterations and it > 0:
                out["eta_s_at_most"] = _num(job.elapsed_s() / max(len(job.iterations), 1)
                                            * max(int(job.max_iterations) - it, 0), 3)
        if job.error:
            out["error"] = job.error
        if job.stop_reason:
            out["stop_reason"] = job.stop_reason
        return out

    @tool
    def stop_job(self, job_id: str) -> dict:
        """Ask a run to stop cleanly after its current iteration (the flow of that moment is saved)."""
        job = self.jobs.stop(job_id)
        return {"job_id": job.id, "status": job.status, "message": "Stop asked; poll job_status until it has ended."}

    # ---- results ------------------------------------------------------------------------------

    @tool
    def get_results(self, project: str) -> dict:
        """Key numbers of the saved run with the software's own verdict, failed checks, what to try and known
        limits. A diverged run gives no numbers. The verdict is the software's and may not be changed."""
        from aeroflowsim.smart_rules import diagnose
        p = self._open(project)
        payload = p.load_results()
        if payload is None:
            raise ToolError("The project has no result yet: run it first.")
        result = payload["result"]
        info = getattr(result, "info", None) or {}
        status = info.get("status") or ("converged" if result.converged else "max_iterations")
        if p.status("run") != "ok":
            freshness = "OUT OF DATE: inputs or mesh changed since this run; run again before using these numbers"
        else:
            freshness = "up to date"
        checks = [self._check(c) for c in payload.get("checks", [])]
        failed = [c for c in checks if c["level"] in ("warning", "error")]
        verdict = {"converged": "converged", "stopped": "stopped (not converged)", "diverged": "DIVERGED",
                   "max_iterations": "max iterations reached (not converged)"}.get(status, status)
        if status in ("converged",) and any(c["level"] == "error" for c in failed):
            verdict = "converged, but a check failed (see failed_checks)"
        out = {"project": project, "verdict": verdict, "results": freshness, "iterations": int(result.iterations),
               "wall_time_s": _num(info.get("wall_time_s"), 4), "failed_checks": failed,
               "known_limits": self._limits(p.case)}
        if status == "diverged":
            out["key_numbers"] = None
            out["message"] = "The run diverged: its numbers are not results and are not given."
        else:
            out["key_numbers"] = {k: [_num(v[0]), v[1]] for k, v in result.key_numbers.items()}
            if status != "converged":
                out["message"] = "Not converged: these numbers are the state of that moment, not an answer."
        try:
            out["what_to_try"] = [{"title": s.title, "suggest": s.text, "why": s.reason[:300]}
                                  for s in diagnose(p.case, p.params(), result)]
        except Exception:                            # noqa: BLE001
            out["what_to_try"] = []
        return out

    @tool
    def get_plot(self, project: str, kind: str = "residuals", field: str | None = None) -> dict:
        """A PNG picture: residuals, fields (1D), contour (2D / 3D field: M, p, T, rho, ...; default M), mesh, wall (pressure
        along the wall)."""
        if kind not in PLOT_KINDS:
            raise ToolError(f"kind must be one of {', '.join(PLOT_KINDS)}.")
        p = self._open(project)
        folder = p.results_dir / "ai_plots"
        folder.mkdir(parents=True, exist_ok=True)
        path = _unique(folder / f"{kind}{'_' + re.sub(r'[^A-Za-z0-9]', '', field) if field else ''}.png")
        payload = p.load_results() if kind != "mesh" else None
        if kind != "mesh" and payload is None:
            raise ToolError("The project has no result yet: run it first.")
        if kind == "residuals":
            from aeroflowsim.runner import plot_residuals
            plot_residuals(path, p.case, payload["result"])
        elif kind == "fields":
            from aeroflowsim.runner import plot_fields
            if hasattr(p.load_mesh(), "patches"):
                raise ToolError("'fields' plots are for 1D templates; use kind='contour' (field=...) or 'wall'.")
            plot_fields(path, p.case, p.load_mesh(), payload["result"], payload.get("reference"))
        else:
            from aeroflowsim.post.pictures import field_picture, mesh_picture
            mesh = p.load_mesh()
            if mesh is None or not hasattr(mesh, "patches"):
                raise ToolError(f"'{kind}' pictures need a 2D or 3D mesh; for 1D templates use kind='fields'.")
            if kind == "mesh":
                fig = mesh_picture(mesh)
            elif kind == "contour":
                from aeroflowsim.post.solution import Solution
                if mesh.dim == 3:
                    from aeroflowsim.post.pictures import slice_picture
                    fig = slice_picture(Solution.from_project(p), field or "M")
                else:
                    fig = field_picture(Solution.from_project(p), field or "M")
            else:
                fig = self._wall_figure(p, payload["result"])
            fig.savefig(path, dpi=110)
        return {"kind": kind, "path": str(path.relative_to(self.workspace.root)),
                "png_base64": base64.b64encode(path.read_bytes()).decode("ascii")}

    @staticmethod
    def _wall_figure(p, result):
        from matplotlib.figure import Figure
        series = getattr(result, "series", {}) or {}
        xs = next((k for k in ("wall_x", "wallp_x", "cp_x") if k in series), None)
        ys = next((k for k in ("wall_p", "wall_pressure", "cp") if k in series), None)
        if xs is None or ys is None:
            raise ToolError(f"This result has no wall distribution (series: {', '.join(list(series)[:12])}).")
        fig = Figure(figsize=(7.0, 3.6))
        ax = fig.add_subplot()
        ax.plot(series[xs], series[ys], ".", ms=3)
        ax.set_xlabel(f"{xs} [SI]")
        ax.set_ylabel(f"{ys} [SI]")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        return fig

    @tool
    def compare_runs(self, projects: list) -> dict:
        """Key numbers and verdicts of several projects side by side."""
        if not isinstance(projects, list) or not 1 <= len(projects) <= 12:
            raise ToolError("projects must be a list of 1 to 12 project names.")
        rows = []
        for name in projects:
            r = self.call("get_results", project=name)
            rows.append({"project": name, "verdict": r.get("verdict", r.get("error")),
                         "results": r.get("results"), "key_numbers": r.get("key_numbers")})
        return {"runs": rows}

    @tool
    def export(self, project: str, format: str = "csv") -> dict:
        """Export the solution: csv (cell values), vtu (ParaView), tecplot, or the mesh as su2 / msh / cgns.
        New file names every time (nothing is overwritten)."""
        from aeroflowsim.post import export as ex
        p = self._open(project)
        folder = p.results_dir / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        fmt = format.lower()
        if fmt in ("su2", "msh", "cgns"):
            from aeroflowsim import mesh_io
            mesh = p.load_mesh()
            if mesh is None or not hasattr(mesh, "patches"):
                raise ToolError("The project has no 2D / 3D mesh to export.")
            path = mesh_io.write_mesh(mesh, _unique(folder / f"mesh.{fmt}"))
        elif fmt in ("csv", "vtu", "tecplot"):
            mesh = p.load_mesh()
            if p.load_results() is None:
                raise ToolError("The project has no result yet: run it first.")
            if mesh is None or not hasattr(mesh, "patches"):
                source = p.results_dir / "fields.csv"
                if fmt != "csv" or not source.is_file():
                    raise ToolError("1D templates export csv only (fields.csv of the run).")
                path = _unique(folder / "fields.csv")
                path.write_bytes(source.read_bytes())
            else:
                from aeroflowsim.post.solution import Solution
                sol = Solution.from_project(p)
                if fmt == "vtu":
                    path = ex.fields_vtu(sol, _unique(folder / "fields.vtu"), ())
                elif fmt == "tecplot":
                    path = ex.fields_tecplot(sol, _unique(folder / "fields.dat"), ())
                else:
                    path = ex.fields_csv(sol, _unique(folder / "fields_cell.csv"), (), "cell")
        else:
            raise ToolError("format must be csv, vtu, tecplot, su2, msh or cgns.")
        return {"path": str(Path(path).relative_to(self.workspace.root))}

    @tool
    def make_report(self, project: str, pdf: bool = False) -> dict:
        """The automatic HTML (and optionally PDF) report of the project's result, in a new folder."""
        from aeroflowsim.post.report import write_report
        p = self._open(project)
        out = _unique(p.results_dir / "report_ai")
        paths = write_report(p, out, formats=("html", "pdf") if pdf else ("html",))
        return {"paths": [str(Path(x).relative_to(self.workspace.root)) for x in paths]}

    # ---- validation and docs ----------------------------------------------------------------------

    def _validation_dir(self) -> Path:
        return DATA_DIR / "validation"

    @tool
    def list_validation_cases(self) -> dict:
        """The validation cases (each compares AeroFlowSim with theory, experiment or another code)."""
        folder = self._validation_dir()
        names = sorted(d.name for d in folder.iterdir() if (d / "reference.toml").is_file()) if folder.is_dir() else []
        return {"cases": names, "report": "get_validation_report(case) shows the measured errors"}

    @tool
    def get_validation_report(self, case: str | None = None) -> dict:
        """The validation report: the overall line, or the section of one case (status, errors, tolerances)."""
        path = self._validation_dir() / "report.md"
        if not path.is_file():
            raise ToolError("There is no validation report in this installation.")
        text = path.read_text(encoding="utf-8")
        overall = next((line for line in text.splitlines() if line.startswith("**Overall")), "")
        if not case:
            return {"overall": overall, "cases": self.list_validation_cases()["cases"]}
        sections = re.split(r"\n(?=## )", text)
        found = next((s for s in sections if f"validation/{case}/" in s), None)    # its reference.toml path
        if found is None:
            found = next((s for s in sections if case in (s.splitlines()[0] if s else "")), None)
        if found is None:
            raise ToolError(f"No section for '{case}' in the validation report.")
        return {"overall": overall, "case": case, "section": found[:MAX_TEXT * 2]}

    @tool
    def search_docs(self, query: str, max_results: int = 5) -> dict:
        """Search the user guide, theory manual and gap register; returns matching sections (file, heading,
        snippet) so limits and methods can be explained with their source."""
        words = [w for w in re.findall(r"[a-z0-9+]+", str(query).lower()) if len(w) > 1]
        if not words:
            raise ToolError("Give some words to search for.")
        hits = []
        for name in ("user_guide.md", "theory_manual.md", "gap_register.md"):
            path = DATA_DIR / "docs" / name
            if not path.is_file():
                continue
            for section in re.split(r"\n(?=#{1,4} )", path.read_text(encoding="utf-8")):
                low = section.lower()
                score = sum(low.count(w) for w in words) + 5 * sum(w in low.splitlines()[0] for w in words if low)
                if score and all(w in low for w in words[:3]):
                    heading = section.splitlines()[0].lstrip("# ").strip() if section else ""
                    hits.append((score, name, heading, " ".join(section.split())[:600]))
        hits.sort(key=lambda h: -h[0])
        return {"results": [{"file": f"docs/{n}", "section": h, "snippet": s}
                            for _sc, n, h, s in hits[:max(1, min(int(max_results), 10))]]}


__all__ = ["Api", "TOOLS", "ToolError", "untrusted"]

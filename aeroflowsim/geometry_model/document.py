# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The geometry document: a planar/axisymmetric flag and an ordered list of operations (the history).

Like a CAD "feature tree", the geometry is not stored as a drawing but as the recipe that makes
it: insert the template shape, rotate it, put a C-domain around it, name these edges ... To get
the geometry, replay() runs the operations from the top, in order, in the CAD kernel. Editing an
earlier operation therefore automatically re-runs the later ones, and undo/redo only has to swap
one list of operations for another.

Saved in a project as geometry/history.json:
    {"format": 1, "axisymmetric": false, "next_number": 4,
     "operations": [{"id": "op1", "type": "template_shape", "suppressed": false}, ...]}

A project WITHOUT history.json uses template_document(case): the template's own geometry, exactly
as before this workspace existed (so old projects are unchanged).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from aeroflowsim.geometry_model.built import BuiltGeometry
from aeroflowsim.geometry_model.kernel import Kernel, gmsh_session
from aeroflowsim.geometry_model.operations import (
    TEMPLATE_TYPES, Operation, TemplateEnclosure, TemplateShape, operation_from_dict)

FORMAT = 1
HISTORY_FILE = "history.json"


class GeometryDocument:
    def __init__(self, operations=(), axisymmetric=False, next_number=None):
        self.operations = list(operations)
        self.axisymmetric = bool(axisymmetric)       # for documents without a template shape
        numbers = [int(op.id[2:]) for op in self.operations if op.id.startswith("op") and op.id[2:].isdigit()]
        self.next_number = max(next_number or 1, max(numbers, default=0) + 1)

    # ---- editing (each returns nothing; the GUI copies the document first for undo) -------------

    def new_id(self) -> str:
        op_id = f"op{self.next_number}"
        self.next_number += 1
        return op_id

    def add(self, op: Operation, index=None) -> Operation:
        """Append (or insert at index) an operation; it gets a fresh id if it has none."""
        if not op.id:
            op.id = self.new_id()
        if index is None:
            self.operations.append(op)
        else:
            self.operations.insert(index, op)
        return op

    def find(self, op_id) -> Operation:
        for op in self.operations:
            if op.id == op_id:
                return op
        raise KeyError(op_id)

    def index(self, op_id) -> int:
        return [op.id for op in self.operations].index(op_id)

    def replace(self, op: Operation):
        self.operations[self.index(op.id)] = op

    def remove(self, op_id):
        del self.operations[self.index(op_id)]

    def copy(self) -> "GeometryDocument":
        return GeometryDocument.from_dict(self.to_dict())

    # ---- facts -----------------------------------------------------------------------------------

    def is_template_only(self) -> bool:
        """True if the document is just the template's own geometry (no edits): then the template's
        own mesher can be used, exactly as before the workspace existed."""
        active = [op for op in self.operations if not op.suppressed]
        return bool(active) and all(op.type in TEMPLATE_TYPES for op in active) and \
            len(active) == len(self.operations)

    def uses_template(self) -> bool:
        return any(op.type in TEMPLATE_TYPES and not op.suppressed for op in self.operations)

    # ---- saving ----------------------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {"format": FORMAT, "axisymmetric": self.axisymmetric, "next_number": self.next_number,
                "operations": [op.to_dict() for op in self.operations]}

    @classmethod
    def from_dict(cls, data) -> "GeometryDocument":
        if int(data.get("format", 0)) > FORMAT:
            raise ValueError("This geometry was saved by a newer AeroFlowSim; please update AeroFlowSim.")
        ops = [operation_from_dict(d) for d in data.get("operations", [])]
        return cls(ops, data.get("axisymmetric", False), data.get("next_number"))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=1)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(self.to_json(), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path) -> "GeometryDocument":
        try:
            return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not read the geometry history {path}: {error}") from None

    def __eq__(self, other):
        return isinstance(other, GeometryDocument) and self.to_dict() == other.to_dict()


def has_workspace(case) -> bool:
    """True if a template's geometry can be edited in the workspace (it makes 2D meshes)."""
    return case is not None and hasattr(case, "workspace_settings")


def template_document(case) -> GeometryDocument:
    """The document of an unedited template: its shape (and its far field, if it has one)."""
    ops = []
    if case is not None and hasattr(case, "geometry"):
        ops.append(TemplateShape("op1"))
        if hasattr(case, "domain"):
            ops.append(TemplateEnclosure("op2"))
    return GeometryDocument(ops)


@dataclass
class ReplayContext:
    """What operations may need besides their own parameters."""

    case: object = None             # the template (Case), for template operations
    params: dict = None             # validated inputs of the template
    folder: Path = None             # project folder (imported files are stored relative to it)
    _profile: object = field(default=None, repr=False)

    def template_geometry(self):
        """The template's WallProfile / ShapeProfile for the inputs (computed once per replay)."""
        if self._profile is None:
            if self.case is None or not hasattr(self.case, "geometry"):
                return None
            self._profile = self.case.geometry(self.params)
        return self._profile

    def path(self, relative) -> Path:
        path = Path(relative)
        return path if path.is_absolute() or self.folder is None else Path(self.folder) / path


def run_operations(kernel, document, context):
    """Apply every active operation in order; stop at the first one that fails (later ones depend on it)."""
    kernel.axisymmetric = document.axisymmetric
    for op in document.operations:
        if op.suppressed:
            continue
        try:
            op.apply(kernel, context)
            kernel.remove_free_points()
        except Exception as error:      # any kernel error becomes a message, never a crash
            text = str(error) or type(error).__name__
            kernel.message(f"{op.title} ({op.id}) failed: {text}", "error")
            kernel.failed_operation = op.id
            break


def replay(document, context=None, triangulate=True) -> BuiltGeometry:
    """Build the geometry of a document (see the module docstring)."""
    context = context or ReplayContext()
    with gmsh_session() as gmsh:
        kernel = Kernel(gmsh)
        run_operations(kernel, document, context)
        return kernel.extract(triangulate)

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The boundary-condition table of the Setup step, decided WITHOUT any window (no Qt), so it is unit-tested.

The value of a "boundaries" input is a dict {patch name: {"type": ..., input: value, ...}} holding only
the boundaries the user changed; every other boundary follows the template's default for its kind
(aeroflowsim/euler/setup.py, conditions). This module turns that into rows for the table:

    BoundaryRow   one boundary: its name, its kind from the mesh (inlet, outlet, wall, ...), the
                  condition in force, whether the user changed it, and a WidgetSpec for every input of
                  its type (numbers in the user's display units, like every other input)

and returns the new table value after an edit (change the type, change one value, back to default).
The Qt widget (aeroflowsim/gui/panel.py, BoundaryTable) only draws these rows.
"""

from dataclasses import dataclass

from aeroflowsim.euler.boundary import BC_TYPES, BoundaryCondition
from aeroflowsim.gui.panel_model import widget_spec
from aeroflowsim.parameters import is_shown

NO_MESH = "Make the mesh first: the boundaries in this table are the named boundaries (patches) of the mesh."


@dataclass
class BoundaryRow:
    """One row of the table."""

    name: str                 # patch name, e.g. "inlet"
    kind: str                 # patch kind from the mesh, e.g. "inlet"
    condition: BoundaryCondition
    changed: bool             # True: set by the user (stored in the table); False: the template's default
    specs: list               # WidgetSpec of every input of the condition's type
    visible: set              # names of the inputs shown (show_if)

    @property
    def type_label(self) -> str:
        return BC_TYPES[self.condition.type].label

    @property
    def suits(self) -> bool:
        """False when the type is unusual for this kind of boundary (e.g. a wall given an inlet)."""
        return self.kind in BC_TYPES[self.condition.type].suits


def type_choices():
    """[(type key, label)] for the type dropdown, in the order of BC_TYPES."""
    return [(key, t.label) for key, t in BC_TYPES.items()]


def rows(table, effective, units=None) -> list[BoundaryRow]:
    """Rows for the table. effective: [(name, kind, BoundaryCondition, changed)] from
    aeroflowsim.euler.setup.table_rows (the mesh patches with the conditions in force)."""
    out = []
    for name, kind, bc, changed in effective:
        inputs = list(BC_TYPES[bc.type].inputs)
        specs = [widget_spec(p, units) for p in inputs]
        visible = {p.name for p in inputs if is_shown(p, bc.values, inputs)}
        out.append(BoundaryRow(name, kind, bc, changed, specs, visible))
    return out


def with_type(table, row: BoundaryRow, new_type) -> dict:
    """The table after choosing another type for a boundary; values of inputs with the same name are kept
    (e.g. p and T when switching between far field and supersonic inlet)."""
    table = dict(table or {})
    keep = {k: v for k, v in row.condition.values.items() if k in {p.name for p in BC_TYPES[new_type].inputs}}
    table[row.name] = BoundaryCondition(new_type, keep).to_dict()
    return table


def with_value(table, row: BoundaryRow, key, value) -> dict:
    """The table after changing one input of a boundary (the whole condition is then stored)."""
    table = dict(table or {})
    entry = row.condition.to_dict()
    entry[key] = value
    table[row.name] = entry
    return table


def without(table, row: BoundaryRow) -> dict:
    """The table after putting a boundary back to the template's default."""
    table = dict(table or {})
    table.pop(row.name, None)
    return table

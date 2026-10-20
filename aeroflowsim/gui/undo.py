# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Undo / redo of input changes with Qt's QUndoStack (Edit > Undo, Ctrl+Z; Edit > Redo, Ctrl+Y).

Every change of the inputs is a command that knows the old and the new values; QUndoStack keeps
the list and calls undo() / redo(). The window applies the values (project, panels, statuses), so
undoing a geometry change also turns an "outdated" mesh back to green when the inputs match again.
"""

from PySide6.QtGui import QUndoCommand


class SetInputs(QUndoCommand):
    """Change one or more inputs: changes = {name: (old value, new value)}."""

    def __init__(self, window, changes, text):
        super().__init__(text)
        self.window = window
        self.changes = dict(changes)

    def redo(self):
        self.window.apply_values({name: new for name, (old, new) in self.changes.items()})

    def undo(self):
        self.window.apply_values({name: old for name, (old, new) in self.changes.items()})

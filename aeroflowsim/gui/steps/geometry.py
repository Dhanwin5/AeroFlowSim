# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Geometry step: the geometry workspace (import, edit, enclosure, name boundaries by clicking).

For templates that make 2D meshes (case.py has workspace_settings) the page shows the project's
geometry history (aeroflowsim/geometry_model/) replayed, in a clickable view:
    tool bar        Select / Move / Drag points modes, Import, Transform, Fillet, Delete,
                    Fluid/solid, Boolean, Enclosure, Name boundary, Refinement, Axisymmetric
    view            click = select (Shift/Ctrl adds), drag in Move mode moves the selection
    History tab     the operations in order: click one to edit its settings, suppress or delete it
    Boundaries tab  the boundary names (mesh patches): accept suggestions, rename, change the type
    Dimensions tab  sizes, areas and the template's key dimensions
Every change makes a new history, which the window puts on the undo stack (Edit > Undo).
The decisions are in gui/geometry_logic.py (no Qt); this page only draws and forwards clicks.

1D templates (no workspace) keep the read-only drawing of aeroflowsim/geometry_preview.py.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
                               QMenu, QMessageBox, QPushButton, QScrollArea, QSplitter, QTabWidget, QToolBar,
                               QToolButton, QVBoxLayout,
                               QWidget)

from aeroflowsim.geometry_model import has_workspace, replay, template_document
from aeroflowsim.geometry_model.boundaries import BOUNDARY_TYPES
from aeroflowsim.geometry_model.importers import file_format, read_coordinate_points, read_wall_profile_points
from aeroflowsim.geometry_model.operations import TEMPLATE_TYPES, ImportFile, Transform
from aeroflowsim.geometry_preview import geometry_preview
from aeroflowsim.gui import geometry_logic as logic
from aeroflowsim.gui.geometry_forms import ImportDialog, OperationDialog, OperationForm, PointTableDialog
from aeroflowsim.gui.geometry_view import GeometryView
from aeroflowsim.gui.logic import readable
from aeroflowsim.gui.theme import PATCH_COLOURS, colour
from aeroflowsim.gui.widgets import Banner, ValueTable

IMPORT_FILTER = ("Geometry files (*.dxf *.step *.stp *.iges *.igs *.csv *.dat *.txt);;DXF (*.dxf);;"
                 "STEP (*.step *.stp);;IGES (*.iges *.igs);;Coordinates (*.csv *.dat *.txt)")
STATE_TEXT = {"ok": "", "template": "", "suppressed": "  (suppressed)", "failed": "  (FAILED)",
              "not run": "  (not run: an earlier step failed)"}
EDIT_MENU = ("transform", "fillet", "delete", "set_role", "boolean")   # in the Edit menu button
TOOLS = (   # (operation kind, button text, tooltip)
    ("transform", "Transform…", "Move, rotate (angle of attack), scale or mirror the selected faces (or everything)"),
    ("fillet", "Fillet…", "Round the selected corner (a point where two edges meet)"),
    ("delete", "Delete", "Delete the selected faces or free curves (Del)"),
    ("set_role", "Fluid / solid…", "Mark the selected faces as fluid (meshed) or solid (cut out)"),
    ("boolean", "Boolean…", "Union, subtract or intersect the selected faces (first = object)"),
    ("enclosure", "Enclosure…", "Put a fluid domain (circle, rectangle, C-domain) around the solid bodies"),
    ("name_boundary", "Name boundary…", "Give the selected edges a boundary name and type (a mesh patch)"),
    ("refinement", "Refinement…", "A box, circle or wake line with smaller cells"),
)


class GeometryPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.banner = Banner()
        self.view = GeometryView()
        self.view.picked.connect(self.on_picked)
        self.view.moved.connect(self.on_moved)
        self.view.point_moved.connect(self.on_point_moved)
        self.preview = None              # 1D templates: the read-only GeometryPreview
        self.built = None                # workspace: the replayed geometry (BuiltGeometry)
        self.document = None             # the history that self.built shows
        self.selection = []              # [(kind, id)]
        self._key = None                 # what self.built was made from (to replay only after changes)
        self._points_op = None           # id of the operation whose points are being dragged
        self._fit_next = False           # fit the camera to the next drawing (after an import)
        self._logged = set()             # geometry messages already written to the Messages panel

        self.toolbar = self._build_toolbar()
        self.history = QListWidget(wordWrap=True)
        self.history.currentRowChanged.connect(self.show_operation)
        self.op_box = QVBoxLayout()
        op_widget = QWidget()
        op_widget.setLayout(self.op_box)
        op_scroll = QScrollArea(widgetResizable=True)
        op_scroll.setWidget(op_widget)
        self.form = None
        history_tab = QWidget()
        h = QVBoxLayout(history_tab)
        h.addWidget(QLabel("Steps, replayed from the top. Click one to change it."))
        h.addWidget(self.history, 2)
        h.addWidget(op_scroll, 3)

        self.boundaries = ValueTable(["Boundary", "Type", "Edges", "Inflation", "Named by"])
        self.boundaries.itemSelectionChanged.connect(self.select_boundary_edges)
        self.boundaries.cellDoubleClicked.connect(lambda row, col: self.change_type() if col == 1 else self.rename())
        boundary_tab = QWidget()
        b = QVBoxLayout(boundary_tab)
        b.addWidget(QLabel("Every boundary edge needs a name and a type; they become the mesh patches."))
        b.addWidget(self.boundaries, 1)
        row = QGridLayout()
        for n, (text, slot, tip) in enumerate((("Accept suggestions", self.accept_suggestions, "Name the unnamed edges as suggested "
                                 "(axis on y = 0, walls of bodies, far field around them, nozzle inlet/outlet)"),
                                ("Rename…", self.rename, "Rename the selected boundary everywhere"),
                                ("Type…", self.change_type, "Change the type of the selected boundary"),
                                ("Inflation on/off", self.toggle_inflation, "Inflation layers on this boundary"))):
            button = QPushButton(text, toolTip=tip)
            button.clicked.connect(slot)
            row.addWidget(button, n // 2, n % 2)
        b.addLayout(row)
        self.suggestion_note = QLabel(wordWrap=True, objectName="hint")
        b.addWidget(self.suggestion_note)

        self.summary = ValueTable(["Quantity", "Value", "Unit"])
        self.tabs = QTabWidget()
        self.tabs.addTab(history_tab, "History")
        self.tabs.addTab(boundary_tab, "Boundaries")
        self.tabs.addTab(self.summary, "Dimensions")
        self.tabs.setMinimumWidth(360)

        splitter = QSplitter()
        splitter.addWidget(self.view)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.banner)
        layout.addWidget(splitter, 1)
        QShortcut(QKeySequence.Delete, self, activated=lambda: self.add_operation("delete"),
                  context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=lambda: self.set_selection([]),
                  context=Qt.WidgetWithChildrenShortcut)

    def _build_toolbar(self):
        bar = QToolBar()
        modes = QActionGroup(self)
        self.mode_actions = {}
        for mode, text, tip in (("select", "Select", "Click to select (Shift/Ctrl-click adds); drag to pan"),
                                ("move", "Move", "Drag the selected faces to move them"),
                                ("points", "Drag points", "Drag the points of the selected outline")):
            action = QAction(text, self, checkable=True, toolTip=tip)
            action.triggered.connect(lambda _=False, m=mode: self.set_mode(m))
            modes.addAction(action)
            bar.addAction(action)
            self.mode_actions[mode] = action
        self.mode_actions["select"].setChecked(True)
        bar.addSeparator()
        self.act_import = bar.addAction("Import…", self.import_file)
        self.act_import.setToolTip("Coordinates (CSV, .dat), nozzle wall CSV (x_mm,r_mm), DXF, STEP or IGES")
        self.act_points = bar.addAction("Point table…", self.edit_points)
        self.act_points.setToolTip("Edit the points of the selected outline in a table (mm)")
        bar.addSeparator()
        self.tool_actions = {}
        edit_menu = QMenu(self)
        for kind, text, tip in TOOLS:
            action = QAction(text, self, toolTip=tip)
            action.triggered.connect(lambda _=False, k=kind: self.add_operation(k))
            self.tool_actions[kind] = action
            if kind in EDIT_MENU:
                edit_menu.addAction(action)
            else:
                bar.addAction(action)
        edit_menu.setToolTipsVisible(True)
        edit_button = QToolButton(text="Edit", popupMode=QToolButton.InstantPopup, toolTip="Transform, fillet, "
                                  "delete, fluid / solid, booleans")
        edit_button.setMenu(edit_menu)
        bar.insertWidget(self.tool_actions["enclosure"], edit_button)
        bar.addSeparator()
        self.act_axi = QAction("Axisymmetric", self, checkable=True,
                               toolTip="Axisymmetric about the x axis (y = r >= 0); otherwise planar 2D")
        self.act_axi.triggered.connect(self.set_axisymmetric)
        bar.addAction(self.act_axi)
        self.act_revert = bar.addAction("Back to template", self.revert)
        self.act_revert.setToolTip("Forget the workspace edits: the template's own geometry again")
        return bar

    # ================================================================================== refreshing

    @property
    def project(self):
        return self.window.project

    def refresh(self):
        project = self.project
        if project is None:
            self.view.clear()
            return
        workspace = has_workspace(project.case)
        self.toolbar.setVisible(workspace)
        self.tabs.setTabVisible(0, workspace)
        self.tabs.setTabVisible(1, workspace)
        if not workspace:
            self._refresh_preview()
            return
        self.preview = None
        try:
            params = project.params_for(("geometry",))
        except ValueError as error:
            self.banner.show_message(f"Geometry problem: {error}", "error")
            self.view.clear("Fix the geometry inputs on the left.")
            self.built, self._key = None, None
            return
        document = project.geometry_document()
        key = (document.to_json(), repr(sorted((k, repr(v)) for k, v in params.items())))
        first = self.built is None or self._fit_next
        if key != self._key:
            self._fit_next = False
            self.built = replay(document, project.replay_context(params))
            self.document, self._key = document, key
            self.selection = [s for s in self.selection if self._exists(s)]
            for level, text in self.built.messages:      # each message once, not after every edit
                if (level, text) not in self._logged:
                    self.window.log(f"Geometry: {text}", level)
            self._logged = set(self.built.messages)
            self.view.show_geometry(self.built, self.selection, keep_camera=not first)
        self._update_banner()
        self._update_lists()
        self._update_actions()

    def _refresh_preview(self):
        project = self.project
        self.built = None
        self.summary.set_rows([])
        try:
            self.preview = geometry_preview(project.case, project.params_for(("geometry",)))
        except ValueError as error:
            self.banner.show_message(f"Geometry problem: {error}", "error")
            self.view.clear("Fix the geometry inputs on the left.")
            return
        if self.preview is None:
            self.banner.show_message("This 1D template has no geometry drawing; its geometry inputs are on the left.")
            self.view.clear()
            return
        warnings = " ".join(self.preview.warnings)
        self.banner.show_message(warnings, "warning") if warnings else self.banner.hide_message()
        self.view.show_curves(self.preview)
        self.summary.set_rows([(label, *readable(v, u, 5)) for label, (v, u) in self.preview.summary.items()])
        self.tabs.setCurrentIndex(2)

    def _exists(self, item):
        kind, entity = item
        return entity in {"vertex": self.built.vertices, "edge": self.built.edges, "face": self.built.faces}[kind]

    def _update_banner(self):
        built = self.built
        errors = built.errors()
        if errors:
            self.banner.show_message(" ".join(errors) + " Change or delete that step in the History tab.", "error")
            return
        from aeroflowsim.geometry_model.boundaries import boundary_problems
        problems = [text for level, text in boundary_problems(built) if level == "error"]
        if built.empty:
            self.banner.show_message("The geometry is empty: import a file (Import…) or go back to the template.")
        elif problems:
            self.banner.show_message(" ".join(problems), "warning")
        else:
            self.banner.hide_message()

    def _update_lists(self):
        built, document = self.built, self.document
        current = self.history.currentRow()
        self.history.blockSignals(True)
        self.history.clear()
        for op_id, text, state in logic.history_rows(document, built):
            item = QListWidgetItem(f"{op_id}  {text}{STATE_TEXT[state]}")
            item.setData(Qt.UserRole, op_id)
            if state in ("failed",):
                item.setForeground(QColor(colour("error")))
            elif state in ("suppressed", "not run"):
                item.setForeground(QColor(colour("muted")))
            self.history.addItem(item)
        self.history.blockSignals(False)
        if 0 <= current < self.history.count():
            self.history.setCurrentRow(current)
        rows = logic.boundary_rows(built)
        self.boundaries.blockSignals(True)
        self.boundaries.set_rows(rows)
        for r, row in enumerate(rows):
            self.boundaries.item(r, 0).setForeground(QColor(PATCH_COLOURS.get(row[1], colour("muted"))))
        self.boundaries.blockSignals(False)
        from aeroflowsim.geometry_model.boundaries import suggestions
        n = len(suggestions(built))
        self.suggestion_note.setText(f"{n} unnamed edge(s) have a suggested name: press Accept suggestions."
                                     if n else "")
        rows = []
        box = built.bbox()
        if box is not None:
            rows += [("Width (x)", logic.mm(box[2] - box[0]), "mm"), ("Height (y)", logic.mm(box[3] - box[1]), "mm")]
        rows.append(("Symmetry", "axisymmetric" if built.axisymmetric else "planar", ""))
        for face in built.faces.values():
            rows.append((f"Area of {face.id} ({face.role})", f"{face.area / logic.MM**2:.6g}", "mm²"))
        rows.append(("Edges / points", f"{len(built.edges)} / {len(built.vertices)}", ""))
        try:
            preview = geometry_preview(self.project.case, self.project.params_for(("geometry",)))
            if preview is not None and self.document.uses_template():
                rows += [(f"Template: {label}", *readable(v, u, 5)) for label, (v, u) in preview.summary.items()]
        except ValueError:
            pass
        self.summary.set_rows(rows)

    def _update_actions(self):
        document = self.document
        uses_template = document.uses_template()
        self.act_axi.setChecked(self.built.axisymmetric)
        self.act_axi.setEnabled(not uses_template)
        self.act_axi.setToolTip("Set by the template shape" if uses_template else
                                "Axisymmetric about the x axis (y = r >= 0); otherwise planar 2D")
        self.act_revert.setEnabled(not document.is_template_only() or
                                   document.to_dict()["operations"] !=
                                   template_document(self.project.case).to_dict()["operations"])
        self.act_points.setEnabled(self._points_operation() is not None)

    # ================================================================================== selection

    def on_picked(self, kind, entity, add):
        if not kind:
            if not add:
                self.set_selection([])
            return
        item = (kind, entity)
        if add:
            selection = [s for s in self.selection if s != item] if item in self.selection else self.selection + [item]
        else:
            selection = [item]
        self.set_selection(selection)

    def set_selection(self, selection):
        self.selection = list(selection)
        self.view.set_selection(self.selection)
        if self.built is not None:
            self.window.show_properties("Selection" if self.selection else "Nothing selected",
                                        logic.selection_rows(self.built, self.selection))
            self.act_points.setEnabled(self._points_operation() is not None)
            if self.view.mode == "points":
                self._show_handles()

    def select_boundary_edges(self):
        rows = {i.row() for i in self.boundaries.selectedIndexes()}
        names = [self.boundaries.item(r, 0).text() for r in rows]
        edges = []
        for name in names:
            if name == "(no name)":
                edges += [e for e in self.built.boundary_edges() if e not in self.built.names]
            else:
                edges += logic.edges_named(self.built, name)
        self.set_selection([("edge", e) for e in edges])

    # ================================================================================== editing

    def commit(self, document, text):
        """Hand a new history to the window (an undoable step)."""
        self.window.edit_geometry(document, text)

    def add_operation(self, kind):
        if self.built is None:
            return
        try:
            op = logic.operation_for(kind, self.selection, self.built)
        except ValueError as error:
            QMessageBox.information(self, "Select first", str(error))
            return
        if kind != "delete":
            notes = {"transform": "Applies to the selected faces; with nothing selected, to everything.",
                     "enclosure": "Sizes are in reference lengths L = the length of the solid bodies along x.",
                     "name_boundary": f"{len(op.params['edges'])} edge(s) selected."}
            dialog = OperationDialog(op, op.title, notes.get(kind, ""), self)
            if not dialog.exec():
                return
            op = dialog.result_op
        document = self.document.copy()
        document.add(op)
        self.set_selection([])
        self.commit(document, op.summary())

    def on_moved(self, dx, dy):
        faces = logic._faces_of(self.selection, self.built)
        if not faces:
            return
        document = self.document.copy()
        op = document.add(Transform(kind="move", targets=faces, dx=dx, dy=dy))
        self.commit(document, op.summary())

    def import_file(self):
        project = self.project
        path, _ = QFileDialog.getOpenFileName(self, "Import geometry", str(Path.home()), IMPORT_FILTER)
        if not path:
            return
        try:
            fmt = file_format(path)
            if fmt == "coordinates":
                op = ImportFile(format=fmt, source=Path(path).name, points=read_coordinate_points(path).tolist())
            elif fmt == "wall_profile":
                op = ImportFile(format=fmt, source=Path(path).name, unit="mm",
                                points=read_wall_profile_points(path).tolist())
            else:
                op = ImportFile(format=fmt, source=Path(path).name, file=project.import_file(path))
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Import", str(error))
            return
        has_template = self.document.uses_template()
        dialog = ImportDialog(op, project.replay_context(), has_template, self)
        if not dialog.exec():
            return
        document = self.document.copy()
        if has_template and dialog.replace.isChecked():
            for template_op in document.operations:
                if template_op.type in TEMPLATE_TYPES:
                    template_op.suppressed = True
        new = document.add(dialog.result_op)
        self._fit_next = True                    # show the whole new geometry
        self.commit(document, new.summary())

    # ---- points ----------------------------------------------------------------------------------

    def _points_operation(self):
        """The operation whose points can be edited: the selected history step, or the one that made the
        selected outline."""
        if self.document is None:
            return None
        candidates = []
        row = self.history.currentRow()
        if 0 <= row < len(self.document.operations):
            candidates.append(self.document.operations[row].id)
        for kind, entity in self.selection:
            if kind == "edge":
                candidates.append(entity.split(":")[0])
            elif kind == "face":
                candidates += [e.split(":")[0] for loop in self.built.faces[entity].loops for e in loop]
        for op_id in candidates:
            try:
                op = self.document.find(op_id)
            except KeyError:
                continue
            if logic.has_points(op):
                return op
        return None

    def edit_points(self):
        op = self._points_operation()
        if op is None:
            QMessageBox.information(self, "Point table", "Select an outline made from points (an imported CSV / "
                                    ".dat file or a sketched polyline / spline).")
            return
        dialog = PointTableDialog(logic.points_of(op), f"Points of {op.id}: {op.summary()}", self)
        if dialog.exec():
            self.commit(logic.replace_operation(self.document, logic.with_points(op, dialog.result_points)),
                        f"edit the points of {op.id}")

    def _show_handles(self):
        op = self._points_operation()
        self._points_op = op.id if op is not None else None
        self.view.set_handles(None if op is None else logic.points_of(op))

    def on_point_moved(self, index, x, y):
        if self._points_op is None:
            return
        op = self.document.find(self._points_op)
        points = logic.points_of(op)
        points[index] = (x, y)
        self.commit(logic.replace_operation(self.document, logic.with_points(op, points)),
                    f"move point {index + 1} of {op.id}")

    def set_mode(self, mode):
        self.view.set_mode(mode)
        self.mode_actions[mode].setChecked(True)
        if mode == "points":
            self._show_handles()
            if self._points_op is None:
                self.banner.show_message("Drag points: select an outline made from points first.", "info")
        else:
            self.view.set_handles(None)

    # ---- history -----------------------------------------------------------------------------------

    def show_operation(self, row):
        while self.op_box.count():
            widget = self.op_box.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self.form = None
        if self.document is None or not 0 <= row < len(self.document.operations):
            return
        op = self.document.operations[row]
        self.op_box.addWidget(QLabel(f"<b>{op.id}: {op.title}</b>"))
        if op.type in TEMPLATE_TYPES:
            self.op_box.addWidget(QLabel("The template's geometry: change it with the geometry inputs in the "
                                         "Inputs panel (left).", wordWrap=True))
        elif logic.fields_for(op):
            self.form = OperationForm(op)
            self.op_box.addWidget(self.form)
        else:
            self.op_box.addWidget(QLabel(op.summary(), wordWrap=True))
        buttons = QHBoxLayout()
        row_widget = QWidget()
        row_widget.setLayout(buttons)
        if self.form is not None:
            apply = QPushButton("Apply")
            apply.clicked.connect(lambda: self.apply_operation(op.id))
            buttons.addWidget(apply)
        if logic.has_points(op):
            points = QPushButton("Point table…")
            points.clicked.connect(self.edit_points)
            buttons.addWidget(points)
        suppress = QPushButton("Unsuppress" if op.suppressed else "Suppress")
        suppress.setToolTip("Skip this step when the history is replayed (it stays in the list)")
        suppress.clicked.connect(lambda: self.toggle_suppressed(op.id))
        delete = QPushButton("Delete step")
        delete.clicked.connect(lambda: self.delete_operation(op.id))
        buttons.addWidget(suppress)
        buttons.addWidget(delete)
        self.op_box.addWidget(row_widget)
        self.op_box.addStretch(1)

    def apply_operation(self, op_id):
        try:
            op = self.form.operation()
        except ValueError as error:
            self.form.problem.setText(str(error))
            return
        op.id = op_id
        self.commit(logic.replace_operation(self.document, op), f"change {op_id}: {op.summary()}")

    def toggle_suppressed(self, op_id):
        document = self.document.copy()
        op = document.find(op_id)
        op.suppressed = not op.suppressed
        self.commit(document, f"{'suppress' if op.suppressed else 'unsuppress'} {op_id}")

    def delete_operation(self, op_id):
        document = self.document.copy()
        document.remove(op_id)
        self.commit(document, f"delete step {op_id}")

    # ---- boundaries ------------------------------------------------------------------------------

    def _selected_boundary(self):
        rows = sorted({i.row() for i in self.boundaries.selectedIndexes()})
        if not rows or self.boundaries.item(rows[0], 0).text() == "(no name)":
            QMessageBox.information(self, "Boundaries", "Select a named boundary in the table first.")
            return None
        return self.boundaries.item(rows[0], 0).text()

    def accept_suggestions(self):
        document = logic.accept_suggestions(self.document, self.built)
        if document is None:
            QMessageBox.information(self, "Suggestions", "There are no suggestions: name the remaining edges by "
                                    "selecting them and pressing Name boundary.")
            return
        self.commit(document, "accept the suggested boundary names")

    def rename(self):
        name = self._selected_boundary()
        if name is None:
            return
        new, ok = QInputDialog.getText(self, "Rename boundary", f"New name for '{name}':", text=name)
        if ok and new and new != name:
            self.commit(logic.rename_boundary(self.document, self.built, name, new), f"rename {name} to {new}")

    def change_type(self):
        name = self._selected_boundary()
        if name is None:
            return
        labels = [label for label, _ in BOUNDARY_TYPES.values()]
        keys = list(BOUNDARY_TYPES)
        current = self.built.names[logic.edges_named(self.built, name)[0]].type
        label, ok = QInputDialog.getItem(self, "Boundary type", f"Type of '{name}':", labels,
                                         keys.index(current), False)
        if ok:
            kind = keys[labels.index(label)]
            if kind != current:
                self.commit(logic.set_boundary_type(self.document, self.built, name, kind),
                            f"make {name} a {kind} boundary")

    def toggle_inflation(self):
        name = self._selected_boundary()
        if name is None:
            return
        edges = logic.edges_named(self.built, name)
        on = not any(self.built.names[e].inflation for e in edges)
        kind = self.built.names[edges[0]].type
        self.commit(logic.set_boundary_type(self.document, self.built, name, kind, inflation=on),
                    f"inflation {'on' if on else 'off'} for {name}")

    # ---- whole document ---------------------------------------------------------------------------

    def set_axisymmetric(self, on):
        document = self.document.copy()
        document.axisymmetric = bool(on)
        self.commit(document, "axisymmetric" if on else "planar")

    def revert(self):
        if QMessageBox.question(self, "Back to template", "Forget every workspace step and use the template's own "
                                "geometry again? (Edit > Undo brings them back.)") != QMessageBox.Yes:
            return
        self.commit(template_document(self.project.case), "back to the template geometry")

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Geometry step of a 3D template: the 3D geometry workspace (bodies, STEP/IGES import, booleans, enclosure, face
names, refinement regions), shown by the Geometry step (gui/steps/geometry.py) for templates with
workspace_settings_3d.

    tool bar        Select / Box select, Bodies (box, cylinder, sphere, cone, revolve, extrude), Import STEP/IGES,
                    Edit (transform, boolean, fluid/solid, delete), Enclosure, Name boundary, Refinement;
                    Hide, Isolate, Show all; Section plane (axis and position)
    view            gui/geometry3d_view.py: click a face (Shift / Ctrl adds), drag a box in Box mode, right-click menu
    History tab     the operations in order: click one to change its settings, suppress or delete it
    Boundaries tab  the boundary names of the faces (mesh patches): accept suggestions, rename, change the type,
                    prism layers on / off
    Dimensions tab  bodies, volumes, areas and the size of the geometry
Every change makes a new history, which the window puts on the undo stack (Edit > Undo). Hide / isolate and the
section plane only change the view (they are not undone). The decisions are in gui/geometry_logic.py (no Qt).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGridLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
                               QMenu, QMessageBox, QPushButton, QScrollArea, QSlider, QSplitter, QTabWidget, QToolBar,
                               QToolButton, QVBoxLayout, QWidget, QHBoxLayout)

from aeroflowsim.geometry_model import replay
from aeroflowsim.geometry_model.boundaries import BOUNDARY_TYPES
from aeroflowsim.geometry_model.operations3d import TEMPLATE_TYPES_3D, ImportSolid
from aeroflowsim.gui import geometry_logic as logic
from aeroflowsim.gui.geometry3d_view import Geometry3DView
from aeroflowsim.gui.geometry_forms import OperationDialog, OperationForm
from aeroflowsim.gui.icons import icon
from aeroflowsim.gui.widgets import Banner, ValueTable

IMPORT_FILTER_3D = "STEP or IGES solids (*.step *.stp *.iges *.igs);;STEP (*.step *.stp);;IGES (*.iges *.igs)"
STATE_TEXT = {"ok": "", "template": "", "suppressed": "  (suppressed)", "failed": "  (FAILED)",
              "not run": "  (not run: an earlier step failed)"}
TOOL_ICONS = {"transform_3d": "transform", "boolean_3d": "boolean", "set_role_3d": "role", "fluid_zones_3d": "role", "nozzle_region_3d": "enclosure",
              "edge_size_3d": "refinement", "fillet_3d": "fillet", "chamfer_3d": "chamfer", "split_body_3d": "split",
              "delete_3d": "delete",
              "enclosure_3d": "enclosure", "name_faces": "name", "refinement_3d": "refinement"}


class Geometry3DPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.banner = Banner()
        self.view = Geometry3DView()
        self.view.picked.connect(self.on_picked)
        self.view.box_selected.connect(self.on_box_selected)
        self.view.context_menu.connect(self.on_context_menu)
        self.built = None                 # the replayed geometry (BuiltGeometry3D)
        self.document = None              # the history that self.built shows
        self.selection = []               # [(kind, id)]
        self.visibility = logic.Visibility()
        self.form = None
        self._key = None                  # what self.built was made from (replay only after changes)
        self._logged = set()

        self.toolbar = self._build_toolbar()
        self.history = QListWidget(wordWrap=True)
        self.history.currentRowChanged.connect(self.show_operation)
        self.op_box = QVBoxLayout()
        op_widget = QWidget()
        op_widget.setLayout(self.op_box)
        op_scroll = QScrollArea(widgetResizable=True)
        op_scroll.setWidget(op_widget)
        history_tab = QWidget()
        h = QVBoxLayout(history_tab)
        h.addWidget(QLabel("Steps, replayed from the top. Click one to change it."))
        h.addWidget(self.history, 2)
        h.addWidget(op_scroll, 3)

        self.boundaries = ValueTable(["Boundary", "Type", "Faces", "Prism layers", "Named by"])
        self.boundaries.itemSelectionChanged.connect(self.select_boundary_faces)
        self.boundaries.cellDoubleClicked.connect(lambda row, col: self.change_type() if col == 1 else self.rename())
        boundary_tab = QWidget()
        b = QVBoxLayout(boundary_tab)
        b.addWidget(QLabel("Every boundary face of the fluid needs a name and a type; they become the mesh patches."))
        b.addWidget(self.boundaries, 1)
        grid = QGridLayout()
        for n, (text, slot, tip) in enumerate((
                ("Accept suggestions", self.accept_suggestions,
                 "Name the unnamed faces as suggested (inlet / outlet across the flow, symmetry on y = 0, walls)"),
                ("Rename…", self.rename, "Rename the selected boundary everywhere"),
                ("Type…", self.change_type, "Change the type of the selected boundary"),
                ("Prism layers on/off", self.toggle_inflation, "Prism layers on this wall"))):
            button = QPushButton(text, toolTip=tip)
            button.clicked.connect(slot)
            grid.addWidget(button, n // 2, n % 2)
        b.addLayout(grid)

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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.banner)
        layout.addWidget(splitter, 1)
        QShortcut(QKeySequence.Delete, self, activated=lambda: self.add_operation("delete_3d"),
                  context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=lambda: self.set_selection([]),
                  context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence(Qt.Key_F), self.view, activated=self.view.fit, context=Qt.WidgetWithChildrenShortcut)

    # ---- tool bar ------------------------------------------------------------------------------

    def _build_toolbar(self):
        bar = QToolBar()
        bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        modes = QActionGroup(self)
        self.mode_actions = {}
        for mode, text, icon_name, tip in (("select", "Select", "select", "Click faces (Shift / Ctrl adds)"),
                                           ("box", "Box select", "box_select",
                                            "Drag a box: left to right takes the faces inside, right to left the "
                                            "faces it touches")):
            action = QAction(icon(icon_name), text, self, checkable=True, toolTip=tip)
            action.triggered.connect(lambda _=False, m=mode: self.view.set_mode(m))
            modes.addAction(action)
            bar.addAction(action)
            self.mode_actions[mode] = action
        self.mode_actions["select"].setChecked(True)
        bar.addSeparator()
        self.tool_actions = {}
        bodies = QMenu(self)
        for kind, text, tip in logic.BODIES_3D:
            action = QAction(text, self, toolTip=tip)
            action.triggered.connect(lambda _=False, k=kind: self.add_operation(k))
            bodies.addAction(action)
            self.tool_actions[kind] = action
        self.bodies_button = self._menu_button("Bodies", "body", bodies, "Add a body: box, cylinder, sphere, cone, "
                                               "revolve or extrude")
        bar.addWidget(self.bodies_button)
        self.act_import = QAction(icon("import"), "Import…", self, toolTip="Import a STEP or IGES solid")
        self.act_import.triggered.connect(self.import_file)
        bar.addAction(self.act_import)
        edit = QMenu(self)
        for kind, text, tip in logic.TOOLS_3D:
            action = QAction(icon(TOOL_ICONS[kind]), text, self, toolTip=tip)
            action.triggered.connect(lambda _=False, k=kind: self.add_operation(k))
            self.tool_actions[kind] = action
            if kind in ("transform_3d", "boolean_3d", "set_role_3d", "fluid_zones_3d", "fillet_3d", "chamfer_3d",
                        "split_body_3d", "edge_size_3d", "delete_3d"):
                edit.addAction(action)
        self.edit_button = self._menu_button("Edit", "edit", edit, "Transform, boolean, fluid / solid, delete")
        bar.addWidget(self.edit_button)
        for kind in ("enclosure_3d", "name_faces", "refinement_3d"):
            bar.addAction(self.tool_actions[kind])
        bar.addSeparator()
        self.act_edges = QAction(icon("split_edge"), "Edges", self, checkable=True,
                                 toolTip="Selection filter: pick edges instead of faces (edge size, fillet, chamfer)")
        self.act_edges.toggled.connect(self.set_edge_filter)
        bar.addAction(self.act_edges)
        self.act_hide = QAction(icon("hide"), "Hide", self, toolTip="Hide the selected faces (view only)")
        self.act_hide.triggered.connect(self.hide_selected)
        self.act_isolate = QAction(icon("isolate"), "Isolate", self, toolTip="Show only the selected faces")
        self.act_isolate.triggered.connect(self.isolate_selected)
        self.act_show = QAction(icon("show"), "Show all", self, toolTip="Show every face again")
        self.act_show.triggered.connect(self.show_all)
        for action in (self.act_hide, self.act_isolate, self.act_show):
            bar.addAction(action)
        bar.addSeparator()
        self.act_suggest = QAction(icon("suggestions"), "Suggestions…", self,
                                   toolTip="Suggested cell sizes and first-layer height, each with its reason")
        self.act_suggest.triggered.connect(self.show_suggestions)
        bar.addAction(self.act_suggest)
        bar.addSeparator()
        bar.addWidget(QLabel(" Section "))
        self.section_axis = QComboBox(toolTip="Cut the view with a plane normal to this axis (view only)")
        self.section_axis.addItems(["off", "x", "y", "z"])
        self.section_axis.currentIndexChanged.connect(lambda _: self.redraw())
        self.section_position = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=50, toolTip="Position of the plane")
        self.section_position.setMaximumWidth(120)
        self.section_position.valueChanged.connect(lambda _: self.redraw())
        bar.addWidget(self.section_axis)
        bar.addWidget(self.section_position)
        return bar

    def _menu_button(self, text, icon_name, menu, tip):
        button = QToolButton(text=text, toolTip=tip, popupMode=QToolButton.InstantPopup,
                             toolButtonStyle=Qt.ToolButtonTextBesideIcon)
        button.setIcon(icon(icon_name))
        button.setMenu(menu)
        return button

    def update_icons(self):
        self.view.update_icons()
        self.bodies_button.setIcon(icon("body"))
        self.edit_button.setIcon(icon("edit"))

    def set_dark(self, dark):
        self.view.set_dark(dark)
        self.redraw()

    # ---- showing the geometry ---------------------------------------------------------------------

    @property
    def project(self):
        return self.window.project

    def refresh(self):
        project = self.project
        if project is None:
            self.view.clear()
            return
        try:
            params = project.params_for(("geometry",))
        except ValueError as error:
            self.banner.show_message(f"Geometry problem: {error}", "error")
            self.view.clear("Fix the geometry inputs on the left.")
            self.built, self._key = None, None
            return
        document = project.geometry_document()
        key = (project.folder, document.to_json(), repr(sorted((k, repr(v)) for k, v in params.items())))
        if key != self._key:
            first = self.built is None
            self.built = replay(document, project.replay_context(params))
            self.document, self._key = document, key
            self.selection = [s for s in self.selection if self._exists(s)]
            for level, text in self.built.messages:
                if (level, text) not in self._logged:
                    self.window.log(f"Geometry: {text}", level)
            self._logged = set(self.built.messages)
            self.redraw(keep_camera=not first)
        self._update_banner()
        self._update_lists()

    def forget(self):
        """Drop the shown geometry (another project was opened)."""
        self.built, self.document, self._key, self.selection = None, None, None, []
        self.visibility.show_all()

    def section(self):
        axis = self.section_axis.currentText()
        return logic.section_plane(self.built, axis, self.section_position.value() / 100.0)

    def redraw(self, keep_camera=True):
        if self.built is None:
            return
        self.view.show_geometry(self.built, self.selection, self.visibility.hidden, self.section(), keep_camera)

    def _exists(self, item):
        kind, entity = item
        return entity in {"face": self.built.faces, "body": self.built.bodies, "edge": self.built.edges}.get(kind, {})

    def _update_banner(self):
        built = self.built
        if built is None:
            return
        if built.errors():
            self.banner.show_message(" ".join(built.errors()), "error")
        elif not built.bodies:
            self.banner.show_message("Add a body (Bodies), or import a STEP / IGES solid (Import).", "info")
        elif not built.bodies_with_role("fluid"):
            self.banner.show_message("There is no fluid yet: put an Enclosure round the solid bodies.", "info")
        elif [f for f in built.boundary_faces() if f not in built.names]:
            self.banner.show_message("Some boundary faces have no name: see the Boundaries tab (Accept suggestions).",
                                     "warning")
        else:
            self.banner.hide_message()

    def _update_lists(self):
        built, document = self.built, self.document
        if built is None:
            return
        row = self.history.currentRow()
        self.history.blockSignals(True)
        self.history.clear()
        for op_id, text, state in logic.history_rows_3d(document, built):
            item = QListWidgetItem(f"{op_id}  {text}{STATE_TEXT[state]}")
            if state in ("failed", "not run", "suppressed"):
                item.setForeground(Qt.gray if state != "failed" else Qt.red)
            self.history.addItem(item)
        self.history.blockSignals(False)
        if 0 <= row < self.history.count():
            self.history.setCurrentRow(row)
        self.boundaries.set_rows(logic.boundary_rows_3d(built))
        self.summary.set_rows(logic.summary_rows_3d(built, self.window.units))

    # ---- selection ------------------------------------------------------------------------------

    def set_edge_filter(self, on):
        """Pick edges (on) or faces (off); the selection starts again."""
        self.view.pick_kind = "edge" if on else "face"
        self.set_selection([])

    def on_picked(self, kind, entity, add):
        self.set_selection(logic.toggle_selection(self.selection, (kind, entity) if kind else None, add))

    def on_box_selected(self, faces, add):
        items = [("face", f) for f in faces]
        self.set_selection(list(dict.fromkeys((self.selection if add else []) + items)))

    def set_selection(self, selection):
        if self.built is None:
            return
        self.selection = [s for s in selection if self._exists(s)]
        self.redraw()
        self.window.show_properties("Selection" if self.selection else "Nothing selected",
                                    logic.selection_rows_3d(self.built, self.selection, self.window.units))

    def select_boundary_faces(self):
        rows = {i.row() for i in self.boundaries.selectedIndexes()}
        faces = [f for r in sorted(rows) for f in logic.faces_named_3d(self.built, self.boundaries.item(r, 0).text())]
        self.set_selection([("face", f) for f in faces])

    def hide_selected(self):
        self.visibility.hide(logic.faces_of_3d(self.selection, self.built))
        self.set_selection([])

    def isolate_selected(self):
        self.visibility.isolate(logic.faces_of_3d(self.selection, self.built), self.built)
        self.redraw()

    def show_all(self):
        self.visibility.show_all()
        self.redraw()

    def on_context_menu(self, kind, entity, position):
        """Right-click: select what is under the cursor (keeping a selection it belongs to) and offer the next steps."""
        if kind and (kind, entity) not in self.selection:
            self.set_selection([(kind, entity)])
        t = self.tool_actions
        menu = QMenu(self)
        if kind:
            for action in (t["name_faces"], t["refinement_3d"], None, t["transform_3d"], t["boolean_3d"],
                           t["set_role_3d"], t["fluid_zones_3d"], t["delete_3d"], None, self.act_hide, self.act_isolate):
                menu.addSeparator() if action is None else menu.addAction(action)
        else:
            body_menu = menu.addMenu(icon("body"), "Add body")
            for k, _, _ in logic.BODIES_3D:
                body_menu.addAction(t[k])
            for action in (self.act_import, None, t["enclosure_3d"], t["nozzle_region_3d"], t["refinement_3d"]):
                menu.addSeparator() if action is None else menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.act_show)
        views = menu.addMenu("View")
        for name in ("iso", "+x", "-x", "+y", "+z"):
            views.addAction(name, lambda n=name: self.view.set_view(n))
        menu.addAction(icon("fit"), "Fit view", self.view.fit)
        self.last_menu = menu                     # kept for tests
        menu.popup(position)

    # ---- editing ------------------------------------------------------------------------------

    def commit(self, document, text):
        """Hand a new history to the window (an undoable step)."""
        self.window.edit_geometry(document, text)

    def add_operation(self, kind):
        if self.built is None or self.document is None:
            return
        try:
            op = logic.operation_for_3d(kind, self.selection, self.built)
        except ValueError as error:
            QMessageBox.information(self, "Geometry", str(error))
            return
        if kind not in logic.NO_DIALOG_3D:
            dialog = OperationDialog(op, op.title, parent=self)
            if not dialog.exec():
                return
            op = dialog.result_op
        if op.type == "revolve" and op.params["profile"] == "wall" and not op.params["file"]:
            path, _ = QFileDialog.getOpenFileName(self, "Nozzle wall profile (x_mm,r_mm)", "", "CSV files (*.csv)")
            if not path:
                return
            op.params["file"] = self.project.import_file(path)      # copied into the project, relative path
            op.params["role"] = "fluid"                               # the gas inside the nozzle
        document = self.document.copy()
        new = document.add(op)
        self.commit(document, new.summary())

    def import_file(self):
        project = self.project
        if project is None or self.document is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import a solid", "", IMPORT_FILTER_3D)
        if not path:
            return
        self.import_path(path)

    def import_path(self, path, ask=True):
        """Copy a STEP / IGES file into the project and add an Import step (ask: show its settings first)."""
        try:
            op = ImportSolid(file=self.project.import_file(path))
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Import", str(error))
            return
        if ask:
            dialog = OperationDialog(op, f"Import {op.summary()[7:]}", parent=self)
            if not dialog.exec():
                return
            op = dialog.result_op
        document = self.document.copy()
        uses_template = [o for o in document.operations if o.type in TEMPLATE_TYPES_3D and not o.suppressed]
        body = next((o for o in uses_template if o.type == "template_body"), None)
        if body is not None:            # the imported solid replaces the template body (its far field stays, after it)
            body.suppressed = True
            document.add(op, document.index(body.id) + 1)
        else:
            document.add(op)
        if op.params["role"] == "fluid":   # an imported fluid (e.g. the gas inside a nozzle) needs no far field round it
            for o in uses_template:
                if o.type == "template_enclosure_3d":
                    o.suppressed = True
        self.commit(document, op.summary())

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
        if op.type in TEMPLATE_TYPES_3D:
            self.op_box.addWidget(QLabel("The template's geometry: change it with the geometry inputs in the Inputs "
                                         "panel (left).", wordWrap=True))
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

    # ---- suggestions (aeroflowsim/smart_rules.py) ------------------------------------------------------

    def suggestions(self):
        """The 3D smart rules' suggestions for the current geometry and inputs (empty if not possible)."""
        from aeroflowsim import smart_rules
        project = self.project
        if self.built is None or not hasattr(project.case, "size_inputs"):
            return []
        try:
            params = project.params_for(("geometry", "mesh"))
            sizes = project.case.size_inputs(params, self.built)
        except (ValueError, AttributeError):
            return []
        try:
            flow = smart_rules.flow_scales(project.case, project.params_for(("geometry", "mesh", "setup")))
        except (ValueError, AttributeError, KeyError):
            flow = None
        context = smart_rules.SizeContext(params, sizes, params.get("mach", project.values.get("mach")), self.document,
                                          flow)
        return smart_rules.suggestions_3d(self.built, context)

    def show_suggestions(self):
        from aeroflowsim.gui.geometry_forms import SuggestionsDialog
        SuggestionsDialog(self.suggestions(), self.apply_suggestion, self).exec()

    def apply_suggestion(self, suggestion):
        if suggestion.kind == "input":
            self.window.set_inputs(suggestion.inputs, f"suggested {suggestion.title.lower()}")

    # ---- boundaries ------------------------------------------------------------------------------

    def _selected_boundary(self):
        rows = sorted({i.row() for i in self.boundaries.selectedIndexes()})
        if not rows or self.boundaries.item(rows[0], 0).text() == logic.UNNAMED:
            QMessageBox.information(self, "Boundaries", "Select a named boundary in the table first.")
            return None
        return self.boundaries.item(rows[0], 0).text()

    def accept_suggestions(self):
        document = logic.accept_suggestions_3d(self.document, self.built)
        if document is None:
            QMessageBox.information(self, "Suggestions", "Every boundary face already has a name.")
            return
        self.commit(document, "accept the suggested boundary names")

    def rename(self):
        name = self._selected_boundary()
        if name is None:
            return
        new, ok = QInputDialog.getText(self, "Rename boundary", f"New name for '{name}':", text=name)
        if ok and new and new != name:
            try:
                document = logic.rename_boundary_3d(self.document, self.built, name, new)
            except ValueError as error:
                QMessageBox.warning(self, "Rename boundary", str(error))
                return
            self.commit(document, f"rename {name} to {new}")

    def change_type(self):
        name = self._selected_boundary()
        if name is None:
            return
        labels = [label for label, _ in BOUNDARY_TYPES.values()]
        keys = list(BOUNDARY_TYPES)
        current = self.built.names[logic.faces_named_3d(self.built, name)[0]].type
        label, ok = QInputDialog.getItem(self, "Boundary type", f"Type of '{name}':", labels, keys.index(current), False)
        if ok:
            kind = keys[labels.index(label)]
            if kind != current:
                self.commit(logic.set_boundary_type_3d(self.document, self.built, name, kind),
                            f"make {name} a {kind} boundary")

    def toggle_inflation(self):
        name = self._selected_boundary()
        if name is None:
            return
        faces = logic.faces_named_3d(self.built, name)
        kind = self.built.names[faces[0]].type
        if kind != "wall":
            QMessageBox.information(self, "Prism layers", "Prism layers grow from walls only.")
            return
        on = not any(self.built.names[f].inflation for f in faces)
        self.commit(logic.set_boundary_type_3d(self.document, self.built, name, kind, inflation=on),
                    f"prism layers {'on' if on else 'off'} for {name}")

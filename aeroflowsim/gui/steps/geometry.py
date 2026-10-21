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

import numpy as np

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, QInputDialog, QLabel, QListWidget, QListWidgetItem,
                               QMenu, QMessageBox, QPushButton, QScrollArea, QSplitter, QTabWidget, QToolBar,
                               QToolButton, QVBoxLayout,
                               QWidget)

from aeroflowsim.geometry_model import has_workspace, replay, template_document
from aeroflowsim.geometry_model.boundaries import BOUNDARY_TYPES
from aeroflowsim.geometry_model.importers import file_format, read_coordinate_points, read_wall_profile_points
from aeroflowsim.geometry_model import FLUID, SOLID, picking
from aeroflowsim.gui import sketch_tools
from aeroflowsim.geometry_model.operations import TEMPLATE_TYPES, ImportFile, Sketch, Transform
from aeroflowsim.geometry_preview import geometry_preview
from aeroflowsim.gui import geometry_logic as logic
from aeroflowsim.gui.geometry_forms import (ImportDialog, OperationDialog, OperationForm, PointTableDialog,
                                             SuggestionsDialog)
from aeroflowsim.gui.geometry_view import GeometryView
from aeroflowsim.gui.icons import icon
from aeroflowsim.gui.logic import readable
from aeroflowsim.gui.theme import PATCH_COLOURS, colour
from aeroflowsim.gui.widgets import Banner, ValueTable

IMPORT_FILTER = ("Geometry files (*.dxf *.step *.stp *.iges *.igs *.csv *.dat *.txt);;DXF (*.dxf);;"
                 "STEP (*.step *.stp);;IGES (*.iges *.igs);;Coordinates (*.csv *.dat *.txt)")
STATE_TEXT = {"ok": "", "template": "", "suppressed": "  (suppressed)", "failed": "  (FAILED)",
              "not run": "  (not run: an earlier step failed)"}
EDIT_MENU = ("transform", "fillet", "chamfer", "split_line", "split_face", "split_edge", "trim", "extend",
             "offset", "pattern", "fill", "merge_faces", "delete", "set_role", "boolean")   # in the Edit menu button
CLICK_TOOLS = ("split_line", "trim", "extend")      # editing tools used with the mouse (gui/sketch_tools.py)
SKETCHES = tuple((kind, cls.title, kind if kind != "polyline" else "line")   # (tool, menu text, icon)
                 for kind, cls in sketch_tools.TOOLS.items())
TOOLS = (   # (operation kind, button text, tooltip)
    ("transform", "Transform…", "Move, rotate (angle of attack), scale or mirror the selected faces (or everything)"),
    ("fillet", "Fillet…", "Round the selected corner (a point where two edges meet)"),
    ("chamfer", "Chamfer…", "Cut the selected corner with a straight line"),
    ("split_line", "Split by line", "Draw a line across a face: the face is split along it"),
    ("split_face", "Split face", "Split the selected faces along the selected free curves"),
    ("split_edge", "Split edge…", "Cut the selected edge at a point (both pieces keep its name)"),
    ("trim", "Trim", "Click pieces of curves to remove them (between crossings)"),
    ("extend", "Extend", "Click near the end of a straight line to lengthen it to the next curve"),
    ("offset", "Offset…", "Parallel copy of the selected edges / face outline at a distance"),
    ("pattern", "Pattern…", "Copies of the selected faces in a row or round a centre"),
    ("fill", "Fill", "Make a face from the selected closed loop of free curves"),
    ("merge_faces", "Merge faces", "Join the selected faces into one"),
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
        self.view.clicked.connect(self.on_sketch_click)
        self.view.tool_clicked.connect(self.on_sketch_click)
        self.view.tool_moved.connect(self.on_tool_moved)
        self.view.tool_finish.connect(self.finish_sketch)
        self.view.box_selected.connect(self.on_box_selected)
        self.view.key_typed.connect(self.on_typed_key)
        self.view.context_menu.connect(self.on_context_menu)
        self.view.dimension_edit.connect(self.edit_dimension)
        self.tool = None                 # the active drawing tool (gui/sketch_tools.py), or None
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
        self.sketch_bar = self._build_sketch_bar()
        layout = QVBoxLayout(self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.sketch_bar)
        layout.addWidget(self.banner)
        layout.addWidget(splitter, 1)
        QShortcut(QKeySequence.Delete, self, activated=lambda: self.add_operation("delete"),
                  context=Qt.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.escape, context=Qt.WidgetWithChildrenShortcut)
        for key, slot in ((Qt.Key_Return, self._enter), (Qt.Key_Enter, self._enter),
                          (Qt.Key_Backspace, self.undo_sketch_point), (Qt.Key_A, self.toggle_arc)):
            QShortcut(QKeySequence(key), self.view, activated=slot, context=Qt.WidgetWithChildrenShortcut)

    def _enter(self):
        if self.tool is not None and not self.sketch_entry.hasFocus():
            self.finish_sketch()

    def _build_toolbar(self):
        """The workspace tool bar: icons with their names under them (gui/icons.py, our own icon set)."""
        bar = QToolBar()
        bar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        bar.setIconSize(QSize(22, 22))
        self.icon_targets = []                       # (action or button, icon name): recoloured with the theme
        modes = QActionGroup(self)
        self.mode_actions = {}
        for mode, text, name, tip in (("select", "Select", "select", "Click to select (Shift/Ctrl-click adds); drag "
                                       "to pan"),
                                      ("move", "Move", "move", "Drag the selected faces to move them"),
                                      ("points", "Drag points", "points", "Drag the points of the selected outline, "
                                       "an enclosure's size or a refinement region's corners")):
            action = QAction(text, self, checkable=True, toolTip=tip)
            action.triggered.connect(lambda _=False, m=mode: self.set_mode(m))
            modes.addAction(action)
            bar.addAction(action)
            self.mode_actions[mode] = action
            self.icon_targets.append((action, name))
        self.mode_actions["select"].setChecked(True)
        bar.addSeparator()
        self.act_import = bar.addAction("Import", self.import_file)
        self.act_import.setToolTip("Coordinates (CSV, .dat), nozzle wall CSV (x_mm,r_mm), DXF, STEP or IGES")
        self.act_points = bar.addAction("Points", self.edit_points)
        self.act_points.setToolTip("Edit the points of the selected outline in a table (mm)")
        self.icon_targets += [(self.act_import, "import"), (self.act_points, "table")]
        sketch_menu = QMenu(self)
        for kind, text, icon_name in SKETCHES:
            action = sketch_menu.addAction(text, lambda k=kind: self.start_sketch(k))
            self.icon_targets.append((action, icon_name))
        bar.addWidget(self._menu_button("Sketch", "sketch", sketch_menu, "Draw lines, arcs, splines, rectangles "
                                        "and circles (snaps to corners, midpoints and the grid; points can be typed)"))
        self.tool_actions = {}
        edit_menu = QMenu(self)
        edit_menu.setToolTipsVisible(True)
        bar.addWidget(self._menu_button("Edit", "edit", edit_menu, "Transform, fillet, delete, fluid / solid, "
                                        "booleans"))
        constrain_menu = QMenu(self)
        constrain_menu.setToolTipsVisible(True)
        self.constraint_actions = {}
        for kind, text, what in logic.CONSTRAINTS:
            action = constrain_menu.addAction(text + ("…" if kind == "dimension" else ""),
                                              lambda k=kind: self.add_constraint(k))
            action.setToolTip(f"Select {what} of a sketch, then choose this")
            self.constraint_actions[kind] = action
            if kind == "dimension":
                self.icon_targets.append((action, "dimension"))
            if kind == "point_on":
                constrain_menu.addSeparator()
        bar.addWidget(self._menu_button("Constrain", "constrain", constrain_menu, "Constraints and driving "
                                        "dimensions for sketches: the shape follows when a dimension is changed"))
        names = {"transform": "transform", "fillet": "fillet", "delete": "delete", "set_role": "role",
                 "boolean": "boolean", "enclosure": "enclosure", "name_boundary": "name", "refinement": "refinement",
                 "chamfer": "chamfer", "split_line": "split", "split_face": "split", "split_edge": "split_edge",
                 "trim": "trim", "extend": "extend", "offset": "offset", "pattern": "pattern", "fill": "fill",
                 "merge_faces": "merge"}
        for kind, text, tip in TOOLS:
            action = QAction(text.rstrip("…"), self, toolTip=tip)
            action.triggered.connect(lambda _=False, k=kind: self.add_operation(k))
            self.tool_actions[kind] = action
            self.icon_targets.append((action, names[kind]))
            (edit_menu if kind in EDIT_MENU else bar).addAction(action)
        self.tool_actions["name_boundary"].setText("Name")
        bar.addSeparator()
        self.act_axi = QAction("Axisymmetric", self, checkable=True,
                               toolTip="Axisymmetric about the x axis (y = r >= 0); otherwise planar 2D")
        self.act_axi.triggered.connect(self.set_axisymmetric)
        bar.addAction(self.act_axi)
        self.act_suggest = bar.addAction("Suggest", self.show_suggestions)
        self.act_suggest.setToolTip("Suggested cell sizes and far-field size from the geometry, each with its reason")
        self.icon_targets += [(self.act_axi, "axisymmetric"), (self.act_suggest, "suggestions")]
        more = QMenu(self)
        more.setToolTipsVisible(True)
        self.act_export = more.addAction("Export geometry…", self.export)
        self.act_export.setToolTip("Save the geometry as STEP, DXF or CSV")
        self.act_revert = more.addAction("Back to the template geometry", self.revert)
        self.act_revert.setToolTip("Forget the workspace edits: the template's own geometry again")
        self.icon_targets += [(self.act_export, "export"), (self.act_revert, "revert")]
        bar.addWidget(self._menu_button("More", "more", more, "Export, back to template"))
        self.update_icons()
        return bar

    def _menu_button(self, text, icon_name, menu, tip):
        """A tool bar button that opens a menu (icon with its name under it)."""
        button = QToolButton(text=text, popupMode=QToolButton.InstantPopup, toolTip=tip,
                             toolButtonStyle=Qt.ToolButtonTextUnderIcon, autoRaise=True)
        button.setIconSize(QSize(22, 22))
        button.setMenu(menu)
        self.icon_targets.append((button, icon_name))
        return button

    def update_icons(self):
        """Icons in the colours of the current theme (called again when the theme changes)."""
        for target, name in self.icon_targets:
            target.setIcon(icon(name))
        self.view.update_icons()

    def _build_sketch_bar(self):
        """The bar shown while drawing: what to do, a box for typed values, options, Finish, Stop."""
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(4, 0, 4, 0)
        self.sketch_help = QLabel(wordWrap=True)
        self.sketch_entry = QLineEdit(placeholderText="type: 25   25<30   @3,4   12,5  (mm)")
        self.sketch_entry.setToolTip("A length along the cursor direction, length<angle, @dx,dy relative, or x,y "
                                     "absolute, in mm; Enter places the point (Enter on an empty box finishes)")
        self.sketch_entry.setMaximumWidth(230)
        self.sketch_entry.returnPressed.connect(self.type_sketch_point)
        self.arc_button = QToolButton(text="Tangent arc (A)", checkable=True, autoRaise=True,
                                      toolTip="The next segment continues as a tangent arc")
        self.arc_button.clicked.connect(self.toggle_arc)
        self.sketch_grid = QCheckBox("Snap to grid")
        self.sketch_role = QComboBox()
        self.sketch_role.addItem("Faces: solid", SOLID)
        self.sketch_role.addItem("Faces: fluid", FLUID)
        self.sketch_role.setToolTip("What closed shapes become: a solid body (cut out of the fluid) or a fluid "
                                    "region (meshed)")
        finish, cancel = QPushButton("Finish"), QPushButton("Stop")
        finish.setToolTip("Finish the shape (Enter, double-click or right-click)")
        cancel.setToolTip("Stop drawing (Esc)")
        finish.clicked.connect(self.finish_sketch)
        cancel.clicked.connect(self.cancel_sketch)
        row.addWidget(self.sketch_help, 1)
        for widget in (self.sketch_entry, self.arc_button, self.sketch_grid, self.sketch_role, finish, cancel):
            row.addWidget(widget)
        bar.setVisible(False)
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
        first = self.built is None or self.built.empty or self._fit_next   # (first shape: fit to it)
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
            status = built.sketch_status.get(op_id, "") if state == "ok" else ""
            item = QListWidgetItem(f"{op_id}  {text}{STATE_TEXT[state]}" + (f"  ({status})" if status else ""))
            item.setData(Qt.UserRole, op_id)
            if status:
                item.setForeground(QColor(self.view.dimension_colour(status)))
            elif state in ("failed",):
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
        if built.faces:
            rows.append(("Reference length L", logic.mm(built.reference_length()), "mm"))
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
        self.selection = [s for s in selection if self.built is None or self._exists(s)]   # never a stale id
        self.view.set_selection(self.selection)
        if self.built is not None:
            self.window.show_properties("Selection" if self.selection else "Nothing selected",
                                        logic.selection_rows(self.built, self.selection))
            self.act_points.setEnabled(self._points_operation() is not None)
            if self.view.mode == "points":
                self._show_handles()

    def context_actions(self, kind):
        """The actions of the right-click menu for what is under the cursor ("" = empty space)."""
        t = self.tool_actions
        if kind == "vertex":
            return [t["fillet"], t["chamfer"], None, t["transform"]]
        if kind == "edge":
            return [t["name_boundary"], t["refinement"], None, t["split_edge"], t["trim"], t["extend"], t["offset"],
                    t["fillet"], t["transform"], t["delete"], None, self.act_points]
        if kind == "face":
            return [t["transform"], t["set_role"], t["split_line"], t["boolean"], t["merge_faces"], t["offset"],
                    t["pattern"], None, t["enclosure"], t["refinement"], None, t["delete"]]
        return [self.act_import, None, t["enclosure"], t["refinement"], None, self.act_suggest]

    def on_context_menu(self, kind, entity, position):
        """Right-click: select what is under the cursor (keeping a selection it belongs to) and offer the
        likely next steps, plus the sketch tools."""
        if kind and (kind, entity) not in self.selection:
            self.set_selection([(kind, entity)])
        menu = QMenu(self)
        for action in self.context_actions(kind):
            if action is None:
                menu.addSeparator()
            else:
                menu.addAction(action)
        if kind in ("vertex", "edge"):
            constrain = menu.addMenu(icon("constrain"), "Constrain")
            for action in self.constraint_actions.values():
                constrain.addAction(action)
        if not kind:
            sketch = menu.addMenu(icon("sketch"), "Sketch")
            for sketch_kind, text, icon_name in SKETCHES:
                sketch.addAction(icon(icon_name), text, lambda k=sketch_kind: self.start_sketch(k))
        menu.addSeparator()
        menu.addAction(icon("fit"), "Fit view", self.view.fit)
        menu.exec(position)

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
        if kind in CLICK_TOOLS:                       # used with the mouse, like the drawing tools
            self.start_sketch(kind)
            return
        try:
            op = logic.operation_for(kind, self.selection, self.built)
        except ValueError as error:
            QMessageBox.information(self, "Select first", str(error))
            return
        if kind not in ("delete", "split_face", "fill", "merge_faces"):
            notes = {"transform": "Applies to the selected faces; with nothing selected, to everything.",
                     "enclosure": "Around bodies: sizes in reference lengths L (the length of the solid bodies "
                                  "along x). Nozzle plume region / plenum: in exit / inlet diameters."}
            note = f"{len(op.params['edges'])} edge(s) selected." if kind == "name_boundary" else notes.get(kind, "")
            dialog = OperationDialog(op, op.title, note, self)
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

    def _handle_operation(self):
        """The operation whose handles are dragged: one with points, or an enclosure / refinement region
        (the selected history step, or the one that made the selection)."""
        op = self._points_operation()
        if op is not None:
            return op
        row = self.history.currentRow()
        if self.document is not None and 0 <= row < len(self.document.operations):
            op = self.document.operations[row]
            if logic.handles(op, self.built) is not None:
                return op
        for kind, entity in self.selection:
            if kind == "edge":
                try:
                    op = self.document.find(self.built.edges[entity].sources[0].split(":")[0])
                except KeyError:
                    continue
                if logic.handles(op, self.built) is not None:
                    return op
        return None

    def _show_handles(self):
        op = self._handle_operation()
        self._points_op = op.id if op is not None else None
        if op is None:
            self.view.set_handles(None)
        else:
            self.view.set_handles(logic.points_of(op) if logic.has_points(op) else logic.handles(op, self.built))

    def on_point_moved(self, index, x, y):
        if self._points_op is None:
            return
        op = self.document.find(self._points_op)
        if logic.has_points(op):
            points = logic.points_of(op)
            points[index] = (x, y)
            new, text = logic.with_points(op, points), f"move point {index + 1} of {op.id}"
        else:
            new, text = logic.move_handle(op, self.built, index, (x, y)), f"drag {op.id}: {op.summary()}"
        self.commit(logic.replace_operation(self.document, new), text)

    def set_mode(self, mode):
        self.view.set_mode(mode)
        self.mode_actions[mode].setChecked(True)
        if mode == "points":
            self._show_handles()
            if self._points_op is None:
                self.banner.show_message("Drag points: select an outline made from points, an enclosure or a "
                                         "refinement region (click it, or its step in the History) first.", "info")
        else:
            self.view.set_handles(None)

    # ---- history -----------------------------------------------------------------------------------

    def show_operation(self, row):
        if self.view.mode == "points":
            self._show_handles()
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
        if op.type == "sketch_group" and op.params["constraints"]:
            self._add_constraint_list(op)
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

    def _add_constraint_list(self, op):
        """The constraints of a sketch, with its status; double-click a dimension to change its value."""
        status = self.built.sketch_status.get(op.id, "")
        if status:
            label = QLabel(f"Constraints: {status}")
            label.setStyleSheet(f"color: {self.view.dimension_colour(status)}")
            self.op_box.addWidget(label)
        self.constraint_list = QListWidget()
        for k, c in enumerate(op.params["constraints"]):
            item = QListWidgetItem(f"{k + 1}. {logic.constraint_text(c)}")
            item.setData(Qt.UserRole, k)
            self.constraint_list.addItem(item)
        self.constraint_list.itemDoubleClicked.connect(lambda item: self.edit_dimension(op.id, item.data(Qt.UserRole)))
        self.op_box.addWidget(self.constraint_list)
        row = QHBoxLayout()
        holder = QWidget()
        holder.setLayout(row)
        change = QPushButton("Change value…", toolTip="Change the selected dimension (the shape follows)")
        change.clicked.connect(lambda: self.constraint_list.currentItem() and
                               self.edit_dimension(op.id, self.constraint_list.currentItem().data(Qt.UserRole)))
        remove = QPushButton("Remove", toolTip="Remove the selected constraint (the shape is free to move there)")
        remove.clicked.connect(lambda: self.constraint_list.currentItem() and
                               self.remove_constraint(op.id, self.constraint_list.currentItem().data(Qt.UserRole)))
        row.addWidget(change)
        row.addWidget(remove)
        self.op_box.addWidget(holder)

    # ---- constraints -------------------------------------------------------------------------------

    def ask_dimension(self, constraint):
        """Ask for a dimension's value (mm or degrees); the new constraint, or None if cancelled."""
        angle = constraint["type"] == "angle"
        scale = 1.0 if angle else 1.0 / logic.MM
        label = {"length": "Length", "radius": "Radius", "angle": "Angle", "distance": "Distance"}.get(
            constraint["type"], constraint["type"].replace("_", " ").capitalize())
        value, ok = QInputDialog.getDouble(self, "Dimension", f"{label} [{'°' if angle else 'mm'}]:",
                                           constraint["value"] * scale, -360.0 if angle else 0.0,
                                           360.0 if angle else 1e9, 6)
        if not ok:
            return None
        if not angle and value <= 0.0:
            QMessageBox.information(self, "Dimension", "A length must be larger than zero.")
            return None
        return {**constraint, "value": value / scale}

    def add_constraint(self, kind):
        """Add a constraint (or a dimension, asking its value) to the sketch of the selected entities."""
        if self.built is None:
            return
        try:
            op_id, constraint = logic.constraint_for(kind, self.selection, self.built, self.document)
        except ValueError as error:
            QMessageBox.information(self, "Constrain", str(error))
            return
        if kind == "dimension":
            constraint = self.ask_dimension(constraint)
            if constraint is None:
                return
        self.commit(logic.add_constraint(self.document, op_id, constraint),
                    f"{op_id}: {logic.constraint_text(constraint)}")

    def edit_dimension(self, op_id, index):
        """Change the value of a sketch's dimension (double-click on it): the shape follows."""
        constraint = self.document.find(op_id).params["constraints"][index]
        if "value" not in constraint:
            return
        new = self.ask_dimension(constraint)
        if new is not None:
            self.commit(logic.set_constraint(self.document, op_id, index, new["value"]),
                        f"{op_id}: {logic.constraint_text(new)}")

    def remove_constraint(self, op_id, index):
        constraint = self.document.find(op_id).params["constraints"][index]
        self.commit(logic.set_constraint(self.document, op_id, index, remove=True),
                    f"{op_id}: remove {logic.constraint_text(constraint)}")

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

    # ---- drawing with the mouse (gui/sketch_tools.py) -----------------------------------------------

    def start_sketch(self, kind):
        """Start a drawing tool; it stays on (shape after shape) until Esc or Stop."""
        if self.built is None:
            return
        self.tool = {**sketch_tools.TOOLS, **sketch_tools.EDIT_TOOLS}[kind](self.built, self._snap_grid())
        self.sketch_help.setText(f"<b>{self.tool.title}</b>: {self.tool.help}")
        self.arc_button.setVisible(kind == "polyline")
        self.sketch_role.setVisible(kind in sketch_tools.TOOLS)
        self.sketch_entry.setVisible(kind not in ("trim", "extend"))
        self.sketch_grid.setVisible(kind not in ("trim", "extend"))
        self.arc_button.setChecked(False)
        self.sketch_bar.setVisible(True)
        self.banner.hide_message()
        self.view.set_mode("draw")
        for action in self.mode_actions.values():
            action.setChecked(False)
        self.view.setFocus()

    def _snap_grid(self):
        """The grid spacing to snap to [m] (the visible grid's), or None when snapping to the grid is off."""
        return getattr(self.view, "_grid_step", None) if self.sketch_grid.isChecked() else None

    @property
    def sketch_kind(self):
        return None if self.tool is None else self.tool.kind

    def on_tool_moved(self, x, y, tolerance):
        if self.tool is None:
            return
        self.tool.grid = self._snap_grid()
        self.tool.move((x, y), tolerance)
        self.view.show_tool_preview(self.tool.preview())

    def on_sketch_click(self, x, y, tolerance):
        """A click while drawing: the tool places the (snapped) point; a finished shape is added."""
        if self.tool is None:
            return
        self.tool.grid = self._snap_grid()
        try:
            done = self.tool.click((x, y), tolerance)
        except ValueError as error:
            self.banner.show_message(str(error), "warning")
            return
        self._after_point(done)

    def type_sketch_point(self):
        """Enter in the typed-value box: place the typed point (an empty box finishes the shape)."""
        if self.tool is None:
            return
        text = self.sketch_entry.text()
        if not text.strip():
            self.finish_sketch()
            return
        try:
            done = self.tool.typed(text)
        except ValueError as error:
            self.banner.show_message(str(error), "warning")
            return
        self.sketch_entry.clear()
        self._after_point(done)

    def _after_point(self, done):
        self.banner.hide_message()
        if done:
            self.finish_sketch()
        else:
            self.view.show_tool_preview(self.tool.preview())

    def finish_sketch(self, *_):
        """Add the drawn shape to the history (Enter, double-click, right-click, or closing it) and
        start the next shape with the same tool."""
        tool = self.tool
        if tool is None:
            return
        if not tool.done and not tool.finish():
            self.banner.show_message("Nothing to add yet: place at least two points.", "info")
            return
        document = self.document.copy()
        op = tool.add_to(document, self.sketch_role.currentData())
        if op is not None:
            self.commit(document, op.summary())
        self.start_sketch(tool.kind)                           # ready for the next shape

    def undo_sketch_point(self):
        """Backspace: take back the last placed point of the shape being drawn."""
        tool = self.tool
        if tool is None or not tool.clicks:
            return
        clicks = [tool.points[i] for i in tool.clicks[:-1]]
        arc = getattr(tool, "arc_next", False)
        self.tool = type(tool)(self.built, self._snap_grid())   # (rebuilt from the remaining points)
        for point in clicks:
            self.tool.place(point)
        if hasattr(self.tool, "arc_next"):
            self.tool.arc_next = arc
        self.view.show_tool_preview(self.tool.preview())

    def toggle_arc(self, *_):
        """A: the next segment of the polyline is a tangent arc (once)."""
        if self.tool is not None and hasattr(self.tool, "arc_next"):
            self.tool.arc_next = not self.tool.arc_next
            self.arc_button.setChecked(self.tool.arc_next)
            self.view.show_tool_preview(self.tool.preview())

    def on_typed_key(self, char):
        """A digit typed over the view while drawing starts the typed-value box."""
        if self.tool is not None:
            self.sketch_entry.setFocus()
            self.sketch_entry.insert(char)

    def cancel_sketch(self):
        self.tool = None
        self.sketch_bar.setVisible(False)
        self.view.show_tool_preview(None)
        self.view.set_handles(None)
        self.set_mode("select")

    def escape(self):
        """Esc: drop the shape being drawn; again (or with nothing drawn): stop drawing; else clear the selection."""
        if self.tool is not None and self.tool.clicks:
            self.start_sketch(self.tool.kind)
        elif self.tool is not None:
            self.cancel_sketch()
        else:
            self.set_selection([])

    def on_box_selected(self, x0, y0, x1, y1, touching, add):
        """A box drawn in empty space: left to right selects what is completely inside, right to left
        what it touches (as in CAD programs)."""
        kinds = tuple(k for k in ("vertex", "edge", "face") if self.view.filters[k].isChecked())
        found = picking.box_select(self.built, x0, y0, x1, y1, touching, kinds)
        selection = list(self.selection) if add else []
        selection += [s for s in found if s not in selection]
        self.set_selection(selection)

    # ---- suggestions and export ------------------------------------------------------------------

    def suggestions(self):
        """The smart rule's suggestions for the current geometry and inputs (empty if not possible)."""
        from aeroflowsim import smart_rules
        project = self.project
        if self.built is None or not hasattr(project.case, "size_inputs"):
            return []
        try:
            params = project.params_for(("geometry", "mesh"))
            sizes = project.case.size_inputs(params, self.built)
        except (ValueError, AttributeError):
            return []
        mach = params.get("mach")
        context = smart_rules.SizeContext(params, sizes, mach, self.document)
        return smart_rules.suggestions(self.built, context)

    def show_suggestions(self):
        SuggestionsDialog(self.suggestions(), self.apply_suggestion, self).exec()

    def apply_suggestion(self, suggestion):
        if suggestion.kind == "input":
            self.window.set_inputs(suggestion.inputs, f"suggested {suggestion.title.lower()}")
            return
        document = self.document.copy()
        op = suggestion.operation
        if op.id:
            document.replace(op)
        else:
            document.add(op)
        self.commit(document, f"suggested {suggestion.title.lower()}")

    def export(self):
        from aeroflowsim.geometry_model.export import export_geometry
        if self.built is None or self.built.empty:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export geometry", str(self.project.folder / "geometry.step"),
                                              "STEP (*.step *.stp);;DXF (*.dxf);;CSV points (*.csv)")
        if not path:
            return
        try:
            export_geometry(self.document, self.project.replay_context(), self.built, path)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Export", str(error))
            return
        self.window.log(f"Geometry exported to {path}")

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

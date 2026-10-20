# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The main window of the desktop GUI.

Layout:
    menu bar (File, Edit, View, Tools, Help) and toolbar
    centre: the page of the current workflow step (Geometry, Mesh, Setup, Run, Results)
    bottom: the workflow strip (step chips with status colours; a running job shows progress there)
    dockable panels: Inputs (the auto-generated panel of the current step), Properties (derived
    numbers or the clicked cell / boundary), Messages (log), Validity checks

The window owns the state: the open Project (aeroflowsim/project.py), the loaded mesh and results,
the background JobRunner and the undo stack. Pages only display it and call methods here.

Signals and slots in one sentence: a widget *emits a signal* when something happens (a button is
clicked, a job ends) and every function *connected* to it (a "slot") is called, e.g.
    self.runner.ended.connect(self.on_job_ended)
"""

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QUndoStack
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QInputDialog, QLabel, QMainWindow, QMessageBox,
                               QPlainTextEdit, QStackedWidget, QVBoxLayout, QWidget)

from aeroflowsim.checks import run_mesh_checks
from aeroflowsim.discovery import find_cases
from aeroflowsim.gui import app_info
from aeroflowsim.gui.dialogs import ProjectPlaceDialog
from aeroflowsim.gui.jobs import JobRunner
from aeroflowsim.gui.logic import auto_rebuild, estimated_cells, is_face_mesh, progress_fraction
from aeroflowsim.gui.panel import InputPanel
from aeroflowsim.gui.panel_model import PanelModel
from aeroflowsim.gui.steps.geometry import GeometryPage
from aeroflowsim.gui.steps.mesh import MeshPage
from aeroflowsim.gui.steps.results import ResultsPage
from aeroflowsim.gui.steps.run import RunPage
from aeroflowsim.gui.steps.setup import SetupPage
from aeroflowsim.gui.steps.welcome import WelcomePage
from aeroflowsim.gui.theme import apply_theme
from aeroflowsim.gui.undo import SetGeometry, SetInputs
from aeroflowsim.gui.widgets import CheckList, ValueTable
from aeroflowsim.gui.workflow_strip import SHORTCUTS, TITLES, WorkflowStrip
from aeroflowsim.mesh import Mesh
from aeroflowsim.parameters import STEPS as INPUT_STEPS
from aeroflowsim.parameters import defaults, install_hint, module_available
from aeroflowsim.project import (SUFFIX, WORKFLOW, Project, default_projects_dir, folder_for, is_project,
                                 old_settings_files)
from aeroflowsim.tasks import Job

MAX_RECENT = 8
PANEL_FOR_STEP = {"geometry": "geometry", "mesh": "mesh", "setup": "setup", "run": "setup", "results": "setup"}
AUTO_MESH_DELAY_MS = 500    # wait this long after the last input change before an automatic re-mesh


def make_settings() -> QSettings:
    """Preferences (theme, recent projects, window layout) in a readable INI file in the user's folder."""
    return QSettings(QSettings.IniFormat, QSettings.UserScope, app_info.ORGANISATION, app_info.APPLICATION)


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or make_settings()
        self.setWindowIcon(QIcon(str(app_info.ICON)))
        self.resize(1500, 900)
        self.project = None
        self.mesh = None            # Mesh or Mesh1D shown in the Mesh step
        self.mesh_checks = []       # validity checks of that mesh
        self.results = None         # payload of the last run (result, reference, checks, ...)
        self.auto_mesh_note = ""    # why an out-of-date mesh was not rebuilt automatically
        self.pending = None         # (kind, fingerprint) of the job that is running
        self.run_after_mesh = False
        self.current_step = None
        self.panels = {}
        self.dark = self.settings.value("theme", "light") == "dark"

        self.runner = JobRunner(self)
        self.runner.updated.connect(self.on_job_updated)
        self.runner.ended.connect(self.on_job_ended)
        self.undo = QUndoStack(self)
        self.undo.cleanChanged.connect(self.update_title)   # a method (not a lambda): Qt disconnects it
                                                             # by itself when the window is deleted

        self.pages = {"welcome": WelcomePage(self), "geometry": GeometryPage(self), "mesh": MeshPage(self),
                      "setup": SetupPage(self), "run": RunPage(self), "results": ResultsPage(self)}
        self.stack = QStackedWidget()
        for page in self.pages.values():
            self.stack.addWidget(page)
        self.strip = WorkflowStrip()
        self.strip.step_clicked.connect(self.go_to)
        self.strip.cancel_requested.connect(self.cancel_job)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.strip)
        self.setCentralWidget(central)

        self.build_docks()
        self.build_actions()
        self.geometry_timer = self._single_shot(150, lambda: self.pages["geometry"].refresh())
        self.auto_mesh_timer = self._single_shot(AUTO_MESH_DELAY_MS, self.maybe_auto_mesh)
        state = self.settings.value("window_state")
        if state is not None:
            self.restoreState(state)
        self.set_dark(self.dark, save=False)
        self.show_welcome()

    def _single_shot(self, ms, slot):
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(ms)
        timer.timeout.connect(slot)
        return timer

    # ================================================================================== building

    def build_docks(self):
        self.inputs = QStackedWidget()
        self.inputs.addWidget(QLabel("  Open or create a project."))
        self.properties_title = QLabel()
        self.properties = ValueTable(["Property", "Value", "Unit"])
        props = QWidget()
        props_layout = QVBoxLayout(props)
        props_layout.setContentsMargins(4, 4, 4, 4)
        props_layout.addWidget(self.properties_title)
        props_layout.addWidget(self.properties)
        self.messages = QPlainTextEdit(readOnly=True)
        self.messages.setMaximumBlockCount(5000)
        self.checks = CheckList()
        self.docks = {}
        for key, title, widget, area in (("inputs", "Inputs", self.inputs, Qt.LeftDockWidgetArea),
                                         ("properties", "Properties", props, Qt.RightDockWidgetArea),
                                         ("checks", "Validity checks", self.checks, Qt.RightDockWidgetArea),
                                         ("messages", "Messages", self.messages, Qt.BottomDockWidgetArea)):
            dock = QDockWidget(title, self)
            dock.setObjectName(f"dock_{key}")     # needed to remember the layout between sessions
            dock.setWidget(widget)
            self.addDockWidget(area, dock)
            self.docks[key] = dock
        self.resizeDocks([self.docks["inputs"]], [420], Qt.Horizontal)
        self.resizeDocks([self.docks["messages"]], [130], Qt.Vertical)

    def _action(self, text, slot, shortcut=None, tip="", checkable=False):
        action = QAction(text, self, checkable=checkable)
        if shortcut:
            action.setShortcuts([QKeySequence(s) for s in ([shortcut] if isinstance(shortcut, str) else shortcut)])
        if tip:
            action.setStatusTip(tip)
            action.setToolTip(f"{tip} ({action.shortcut().toString()})" if shortcut else tip)
        action.triggered.connect(slot)
        return action

    def build_actions(self):
        a = self._action
        self.act = {
            "new": a("&New project...", lambda: self.new_project(), "Ctrl+N", "New project from a template"),
            "open": a("&Open project...", lambda: self.open_project(), "Ctrl+O", "Open a project folder"),
            "save": a("&Save", self.save, "Ctrl+S", "Save the project"),
            "save_as": a("Save &as...", self.save_as, "Ctrl+Shift+S", "Copy the project to a new folder and continue there"),
            "duplicate": a("&Duplicate...", self.duplicate, None, "Make a copy of the project"),
            "import": a("&Import old settings...", self.import_old_settings, None, "Old Streamlit settings file -> project"),
            "folder": a("Show project &folder", self.show_folder, None, "Open the project folder"),
            "close": a("&Close project", self.close_project, "Ctrl+W", "Close the project"),
            "quit": a("&Quit", self.close, "Ctrl+Q", "Quit AeroFlowSim"),
            "reset": a("&Reset all inputs to defaults", self.reset_inputs, None, "Every input back to its default"),
            "fit": a("&Fit view", self.fit_view, "F", "Show the whole drawing"),
            "dark": a("&Dark theme", lambda on: self.set_dark(on), "Ctrl+T", "Switch light / dark", checkable=True),
            "generate": a("&Generate mesh", lambda: self.generate_mesh(), "Ctrl+G", "Build the mesh"),
            "run": a("&Run", self.run_case, "F5", "Mesh if needed, then solve"),
            "stop": a("&Stop", self.cancel_job, "Shift+F5", "Stop the running job"),
            "validation": a("Run &validation suite...", self.run_validation, None, "Run all validation cases"),
            "about": a("&About AeroFlowSim", self.about, None, "Version, licence, how to cite"),
            "manual": a("&Theory manual", lambda: self.open_local(app_info.THEORY_MANUAL), None, "Equations and methods"),
            "devguide": a("&Developer guide", lambda: self.open_local(app_info.DEVELOPER_GUIDE), None, "How the GUI works"),
            "report": a("&Validation report", lambda: self.open_local(app_info.VALIDATION_REPORT), None, "Latest validation results"),
        }
        self.act["dark"].setChecked(self.dark)
        self.act["undo"] = self.undo.createUndoAction(self, "&Undo")
        self.act["undo"].setShortcuts([QKeySequence("Ctrl+Z")])
        self.act["redo"] = self.undo.createRedoAction(self, "&Redo")
        self.act["redo"].setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])

        menu = self.menuBar()
        file_menu = menu.addMenu("&File")
        file_menu.addActions([self.act["new"], self.act["open"]])
        self.recent_menu = file_menu.addMenu("Open &recent")
        file_menu.addSeparator()
        file_menu.addActions([self.act[k] for k in ("save", "save_as", "duplicate")])
        file_menu.addSeparator()
        file_menu.addActions([self.act[k] for k in ("import", "folder", "close")])
        file_menu.addSeparator()
        file_menu.addAction(self.act["quit"])
        edit_menu = menu.addMenu("&Edit")
        edit_menu.addActions([self.act["undo"], self.act["redo"]])
        edit_menu.addSeparator()
        edit_menu.addAction(self.act["reset"])
        view_menu = menu.addMenu("&View")
        for step in WORKFLOW:
            view_menu.addAction(self._action(TITLES[step], lambda _=False, s=step: self.go_to(s), SHORTCUTS[step]))
        view_menu.addSeparator()
        view_menu.addActions([self.act["fit"], self.act["dark"]])
        panels = view_menu.addMenu("&Panels")
        for dock in self.docks.values():
            panels.addAction(dock.toggleViewAction())
        tools_menu = menu.addMenu("&Tools")
        tools_menu.addActions([self.act[k] for k in ("generate", "run", "stop")])
        tools_menu.addSeparator()
        tools_menu.addAction(self.act["validation"])
        help_menu = menu.addMenu("&Help")
        help_menu.addActions([self.act[k] for k in ("manual", "devguide", "report")])
        help_menu.addSeparator()
        help_menu.addAction(self.act["about"])

        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("toolbar_main")
        toolbar.addActions([self.act[k] for k in ("new", "open", "save")])
        toolbar.addSeparator()
        # Toolbar Undo/Redo keep short fixed labels; the Edit menu shows what will be undone
        # ("Undo change Throat diameter"), which would make toolbar buttons grow and jump.
        for key, slot, signal in (("undo", self.undo.undo, self.undo.canUndoChanged),
                                  ("redo", self.undo.redo, self.undo.canRedoChanged)):
            short = QAction(key.capitalize(), self, enabled=False)
            short.setToolTip(f"{key.capitalize()} the last input change ({self.act[key].shortcut().toString()})")
            short.triggered.connect(slot)
            signal.connect(short.setEnabled)
            toolbar.addAction(short)
        toolbar.addSeparator()
        toolbar.addActions([self.act[k] for k in ("generate", "run", "stop")])
        toolbar.addSeparator()
        toolbar.addActions([self.act["fit"], self.act["dark"]])
        self.update_recent_menu()

    # ================================================================================== state helpers

    def templates(self):
        cases, problems = find_cases()
        for name, problem in problems.items():
            self.log(f"Template {name} is broken: {problem}", "error")
        return cases

    def log(self, text, level="info"):
        mark = {"info": "", "warning": "WARNING: ", "error": "ERROR: "}[level]
        self.messages.appendPlainText(f"{mark}{text}")

    def show_properties(self, title, rows):
        self.properties_title.setText(f"<b>{title}</b>")
        self.properties.set_rows(rows)
        self.docks["properties"].raise_()

    def update_title(self, *_):
        if self.project is None:
            self.setWindowTitle("AeroFlowSim")
            return
        star = "*" if self.unsaved() else ""
        self.setWindowTitle(f"{self.project.name}{star} - {self.project.case.title} - AeroFlowSim")

    def unsaved(self) -> bool:
        return self.project is not None and (self.project.dirty or not self.undo.isClean())

    def refresh_status(self):
        if self.project is None:
            return
        statuses = self.project.statuses()
        self.strip.set_statuses(statuses)
        busy = self.runner.busy
        self.act["generate"].setEnabled(not busy)
        self.act["run"].setEnabled(not busy and self.project.case.has_solver)
        self.act["stop"].setEnabled(busy)

    def refresh_all(self):
        self.refresh_status()
        self.update_title()
        self.update_checks()
        if self.current_step:
            self.pages[self.current_step].refresh()

    def update_checks(self):
        sections = []
        if self.mesh is not None and self.project is not None:
            note = "" if self.project.status("mesh") == "ok" else " (out of date)"
            sections.append((f"Mesh{note}", self.mesh_checks))
        if self.results is not None and self.project is not None:
            note = "" if self.project.status("results") == "ok" else " (out of date)"
            sections.append((f"Results{note}", self.results.get("checks", [])))
        self.checks.set_sections(sections)

    # ================================================================================== navigation

    def show_welcome(self):
        self.current_step = None
        self.checks.set_sections([])             # nothing from a closed project stays on screen
        self.properties_title.setText("")
        self.properties.set_rows([])
        self.docks["inputs"].setWindowTitle("Inputs")
        self.stack.setCurrentWidget(self.pages["welcome"])
        self.pages["welcome"].refresh()
        self.strip.setVisible(False)
        for key in ("save", "save_as", "duplicate", "folder", "close", "reset", "generate", "run", "stop"):
            self.act[key].setEnabled(False)
        self.update_title()

    def go_to(self, step):
        if self.project is None or self.strip.chips[step].status == "disabled":
            return
        self.current_step = step
        self.stack.setCurrentWidget(self.pages[step])
        self.inputs.setCurrentWidget(self.panels[PANEL_FOR_STEP[step]])
        self.docks["inputs"].setWindowTitle(f"Inputs - {TITLES[PANEL_FOR_STEP[step]]}")
        self.strip.set_current(step)
        self.pages[step].refresh()

    def fit_view(self):
        page = self.pages.get(self.current_step)
        view = getattr(page, "view", None)
        if hasattr(view, "fit"):
            view.fit()

    def set_dark(self, dark, save=True):
        self.dark = dark
        apply_theme(dark)
        for page in self.pages.values():
            view = getattr(page, "view", None)
            if hasattr(view, "set_dark"):
                view.set_dark(dark)
        if save:
            self.settings.setValue("theme", "dark" if dark else "light")
        self.redraw_for_theme()

    def redraw_for_theme(self):
        """Things that carry colours inside their content (plots, check list, Details, card) are
        drawn again; everything else follows the new style sheet by itself."""
        for panel in self.panels.values():
            panel.restyle()
        self.update_checks()
        results = self.pages["results"]
        results._shown = None                  # re-create its plots with the new matplotlib colours
        results.card.restyle()
        self.pages["mesh"]._shown = None if not is_face_mesh(self.mesh) else self.pages["mesh"]._shown
        self.pages["run"].redraw()
        if self.current_step:
            self.pages[self.current_step].refresh()

    # ================================================================================== projects

    def recent_projects(self):
        recent = self.settings.value("recent", []) or []
        recent = [recent] if isinstance(recent, str) else list(recent)
        return [p for p in recent if is_project(p)]

    def add_recent(self, folder):
        recent = [str(folder)] + [p for p in self.recent_projects() if Path(p) != Path(folder)]
        self.settings.setValue("recent", recent[:MAX_RECENT])
        self.update_recent_menu()

    def update_recent_menu(self):
        self.recent_menu.clear()
        for path in self.recent_projects():
            self.recent_menu.addAction(Path(path).name, lambda p=path: self.open_project(p))
        self.recent_menu.setEnabled(bool(self.recent_projects()))

    def new_project(self, template=None):
        if not self.maybe_save():
            return
        dialog = ProjectPlaceDialog("New project", parent=self, templates=self.templates(), template=template)
        if not dialog.exec():
            return
        try:
            project = Project.create(dialog.template(), dialog.folder)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "New project", str(error))
            return
        self.load_project(project)

    def create_from_template(self, template):
        """Start page double-click: a new project from this template at once, named "My <template>"
        (numbered if that exists) in the default projects folder."""
        if not template or not self.maybe_save():
            return
        case = self.templates().get(template)
        if case is None:
            return
        folder, n = folder_for(f"My {case.title}"), 2
        while folder.exists():
            folder = folder_for(f"My {case.title} {n}")
            n += 1
        try:
            project = Project.create(template, folder)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "New project", str(error))
            return
        self.log(f"New project {folder.name} from the template '{case.title}'")
        self.load_project(project)

    def open_project(self, folder=None):
        if not self.maybe_save():
            return
        if folder is None:
            start = str(default_projects_dir() if default_projects_dir().is_dir() else Path.home())
            folder = QFileDialog.getExistingDirectory(self, f"Open a project folder (*{SUFFIX})", start)
            if not folder:
                return
        try:
            project = Project.open(folder)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Open project", str(error))
            return
        self.load_project(project)

    def load_project(self, project):
        """Show a project: panels, mesh, results, statuses."""
        self.close_project(ask=False)
        self.project = project
        self.undo.clear()
        for step in INPUT_STEPS:
            panel = InputPanel(PanelModel(project.case.parameters(), step), project.values,
                               file_handler=lambda name, path: self.project.import_file(path))
            panel.value_changed.connect(self.on_panel_edit)
            self.panels[step] = panel
            self.inputs.addWidget(panel)
        self.mesh = self.results = None
        self.mesh_checks = []
        self.pages["run"].reset()                # no progress text left from another project
        try:
            self.mesh = project.load_mesh()
            if self.mesh is not None:
                self.mesh_checks = run_mesh_checks(project.case, project.params_for(("geometry", "mesh")), self.mesh)
        except (ValueError, OSError) as error:
            self.log(f"The saved mesh could not be read: {error}", "warning")
        try:
            self.results = project.load_results()
            if self.results is not None and self.mesh is None and "mesh1d" in self.results:
                self.mesh = self.results["mesh1d"]
        except (ValueError, OSError, KeyError) as error:
            self.log(f"The saved results could not be read: {error}", "warning")
        if self.results is not None:
            self.results["run_s"] = (project.steps.get("run") or {}).get("run_s")
            self.pages["run"].show_history(self.results["result"], self.results["params"].get("tol"))
        self.add_recent(project.folder)
        self.strip.setVisible(True)
        for key in ("save", "save_as", "duplicate", "folder", "close", "reset"):
            self.act[key].setEnabled(True)
        self.log(f"Opened {project.folder}")
        for warning in project.warnings:
            self.log(warning, "warning")
        if project.warnings:
            QMessageBox.information(self, "Project opened", "\n\n".join(project.warnings))
        self.go_to("geometry")
        self.refresh_all()
        self.pages["geometry"].refresh()

    def close_project(self, ask=True):
        if self.project is None:
            return True
        if ask and not self.maybe_save():
            return False
        if self.runner.busy:
            self.runner.cancel()
        for panel in self.panels.values():
            self.inputs.removeWidget(panel)
            panel.hide()
            panel.setParent(None)
            panel.deleteLater()
        self.panels = {}
        self.project = self.mesh = self.results = None
        self.undo.clear()
        self.show_welcome()
        return True

    def maybe_save(self) -> bool:
        """Ask to save unsaved input changes. False = the user cancelled."""
        if not self.unsaved():
            return True
        answer = QMessageBox.question(self, "Unsaved changes", f"Save the changes to {self.project.name}?",
                                      QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            self.save()
        return True

    def save(self):
        if self.project is None:
            return
        self.project.save()
        self.undo.setClean()
        self.update_title()
        self.strip.show_message(f"Saved {self.project.modified[11:16]}")

    def _ask_place(self, title):
        dialog = ProjectPlaceDialog(title, name=f"{self.project.name} copy", parent=self)
        dialog.location.setText(str(self.project.folder.parent))
        return dialog.folder if dialog.exec() else None

    def save_as(self):
        folder = self._ask_place("Save project as")
        if folder:
            self.project.save_as(folder)
            self.undo.setClean()
            self.add_recent(folder)
            self.update_title()
            self.log(f"Saved as {folder}")

    def duplicate(self):
        folder = self._ask_place("Duplicate project")
        if not folder:
            return
        copy = self.project.duplicate(folder)
        self.add_recent(folder)
        self.log(f"Duplicated to {folder}")
        if QMessageBox.question(self, "Duplicate", f"Open the copy {copy.name} now?") == QMessageBox.Yes:
            self.open_project(str(folder))

    def show_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project.folder)))

    def import_old_settings(self):
        files = old_settings_files()
        if not files:
            QMessageBox.information(self, "Import old settings", "No old settings files were found.")
            return
        labels = [f"{f.parents[1].name} / {f.stem}" for f in files]
        label, ok = QInputDialog.getItem(self, "Import old settings", "Settings file to turn into a project:",
                                         labels, 0, False)
        if not ok or not self.maybe_save():
            return
        source = files[labels.index(label)]
        folder = folder_for(f"{source.parents[1].name} {source.stem}")
        n = 2
        while folder.exists():
            folder = folder_for(f"{source.parents[1].name} {source.stem} {n}")
            n += 1
        try:
            project = Project.from_old_settings(source, folder)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Import old settings", str(error))
            return
        self.log(f"Imported {source} as {folder} (the old file is unchanged)")
        self.load_project(project)

    # ================================================================================== inputs and undo

    def on_panel_edit(self, name, value):
        """Slot: the user changed an input in a panel -> an undoable command."""
        old = self.project.values.get(name)
        label = next((p.label for p in self.project.case.parameters() if p.name == name), name)
        self.undo.push(SetInputs(self, {name: (old, value)}, f"change {label}"))

    def reset_inputs(self):
        if self.project is None:
            return
        base = defaults(self.project.case.parameters())
        changes = {k: (self.project.values[k], v) for k, v in base.items() if self.project.values.get(k) != v}
        for p in self.project.case.parameters():        # keep the project's own copies of default files
            if p.type == "file":
                changes.pop(p.name, None)
        if changes:
            self.undo.push(SetInputs(self, changes, "reset inputs to defaults"))

    def apply_values(self, values):
        """Put values into the project and every panel (used by undo/redo commands)."""
        for name, value in values.items():
            self.project.set_value(name, value)
        for panel in self.panels.values():
            panel.set_values(values)
        steps = {p.step for p in self.project.case.parameters() if p.name in values}
        if "geometry" in steps:
            self.geometry_timer.start()
        if steps & {"geometry", "mesh"}:
            self.auto_mesh_note = ""
            self.auto_mesh_timer.start()
        self.refresh_all()

    def edit_geometry(self, document, text):
        """Slot of the geometry workspace: a new history -> an undoable command."""
        old = self.project.geometry_document()
        if document.to_dict()["operations"] != old.to_dict()["operations"] or                 document.axisymmetric != old.axisymmetric:
            self.undo.push(SetGeometry(self, old, document, text))

    def apply_geometry(self, document):
        """Use a geometry history (called by undo/redo commands)."""
        self.project.set_geometry_document(document)
        self.auto_mesh_note = ""
        self.auto_mesh_timer.start()
        self.refresh_all()
        if self.current_step != "geometry":
            self.pages["geometry"].refresh()

    # ================================================================================== jobs

    def maybe_auto_mesh(self):
        """Rebuild an out-of-date mesh by itself when it is small (as the old GUI did)."""
        project = self.project
        if project is None or self.runner.busy or self.mesh is None or project.status("mesh") != "outdated":
            return
        try:
            params = project.params_for(("geometry", "mesh"))
        except ValueError:
            return
        if project.edited_geometry is None:
            estimate = estimated_cells(project.case, params)
        else:                                    # an edited geometry: estimate from the workspace drawing
            from aeroflowsim.workspace_mesh import estimate_cells
            built = self.pages["geometry"].built
            try:
                estimate = estimate_cells(built, project.case.workspace_settings(params, built))
            except (ValueError, AttributeError):
                return
        if auto_rebuild(estimate):
            self.generate_mesh(auto=True)
        else:
            self.auto_mesh_note = (f"It would have about {estimate:,} cells: press Generate mesh "
                                   "(automatic rebuilding only below 50,000 cells).")
            self.refresh_all()

    def generate_mesh(self, auto=False):
        project = self.project
        if project is None or self.runner.busy:
            return
        try:
            params = project.params_for(("geometry", "mesh"))
        except ValueError as error:
            self.run_after_mesh = False
            if not auto:
                QMessageBox.warning(self, "Cannot mesh yet", str(error))
            return
        missing = [name for name in project.case.requires if not module_available(name)]
        if missing:
            QMessageBox.warning(self, "Missing package", f"This template needs {', '.join(missing)}. Install it with: "
                                f"{install_hint(missing[0])}")
            return
        self.pending = ("mesh", project.fingerprint("mesh"), params)
        edited = project.edited_geometry
        self.runner.submit(Job("mesh", str(project.case.folder), params, str(project.mesh_dir),
                               geometry=None if edited is None else edited.to_dict(), folder=str(project.folder)))
        self.strip.set_busy("mesh", None, "meshing")
        self.log(("Automatic re-mesh" if auto else "Meshing") + f" ({project.case.title})")
        self.refresh_all()

    def run_case(self):
        project = self.project
        if project is None or self.runner.busy or not project.case.has_solver:
            return
        problems = project.problems()
        if problems:
            labels = {p.name: (p.label, p.step) for p in project.case.parameters()}
            text = "\n".join(f"- {labels[k][0]}: {msg}" for k, msg in problems.items())
            QMessageBox.warning(self, "Inputs to fix", f"Please fix these inputs first:\n{text}")
            self.go_to(labels[next(iter(problems))][1])
            return
        if self.mesh is None or project.status("mesh") != "ok":
            self.run_after_mesh = True
            self.go_to("run")
            self.generate_mesh()
            return
        self.start_run()

    def start_run(self):
        project = self.project
        params = project.params()
        mesh = str(project.mesh_dir / "mesh.npz") if is_face_mesh(self.mesh) else self.mesh
        self.pending = ("run", project.fingerprint("run"), params)
        self.runner.submit(Job("run", str(project.case.folder), params, str(project.results_dir), mesh=mesh))
        self.strip.set_busy("run", 0.0, "starting")
        self.log(f"Run started ({project.case.title})")
        self.go_to("run")
        self.refresh_all()

    def cancel_job(self):
        if self.runner.busy:
            self.run_after_mesh = False
            self.runner.cancel()

    def on_job_updated(self, task):
        if task.job.kind == "run" and task.iterations:
            fraction = progress_fraction(task.job.params, task.iterations[-1], task.residuals[-1])
            self.strip.set_busy("run", fraction, f"{100 * fraction:.0f}%")
        self.pages["run"].show_task(task)

    def on_job_ended(self, task):
        kind, fingerprint, params = self.pending or (task.job.kind, None, task.job.params)
        self.pending = None
        self.strip.set_idle()
        project = self.project
        if project is None:
            return
        seconds = f"{task.elapsed_s:.2f} s"
        if task.status == "finished" and kind == "mesh":
            payload = task.payload
            mesh = Mesh.load(payload["mesh_path"]) if "mesh_path" in payload else payload["mesh"]
            project.record_mesh(mesh, {"build_s": round(payload.get("build_s", 0.0), 3)}, fingerprint=fingerprint)
            self.undo.setClean()                  # making a mesh saves the project (see project.py)
            self.mesh = mesh
            self.mesh_checks = run_mesh_checks(project.case, params, mesh)
            self.log(f"Mesh ready: {mesh.n_cells:,} cells in {seconds}")
            errors = [c for c in self.mesh_checks if c.level == "error"]
            for check in errors:
                self.log(f"{check.name}: {check.message}", "error")
            if self.run_after_mesh:
                self.run_after_mesh = False
                if errors:
                    QMessageBox.warning(self, "Mesh check failed", "The mesh has an error-level check; the solver "
                                        "will not run. See Validity checks.")
                else:
                    self.refresh_all()
                    self.start_run()
                    return
        elif task.status == "finished" and kind == "run":
            payload = dict(task.payload)
            project.record_run(payload, self.mesh, fingerprint=fingerprint)
            self.undo.setClean()
            self.results = payload
            result = payload["result"]
            done = "converged" if result.converged else "finished, NOT converged"
            self.log(f"Run {done}: {result.iterations:,} iterations, {payload.get('run_s', 0):.3g} s")
            self.pages["run"].show_task(task, force=True)
            self.refresh_all()
            self.go_to("results")
            return
        elif task.status == "stopped":
            self.log(f"Run stopped by you after {seconds}: no new results.")
        elif task.status == "cancelled":
            self.run_after_mesh = False
            self.log(f"{kind.capitalize()} cancelled after {seconds}.")
        elif task.status == "failed":
            self.run_after_mesh = False
            project.record_failure(kind, task.error, fingerprint=fingerprint)
            self.undo.setClean()
            self.log(f"{kind.capitalize()} failed: {task.error}", "error")
            if task.details:
                self.messages.appendPlainText(task.details)
        self.refresh_all()
        self.auto_mesh_timer.start()             # inputs may have changed while the job ran

    # ================================================================================== tools and help

    def run_validation(self):
        if not app_info.VALIDATION_SCRIPT.is_file():
            QMessageBox.information(self, "Validation", "The validation suite is only in a full source checkout.")
            return
        if getattr(self, "validation", None) is not None:
            return
        self.validation = QProcess(self)
        self.validation.setWorkingDirectory(str(app_info.VALIDATION_SCRIPT.parents[1]))
        self.validation.setProcessChannelMode(QProcess.MergedChannels)
        self.validation.readyReadStandardOutput.connect(
            lambda: self.messages.appendPlainText(bytes(self.validation.readAllStandardOutput()).decode(errors="replace").rstrip()))
        self.validation.finished.connect(self._validation_done)
        self.log("Validation suite started (this takes a few minutes; you can keep working).")
        self.validation.start(sys.executable, [str(app_info.VALIDATION_SCRIPT)])

    def _validation_done(self, code, _status):
        self.validation = None
        self.log(f"Validation suite finished (exit code {code}).", "info" if code == 0 else "error")
        if QMessageBox.question(self, "Validation", "Validation finished. Open the report?") == QMessageBox.Yes:
            self.open_local(app_info.VALIDATION_REPORT)

    def open_local(self, path):
        """Open a local document with the system's viewer (no network)."""
        if Path(path).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.information(self, "Not found", f"{path} is not available in this installation.")

    def about(self):
        box = QMessageBox(self)
        box.setWindowTitle("About AeroFlowSim")
        box.setIconPixmap(QIcon(str(app_info.ICON)).pixmap(96, 96))
        box.setText(app_info.about_html())
        box.exec()

    # ================================================================================== closing

    def closeEvent(self, event):
        if not self.maybe_save():
            event.ignore()
            return
        self.settings.setValue("window_state", self.saveState())
        self.geometry_timer.stop()          # no delayed redraw after the views are closed
        self.auto_mesh_timer.stop()
        self.runner.shutdown()
        for page in self.pages.values():
            view = getattr(page, "view", None)
            if hasattr(view, "close_view"):
                view.close_view()
        super().closeEvent(event)

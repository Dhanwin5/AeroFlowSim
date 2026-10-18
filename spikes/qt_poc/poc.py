# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Throwaway proof of concept for the Qt + PyVista desktop GUI (Prompt 6c, step 0).

Run from the project folder:   .venv\\Scripts\\python.exe spikes\\qt_poc\\poc.py

It proves the pieces Prompt 6d needs: main window with menus, toolbar, dockable panels and a VTK
view; our meshes shown with edges and a colour field; click a boundary edge -> its patch; click a
cell -> its values; a draggable point handle and box with live coordinates; a long meshing job in
a separate process with progress and Cancel; light and dark theme. Not part of the package.
"""

import multiprocessing
import queue as queue_module
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (QApplication, QComboBox, QDockWidget, QFormLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QTextEdit, QWidget)
from vtkmodules.vtkRenderingCore import vtkCellPicker, vtkCoordinate

from aeroflowsim.discovery import load_case
from aeroflowsim.mesh import CELL_TYPES, Mesh
from aeroflowsim.parameters import defaults, validate

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from convert import mesh_to_grid, patch_lines   # noqa: E402  (spike-local modules)
import mesh_worker                              # noqa: E402

PROJECT_DIR = HERE.parents[1]
ICON = PROJECT_DIR / "assets" / "icon.png"
COLOUR_FIELDS = ["aspect_ratio", "non_orthogonality", "cell_volume"]
PATCH_COLOURS = {"wall": "#d62728", "inlet": "#1f77b4", "outlet": "#2ca02c", "axis": "#9467bd",
                 "farfield": "#17becf", "symmetry": "#ff7f0e"}

# The two starting meshes (template defaults) and the slow jobs for the background test.
START_MESHES = {
    "Nozzle (axisymmetric, structured)": ("nozzle_axi", {}),
    "Cylinder in free stream (Gmsh)": ("external_2d", {"shape": "Circular cylinder"}),
}
FINE_JOBS = {
    "Nozzle - structured Fine preset": ("nozzle_axi", {"mesh_preset": "Fine"}),
    "Cylinder - very fine Gmsh (slow: try Cancel)": (
        "external_2d", {"shape": "Circular cylinder", "surface_size": 0.0008, "farfield_size": 0.5}),
}


def build_mesh_now(case_name, params):
    """Build a mesh in this process (used only for the small starting meshes)."""
    case = load_case(case_name)
    return case.build_mesh(validate(case.parameters(), {**defaults(case.parameters()), **params}))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AeroFlowSim - Qt + PyVista spike")
        self.setWindowIcon(QIcon(str(ICON)))
        self.resize(1400, 850)
        self.dark = False
        self.meshes = {name: build_mesh_now(*job) for name, job in START_MESHES.items()}
        self.mesh = None
        self.press_pos = None
        self.process = None
        self.queue = None
        self.job_started = 0.0

        # Central VTK view (a Qt widget that holds a VTK render window).
        self.view = QtInteractor(self)
        self.setCentralWidget(self.view.interactor)
        self.view.iren.add_observer("LeftButtonPressEvent", self.on_press)
        self.view.iren.add_observer("LeftButtonReleaseEvent", self.on_release)

        self.build_actions()
        self.build_docks()
        self.build_status_bar()
        self.timer = QTimer(self)            # polls the background job; never blocks the window
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll_job)
        self.show_mesh(next(iter(self.meshes)))

    # ---- menus, toolbar, docks ------------------------------------------------------------------

    def build_actions(self):
        menu = self.menuBar()
        file_menu, view_menu = menu.addMenu("&File"), menu.addMenu("&View")
        tools_menu, help_menu = menu.addMenu("&Tools"), menu.addMenu("&Help")
        toolbar = self.addToolBar("Main")

        quit_action = QAction("&Quit", self, shortcut="Ctrl+Q", triggered=self.close)
        file_menu.addAction(quit_action)

        self.edges_action = QAction("Show &edges", self, checkable=True, checked=True, shortcut="E",
                                    triggered=lambda: self.show_mesh(self.mesh_name))
        self.dark_action = QAction("&Dark theme", self, checkable=True, shortcut="Ctrl+T",
                                   triggered=self.toggle_theme)
        reset_action = QAction("&Reset camera", self, shortcut="R", triggered=self.reset_camera)
        view_menu.addActions([self.edges_action, self.dark_action, reset_action])

        # Pick mode: exclusive choice between edges (boundary patches) and cells.
        self.pick_group = QActionGroup(self)
        self.pick_edge = QAction("Pick &edge", self, checkable=True, checked=True, shortcut="Ctrl+1")
        self.pick_cell = QAction("Pick &cell", self, checkable=True, shortcut="Ctrl+2")
        for a in (self.pick_edge, self.pick_cell):
            self.pick_group.addAction(a)
        generate_action = QAction("&Generate fine mesh", self, shortcut="Ctrl+G", triggered=self.start_job)
        tools_menu.addActions([self.pick_edge, self.pick_cell, generate_action])
        help_menu.addAction(QAction("&About", self, triggered=lambda: QMessageBox.about(
            self, "About", "AeroFlowSim Qt spike\nPySide6 + PyVista/VTK\nGPL-3.0-or-later")))

        toolbar.addActions([self.pick_edge, self.pick_cell])
        toolbar.addSeparator()
        toolbar.addActions([self.edges_action, reset_action, self.dark_action])
        toolbar.addSeparator()
        toolbar.addAction(generate_action)

    def build_docks(self):
        # Left: inputs.
        inputs = QWidget()
        form = QFormLayout(inputs)
        self.mesh_box = QComboBox()
        self.mesh_box.addItems(list(self.meshes))
        self.mesh_box.currentTextChanged.connect(self.show_mesh)
        self.colour_box = QComboBox()
        self.colour_box.addItems(COLOUR_FIELDS)
        self.colour_box.currentTextChanged.connect(lambda _: self.show_mesh(self.mesh_name))
        self.job_box = QComboBox()
        self.job_box.addItems(list(FINE_JOBS))
        self.point_label = QLabel("-")
        self.box_label = QLabel("-")
        self.box_label.setWordWrap(True)
        form.addRow("Mesh", self.mesh_box)
        form.addRow("Colour cells by", self.colour_box)
        form.addRow("Background job", self.job_box)
        form.addRow(QLabel("<b>Drag the white sphere and the box in the view:</b>"))
        form.addRow("Point handle [mm]", self.point_label)
        form.addRow("Refinement box [mm]", self.box_label)
        dock = QDockWidget("Inputs", self)
        dock.setWidget(inputs)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

        # Right: what was clicked.
        self.info = QTextEdit(readOnly=True)
        self.info.setHtml("Click a boundary edge (Pick edge) or a cell (Pick cell).")
        dock = QDockWidget("Selection info", self)
        dock.setWidget(self.info)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def build_status_bar(self):
        self.status_label = QLabel("Ready")
        self.progress = QProgressBar(maximumWidth=200, visible=False)
        self.cancel_button = QPushButton("Cancel", visible=False, clicked=self.cancel_job)
        bar = self.statusBar()
        bar.addWidget(self.status_label, 1)
        bar.addPermanentWidget(self.progress)
        bar.addPermanentWidget(self.cancel_button)

    # ---- drawing the mesh -----------------------------------------------------------------------

    def show_mesh(self, name):
        """(Re)draw the chosen mesh, its boundary patches and the two drag widgets."""
        self.mesh_name = name
        self.mesh = self.meshes[name]
        self.grid = mesh_to_grid(self.mesh)
        self.lines = patch_lines(self.mesh)
        fg = "white" if self.dark else "black"
        p = self.view
        p.clear()
        p.clear_box_widgets()
        p.clear_sphere_widgets()
        p.set_background("#202124" if self.dark else "white")
        field = self.colour_box.currentText() if hasattr(self, "colour_box") else COLOUR_FIELDS[0]
        self.mesh_actor = p.add_mesh(self.grid, scalars=field, cmap="viridis",
                                     show_edges=self.edges_action.isChecked(),
                                     edge_color="#555555" if self.dark else "#333333", line_width=0.5,
                                     scalar_bar_args={"title": field, "color": fg, "vertical": False,
                                                      "position_x": 0.25, "position_y": 0.03,
                                                      "width": 0.5, "height": 0.08})
        # Each patch gets its own colour; all patch lines are one actor so one picker finds them.
        colours = np.array([pv.Color(PATCH_COLOURS.get(pt.type, "gray")).int_rgb
                            for pt in self.mesh.patches], dtype=np.uint8)
        self.lines.cell_data["rgb"] = colours[self.lines.cell_data["patch"]]
        self.lines_actor = p.add_mesh(self.lines, scalars="rgb", rgb=True, line_width=4,
                                      render_lines_as_tubes=False)
        legend = [[f"{pt.name} ({pt.type})", PATCH_COLOURS.get(pt.type, "gray")] for pt in self.mesh.patches]
        p.add_legend(legend, bcolor=None, face="line", size=(0.18, 0.18), loc="upper right")
        p.add_text(f"{self.mesh.n_cells:,} cells", font_size=9, color=fg, position="upper_left")
        if hasattr(self, "info"):
            self.info.setHtml("Click a boundary edge (Pick edge) or a cell (Pick cell).")
        self.highlight = None
        self.add_widgets()
        p.enable_parallel_projection()
        p.enable_2d_style()             # 2D: left button pans, wheel zooms (3D later: rotate)
        p.view_xy()

    def add_widgets(self):
        """A point handle (sphere) and a refinement box, both draggable, with live coordinates."""
        xmin, xmax, ymin, ymax, _, _ = self.grid.bounds
        size = max(xmax - xmin, ymax - ymin)
        centre = ((xmin + xmax) / 2, (ymin + ymax) / 2, 0.0)
        self.view.add_sphere_widget(self.on_point_moved, center=centre, radius=0.02 * size,
                                    color="white", interaction_event="always")
        dx, dy = 0.15 * (xmax - xmin), 0.25 * (ymax - ymin)
        self.view.add_box_widget(self.on_box_moved, bounds=(centre[0] - dx, centre[0] + dx,
                                 centre[1] - dy, centre[1] + dy, -0.02 * size, 0.02 * size),
                                 rotation_enabled=False, interaction_event="always", color="orange")
        self.on_point_moved(centre)

    def on_point_moved(self, centre):
        self.point_label.setText(f"x = {centre[0] * 1e3:.4g}, y = {centre[1] * 1e3:.4g}")

    def on_box_moved(self, box):
        b = np.array(box.bounds) * 1e3
        self.box_label.setText(f"x {b[0]:.4g} … {b[1]:.4g}\ny {b[2]:.4g} … {b[3]:.4g}")

    def reset_camera(self):
        self.view.view_xy()
        self.view.reset_camera()

    # ---- picking --------------------------------------------------------------------------------

    def on_press(self, interactor, _event):
        self.press_pos = interactor.GetEventPosition()

    def on_release(self, interactor, _event):
        """A click is a press + release that hardly moved (otherwise it was a pan)."""
        x, y = interactor.GetEventPosition()
        if self.press_pos is None or abs(x - self.press_pos[0]) + abs(y - self.press_pos[1]) > 4:
            return
        if self.pick_edge.isChecked():
            line_id = self.nearest_edge(x, y)
            if line_id is not None:
                self.show_edge(line_id)
            return
        picker = vtkCellPicker()            # cells: VTK's picker is exact (point-in-cell test)
        picker.PickFromListOn()
        picker.AddPickList(self.mesh_actor)
        if picker.Pick(x, y, 0, self.view.renderer) and picker.GetCellId() >= 0:
            self.show_cell(picker.GetCellId())

    def world_point(self, x, y):
        """The point on the z = 0 plane under the screen pixel (x, y) [m] (parallel 2D view)."""
        c = vtkCoordinate()
        c.SetCoordinateSystemToDisplay()
        c.SetValue(x, y, 0.0)
        return np.array(c.GetComputedWorldValue(self.view.renderer))[:2]

    def nearest_edge(self, x, y, max_pixels=8):
        """Boundary edge closest to the click (exact distance to each segment), or None if too far.

        VTK's line picker takes the first line inside its tolerance, which can be a neighbour
        when edges are only a pixel or two long, so we measure the distance ourselves.
        """
        p = self.world_point(x, y)
        ends = self.lines.points[self.lines.lines.reshape(-1, 3)[:, 1:], :2]   # (n, 2 ends, xy)
        a, b = ends[:, 0], ends[:, 1]
        ab = b - a
        t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-300), 0.0, 1.0)
        dist = np.linalg.norm(a + t[:, None] * ab - p, axis=1)
        best = int(dist.argmin())
        metres_per_pixel = np.linalg.norm(self.world_point(x + 1, y) - p)
        return best if dist[best] <= max_pixels * metres_per_pixel else None

    def set_highlight(self, dataset, colour, width):
        if self.highlight is not None:
            self.view.remove_actor(self.highlight)
        self.highlight = self.view.add_mesh(dataset, color=colour, line_width=width, style="wireframe",
                                            reset_camera=False)
        self.view.render()

    def show_edge(self, line_id):
        k = int(self.lines.cell_data["patch"][line_id])
        patch = self.mesh.patches[k]
        face = patch.start + (line_id - int(np.flatnonzero(self.lines.cell_data["patch"] == k)[0]))
        self.set_highlight(self.lines.extract_cells(np.flatnonzero(self.lines.cell_data["patch"] == k)),
                           "yellow", 7)
        length = self.mesh.face_areas[face]          # 2D: edge length x 1 m depth [m²] -> length [m]
        self.info.setHtml(f"<h3>Boundary patch: {patch.name}</h3>type <b>{patch.type}</b><br>"
                          f"{patch.count} faces<br><br>clicked face #{face}<br>"
                          f"edge length {length * 1e3:.4g} mm")

    def show_cell(self, cell):
        self.set_highlight(self.grid.extract_cells([cell]), "magenta", 4)
        d = self.grid.cell_data
        c = self.mesh.cell_centres[cell] * 1e3
        self.info.setHtml(
            f"<h3>Cell #{cell}</h3>type {CELL_TYPES[int(self.mesh.cell_types[cell])].name}<br>"
            f"centre ({c[0]:.4g}, {c[1]:.4g}) mm<br>volume {d['cell_volume'][cell]:.4g} m³ (per m depth)<br>"
            f"aspect ratio {d['aspect_ratio'][cell]:.4g}<br>"
            f"non-orthogonality {d['non_orthogonality'][cell]:.3g}°")

    # ---- theme ----------------------------------------------------------------------------------

    def toggle_theme(self, dark):
        self.dark = dark
        QApplication.instance().styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
        self.show_mesh(self.mesh_name)

    # ---- background job (separate process) ------------------------------------------------------

    def start_job(self):
        if self.process is not None:
            return
        case_name, params = FINE_JOBS[self.job_box.currentText()]
        out = Path(tempfile.gettempdir()) / "aeroflowsim_poc" / f"{case_name}_fine.npz"
        out.parent.mkdir(exist_ok=True)
        ctx = multiprocessing.get_context("spawn")
        self.queue = ctx.Queue()
        self.process = ctx.Process(target=mesh_worker.build, args=(case_name, params, out, self.queue),
                                   daemon=True)
        self.process.start()
        self.job_started = time.perf_counter()
        self.progress.setRange(0, 0)       # "busy" bar: Gmsh gives no percentage
        self.progress.setVisible(True)
        self.cancel_button.setVisible(True)
        self.status_label.setText("Starting background process ...")
        self.timer.start()

    def poll_job(self):
        elapsed = time.perf_counter() - self.job_started
        try:
            while True:
                message = self.queue.get_nowait()
                if message[0] == "stage":
                    self.stage = message[1]
                elif message[0] == "done":
                    self.finish_job(f"Done in {elapsed:.1f} s: {message[2]:,} cells")
                    name = f"Fine: {self.job_box.currentText()}"
                    self.meshes[name] = Mesh.load(message[1])
                    self.mesh_box.addItem(name)
                    self.mesh_box.setCurrentText(name)
                    return
                elif message[0] == "error":
                    self.finish_job("Failed")
                    QMessageBox.warning(self, "Mesh failed", message[1])
                    return
        except queue_module.Empty:
            pass
        if self.process is not None and not self.process.is_alive():
            self.finish_job("Background process ended unexpectedly")
            return
        self.status_label.setText(f"{getattr(self, 'stage', '...')}  -  {elapsed:.1f} s (window stays responsive)")

    def cancel_job(self):
        if self.process is not None:
            self.process.terminate()        # stops Gmsh immediately, even mid-meshing
            self.process.join(2)
            self.finish_job(f"Cancelled after {time.perf_counter() - self.job_started:.1f} s")

    def finish_job(self, text):
        self.timer.stop()
        self.process = None
        self.queue = None
        self.stage = "..."
        self.progress.setVisible(False)
        self.cancel_button.setVisible(False)
        self.status_label.setText(text)

    def closeEvent(self, event):
        self.cancel_job()
        self.view.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(ICON)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":     # required: the "spawn" child process re-imports this file
    sys.exit(main())

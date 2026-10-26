# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The VTK view: meshes and geometry in the window, with picking (PyVista + pyvistaqt).

VTK is the visualisation library behind ParaView; PyVista makes it pleasant to use from Python
and pyvistaqt puts a VTK render window inside a Qt widget (QtInteractor). This view shows
  - a face-based Mesh: cells (optionally coloured by a per-cell field), cell edges, boundary
    patches as coloured lines with a legend;
  - a geometry preview: the named boundary curves of aeroflowsim/geometry_preview.py.
Mouse: left drag pans, wheel zooms (2D style; 3D rotation comes with 3D meshes). A click (press
and release without moving) picks a cell, or the boundary edge nearest to the cursor; the view
then emits cell_picked(cell) or edge_picked(patch index, face index). A right click (without dragging)
opens a menu: zoom to fit, reset view, save picture (subclasses add their own entries).

Our Mesh already stores VTK cell types and VTK node order, so mesh_to_grid only re-packs arrays.
"""

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QMenu, QToolButton, QVBoxLayout, QWidget
from vtkmodules.vtkRenderingCore import vtkCellPicker, vtkCoordinate

from aeroflowsim.gui.theme import PATCH_COLOURS, view_colours

CLICK_PIXELS = 4      # a press + release closer than this is a click, not a pan [px]
EDGE_PICK_PIXELS = 8  # the nearest boundary edge must be closer than this to be picked [px]


def mesh_to_grid(mesh) -> pv.UnstructuredGrid:
    """The cells of a face-based Mesh as a PyVista grid."""
    counts = (mesh.cell_nodes >= 0).sum(axis=1)
    table = np.column_stack([counts, mesh.cell_nodes])          # [n, node0, ..., -1 padding] per cell
    keep = np.column_stack([np.ones(len(counts), bool), mesh.cell_nodes >= 0])
    cells = table[keep].astype(np.int64)                         # row by row, padding dropped
    return pv.UnstructuredGrid(cells, mesh.cell_types.astype(np.uint8), mesh.nodes)


def patch_lines(mesh) -> pv.PolyData:
    """Boundary faces (edges in 2D) as lines; cell data 'patch' = index into mesh.patches, 'face' = face number."""
    faces = np.concatenate([p.faces for p in mesh.patches])
    patch = np.concatenate([np.full(p.count, k) for k, p in enumerate(mesh.patches)])
    nodes = mesh.face_nodes[faces, :2]                      # 2D: every boundary face is an edge
    lines = np.column_stack([np.full(len(faces), 2), nodes]).ravel()
    poly = pv.PolyData(mesh.nodes, lines=lines)
    poly.cell_data["patch"] = patch.astype(np.int32)
    poly.cell_data["face"] = faces.astype(np.int64)
    return poly


def _polyline(points) -> pv.PolyData:
    pts = np.column_stack([points, np.zeros(len(points))])
    return pv.lines_from_points(pts)


class MeshView(QWidget):
    cell_picked = Signal(int)
    edge_picked = Signal(int, int)       # patch index, face index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dark = False
        self.pick_mode = "cell"          # "cell" or "edge"
        self.mesh = self.grid = self.lines = None
        self.mesh_actor = self.highlight = None
        self.body_bounds = None          # (xmin, xmax, ymin, ymax) of a body, for "Zoom to body"
        self._press = None

        self.plotter = QtInteractor(self)
        self.plotter.iren.add_observer("LeftButtonPressEvent", self._on_press)
        self.plotter.iren.add_observer("LeftButtonReleaseEvent", self._on_release)
        self.plotter.iren.add_observer("RightButtonPressEvent", self._on_right_press)
        self.plotter.iren.add_observer("RightButtonReleaseEvent", self._on_right_release)
        self._right = None
        bar = QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 2)
        self.fit_button = QToolButton(text="Fit", toolTip="Show everything (F)", autoRaise=True)
        self.fit_button.clicked.connect(self.fit)
        self.body_button = QToolButton(text="Zoom to body", toolTip="Zoom in on the body (B)", autoRaise=True)
        self.body_button.clicked.connect(self.zoom_to_body)
        self.body_button.setVisible(False)
        bar.addWidget(self.fit_button)
        bar.addWidget(self.body_button)
        bar.addStretch(1)
        self.toolbar = bar
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(bar)
        layout.addWidget(self.plotter.interactor, 1)
        self.clear()

    # ---- drawing ---------------------------------------------------------------------------

    @property
    def closed(self) -> bool:
        return bool(getattr(self.plotter, "_closed", False))

    def clear(self, message=""):
        if self.closed:
            return
        p = self.plotter
        p.clear()
        colours = view_colours(self.dark)
        p.set_background(colours["background"])
        if message:
            p.add_text(message, position="upper_left", font_size=10, color=colours["text"])
        self.mesh = self.grid = self.lines = self.mesh_actor = self.highlight = None
        self.body_bounds = None
        self.bar_room = False
        self.body_button.setVisible(False)
        p.render()

    def _legend(self, entries):
        if entries:
            self.plotter.add_legend([[name, PATCH_COLOURS.get(kind, "gray")] for name, kind in entries],
                                    bcolor=None, face="line", size=(0.12, 0.035 * len(entries)),
                                    loc="upper right", font_family="arial")

    def show_mesh(self, mesh, values=None, title="", edges=True, body_bounds=None, cmap="viridis", clim=None,
                  keep_camera=False):
        """Draw a face-based Mesh; values: one number per cell to colour by (None = plain).

        cmap: colour map name; clim: (min, max) of the colour range (None = the values' own range);
        keep_camera: True keeps the current zoom (e.g. when only the field or colour map changed)."""
        camera = self.plotter.camera_position if keep_camera and self.mesh is not None else None
        if self.closed:
            return
        self.clear()
        colours = view_colours(self.dark)
        p = self.plotter
        self.mesh, self.grid, self.lines = mesh, mesh_to_grid(mesh), patch_lines(mesh)
        self.bar_room = values is not None      # leave room under the drawing for the colour bar
        style = dict(show_edges=edges, edge_color=colours["edges"], line_width=0.5)
        if values is not None:
            self.grid.cell_data[title or "value"] = np.asarray(values, dtype=float)
            self.mesh_actor = p.add_mesh(self.grid, scalars=title or "value", cmap=cmap, nan_color="gray", clim=clim,
                                         scalar_bar_args={"title": title, "color": colours["text"],
                                                          "vertical": False, "position_x": 0.25,
                                                          "position_y": 0.05, "width": 0.5, "height": 0.05,
                                                          "n_labels": 3, "fmt": "%.3g",    # no overlapping labels
                                                          "title_font_size": 12, "label_font_size": 11},
                                         **style)
        else:
            self.mesh_actor = p.add_mesh(self.grid, color="#c7d7ea" if not self.dark else "#3b4a5c", **style)
        rgb = np.array([pv.Color(PATCH_COLOURS.get(pt.type, "gray")).int_rgb for pt in mesh.patches], dtype=np.uint8)
        self.lines.cell_data["rgb"] = rgb[self.lines.cell_data["patch"]]
        p.add_mesh(self.lines, scalars="rgb", rgb=True, line_width=3, reset_camera=False)
        self._legend([(pt.name, pt.type) for pt in mesh.patches])
        self._set_body(body_bounds)
        if camera is not None:
            self.plotter.camera_position = camera
            self.plotter.render()
        else:
            self.fit()

    def show_curves(self, preview):
        """Draw a GeometryPreview: each named boundary curve in its patch colour."""
        if self.closed:
            return
        self.clear()
        p = self.plotter
        seen = []
        for curve in preview.curves:
            p.add_mesh(_polyline(curve.points), color=PATCH_COLOURS.get(curve.type, "gray"), line_width=3)
            if (curve.name, curve.type) not in seen:
                seen.append((curve.name, curve.type))
        self._legend(seen)
        walls = [c.points for c in preview.curves if c.type == "wall"]
        bounds = None
        if walls and any(c.type == "farfield" for c in preview.curves):
            pts = np.vstack(walls)
            bounds = (pts[:, 0].min(), pts[:, 0].max(), pts[:, 1].min(), pts[:, 1].max())
        self._set_body(bounds)
        self.fit()

    def _set_body(self, bounds):
        self.body_bounds = bounds
        self.body_button.setVisible(bounds is not None)

    def set_edges(self, visible):
        if self.mesh_actor is not None:
            self.mesh_actor.prop.show_edges = visible
            self.plotter.render()

    def set_dark(self, dark):
        self.dark = dark
        if self.closed:
            return
        self.plotter.set_background(view_colours(dark)["background"])
        self.plotter.render()

    # ---- camera ----------------------------------------------------------------------------

    def _show_box(self, xmin, xmax, ymin, ymax, margin=1.08):
        """Look at the box from +z with a parallel projection, fitting both its width and height."""
        p = self.plotter
        p.enable_parallel_projection()
        p.enable_2d_style()
        cx, cy = 0.5 * (xmin + xmax), 0.5 * (ymin + ymax)
        width, height = max(xmax - xmin, 1e-12), max(ymax - ymin, 1e-12)
        w, h = max(self.plotter.interactor.width(), 1), max(self.plotter.interactor.height(), 1)
        cam = p.camera
        distance = 10.0 * max(width, height)
        cam.focal_point = (cx, cy, 0.0)
        cam.position = (cx, cy, distance)
        cam.up = (0.0, 1.0, 0.0)
        cam.parallel_scale = 0.5 * margin * max(height, width * h / w)   # half the visible height [m]
        p.renderer.ResetCameraClippingRange()
        p.render()

    def fit(self):
        if self.closed:
            return
        b = self.plotter.renderer.ComputeVisiblePropBounds()
        if b[0] > b[1]:                       # nothing drawn
            return
        ymin = b[2]
        if getattr(self, "bar_room", False):  # the horizontal colour bar sits in the bottom fifth of the view
            ymin -= 0.3 * max(b[3] - b[2], 0.25 * (b[1] - b[0]))
        self._show_box(b[0], b[1], ymin, b[3])

    def zoom_to_body(self):
        if self.body_bounds is not None:
            xmin, xmax, ymin, ymax = self.body_bounds
            size = max(xmax - xmin, ymax - ymin)
            self._show_box(xmin - 0.6 * size, xmax + 0.6 * size, ymin - 0.6 * size, ymax + 0.6 * size, margin=1.0)

    # ---- picking ---------------------------------------------------------------------------

    def _on_press(self, interactor, _event):
        self._press = interactor.GetEventPosition()

    def _on_release(self, interactor, _event):
        x, y = interactor.GetEventPosition()
        if self._press is None or self.mesh is None:
            return
        if abs(x - self._press[0]) + abs(y - self._press[1]) > CLICK_PIXELS:
            return                            # it was a pan
        self.pick(x, y)

    def _on_right_press(self, interactor, _event):
        self._right = interactor.GetEventPosition()

    def _on_right_release(self, interactor, _event):
        x, y = interactor.GetEventPosition()
        if self._right is None or abs(x - self._right[0]) + abs(y - self._right[1]) > CLICK_PIXELS:
            return                            # it was a right-drag zoom
        self._right = None
        menu = QMenu(self)
        self.context_actions(menu, self.world_point(x, y))
        self.last_menu = menu                 # kept for tests
        menu.popup(QCursor.pos())

    def context_actions(self, menu, xy):
        """The entries of the right-click menu (world point xy); subclasses add their own first."""
        menu.addAction("Zoom to fit", self.fit)
        if self.body_bounds is not None:
            menu.addAction("Zoom to body", self.zoom_to_body)
        menu.addAction("Reset view", self.reset_view)
        menu.addAction("Save picture...", self.ask_save_picture)

    def reset_view(self):
        """Back to the 2D view from +z with everything visible (after rotating a 3D view)."""
        self.plotter.enable_parallel_projection()
        self.plotter.enable_2d_style()
        self.fit()

    def ask_save_picture(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save picture", "picture.png", "PNG pictures (*.png)")
        if path:
            self.save_picture(path)

    def pick(self, x, y):
        """Pick at screen pixel (x, y) (VTK display coordinates: origin bottom left)."""
        if self.pick_mode == "edge":
            line = self.nearest_edge(x, y)
            if line is not None:
                patch, face = int(self.lines.cell_data["patch"][line]), int(self.lines.cell_data["face"][line])
                self._highlight(self.lines.extract_cells([line]), "yellow", 6)
                self.edge_picked.emit(patch, face)
            return
        if self.mesh.dim == 2:
            # 2D: the cell that contains the clicked point (exact). VTK's cell picker accepts any cell
            # within a tolerance of the ray and can return a neighbour when cells are only a few pixels.
            x_w, y_w = self.world_point(x, y)
            cell = int(self.grid.find_containing_cell([x_w, y_w, 0.0]))
        else:
            picker = vtkCellPicker()
            picker.SetTolerance(0.0005)
            picker.PickFromListOn()
            picker.AddPickList(self.mesh_actor)
            cell = picker.GetCellId() if picker.Pick(x, y, 0, self.plotter.renderer) else -1
        if cell >= 0:
            self._highlight(self.grid.extract_cells([cell]), "magenta", 4)
            self.cell_picked.emit(cell)

    def world_point(self, x, y):
        c = vtkCoordinate()
        c.SetCoordinateSystemToDisplay()
        c.SetValue(x, y, 0.0)
        return np.array(c.GetComputedWorldValue(self.plotter.renderer))[:2]

    def display_point(self, xy):
        """Screen pixel of a world point (used by tests to click on a known spot)."""
        c = vtkCoordinate()
        c.SetCoordinateSystemToWorld()
        c.SetValue(float(xy[0]), float(xy[1]), 0.0)
        return c.GetComputedDisplayValue(self.plotter.renderer)

    def nearest_edge(self, x, y):
        """Boundary edge closest to the pixel (exact distance to each segment), or None if too far.

        VTK's own line picker takes the first line inside its tolerance, which can be a neighbour
        when edges are only a pixel or two long (found in the spike), so the distance is measured here.
        """
        p = self.world_point(x, y)
        ends = self.lines.points[self.lines.lines.reshape(-1, 3)[:, 1:], :2]
        a, b = ends[:, 0], ends[:, 1]
        ab = b - a
        t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-300), 0.0, 1.0)
        dist = np.linalg.norm(a + t[:, None] * ab - p, axis=1)
        best = int(dist.argmin())
        metres_per_pixel = np.linalg.norm(self.world_point(x + 1, y) - p)
        return best if dist[best] <= EDGE_PICK_PIXELS * metres_per_pixel else None

    def _highlight(self, dataset, colour, width):
        if self.highlight is not None:
            self.plotter.remove_actor(self.highlight)
        self.highlight = self.plotter.add_mesh(dataset, color=colour, line_width=width, style="wireframe",
                                               reset_camera=False)
        self.plotter.render()

    def save_picture(self, path):
        self.plotter.screenshot(str(path))

    def close_view(self):
        self.plotter.close()

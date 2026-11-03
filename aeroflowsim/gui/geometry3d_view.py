# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The 3D geometry view: the faces of a BuiltGeometry3D in a VTK window, with picking (PyVista + pyvistaqt).

What it shows: every visible face filled in the colour of its boundary type (gui/theme.py PATCH_COLOURS; unnamed
faces grey, solid bodies' faces lighter), its edges as thin lines, the selection in the accent colour, refinement
regions as wireframes, an axes triad. A section plane cuts the drawing (the part on its - side is hidden) so inner
faces, e.g. a body inside its enclosure, can be seen and clicked.

Mouse (the usual 3D CAD conventions):
    left drag        rotate (trackball);  middle drag / Shift + left drag  pan;  wheel  zoom
    left click       pick the face under the cursor (Shift / Ctrl adds or removes);  empty space clears
    Box mode         left drag draws a rectangle: left to right takes the faces fully inside, right to left the
                     faces it touches (as in SpaceClaim and most CAD programs)
    right click      menu (name, hide, isolate, show all, section, views); right drag zooms
The decisions (what a click or a box selects, hide / isolate, the section plane) are in gui/geometry_logic.py.
"""

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QRubberBand, QToolButton, QVBoxLayout, QWidget
from vtkmodules.vtkRenderingCore import vtkCellPicker

from aeroflowsim.gui import geometry_logic as logic
from aeroflowsim.gui.icons import icon
from aeroflowsim.gui.theme import PATCH_COLOURS, view_colours

CLICK_PIXELS = 4        # a press + release closer than this is a click, not a drag [px]
UNNAMED_COLOUR = "#9aa0a6"
SOLID_COLOUR = "#c8ccd2"
SELECTED_COLOUR = "#ffc400"     # selected faces (amber: visible on every patch colour, light and dark)
VIEWS = {"+x": ((1, 0, 0), (0, 0, 1)), "-x": ((-1, 0, 0), (0, 0, 1)), "+y": ((0, 1, 0), (0, 0, 1)),
         "-y": ((0, -1, 0), (0, 0, 1)), "+z": ((0, 0, 1), (0, 1, 0)), "-z": ((0, 0, -1), (0, 1, 0)),
         "iso": ((1, -1, 0.8), (0, 0, 1))}      # view direction (from the camera to the object, reversed) and up


class Geometry3DView(QWidget):
    picked = Signal(str, str, bool)          # kind ("face" or "" for empty space), id, add (Shift / Ctrl)
    box_selected = Signal(list, bool)        # face ids inside the box, add
    context_menu = Signal(str, str, QPoint)  # kind, id ("" for empty space), global position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dark = False
        self.built = None
        self.face_ids = []                    # face id of every cell of the drawn surface (cell data "face")
        self.surface = self.surface_actor = None
        self.mode = "select"                  # "select" or "box"
        self._press = self._right = None
        self._band, self._band_start = QRubberBand(QRubberBand.Rectangle, self), None

        self.plotter = QtInteractor(self)
        self.plotter.enable_trackball_style()
        self.plotter.iren.add_observer("LeftButtonPressEvent", self._on_press)
        self.plotter.iren.add_observer("LeftButtonReleaseEvent", self._on_release)
        self.plotter.iren.add_observer("RightButtonPressEvent", self._on_right_press)
        self.plotter.iren.add_observer("RightButtonReleaseEvent", self._on_right_release)
        self.plotter.interactor.installEventFilter(self)

        bar = QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 2)
        self.view_buttons = {}
        for name, tip in (("iso", "Isometric view"), ("+x", "Look along -x (from +x)"), ("+y", "Look from +y"),
                          ("+z", "Look from +z (top)"), ("-x", "Look from -x (upstream)")):
            button = QToolButton(text=name, toolTip=tip, autoRaise=True)
            button.clicked.connect(lambda _=False, n=name: self.set_view(n))
            bar.addWidget(button)
            self.view_buttons[name] = button
        self.fit_button = QToolButton(toolTip="Show everything (F)", autoRaise=True)
        self.fit_button.clicked.connect(self.fit)
        bar.addWidget(self.fit_button)
        bar.addStretch(1)
        self.status = QLabel("", objectName="hint")
        bar.addWidget(self.status)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(bar)
        layout.addWidget(self.plotter.interactor, 1)
        self.update_icons()
        self.clear()

    # ---- drawing ---------------------------------------------------------------------------

    @property
    def closed(self) -> bool:
        return bool(getattr(self.plotter, "_closed", False))

    def update_icons(self):
        self.fit_button.setIcon(icon("fit"))
        self.fit_button.setIconSize(QSize(18, 18))

    def clear(self, message=""):
        if self.closed:
            return
        p = self.plotter
        p.clear()
        colours = view_colours(self.dark)
        p.set_background(colours["background"])
        if message:
            p.add_text(message, position="upper_left", font_size=10, color=colours["text"])
        self.built, self.surface, self.surface_actor, self.face_ids = None, None, None, []
        p.render()

    def face_colour(self, built, face) -> str:
        b = built.names.get(face.id)
        if b is not None:
            return PATCH_COLOURS.get(b.type, UNNAMED_COLOUR)
        solid = all(built.bodies[x].role == "solid" for x in face.bodies if x in built.bodies) and face.bodies
        return SOLID_COLOUR if solid else UNNAMED_COLOUR

    def show_geometry(self, built, selection=(), hidden=(), section=None, keep_camera=True):
        """Draw the visible faces of a BuiltGeometry3D; selection: [(kind, id)]; section: (origin, normal) or None."""
        if self.closed:
            return
        camera = self.plotter.camera_position if keep_camera and self.built is not None else None
        self.clear()
        self.built = built
        p = self.plotter
        colours = view_colours(self.dark)
        selected = set(logic.faces_of_3d(selection, built))
        accent = SELECTED_COLOUR
        points, cells, owners, rgb = [], [], [], []
        offset = 0
        hidden = set(hidden)
        self.face_ids = [f for f in built.faces if f not in hidden and built.faces[f].triangles is not None]
        for k, face_id in enumerate(self.face_ids):
            tri = built.faces[face_id].triangles.reshape(-1, 3)
            n = len(tri) // 3
            points.append(tri)
            cells.append(np.column_stack([np.full(n, 3), offset + np.arange(3 * n).reshape(n, 3)]))
            owners.append(np.full(n, k))
            colour_text = accent if face_id in selected else self.face_colour(built, built.faces[face_id])
            rgb.append(np.tile(pv.Color(colour_text).int_rgb, (n, 1)))
            offset += 3 * n
        if points:
            surface = pv.PolyData(np.vstack(points), np.vstack(cells).ravel())
            surface.cell_data["face"] = np.concatenate(owners).astype(np.int32)
            surface.cell_data["rgb"] = np.vstack(rgb).astype(np.uint8)
            surface = surface.clean(tolerance=1e-12 * built.size)
            if section is not None:
                surface = surface.clip(normal=section[1], origin=section[0], invert=False)
            self.surface = surface
            if surface.n_cells:
                self.surface_actor = p.add_mesh(surface, scalars="rgb", rgb=True, smooth_shading=False,
                                                show_edges=False, pickable=True, reset_camera=False)
        lines = [e.points for e in built.edges.values() if any(f not in hidden for f in e.faces)]
        if lines:
            poly = pv.merge([pv.lines_from_points(pts) for pts in lines])
            if section is not None:
                poly = poly.clip(normal=section[1], origin=section[0], invert=False)
            if poly.n_points:
                p.add_mesh(poly, color=colours["outline"], line_width=1.5, pickable=False, reset_camera=False)
        for region in built.regions:
            outline = _region_outline(region)
            if outline is not None:
                p.add_mesh(outline, color=accent, style="wireframe", line_width=1, opacity=0.6, pickable=False,
                           reset_camera=False)
        p.add_axes(color=colours["text"], line_width=2)
        legend = sorted({(b.name, b.type) for f, b in built.names.items() if f in built.faces and f not in hidden})
        if legend:
            p.add_legend([[name, PATCH_COLOURS.get(kind, UNNAMED_COLOUR)] for name, kind in legend], bcolor=None,
                         face="rectangle", size=(0.14, 0.035 * len(legend)), loc="upper right", font_family="arial")
        self.status.setText(f"{len(built.bodies)} bodies, {len(built.faces)} faces"
                            + (f", {len(hidden & set(built.faces))} hidden" if hidden & set(built.faces) else "")
                            + (", section on" if section is not None else ""))
        if camera is not None:
            p.camera_position = camera
            p.render()
        else:
            self.set_view("iso")

    def set_dark(self, dark):
        self.dark = dark
        if not self.closed:
            self.plotter.set_background(view_colours(dark)["background"])
            self.plotter.render()

    # ---- camera ----------------------------------------------------------------------------

    def set_view(self, name):
        """Look at everything from a standard direction ("iso", "+x", "-x", "+y", "-y", "+z", "-z")."""
        if self.closed:
            return
        direction, up = VIEWS[name]
        p = self.plotter
        p.disable_parallel_projection()
        b = p.renderer.ComputeVisiblePropBounds()
        if b[0] > b[1]:
            return
        centre = np.array([0.5 * (b[0] + b[1]), 0.5 * (b[2] + b[3]), 0.5 * (b[4] + b[5])])
        size = max(b[1] - b[0], b[3] - b[2], b[5] - b[4], 1e-12)
        d = np.asarray(direction, dtype=float)
        p.camera.focal_point = centre
        p.camera.position = centre + 2.5 * size * d / np.linalg.norm(d)
        p.camera.up = up
        p.reset_camera()
        p.render()

    def fit(self):
        if not self.closed:
            self.plotter.reset_camera()
            self.plotter.render()

    # ---- picking ---------------------------------------------------------------------------

    def face_at(self, x, y):
        """The face id under the VTK display pixel (x, y), or None."""
        if self.surface_actor is None:
            return None
        picker = vtkCellPicker()
        picker.SetTolerance(0.0005)
        picker.PickFromListOn()
        picker.AddPickList(self.surface_actor)
        if not picker.Pick(x, y, 0, self.plotter.renderer):
            return None
        cell = picker.GetCellId()
        if cell < 0:
            return None
        return self.face_ids[int(self.surface.cell_data["face"][cell])]

    def _modifiers(self, interactor) -> bool:
        return bool(interactor.GetShiftKey() or interactor.GetControlKey())

    def _on_press(self, interactor, _event):
        self._press = interactor.GetEventPosition()

    def _on_release(self, interactor, _event):
        if self._press is None or self.mode != "select":
            return
        x, y = interactor.GetEventPosition()
        if abs(x - self._press[0]) + abs(y - self._press[1]) > CLICK_PIXELS:
            return                                # it was a rotation
        self.pick_at(x, y, self._modifiers(interactor))

    def pick_at(self, x, y, add=False):
        """A click at VTK display pixel (x, y) (origin bottom left): emits picked."""
        face = self.face_at(x, y)
        self.picked.emit("face" if face else "", face or "", bool(add))

    def _on_right_press(self, interactor, _event):
        self._right = interactor.GetEventPosition()

    def _on_right_release(self, interactor, _event):
        x, y = interactor.GetEventPosition()
        if self._right is None or abs(x - self._right[0]) + abs(y - self._right[1]) > CLICK_PIXELS:
            return                                # it was a right-drag zoom
        self._right = None
        face = self.face_at(x, y)
        from PySide6.QtGui import QCursor
        self.context_menu.emit("face" if face else "", face or "", QCursor.pos())

    # ---- box selection (Qt events, before VTK sees them, only in Box mode) -----------------------

    def set_mode(self, mode):
        self.mode = mode
        self.plotter.interactor.setCursor(Qt.CrossCursor if mode == "box" else Qt.ArrowCursor)

    def eventFilter(self, obj, event):
        if self.mode != "box" or obj is not self.plotter.interactor:
            return super().eventFilter(obj, event)
        kind = event.type()
        if kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._band_start = self._local(event)
            self._band.setGeometry(QRect(self._band_start, QSize()))
            self._band.show()
            return True
        if kind == QEvent.MouseMove and self._band_start is not None:
            self._band.setGeometry(QRect(self._band_start, self._local(event)).normalized())
            return True
        if kind == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and self._band_start is not None:
            start, end = self._band_start, self._local(event)
            self._band.hide()
            self._band_start = None
            add = bool(event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier))
            self.select_box(self._vtk_pixel(start), self._vtk_pixel(end), add)
            return True
        return super().eventFilter(obj, event)

    def _local(self, event) -> QPoint:
        """The event position in this widget's coordinates (where the rubber band is drawn)."""
        return self.plotter.interactor.mapTo(self, event.position().toPoint())

    def _vtk_pixel(self, point):
        """A point of this widget as a VTK display pixel (origin bottom left, device pixels)."""
        inner = self.plotter.interactor.mapFrom(self, point)
        ratio = self.plotter.interactor.devicePixelRatioF()
        return inner.x() * ratio, (self.plotter.interactor.height() - inner.y()) * ratio

    def projected_faces(self) -> dict:
        """{face id: (n, 2) VTK display pixels of the corners of its drawn triangles} (visible faces)."""
        if self.surface is None or not self.surface.n_cells:
            return {}
        renderer = self.plotter.renderer
        width, height = renderer.GetSize()
        matrix = renderer.GetActiveCamera().GetCompositeProjectionTransformMatrix(width / max(height, 1), -1, 1)
        m = np.array([[matrix.GetElement(i, j) for j in range(4)] for i in range(4)])
        pts = np.column_stack([self.surface.points, np.ones(self.surface.n_points)]) @ m.T
        ndc = pts[:, :2] / pts[:, 3:4]
        x0, y0 = renderer.GetOrigin()
        pixels = np.column_stack([x0 + (ndc[:, 0] + 1.0) * 0.5 * width, y0 + (ndc[:, 1] + 1.0) * 0.5 * height])
        corners = self.surface.regular_faces if hasattr(self.surface, "regular_faces") else \
            self.surface.faces.reshape(-1, 4)[:, 1:]
        owner = np.asarray(self.surface.cell_data["face"])
        out = {}
        for k in np.unique(owner).tolist():
            out[self.face_ids[k]] = pixels[np.unique(corners[owner == k])]
        return out

    def select_box(self, start, end, add=False):
        """Box selection between two VTK display pixels: left-to-right = faces fully inside, right-to-left = faces
        touched (see geometry_logic.faces_in_rectangle); emits box_selected."""
        touching = end[0] < start[0]
        faces = logic.faces_in_rectangle(self.projected_faces(), (*start, *end), touching)
        self.box_selected.emit(faces, bool(add))

    def save_picture(self, path):
        self.plotter.screenshot(str(path))

    def close_view(self):
        self.plotter.close()


def _region_outline(region):
    """A refinement region as a PyVista shape (drawn as a wireframe)."""
    p = region.params
    if region.shape == "box":
        return pv.Box((p["x0"], p["x1"], p["y0"], p["y1"], p["z0"], p["z1"]))
    if region.shape == "sphere":
        return pv.Sphere(p["radius"], (p["xc"], p["yc"], p["zc"]), theta_resolution=16, phi_resolution=12)
    if region.shape == "cylinder":
        a, b = np.array([p["x0"], p["y0"], p["z0"]]), np.array([p["x1"], p["y1"], p["z1"]])
        return pv.Cylinder(0.5 * (a + b), b - a, p["radius"], float(np.linalg.norm(b - a)), resolution=24)
    return None

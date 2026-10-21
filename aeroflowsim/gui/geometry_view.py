# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The VTK view of the geometry workspace: faces, edges coloured by boundary type, points, regions,
the selection, and dragging.

It builds on MeshView (gui/vtk_view.py: camera, Fit, click-versus-pan). What it adds:
  - show_geometry(built, selection): fluid faces light blue, solid faces grey, every edge coloured
    by its boundary type (unnamed boundary edges grey and dashed-looking thin), points as dots,
    refinement regions semi-transparent orange, the selection yellow;
  - a click picks with aeroflowsim/geometry_model/picking.py (vertex, else edge, else face) within
    PICK_PIXELS of the cursor, and emits picked(kind, id, add) - add is True with Shift or Ctrl;
  - modes: "select" (left drag pans), "move" (drag the selection: emits moved(dx, dy) [m]),
    "points" (drag one of the handle points - outline points, enclosure size, region corners -:
    emits point_moved(index, x, y) [m]),
    "click" (sketching: emits clicked(x, y, tolerance) [m]). In those modes the mouse wheel still zooms.

View aids (the row above the view): a background grid that follows the zoom (spacing shown),
an xyz axes triad, the cursor position in mm, the legend of boundary names, a 2D / 3D switch
(3D: rotate freely; editing stays in 2D) and, for axisymmetric geometry, a revolve preview (the
boundaries swept 270 degrees about the x axis). Hovering shows what a click would pick; a
right-click emits context_menu(kind, id, global position) for the page's context menu.
"""

import html

import numpy as np
import pyvista as pv
from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QToolButton
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleUser

from aeroflowsim.geometry_model import FLUID, picking
from aeroflowsim.geometry_model.snapping import visible_grid
from aeroflowsim.gui.icons import icon
from aeroflowsim.gui.theme import PATCH_COLOURS, colour, view_colours
from aeroflowsim.gui.vtk_view import CLICK_PIXELS, MeshView

HOVER = "#4fc3f7"            # what a click would pick
GRID = {False: ("#e3e7ec", "#c9d0d8"), True: ("#2b2d31", "#3c4043")}   # (minor, major) grid line colours
REVOLVE_ANGLE = 270.0        # the revolve preview leaves a quarter open, to see inside [deg]
REVOLVE_STEPS = 72           # angular resolution of the revolve preview [-]

PICK_PIXELS = 8              # a click within this many pixels of an edge / point picks it [px]
SELECTED = "#fbbc04"         # selection colour (yellow, readable on both themes)
UNNAMED = "#9aa0a6"          # boundary edges without a name yet
REGION = "#ff9800"           # refinement regions
FACE_COLOURS = {False: {FLUID: "#cfe3f7", "solid": "#9aa0a6"}, True: {FLUID: "#2d4a66", "solid": "#5f6368"}}


def _lines(points_list, z=0.0) -> pv.PolyData:
    """Several polylines (each (n, 2)) as one PolyData, at height z (higher = drawn in front)."""
    pts, cells, offset = [], [], 0
    for p in points_list:
        pts.append(np.column_stack([p, np.full(len(p), z)]))
        cells += [len(p)] + list(range(offset, offset + len(p)))
        offset += len(p)
    return pv.PolyData(np.vstack(pts), lines=np.array(cells)) if pts else pv.PolyData()


def _triangles(tris, z=0.0) -> pv.PolyData:
    pts = np.column_stack([tris.reshape(-1, 2), np.full(3 * len(tris), z)])
    faces = np.column_stack([np.full(len(tris), 3), np.arange(3 * len(tris)).reshape(-1, 3)]).ravel()
    return pv.PolyData(pts, faces=faces)


def region_outline(region) -> np.ndarray:
    """The outline of a refinement region as points (n, 2) [m]."""
    p = region.params
    if region.shape == "box":
        return np.array([[p["x0"], p["y0"]], [p["x1"], p["y0"]], [p["x1"], p["y1"]], [p["x0"], p["y1"]],
                         [p["x0"], p["y0"]]])
    if region.shape == "circle":
        a = np.linspace(0.0, 2.0 * np.pi, 97)
        return np.column_stack([p["xc"] + p["radius"] * np.cos(a), p["yc"] + p["radius"] * np.sin(a)])
    start, end = np.array([p["x0"], p["y0"]]), np.array([p["x1"], p["y1"]])
    d = end - start
    n = np.array([-d[1], d[0]]) / max(np.linalg.norm(d), 1e-300) * 0.5 * p["width"]
    return np.array([start + n, end + n, end - n, start - n, start + n])


class GeometryView(MeshView):
    picked = Signal(str, str, bool)          # kind ("vertex", "edge", "face" or "" for nothing), id, add
    moved = Signal(float, float)             # drag of the selection ended: dx, dy [m]
    point_moved = Signal(int, float, float)  # a handle point was dragged to x, y [m]
    clicked = Signal(float, float, float)    # a click in "click" mode at x, y [m], with the pick tolerance [m]
    context_menu = Signal(str, str, QPoint)  # right-click: kind, id under the cursor ("" for nothing), screen position
    cursor_moved = Signal(float, float)      # the cursor's world position x, y [m]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.built = None
        self.selection = []
        self.mode = "select"
        self.handles = None                  # (n, 2) points shown as draggable handles, or None
        self._dz = 1e-3
        self._drag = None                    # what is being dragged: ("move", start xy) or ("point", index)
        self._preview = None
        self._style_2d = None
        self._hover, self._hover_actor = None, None
        self._grid_actors, self._grid_box = [], None
        self._revolve_actors = []
        self._right_press = None
        self.view3d = False
        self.plotter.iren.add_observer("MouseMoveEvent", self._on_move)
        self.plotter.iren.add_observer("MouseWheelForwardEvent", lambda *_: self._wheel(0.85))
        self.plotter.iren.add_observer("MouseWheelBackwardEvent", lambda *_: self._wheel(1.0 / 0.85))
        self.plotter.iren.add_observer("RightButtonPressEvent", self._on_right_press)
        self.plotter.iren.add_observer("RightButtonReleaseEvent", self._on_right_release)
        self.plotter.renderer.AddObserver("EndEvent", self._after_render)
        self._grid_timer = QTimer(self, singleShot=True, interval=0)
        self._grid_timer.timeout.connect(self._update_grid)
        # The row above the view: view switches, legend, cursor position and grid spacing.
        self.toggles = {}
        for key, text, tip, on in (("grid", "Grid", "Background grid (follows the zoom)", True),
                                   ("view3d", "3D", "Rotate the view freely (editing stays in 2D)", False),
                                   ("revolve", "Revolve", "Axisymmetric geometry swept about the x axis (3D)", False)):
            button = QToolButton(text=text, toolTip=tip, checkable=True, checked=on, autoRaise=True,
                                 toolButtonStyle=Qt.ToolButtonTextBesideIcon)
            button.setIconSize(QSize(16, 16))
            button.toggled.connect(lambda checked, k=key: self._toggled(k, checked))
            self.toolbar.insertWidget(self.toolbar.count() - 1, button)
            self.toggles[key] = button
        self.position_label = QLabel(objectName="hint")
        self.position_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.toolbar.addWidget(self.position_label)
        # The legend has its own line under the switches, so long boundary names never crowd them out.
        self.legend_label = QLabel(textFormat=Qt.RichText, wordWrap=True)
        self.legend_label.setContentsMargins(6, 0, 6, 2)
        self.layout().insertWidget(1, self.legend_label)
        self.plotter.add_axes(line_width=2, labels_off=False)
        self.update_icons()

    def update_icons(self):
        for key, name in (("grid", "grid"), ("view3d", "view3d"), ("revolve", "revolve")):
            self.toggles[key].setIcon(icon(name, self.dark))
        self.fit_button.setIcon(icon("fit", self.dark))

    # ---- drawing -------------------------------------------------------------------------------

    def show_geometry(self, built, selection=(), keep_camera=True):
        """Draw a BuiltGeometry with the selection highlighted (keeps the camera unless asked)."""
        if self.closed:
            return
        camera = self.plotter.camera.copy() if keep_camera and self.built is not None else None
        self.clear()
        self.built, self.selection = built, list(selection)
        self._dz = 1e-3 * (built.size if built is not None else 1.0)    # small height steps: drawing order
        if built is None or built.empty:
            self.plotter.render()
            return
        p = self.plotter
        colours = view_colours(self.dark)
        for face in built.faces.values():
            if face.triangles is not None and len(face.triangles):
                p.add_mesh(_triangles(face.triangles, -self._dz), color=FACE_COLOURS[self.dark].get(face.role, UNNAMED),
                           opacity=0.55 if face.role == FLUID else 0.8, show_edges=False, reset_camera=False)
        for region in built.regions:
            outline = region_outline(region)
            p.add_mesh(_lines([outline]), color=REGION, line_width=2, reset_camera=False)
            if region.shape in ("box", "circle"):
                fill = pv.PolyData(np.column_stack([outline[:-1], np.zeros(len(outline) - 1)]),
                                   faces=np.r_[len(outline) - 1, np.arange(len(outline) - 1)]).triangulate()
                p.add_mesh(fill, color=REGION, opacity=0.15, reset_camera=False)
        boundary = set(built.boundary_edges())
        groups = {}
        legend = []
        for edge in built.edges.values():
            b = built.names.get(edge.id)
            if edge.id in boundary and b is not None:
                colour, width = PATCH_COLOURS.get(b.type, "gray"), 3
                if (b.name, b.type) not in legend:
                    legend.append((b.name, b.type))
            elif edge.id in boundary:
                colour, width = UNNAMED, 2
            else:
                colour, width = colours["outline"], 1.5
            groups.setdefault((colour, width), []).append(edge.points)
        for (colour, width), pts in groups.items():
            p.add_mesh(_lines(pts), color=colour, line_width=width, reset_camera=False)
        corners = [v.xy for v in built.vertices.values() if v.corner]
        if corners:
            dots = np.array(corners)
            p.add_points(np.column_stack([dots, np.zeros(len(dots))]), color=colours["outline"], point_size=6,
                         render_points_as_spheres=True, reset_camera=False)
        if any(e in boundary and e not in built.names for e in built.edges):
            legend.append(("(no name)", "_unnamed"))
        self._legend(legend)
        self._draw_selection()
        self._draw_handles()
        if not p.renderer.axes_enabled:
            p.add_axes(line_width=2, labels_off=False)
        self.toggles["revolve"].setEnabled(built.axisymmetric)
        self._draw_revolve()
        if camera is not None:
            p.camera = camera
            p.render()
        elif self.view3d:
            p.reset_camera()
        else:
            self.fit()
        self._grid_box = None
        self._update_grid()

    def _legend(self, entries):
        """The boundary names with their colours, in the row above the view (always readable, never cut)."""
        parts = [f'<span style="color:{UNNAMED if kind == "_unnamed" else PATCH_COLOURS.get(kind, "gray")}">'
                 f'&#9632;</span>&nbsp;{html.escape(name)}' for name, kind in entries]
        self.legend_label.setText("&nbsp;&nbsp; ".join(parts))

    def _draw_selection(self):
        built = self.built
        if self.highlight is not None:
            for actor in self.highlight:
                self.plotter.remove_actor(actor)
        self.highlight = []
        edges = [built.edges[e].points for k, e in self.selection if k == "edge" and e in built.edges]
        for kind, entity in self.selection:
            if kind == "face" and entity in built.faces:
                face = built.faces[entity]
                if face.triangles is not None:
                    self.highlight.append(self.plotter.add_mesh(_triangles(face.triangles, -0.5 * self._dz),
                                                                color=SELECTED, opacity=0.35,
                                                                reset_camera=False))
                edges += [built.edges[e].points for loop in face.loops for e in loop]
        if edges:
            self.highlight.append(self.plotter.add_mesh(_lines(edges, self._dz), color=SELECTED, line_width=6,
                                                        reset_camera=False))
        dots = [built.vertices[v].xy for k, v in self.selection if k == "vertex" and v in built.vertices]
        if dots:
            dots = np.array(dots)
            self.highlight.append(self.plotter.add_points(np.column_stack([dots, np.full(len(dots), 2 * self._dz)]),
                                                          color=SELECTED,
                                                          point_size=14, render_points_as_spheres=True,
                                                          reset_camera=False))
        self.plotter.render()

    def set_selection(self, selection):
        self.selection = list(selection)
        if self.built is not None and not self.closed:
            self._draw_selection()

    def set_handles(self, points):
        """Show draggable handle points ((n, 2) [m]) for "points" mode; None removes them."""
        self.handles = None if points is None else np.asarray(points, dtype=float)
        if self.built is not None and not self.closed:
            self._draw_handles()

    def set_preview(self, points):
        """A thin line through the points of the sketch being drawn ((n, 2) [m]); None removes it."""
        if getattr(self, "_sketch_actor", None) is not None:
            self.plotter.remove_actor(self._sketch_actor)
            self._sketch_actor = None
        if points is not None and len(points) >= 2:
            self._sketch_actor = self.plotter.add_mesh(_lines([np.asarray(points)], 2 * self._dz), color="#ea4335",
                                                       line_width=2, reset_camera=False)
        self.plotter.render()

    def _draw_handles(self):
        if getattr(self, "_handle_actor", None) is not None:
            self.plotter.remove_actor(self._handle_actor)
            self._handle_actor = None
        if self.handles is not None and len(self.handles):
            pts = np.column_stack([self.handles, np.full(len(self.handles), 3 * self._dz)])
            self._handle_actor = self.plotter.add_points(pts, color="#ea4335", point_size=10,
                                                         render_points_as_spheres=True, reset_camera=False)
        self.plotter.render()

    def clear(self, message=""):
        self._handle_actor = self._sketch_actor = self._hover_actor = None
        self._hover = None
        self._grid_actors, self._grid_box, self._revolve_actors = [], None, []
        if hasattr(self, "legend_label"):
            self.legend_label.setText("")
        super().clear(message)
        self.highlight = None

    def set_dark(self, dark):
        super().set_dark(dark)
        self._grid_box = None                    # redraw the grid in the new colours
        self.update_icons()
        if not self.closed:
            self._update_grid()

    # ---- view aids: grid, 3D, revolve, hover ------------------------------------------------------

    def _toggled(self, key, checked):
        if key == "revolve":
            if checked and not self.toggles["view3d"].isChecked():
                self.toggles["view3d"].setChecked(True)        # a revolved body is seen in 3D (calls _set_3d)
            self._draw_revolve()
        elif key == "view3d":
            if not checked and self.toggles["revolve"].isChecked():
                self.toggles["revolve"].setChecked(False)      # back in 2D: no revolve preview
            self._set_3d(checked)
        elif key == "grid":
            self._grid_box = None
            self._update_grid()

    def _set_3d(self, on):
        """3D: free rotation with perspective; back to 2D: the flat view from +z, fitted."""
        self.view3d = on
        p = self.plotter
        if on:
            self.set_mode("select")
            p.disable_parallel_projection()
            p.enable_trackball_style()
            p.view_isometric()
            p.reset_camera()
        else:
            self.fit()                                       # parallel projection and 2D style again
        self._remove_hover()
        self._grid_box = None
        self._update_grid()
        p.render()

    def _draw_revolve(self):
        """The boundaries swept about the x axis (axisymmetric geometry only)."""
        for actor in self._revolve_actors:
            self.plotter.remove_actor(actor)
        self._revolve_actors = []
        built = self.built
        if not self.toggles["revolve"].isChecked() or built is None or not built.axisymmetric:
            self.plotter.render()
            return
        for edge_id in built.boundary_edges():
            b = built.names.get(edge_id)
            if b is not None and b.type == "axis":
                continue                                   # the axis sweeps to a line
            line = _lines([built.edges[edge_id].points])
            surface = line.extrude_rotate(resolution=REVOLVE_STEPS, angle=REVOLVE_ANGLE, rotation_axis=(1, 0, 0),
                                          capping=False)
            colour_ = PATCH_COLOURS.get(b.type, UNNAMED) if b is not None else UNNAMED
            self._revolve_actors.append(self.plotter.add_mesh(surface, color=colour_, opacity=0.55, smooth_shading=True,
                                                              reset_camera=False))
        self.plotter.render()

    def fit(self):
        if self.view3d and not self.closed:
            self.plotter.reset_camera()
            self.plotter.render()
        else:
            super().fit()

    def visible_box(self):
        """(x0, x1, y0, y1) [m] of the 2D view (parallel projection from +z)."""
        cam = self.plotter.camera
        w, h = max(self.plotter.interactor.width(), 1), max(self.plotter.interactor.height(), 1)
        half_h = cam.parallel_scale
        half_w = half_h * w / h
        cx, cy = cam.focal_point[:2]
        return cx - half_w, cx + half_w, cy - half_h, cy + half_h

    def _after_render(self, *_):
        """After every render: redraw the grid (later, never inside a render) if the view moved."""
        if self.closed or self.built is None:
            return
        box = None if self.view3d else tuple(round(v, 12) for v in self.visible_box())
        if box != self._grid_box and not self._grid_timer.isActive():
            self._grid_timer.start()

    def _update_grid(self):
        if self.closed:
            return
        for actor in self._grid_actors:
            self.plotter.remove_actor(actor)
        self._grid_actors = []
        if self.built is None or self.built.empty or not self.toggles["grid"].isChecked():
            self._grid_box = None
            self.position_label.setText(self.position_label.text().split("   grid")[0])
            self.plotter.render()
            return
        if self.view3d:
            x0, y0, x1, y1 = self.built.bbox()
            pad = 0.25 * max(x1 - x0, y1 - y0)
            box = (x0 - pad, x1 + pad, y0 - pad, y1 + pad)
        else:
            box = self.visible_box()
        step, xs, ys, x_major, y_major = visible_grid(*box)
        minor_colour, major_colour = GRID[self.dark]
        z = -3.0 * self._dz                                  # behind everything else
        for major, colour_ in ((False, minor_colour), (True, major_colour)):
            segments = [np.array([[x, box[2]], [x, box[3]]]) for x, m in zip(xs, x_major) if m == major]
            segments += [np.array([[box[0], y], [box[1], y]]) for y, m in zip(ys, y_major) if m == major]
            if segments:
                self._grid_actors.append(self.plotter.add_mesh(_lines(segments, z), color=colour_, line_width=1,
                                                               reset_camera=False, pickable=False))
        self._grid_step = step
        self._grid_box = None if self.view3d else tuple(round(v, 12) for v in box)
        self._show_position()
        self.plotter.render()

    def _show_position(self, xy=None):
        text = "" if xy is None else f"x {xy[0] * 1e3:.4g}   y {xy[1] * 1e3:.4g} mm"
        if self.toggles["grid"].isChecked() and getattr(self, "_grid_step", None) and self.built is not None:
            text += f"   grid {self._grid_step * 1e3:.4g} mm"
        self.position_label.setText(text.strip())

    def _remove_hover(self):
        if self._hover_actor is not None:
            self.plotter.remove_actor(self._hover_actor)
            self._hover_actor = None
        self._hover = None

    def _draw_hover(self, hit):
        """Light-blue outline of what a click would pick now (pre-selection)."""
        if hit == self._hover:
            return
        self._remove_hover()
        self._hover = hit
        if hit is None or tuple(hit) in [tuple(s) for s in self.selection]:
            self.plotter.render()
            return
        kind, entity = hit
        if kind == "edge":
            self._hover_actor = self.plotter.add_mesh(_lines([self.built.edges[entity].points], 1.5 * self._dz),
                                                      color=HOVER, line_width=5, reset_camera=False)
        elif kind == "vertex":
            xy = self.built.vertices[entity].xy
            self._hover_actor = self.plotter.add_points(np.array([[xy[0], xy[1], 2.5 * self._dz]]), color=HOVER,
                                                        point_size=12, render_points_as_spheres=True,
                                                        reset_camera=False)
        else:
            face = self.built.faces[entity]
            edges = [self.built.edges[e].points for loop in face.loops for e in loop]
            self._hover_actor = self.plotter.add_mesh(_lines(edges, 1.5 * self._dz), color=HOVER, line_width=3,
                                                      reset_camera=False)
        self.plotter.render()

    # ---- modes -------------------------------------------------------------------------------------

    def set_mode(self, mode):
        """"select" (left drag pans the view) or "move", "points", "click" (left drag edits)."""
        self.mode = mode
        iren = self.plotter.iren.interactor
        if mode == "select":
            if self._style_2d is not None:
                iren.SetInteractorStyle(self._style_2d)
                self._style_2d = None
        elif self._style_2d is None:
            self._style_2d = iren.GetInteractorStyle()
            iren.SetInteractorStyle(vtkInteractorStyleUser())     # no camera moves on the left button

    def _wheel(self, factor):
        if self.mode != "select" and not self.closed:     # the 2D style zooms by itself in select mode
            self.plotter.camera.parallel_scale *= factor
            self.plotter.render()

    # ---- mouse ---------------------------------------------------------------------------------------

    def tolerance(self, x, y) -> float:
        """PICK_PIXELS converted to metres at the pixel (x, y)."""
        return PICK_PIXELS * float(np.linalg.norm(self.world_point(x + 1, y) - self.world_point(x, y)))

    def _on_press(self, interactor, _event):
        self._press = interactor.GetEventPosition()
        if self.built is None or self.mode == "select":
            return
        x, y = self._press
        p = self.world_point(x, y)
        if self.mode == "move" and self.selection:
            if self._on_selection(picking.pick(self.built, p, self.tolerance(x, y))):
                self._drag = ("move", p)
        elif self.mode == "points" and self.handles is not None and len(self.handles):
            d = np.linalg.norm(self.handles - p, axis=1)
            k = int(d.argmin())
            if d[k] <= self.tolerance(x, y):
                self._drag = ("point", k)

    def _on_move(self, interactor, _event):
        if self.built is None or self.closed or self.view3d:
            return
        x, y = interactor.GetEventPosition()
        p = self.world_point(x, y)
        if self._drag is None:
            self._show_position(p)
            self.cursor_moved.emit(float(p[0]), float(p[1]))
            if self.mode == "select" and not self.built.empty:
                self._draw_hover(picking.pick(self.built, p, self.tolerance(x, y)))
            return
        if self._preview is not None:
            self.plotter.remove_actor(self._preview)
        if self._drag[0] == "move":
            shift = p - self._drag[1]
            edges = [self.built.edges[e].points + shift for e in self._selected_edges()]
            self._preview = self.plotter.add_mesh(_lines(edges), color=SELECTED, line_width=2, reset_camera=False)
        else:
            pts = self.handles.copy()
            pts[self._drag[1]] = p
            self._preview = self.plotter.add_mesh(_lines([pts]), color="#ea4335", line_width=2, reset_camera=False)
        self.plotter.render()

    def _on_selection(self, hit) -> bool:
        """True if the picked entity is selected, or is an edge / the inside of a selected face."""
        if hit is None:
            return False
        selected = [tuple(s) for s in self.selection]
        if hit in selected:
            return True
        faces = {entity for kind, entity in selected if kind == "face"}
        if hit[0] == "edge":
            return bool(faces & set(self.built.edges[hit[1]].faces))
        return False

    def _selected_edges(self):
        out = []
        for kind, entity in self.selection:
            if kind == "face":
                out += [e for loop in self.built.faces[entity].loops for e in loop]
            elif kind == "edge":
                out.append(entity)
        return out

    def _on_release(self, interactor, _event):
        x, y = interactor.GetEventPosition()
        if self._preview is not None:
            self.plotter.remove_actor(self._preview)
            self._preview = None
        drag, self._drag = self._drag, None
        if self._press is None or self.built is None or self.view3d:      # 3D: rotate only, no picking
            return
        moved_pixels = abs(x - self._press[0]) + abs(y - self._press[1])
        p = self.world_point(x, y)
        if drag is not None and moved_pixels > CLICK_PIXELS:
            if drag[0] == "move":
                d = p - drag[1]
                self.moved.emit(float(d[0]), float(d[1]))
            else:
                self.point_moved.emit(int(drag[1]), float(p[0]), float(p[1]))
            return
        if moved_pixels > CLICK_PIXELS:
            return                                           # it was a pan
        if self.mode == "click":
            self.clicked.emit(float(p[0]), float(p[1]), self.tolerance(x, y))
            return
        self.pick_at(x, y, bool(interactor.GetShiftKey() or interactor.GetControlKey()))

    def _on_right_press(self, interactor, _event):
        self._right_press = interactor.GetEventPosition()

    def _on_right_release(self, interactor, _event):
        """A right-click (not a drag, which zooms) opens the context menu for what is under the cursor."""
        if self._right_press is None or self.built is None or self.view3d:
            return
        x, y = interactor.GetEventPosition()
        if abs(x - self._right_press[0]) + abs(y - self._right_press[1]) > CLICK_PIXELS:
            return
        hit = picking.pick(self.built, self.world_point(x, y), self.tolerance(x, y))
        kind, entity = hit if hit is not None else ("", "")
        widget = self.plotter.interactor
        ratio = widget.devicePixelRatioF()                  # VTK counts physical pixels, from the bottom
        local = QPoint(int(x / ratio), int(widget.height() - y / ratio))
        self.context_menu.emit(kind, entity, widget.mapToGlobal(local))

    def pick_at(self, x, y, add=False):
        """Pick at screen pixel (x, y) (VTK display coordinates) and emit picked()."""
        hit = picking.pick(self.built, self.world_point(x, y), self.tolerance(x, y))
        kind, entity = hit if hit is not None else ("", "")
        self.picked.emit(kind, entity, add)

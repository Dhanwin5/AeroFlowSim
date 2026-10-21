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
import time

import numpy as np
import pyvista as pv
from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton

from aeroflowsim.geometry_model import FLUID, picking
from aeroflowsim.geometry_model.snapping import visible_grid
from aeroflowsim.gui.icons import icon
from aeroflowsim.gui.theme import PATCH_COLOURS, colour, view_colours
from aeroflowsim.gui.vtk_view import CLICK_PIXELS, MeshView

HOVER = "#4fc3f7"            # what a click would pick
GRID = {False: ("#e3e7ec", "#c9d0d8"), True: ("#2b2d31", "#3c4043")}   # (minor, major) grid line colours
REVOLVE_ANGLE = 270.0        # the revolve preview leaves a quarter open, to see inside [deg]
REVOLVE_STEPS = 72           # angular resolution of the revolve preview [-]
TOOL = "#ea4335"             # the shape being drawn
GUIDE = "#9aa0a6"            # dashed guide lines while drawing
MARKER = "#1a73e8"           # the snap marker
BOX_COLOURS = {False: "#1a73e8", True: "#34a853"}
DIMENSION_PIXELS = 18        # a double-click this close to a dimension's value edits it [px]   # box selection: inside (left to right) / touching (right to left)
DOUBLE_CLICK_S = 0.35        # two clicks closer in time than this are a double-click [s]

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


def _dashes(points, dash):
    """A polyline cut into dashes of length `dash` [m] (every other piece kept): [(2, 2)] segments."""
    out = []
    for a, b in zip(points[:-1], points[1:]):
        length = float(np.linalg.norm(b - a))
        if length <= 0.0 or dash <= 0.0:
            continue
        n = max(1, int(length / dash))
        t = np.linspace(0.0, 1.0, n + 1)
        out += [np.array([a + (b - a) * t[k], a + (b - a) * t[k + 1]]) for k in range(0, n, 2)]
    return out


def marker_shape(kind, p, s):
    """The snap marker for an inference kind at point p, size s [m]: a list of polylines.

    endpoint: square, intersection: X, centre: circle with a cross, midpoint: triangle, tangent: circle
    and a line, perpendicular: right-angle sign, on curve: diamond, angle / aligned: plus, grid: small square."""
    x, y = p
    circle = np.column_stack([x + s * np.cos(np.linspace(0, 2 * np.pi, 25)), y + s * np.sin(np.linspace(0, 2 * np.pi, 25))])
    shapes = {
        "endpoint": [np.array([[x - s, y - s], [x + s, y - s], [x + s, y + s], [x - s, y + s], [x - s, y - s]])],
        "intersection": [np.array([[x - s, y - s], [x + s, y + s]]), np.array([[x - s, y + s], [x + s, y - s]])],
        "centre": [circle, np.array([[x - s, y], [x + s, y]]), np.array([[x, y - s], [x, y + s]])],
        "midpoint": [np.array([[x - s, y - 0.6 * s], [x + s, y - 0.6 * s], [x, y + s], [x - s, y - 0.6 * s]])],
        "tangent": [circle, np.array([[x - 1.6 * s, y + s], [x + 1.6 * s, y + s]])],
        "perpendicular": [np.array([[x - s, y + s], [x - s, y - s], [x + s, y - s]]),
                          np.array([[x - s, y], [x, y], [x, y - s]])],
        "on curve": [np.array([[x, y - s], [x + s, y], [x, y + s], [x - s, y], [x, y - s]])],
        "grid": [np.array([[x - 0.5 * s, y - 0.5 * s], [x + 0.5 * s, y - 0.5 * s], [x + 0.5 * s, y + 0.5 * s],
                           [x - 0.5 * s, y + 0.5 * s], [x - 0.5 * s, y - 0.5 * s]])],
    }
    return shapes.get(kind, [np.array([[x - s, y], [x + s, y]]), np.array([[x, y - s], [x, y + s]])])


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
    tool_moved = Signal(float, float, float)     # drawing: the cursor moved to x, y [m] (with the pick tolerance)
    tool_clicked = Signal(float, float, float)   # drawing: a point was clicked at x, y [m]
    tool_finish = Signal()                       # drawing: double-click or right-click (finish the shape)
    box_selected = Signal(float, float, float, float, bool, bool)   # x0, y0, x1, y1 [m], touching?, add?
    key_typed = Signal(str)                      # drawing: a digit (or . - @ <) typed over the view
    dimension_edit = Signal(str, int)            # double-click on a dimension: sketch op id, constraint index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.built = None
        self.selection = []
        self.mode = "select"
        self.handles = None                  # (n, 2) points shown as draggable handles, or None
        self._dz = 1e-3
        self._drag = None                    # what is being dragged: ("move", start xy) or ("point", index)
        self._preview = None
        self._hover, self._hover_actor = None, None
        self._tool_actors, self._cursor_pixel, self._last_click = [], (0, 0), None
        self._grid_actors, self._grid_box = [], None
        self._revolve_actors = []
        self._dimension_spots = []           # [(label position (2,) [m], op id, constraint index)]
        self._right_press = None
        self.view3d = False
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
        # Second line: the selection filter (what clicks and boxes may pick) and the legend.
        second = QHBoxLayout()
        second.setContentsMargins(4, 0, 4, 2)
        second.addWidget(QLabel("Pick:", objectName="hint"))
        self.filters = {}
        for kind, text, tip in (("vertex", "Points", "Clicks and boxes select corner points"),
                                ("edge", "Edges", "Clicks and boxes select edges"),
                                ("face", "Faces", "Clicks and boxes select faces")):
            button = QToolButton(text=text, toolTip=tip, checkable=True, checked=True, autoRaise=True)
            second.addWidget(button)
            self.filters[kind] = button
        self.position_label = QLabel(objectName="hint")
        self.position_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.toolbar.addWidget(self.position_label)
        # The legend shares the second line, so long boundary names never crowd out the switches.
        self.legend_label = QLabel(textFormat=Qt.RichText, wordWrap=True)
        self.legend_label.setContentsMargins(12, 0, 0, 0)
        second.addWidget(self.legend_label, 1)
        self.layout().insertLayout(1, second)
        self.plotter.add_axes(line_width=2, labels_off=False)
        self.update_icons()
        self._ready = True
        self.plotter.interactor.installEventFilter(self)      # 2D mouse handling (see eventFilter): set up last

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
            if built is not None and not self.view3d:     # an empty sheet: flat 2D view, 100 mm across
                self._show_box(-0.05, 0.05, -0.05, 0.05)
                self._grid_box = None
                self._update_grid()
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
        self._draw_dimensions(built)
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

    def dimension_colour(self, status) -> str:
        """Colour of a sketch's dimensions by its constraint status: green = fully constrained,
        red = conflicting, blue = still free to move (degrees of freedom left)."""
        if status == "fully constrained":
            return colour("ok", self.dark)
        return colour("error", self.dark) if status == "conflicting" else ("#8ab4f8" if self.dark else MARKER)

    def _draw_dimensions(self, built):
        """The driving dimensions of constrained sketches (operations.dimension_marks): a thin line with
        end ticks, set off from the shape, and the value next to it (double-click it to change it)."""
        self._dimension_spots = []
        if not built.dimensions:
            return
        centre = np.mean(np.vstack([e.points for e in built.edges.values()]), axis=0)
        gap = 0.04 * built.size                         # how far a dimension line is set off from the shape
        lines, spots, texts, colours = [], [], [], []
        for d in built.dimensions:
            a, b = (np.asarray(q, dtype=float) for q in d["line"])
            if d["type"] in ("radius", "angle"):          # drawn from the centre / along the first line
                lines.append(np.array([a, b]))
                spot = 0.5 * (a + b) if d["type"] == "radius" else a + 0.25 * (b - a)
            else:
                t = b - a
                n = np.array([-t[1], t[0]]) / max(np.linalg.norm(t), 1e-300)
                if (0.5 * (a + b) - centre) @ n < 0.0:      # set it off on the outer side
                    n = -n
                a2, b2 = a + gap * n, b + gap * n
                tick = 0.25 * gap * t / max(np.linalg.norm(t), 1e-300)
                lines += [np.array([a, a2 + 0.3 * gap * n]), np.array([b, b2 + 0.3 * gap * n]), np.array([a2, b2]),
                          np.array([a2 - tick, a2 + tick]), np.array([b2 - tick, b2 + tick])]
                spot = 0.5 * (a2 + b2)
            spots.append(spot)
            texts.append(d["text"])
            colours.append(self.dimension_colour(built.sketch_status.get(d["op"], "")))
            self._dimension_spots.append((spot, d["op"], d["index"]))
        p, z = self.plotter, 2.0 * self._dz
        p.add_mesh(_lines(lines, z), color=colours[0], line_width=1, reset_camera=False)
        for colour_, group in {c: [k for k in range(len(spots)) if colours[k] == c] for c in set(colours)}.items():
            p.add_point_labels(np.array([[*spots[k], z] for k in group]), [texts[k] for k in group], font_size=11,
                               text_color=colour_, shape_color=colour("base", self.dark), shape_opacity=0.85,
                               show_points=False, always_visible=True, reset_camera=False, margin=2)

    def dimension_at(self, x, y):
        """(op id, constraint index) of the dimension whose value is at display pixel x, y, or None."""
        if not self._dimension_spots:
            return None
        xy = np.asarray(self.world_point(x, y))[:2]
        limit = DIMENSION_PIXELS * self.metres_per_pixel(x, y)
        best = min(self._dimension_spots, key=lambda s: np.linalg.norm(s[0] - xy))
        return (best[1], best[2]) if np.linalg.norm(best[0] - xy) <= limit else None

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
        self._dimension_spots = []
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
        """"select", "move" (drag the selection), "points" (drag handles) or "draw" (a sketch tool is active)."""
        self.mode = mode
        self._remove_hover()
        if mode != "draw":
            self.show_tool_preview(None)

    def _shift_camera(self, shift):
        """Move the 2D camera by shift [m] (the drawing moves the other way)."""
        cam = self.plotter.camera
        fx, fy, fz = cam.focal_point
        px, py, pz = cam.position
        cam.focal_point = (fx + shift[0], fy + shift[1], fz)
        cam.position = (px + shift[0], py + shift[1], pz)
        self.plotter.render()

    # ---- mouse: a Qt event filter, before VTK sees the events ----------------------------------------
    #
    # In 2D the view handles the mouse itself, like CAD programs: left = select / box select / draw /
    # drag, middle or Shift + left = pan, wheel = zoom about the cursor, right = context menu (or finish
    # the shape being drawn). The events are caught in Qt BEFORE VTK sees them (eventFilter), so no VTK
    # camera style can pan or zoom at the same time; in 3D they pass through to VTK's rotation.
    # Positions are converted to VTK display pixels (origin bottom left, physical pixels), the
    # coordinates world_point() and the picking use.

    def eventFilter(self, obj, event):
        if not getattr(self, "_ready", False) or obj is not self.plotter.interactor or self.view3d or                 self.built is None or self.closed:
            return False
        kind = event.type()
        if kind == QEvent.KeyPress:
            text = event.text()
            if self.mode == "draw" and text and (text.isdigit() or text in ".-@<,"):
                self.key_typed.emit(text)
                return True
            return False
        if kind not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove,
                        QEvent.MouseButtonDblClick, QEvent.Wheel):
            return False
        x, y = self._vtk_pixel(event)
        mods = event.modifiers()
        shift, ctrl = bool(mods & Qt.ShiftModifier), bool(mods & Qt.ControlModifier)
        if kind == QEvent.Wheel:
            self.zoom_at(x, y, 0.85 if event.angleDelta().y() > 0 else 1.0 / 0.85)
        elif kind == QEvent.MouseMove:
            self.mouse_move(x, y)
        elif kind == QEvent.MouseButtonDblClick:
            if event.button() == Qt.LeftButton and self.mode == "draw":
                self.tool_finish.emit()                     # the first click of the pair placed the point
            elif event.button() == Qt.LeftButton and self.dimension_at(x, y) is not None:
                self.dimension_edit.emit(*self.dimension_at(x, y))
        elif kind == QEvent.MouseButtonPress:
            self.plotter.interactor.setFocus()
            if event.button() == Qt.LeftButton:
                self.mouse_press(x, y, shift)
            elif event.button() == Qt.MiddleButton:
                self._drag = ("pan", self.world_point(x, y))
            elif event.button() == Qt.RightButton:
                self._right_press = (x, y)
        else:
            if event.button() == Qt.LeftButton:
                self.mouse_release(x, y, shift or ctrl)
            elif event.button() == Qt.MiddleButton:
                self._drag = None
            elif event.button() == Qt.RightButton:
                self.right_click(x, y)
        return True

    def _vtk_pixel(self, event):
        widget = self.plotter.interactor
        ratio = widget.devicePixelRatioF()
        pos = event.position()
        return pos.x() * ratio, (widget.height() - pos.y()) * ratio

    def _on_press(self, *_):        # (MeshView's VTK observers: the event filter does this work in 2D)
        pass

    def _on_release(self, *_):
        pass

    def zoom_at(self, x, y, factor):
        """Zoom by `factor` about the pixel (x, y): the point under the cursor stays where it is."""
        before = self.world_point(x, y)
        self.plotter.camera.parallel_scale *= factor
        self._shift_camera(before - self.world_point(x, y))

    def tolerance(self, x, y) -> float:
        """PICK_PIXELS converted to metres at the pixel (x, y)."""
        return PICK_PIXELS * self.metres_per_pixel(x, y)

    def metres_per_pixel(self, x=0, y=0) -> float:
        return float(np.linalg.norm(self.world_point(x + 1, y) - self.world_point(x, y)))

    def pick_hit(self, x, y):
        """(kind, id) under the pixel (x, y), allowing only the kinds of the selection filter, or None."""
        kinds = tuple(k for k in ("vertex", "edge", "face") if self.filters[k].isChecked())
        return picking.pick(self.built, self.world_point(x, y), self.tolerance(x, y), kinds)

    def mouse_press(self, x, y, shift=False):
        """Left button down at the VTK pixel (x, y)."""
        self._press = self._cursor_pixel = (x, y)
        self._drag = None
        if self.mode == "draw":
            return                                          # drawing: handled on release (click or drag)
        p = self.world_point(x, y)
        if shift and self.mode == "select":
            self._drag = ("pan", p)                          # Shift + drag pans (no middle button needed)
        elif self.mode == "move" and self.selection and self._on_selection(self.pick_hit(x, y)):
            self._drag = ("move", p)
        elif self.mode == "points" and self.handles is not None and len(self.handles):
            d = np.linalg.norm(self.handles - p, axis=1)
            k = int(d.argmin())
            if d[k] <= self.tolerance(x, y):
                self._drag = ("point", k)
        hit = self.pick_hit(x, y) if self._drag is None else None
        if self._drag is None and (hit is None or hit[0] == "face"):
            self._drag = ("box", p)                          # empty space or inside a face: a box selection if it
                                                             # becomes a drag (a plain click still selects the face)

    def mouse_move(self, x, y):
        """The cursor moved to the VTK pixel (x, y) (with or without a button down)."""
        self._cursor_pixel = (x, y)
        p = self.world_point(x, y)
        if self._drag is None:
            self._show_position(p)
            self.cursor_moved.emit(float(p[0]), float(p[1]))
            if self.mode == "draw":
                self.tool_moved.emit(float(p[0]), float(p[1]), self.tolerance(x, y))
            elif self.mode == "select" and not self.built.empty:
                self._draw_hover(self.pick_hit(x, y))
            return
        kind = self._drag[0]
        if kind == "pan":                                    # keep the grabbed point under the cursor
            self._shift_camera(self._drag[1] - p)
            return
        if self._preview is not None:
            self.plotter.remove_actor(self._preview)
            self._preview = None
        if kind == "box":
            a = self._drag[1]
            if np.linalg.norm(p - a) / self.metres_per_pixel(x, y) <= CLICK_PIXELS:
                self.plotter.render()
                return
            corners = np.array([a, [p[0], a[1]], p, [a[0], p[1]], a])
            crossing = p[0] < a[0]                           # right to left: touching; left to right: inside
            outline = _dashes(corners, 6 * self.metres_per_pixel(x, y)) if crossing else [corners]
            self._preview = self.plotter.add_mesh(_lines(outline, 4 * self._dz), color=BOX_COLOURS[crossing],
                                                  line_width=1.5, reset_camera=False)
        elif kind == "move":
            shift = p - self._drag[1]
            edges = [self.built.edges[e].points + shift for e in self._selected_edges()]
            self._preview = self.plotter.add_mesh(_lines(edges), color=SELECTED, line_width=2, reset_camera=False)
        else:
            pts = self.handles.copy()
            pts[self._drag[1]] = p
            self._preview = self.plotter.add_mesh(_lines([pts]), color=TOOL, line_width=2, reset_camera=False)
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

    def mouse_release(self, x, y, add=False):
        """Left button up at the VTK pixel (x, y): a click, the end of a drag, or a point of a drawing."""
        if self._preview is not None:
            self.plotter.remove_actor(self._preview)
            self._preview = None
        drag, self._drag = self._drag, None
        self._cursor_pixel = (x, y)                          # (the drawing label goes next to the cursor)
        if self._press is None:
            return
        moved_pixels = abs(x - self._press[0]) + abs(y - self._press[1])
        p = self.world_point(x, y)
        if self.mode == "draw":
            tol = self.tolerance(x, y)
            if moved_pixels > CLICK_PIXELS:                  # press - drag - release: two points in one move
                a = self.world_point(*self._press)
                self.tool_clicked.emit(float(a[0]), float(a[1]), tol)
            self.tool_clicked.emit(float(p[0]), float(p[1]), tol)
            return
        if drag is not None and drag[0] == "pan":
            return
        if drag is not None and drag[0] == "box" and moved_pixels > CLICK_PIXELS:
            a = drag[1]
            self.box_selected.emit(float(a[0]), float(a[1]), float(p[0]), float(p[1]), bool(p[0] < a[0]), add)
            return
        if drag is not None and drag[0] in ("move", "point") and moved_pixels > CLICK_PIXELS:
            if drag[0] == "move":
                d = p - drag[1]
                self.moved.emit(float(d[0]), float(d[1]))
            else:
                self.point_moved.emit(int(drag[1]), float(p[0]), float(p[1]))
            return
        if moved_pixels > CLICK_PIXELS:
            return
        self.pick_at(x, y, add)

    def right_click(self, x, y):
        """Right button up: finishes the shape being drawn; otherwise the context menu (not after a drag)."""
        if self._right_press is None or abs(x - self._right_press[0]) + abs(y - self._right_press[1]) > CLICK_PIXELS:
            return
        if self.mode == "draw":
            self.tool_finish.emit()
            return
        hit = self.pick_hit(x, y)
        kind, entity = hit if hit is not None else ("", "")
        widget = self.plotter.interactor
        ratio = widget.devicePixelRatioF()
        local = QPoint(int(x / ratio), int(widget.height() - y / ratio))
        self.context_menu.emit(kind, entity, widget.mapToGlobal(local))

    def pick_at(self, x, y, add=False):
        """Pick at screen pixel (x, y) (VTK display coordinates) and emit picked()."""
        hit = self.pick_hit(x, y)
        kind, entity = hit if hit is not None else ("", "")
        self.picked.emit(kind, entity, add)

    # ---- the drawing tool's preview -------------------------------------------------------------------

    def show_tool_preview(self, preview):
        """Draw a sketch tool's preview (gui/sketch_tools.Preview): the shape so far, the rubber band,
        dashed guides, the snap marker and the label next to the cursor. None removes it."""
        for actor in self._tool_actors:
            self.plotter.remove_actor(actor)
        self._tool_actors = []
        if preview is None or self.closed or self.built is None:
            if not self.closed:
                self.plotter.render()
            return
        z, add = 4.0 * self._dz, self._tool_actors.append
        px = self.metres_per_pixel(*self._cursor_pixel)
        if preview.lines:
            add(self.plotter.add_mesh(_lines([np.asarray(l) for l in preview.lines if len(l) >= 2], z), color=TOOL,
                                      line_width=2.5, reset_camera=False))
        if preview.points:
            pts = np.array(preview.points)
            add(self.plotter.add_points(np.column_stack([pts, np.full(len(pts), z)]), color=TOOL, point_size=7,
                                        render_points_as_spheres=True, reset_camera=False))
        dashes = [d for a, b in preview.guides for d in _dashes(np.array([a, b]), 6 * px)]
        if dashes:
            add(self.plotter.add_mesh(_lines(dashes, z), color=GUIDE, line_width=1, reset_camera=False))
        if preview.marker is not None:
            add(self.plotter.add_mesh(_lines(marker_shape(preview.marker[1], preview.marker[0], 7 * px), 1.2 * z),
                                      color=MARKER, line_width=2, reset_camera=False))
        if preview.label:
            x, y = self._cursor_pixel
            add(self.plotter.add_text(preview.label, position=(int(x) + 16, int(y) + 12), font_size=7,
                                      color=colour("text", self.dark)))
        self.plotter.render()

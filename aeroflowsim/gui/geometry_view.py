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
    "points" (drag one of the handle points: emits point_moved(index, x, y) [m]),
    "click" (sketching: emits clicked(x, y) [m]). In the drag modes the mouse wheel still zooms.
"""

import numpy as np
import pyvista as pv
from PySide6.QtCore import Signal
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleUser

from aeroflowsim.geometry_model import FLUID, picking
from aeroflowsim.gui.theme import PATCH_COLOURS, view_colours
from aeroflowsim.gui.vtk_view import CLICK_PIXELS, MeshView

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
    clicked = Signal(float, float)           # a click in "click" mode at x, y [m]

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
        self.plotter.iren.add_observer("MouseMoveEvent", self._on_move)
        self.plotter.iren.add_observer("MouseWheelForwardEvent", lambda *_: self._wheel(0.85))
        self.plotter.iren.add_observer("MouseWheelBackwardEvent", lambda *_: self._wheel(1.0 / 0.85))

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
        if camera is not None:
            p.camera = camera
            p.render()
        else:
            self.fit()

    def _legend(self, entries):
        if entries:
            colours = [[name, UNNAMED if kind == "_unnamed" else PATCH_COLOURS.get(kind, "gray")]
                       for name, kind in entries]
            self.plotter.add_legend(colours, bcolor=None, face="line", size=(0.16, 0.045 * len(entries)),
                                    loc="upper right", font_family="arial")

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
        self._handle_actor = None
        super().clear(message)
        self.highlight = None

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
        if self._drag is None:
            return
        x, y = interactor.GetEventPosition()
        p = self.world_point(x, y)
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
        if self._press is None or self.built is None:
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
            self.clicked.emit(float(p[0]), float(p[1]))
            return
        self.pick_at(x, y, bool(interactor.GetShiftKey() or interactor.GetControlKey()))

    def pick_at(self, x, y, add=False):
        """Pick at screen pixel (x, y) (VTK display coordinates) and emit picked()."""
        hit = picking.pick(self.built, self.world_point(x, y), self.tolerance(x, y))
        kind, entity = hit if hit is not None else ("", "")
        self.picked.emit(kind, entity, add)

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The 2D flow view of the Results step: draws a Scene (gui/results_logic.py) with VTK.

    filled contours   smooth (node values interpolated across each cell), flat per cell, or banded colours
    contour lines     VTK contour filter on the node values, optional labels
    vectors           arrows at evenly spread cells (VTK glyphs), coloured by a field or plain
    streamlines       VTK stream tracer on the node velocities, from a line / rake surface or clicked points,
                      both directions, with arrow marks
    mirror            the picture reflected about the axis / symmetry line y = 0 (display only)
    revolve           axisymmetric results as a 3D surface of revolution (the wall and two meridian planes);
                      the mouse then rotates the view
    surfaces          the project's surfaces drawn on top (lines, rakes, points, iso-lines)

ViewGrid holds 1, 2 or 4 FlowViews whose cameras are linked (one shared vtkCamera): pan or zoom one and the
others follow. Right-click menus, a hover tooltip and picture export (any resolution, transparent background,
light paper style whatever the theme) are in MeshView / FlowView.
"""

import numpy as np
import pyvista as pv
from PySide6.QtCore import QPoint, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QGridLayout, QMenu, QToolTip, QWidget

from aeroflowsim.gui.results_logic import BANDED, FLAT
from aeroflowsim.gui.theme import view_colours
from aeroflowsim.gui.vtk_view import MeshView, mesh_to_grid, patch_lines

SURFACE_COLOUR = "#ff00ff"


class FlowView(MeshView):
    """A MeshView that draws a whole Scene and offers the Results right-click menu."""

    clicked = Signal(float, float)                  # a left click at world x, y [m]
    probe_requested = Signal(float, float)          # world x, y [m]
    point_surface_requested = Signal(float, float)
    line_surface_requested = Signal(float, float, float, float)
    seed_requested = Signal(float, float)
    save_requested = Signal()
    view_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sol = self.scene = self.data = None
        self.hover = None                    # function (x, y) -> tooltip text, set by the page
        self.line_start = None               # first point of a line being drawn by two clicks
        self.surface_actors = []
        self._paper = False
        self.plotter.iren.add_observer("MouseMoveEvent", self._on_move)

    # ---- drawing the scene ------------------------------------------------------------------

    def draw(self, sol, scene, data, surfaces=(), keep_camera=True, paper=False):
        """Draw a Scene. surfaces: post.surfaces.SurfaceData list to overlay. paper: light colours (saving)."""
        if self.closed:
            return
        camera = self.plotter.camera_position if keep_camera and self.mesh is not None else None
        if scene.camera and not keep_camera:
            camera = [tuple(c) for c in scene.camera]
        self.sol, self.scene, self.data = sol, scene, data
        dark = self.dark and not paper
        colours = view_colours(dark)
        p = self.plotter
        p.clear()
        p.set_background(colours["background"])
        mesh = sol.mesh
        self.mesh, self.grid, self.lines = mesh, mesh_to_grid(mesh), patch_lines(mesh)
        self.highlight = None
        grid = self.grid
        grid.point_data["value"] = np.asarray(data.node, dtype=float)
        grid.cell_data["value_cell"] = np.asarray(data.cell, dtype=float)
        pieces = [grid]
        if scene.mirror and not scene.revolve:
            pieces.append(grid.reflect((0.0, 1.0, 0.0), point=(0.0, 0.0, 0.0)))
        bar = self._bar_args(scene, data, colours)
        self.bar_room = scene.bar_position == "Bottom"
        common = dict(cmap=scene.cmap, clim=(data.vmin, data.vmax), log_scale=scene.log_scale,
                      show_edges=scene.edges, edge_color=colours["edges"], line_width=0.5, nan_color="gray")
        if scene.revolve:
            self._draw_revolved(sol, scene, data, common, bar)
        else:
            for k, piece in enumerate(pieces):
                kw = dict(common, show_scalar_bar=(k == 0 and scene.bar_position != "Hidden"),
                          scalar_bar_args=bar)
                if scene.colouring == FLAT:
                    actor = p.add_mesh(piece, scalars="value_cell", preference="cell", **kw)
                else:
                    if scene.colouring == BANDED:
                        kw["n_colors"] = max(int(scene.n_bands), 2)
                    actor = p.add_mesh(piece, scalars="value", preference="point", interpolate_before_map=True, **kw)
                if k == 0:
                    self.mesh_actor = actor
            if scene.contour_lines and len(data.levels):
                self._draw_contour_lines(pieces, scene, data, dark)
            if scene.vectors and data.vectors is not None:
                self._draw_vectors(sol, scene, data, colours, mirror=scene.mirror)
            if scene.streamlines and data.node_velocity is not None and data.seeds is not None:
                self._draw_streamlines(scene, data, colours, mirror=scene.mirror)
            if scene.boundaries:
                lines = self.lines
                from aeroflowsim.gui.theme import PATCH_COLOURS
                rgb = np.array([pv.Color(PATCH_COLOURS.get(pt.type, "gray")).int_rgb for pt in mesh.patches],
                               dtype=np.uint8)
                lines.cell_data["rgb"] = rgb[lines.cell_data["patch"]]
                p.add_mesh(lines, scalars="rgb", rgb=True, line_width=2.5, reset_camera=False)
                if scene.mirror:
                    p.add_mesh(lines.reflect((0.0, 1.0, 0.0), point=(0.0, 0.0, 0.0)), scalars="rgb", rgb=True,
                               line_width=2.5, reset_camera=False)
            self.draw_surfaces(surfaces)
        bbox = mesh.info.get("body_bbox")
        self._set_body((bbox[0], bbox[2], bbox[1], bbox[3]) if bbox is not None and len(bbox) == 4 else None)
        if scene.revolve:
            p.disable_parallel_projection()
            p.enable_trackball_style()
            if camera is None:
                p.reset_camera()
                p.view_isometric()
        elif camera is not None:
            self._restore_2d(camera)
        else:
            self.fit()
        p.render()

    def _restore_2d(self, camera):
        p = self.plotter
        p.enable_parallel_projection()
        p.enable_2d_style()
        try:
            p.camera_position = camera
        except (TypeError, ValueError):
            self.fit()

    def _bar_args(self, scene, data, colours):
        if scene.bar_position == "Right":
            pos = {"vertical": True, "position_x": 0.86, "position_y": 0.15, "width": 0.07, "height": 0.7}
        else:
            pos = {"vertical": False, "position_x": 0.2, "position_y": 0.04, "width": 0.6, "height": 0.06}
        return {"title": data.title, "color": colours["text"], "n_labels": 5, "fmt": scene.bar_format or "%.4g",
                "title_font_size": 12, "label_font_size": 11, **pos}

    def _draw_contour_lines(self, pieces, scene, data, dark):
        colour = "white" if dark else "black"
        for k, piece in enumerate(pieces):
            iso = piece.contour(isosurfaces=list(map(float, data.levels)), scalars="value", preference="point")
            if iso.n_points == 0:
                continue
            self.plotter.add_mesh(iso, color=colour, line_width=1.2, reset_camera=False, show_scalar_bar=False)
            if scene.line_labels and k == 0:
                pts, labels = [], []
                values = iso.point_data.get("value")
                for level in data.levels:
                    idx = np.flatnonzero(np.isclose(values, level, rtol=1e-6, atol=1e-12)) if values is not None else []
                    if len(idx):
                        pts.append(iso.points[idx[len(idx) // 2]])
                        labels.append(f"{level:.3g}")
                if pts:
                    self.plotter.add_point_labels(np.array(pts), labels, font_size=10, point_size=1, shape=None,
                                                  text_color=colour, always_visible=True, show_points=False)

    def _draw_vectors(self, sol, scene, data, colours, mirror=False):
        cells = data.vector_cells
        pts = np.column_stack([sol.geom.cell_centres[cells, :2], np.zeros(len(cells))])
        vec = data.vectors[cells]
        mag = np.linalg.norm(vec, axis=1)
        span = np.ptp(sol.mesh.nodes[:, :2], axis=0).max()
        if scene.vector_fixed_length:
            vec = vec / np.where(mag > 0, mag, 1.0)[:, None]
            factor = 0.025 * span * scene.vector_scale
        else:
            factor = 0.05 * span * scene.vector_scale / max(float(mag.max()), 1e-300)
        cloud = pv.PolyData(pts)
        cloud["vec"] = vec
        kw = {"color": colours["text"]}
        if data.vector_colour is not None:
            cloud["colour"] = data.vector_colour[cells]
            kw = {"scalars": "colour", "cmap": "plasma", "show_scalar_bar": False}
        arrows = cloud.glyph(orient="vec", scale=False if scene.vector_fixed_length else "vec", factor=factor,
                             geom=pv.Arrow(tip_length=0.3, tip_radius=0.12, shaft_radius=0.035))
        self.plotter.add_mesh(arrows, reset_camera=False, **kw)
        if mirror:
            self.plotter.add_mesh(arrows.reflect((0.0, 1.0, 0.0), point=(0.0, 0.0, 0.0)), reset_camera=False, **kw)

    def _draw_streamlines(self, scene, data, colours, mirror=False):
        grid = self.grid.copy()
        grid.point_data["vel"] = data.node_velocity
        if data.stream_colour_node is not None:
            grid.point_data["scol"] = data.stream_colour_node
        span = float(np.ptp(self.mesh.nodes[:, :2], axis=0).max())
        lines = grid.streamlines_from_source(pv.PolyData(np.asarray(data.seeds, dtype=float)), vectors="vel",
                                             integration_direction="both", max_length=10.0 * span,
                                             initial_step_length=0.2, step_unit="cl", max_steps=20000)
        if lines.n_points == 0:
            return
        kw = {"color": colours["text"], "line_width": 1.6}
        if data.stream_colour_node is not None and "scol" in lines.point_data:
            kw = {"scalars": "scol", "cmap": "plasma", "line_width": 2.0, "show_scalar_bar": False}
        self.plotter.add_mesh(lines, reset_camera=False, **kw)
        if mirror:
            self.plotter.add_mesh(lines.reflect((0.0, 1.0, 0.0), point=(0.0, 0.0, 0.0)), reset_camera=False, **kw)
        if scene.stream_arrows and lines.n_points > 10:
            step = max(lines.n_points // 40, 1)
            marks = pv.PolyData(lines.points[::step])
            vel = lines.point_data["vel"][::step]
            marks["dir"] = vel / np.maximum(np.linalg.norm(vel, axis=1), 1e-300)[:, None]
            heads = marks.glyph(orient="dir", scale=False, factor=0.015 * span,
                                geom=pv.Cone(direction=(1, 0, 0), height=1.0, radius=0.35, resolution=8))
            self.plotter.add_mesh(heads, color=kw.get("color", colours["text"]), reset_camera=False)

    def _draw_revolved(self, sol, scene, data, common, bar):
        """Wall surface of revolution and the two meridian planes at 0 and the sweep angle (rotate about x)."""
        p = self.plotter
        angle = float(scene.revolve_angle)
        plane = self.grid
        kw = dict(common, show_scalar_bar=scene.bar_position != "Hidden", scalar_bar_args=bar)
        self.mesh_actor = p.add_mesh(plane, scalars="value", preference="point", interpolate_before_map=True, **kw)
        other = plane.rotate_x(angle, point=(0.0, 0.0, 0.0), inplace=False)
        p.add_mesh(other, scalars="value", preference="point", interpolate_before_map=True,
                   **dict(common, show_scalar_bar=False))
        walls = [k for k, pt in enumerate(sol.mesh.patches) if pt.type in ("wall", "inlet", "outlet", "farfield")]
        lines = self.lines
        keep = np.isin(lines.cell_data["patch"], walls)
        if keep.any():
            outer = lines.extract_cells(np.flatnonzero(keep)).extract_surface()
            outer.point_data["value"] = data.node[outer.point_data["vtkOriginalPointIds"]] \
                if "vtkOriginalPointIds" in outer.point_data else np.interp(outer.points[:, 0], self.mesh.nodes[:, 0],
                                                                             data.node)
            swept = outer.extrude_rotate(resolution=max(int(angle / 4), 8), angle=angle, rotation_axis=(1, 0, 0),
                                         capping=False)
            p.add_mesh(swept, scalars="value", interpolate_before_map=True, smooth_shading=True,
                       **dict(common, show_scalar_bar=False, show_edges=False))

    def draw_surfaces(self, surfaces):
        """Overlay surface data (post.surfaces.SurfaceData): segments as magenta lines, probe / seed points as dots."""
        for actor in self.surface_actors:
            self.plotter.remove_actor(actor)
        self.surface_actors = []
        for d in surfaces or ():
            if d.n == 0:
                continue
            if d.surface.type == "point":
                pts = np.column_stack([d.seeds, np.zeros(len(d.seeds))])
                self.surface_actors.append(self.plotter.add_points(pts, color=SURFACE_COLOUR, point_size=10,
                                                                   render_points_as_spheres=True, reset_camera=False))
                continue
            pts = np.column_stack([np.vstack([d.a, d.b]), np.zeros(2 * d.n)])
            n = d.n
            lines = np.column_stack([np.full(n, 2), np.arange(n), np.arange(n) + n]).ravel()
            self.surface_actors.append(self.plotter.add_mesh(pv.PolyData(pts, lines=lines), color=SURFACE_COLOUR,
                                                             line_width=3, reset_camera=False))
            if d.seeds is not None:
                seeds = np.column_stack([d.seeds, np.zeros(len(d.seeds))])
                self.surface_actors.append(self.plotter.add_points(seeds, color=SURFACE_COLOUR, point_size=8,
                                                                   render_points_as_spheres=True, reset_camera=False))
        self.plotter.render()

    # ---- mouse: hover, right click, two-click lines -------------------------------------------

    def _on_move(self, interactor, _event):
        if self.hover is None or self.mesh is None or (self.scene is not None and self.scene.revolve):
            return
        x, y = interactor.GetEventPosition()
        try:
            text = self.hover(*self.world_point(x, y))
        except Exception:      # noqa: BLE001 - a tooltip must never break the view
            text = ""
        if text:
            QToolTip.showText(QCursor.pos(), text, self)
        else:
            QToolTip.hideText()

    def pick(self, x, y):
        if self.line_start is not None:         # second click of a line surface
            x0, y0 = self.line_start
            x1, y1 = self.world_point(x, y)
            self.line_start = None
            self.line_surface_requested.emit(float(x0), float(y0), float(x1), float(y1))
            return
        xw, yw = self.world_point(x, y)
        self.clicked.emit(float(xw), float(yw))
        super().pick(x, y)

    def context_actions(self, menu, xy):
        """Results menu entries (world point xy)."""
        x, y = float(xy[0]), float(xy[1])
        menu.addAction("Probe here", lambda: self.probe_requested.emit(x, y))
        menu.addAction("Pin a probe here (point surface)", lambda: self.point_surface_requested.emit(x, y))
        menu.addAction("Start a line surface here (click the end point)", lambda: self._start_line(x, y))
        menu.addAction("Seed a streamline here", lambda: self.seed_requested.emit(x, y))
        menu.addSeparator()
        super().context_actions(menu, xy)

    def _start_line(self, x, y):
        self.line_start = (x, y)

    # ---- pictures ---------------------------------------------------------------------------

    def picture(self, path, scale=2, transparent=False, paper=True, surfaces=()):
        """Save the scene as PNG: `scale` x the window resolution, optional transparent background, light paper
        colours whatever the theme (redrawn, then the window's own colours are restored)."""
        if self.sol is None:
            return self.save_picture(path)
        camera = self.plotter.camera_position
        if paper and self.dark:
            self.draw(self.sol, self.scene, self.data, surfaces, keep_camera=True, paper=True)
            self.plotter.camera_position = camera
        self.plotter.screenshot(str(path), transparent_background=transparent, scale=int(scale))
        if paper and self.dark:
            self.draw(self.sol, self.scene, self.data, surfaces, keep_camera=True)
            self.plotter.camera_position = camera
            self.plotter.render()


class ViewGrid(QWidget):
    """1, 2 or 4 FlowViews with linked cameras (one shared vtkCamera)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.views = [FlowView(self)]
        self.layout_ = QGridLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(2)
        self.layout_.addWidget(self.views[0], 0, 0)
        self.count = 1
        self._link(self.views[0])

    def set_count(self, n):
        """Show n views (1, 2 or 4); extra views are created once and kept."""
        while len(self.views) < n:
            v = FlowView(self)
            v.set_dark(self.views[0].dark)
            self.views.append(v)
            self._link(v)
        for i, v in enumerate(self.views):
            self.layout_.removeWidget(v)
            v.setVisible(i < n)
        positions = {1: [(0, 0)], 2: [(0, 0), (0, 1)], 4: [(0, 0), (0, 1), (1, 0), (1, 1)]}[n]
        for v, (r, c) in zip(self.views, positions):
            self.layout_.addWidget(v, r, c)
        self.count = n

    def _link(self, view):
        first = self.views[0]
        if view is not first:
            view.plotter.renderer.camera = first.plotter.renderer.camera     # the same vtkCamera object

        def follow(*_args, source=view):
            for other in self.views[:self.count]:
                if other is not source and not other.closed:
                    other.plotter.render()
        view.plotter.iren.add_observer("InteractionEvent", follow)
        view.plotter.iren.add_observer("MouseWheelForwardEvent", follow)
        view.plotter.iren.add_observer("MouseWheelBackwardEvent", follow)

    def active(self):
        return self.views[: self.count]

    def set_dark(self, dark):
        for v in self.views:
            v.set_dark(dark)

    def close_views(self):
        for v in self.views:
            v.close_view()

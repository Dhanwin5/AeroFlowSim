# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Drawing with the mouse: one small state machine per sketch tool (no Qt, so tested without a window).

The view forwards mouse positions in world coordinates [m] with the pick tolerance; a tool
    move(xy, tol)   follows the cursor: snaps it (geometry_model/inference.py) for the rubber band
    click(xy, tol)  places a point (snapped); returns True when the shape is finished
    typed(text)     places a typed point (mm): "12, 5" absolute, "@3, 4" relative to the last point,
                    "25" a length along the cursor direction (a circle: its radius),
                    "25<30" a length and an angle [deg]
    finish()        ends an open shape (Enter, double-click or right-click)
    preview()       what to draw now: the shape so far plus the rubber band, guides, snap marker, label
    operation(role) the finished sketch as a SketchGroup history operation
Points are shared between entities (a polyline's lines meet in one point), so outlines are
exactly connected; clicking the first point again closes a polyline or spline into a face.
"""

import math
from dataclasses import dataclass, field

import numpy as np

from aeroflowsim.geometry_model.inference import Inference, infer
from aeroflowsim.geometry_model.operations import SketchGroup, arc_angles, entity_points

MM = 1e-3          # typed numbers are millimetres [m]


@dataclass
class Preview:
    lines: list = field(default_factory=list)        # [(n, 2)] the shape so far and the rubber band [m]
    points: list = field(default_factory=list)       # [(2,)] placed points
    guides: list = field(default_factory=list)       # [(a, b)] dashed helper lines
    marker: tuple = None                             # (point, kind) of the snap under the cursor
    label: str = ""                                  # e.g. "L 12.5 mm  30°"


def parse_typed(text, last=None, cursor=None):
    """A typed point (see the module docstring) -> (2,) [m]; ValueError with a message if unclear."""
    t = text.strip().replace(";", ",").replace(" ", "")
    if not t:
        raise ValueError("Type a point: x, y (mm), @dx, dy, a length, or length<angle.")
    try:
        if "<" in t:
            length, angle = (float(v) for v in t.split("<"))
            if last is None:
                raise ValueError("A length and angle need a first point; type x, y first.")
            a = math.radians(angle)
            return np.asarray(last) + length * MM * np.array([math.cos(a), math.sin(a)])
        if t.startswith("@"):
            dx, dy = (float(v) for v in t[1:].split(","))
            if last is None:
                raise ValueError("@dx, dy is relative to the last point; type x, y first.")
            return np.asarray(last) + np.array([dx, dy]) * MM
        if "," in t:
            x, y = (float(v) for v in t.split(","))
            return np.array([x, y]) * MM
        length = float(t)
    except ValueError as error:
        if "first point" in str(error) or "last point" in str(error):
            raise
        raise ValueError(f"'{text}' is not understood: use x, y   @dx, dy   length   or   length<angle.") from None
    if last is None:
        raise ValueError("A length needs a first point; type x, y first.")
    direction = None if cursor is None else np.asarray(cursor) - np.asarray(last)
    if direction is None or np.linalg.norm(direction) == 0.0:
        direction = np.array([1.0, 0.0])
    return np.asarray(last) + length * MM * direction / np.linalg.norm(direction)


class DrawTool:
    """What every drawing tool shares: points, entities, snapping, preview and the operation."""

    kind = ""
    title = ""
    help = ""
    count = None                                    # fixed number of clicks, or None (finish by hand)

    def __init__(self, built=None, grid=None):
        self.built, self.grid = built, grid
        self.points = []                            # placed points [(2,)] [m]
        self.entities = []                          # SketchGroup entities made so far
        self.clicks = []                            # indices of the points clicked, in order
        self.cursor = Inference(np.zeros(2))
        self.done = False

    # ---- input ----------------------------------------------------------------------------------

    @property
    def last(self):
        return self.points[self.clicks[-1]] if self.clicks else None

    def _segments(self):
        out = []
        for e in self.entities:
            if e["type"] == "line":
                out.append((self.points[e["p"][0]], self.points[e["p"][1]]))
        return out

    def snap(self, xy, tol) -> Inference:
        return infer(self.built, xy, tol, self.last, self.points, self.grid, self._segments())

    def move(self, xy, tol):
        self.cursor = self.snap(xy, tol)

    def click(self, xy, tol) -> bool:
        self.cursor = self.snap(xy, tol)
        return self.place(self.cursor.point)

    def typed(self, text) -> bool:
        return self.place(parse_typed(text, self.last, self.cursor.point if self.clicks else None))

    def _index(self, point) -> int:
        """The number of a point (an existing sketch point at the same place is reused)."""
        point = np.asarray(point, dtype=float)
        for k, q in enumerate(self.points):
            if np.allclose(q, point, rtol=0.0, atol=1e-12 * max(1.0, float(np.abs(point).max()))):
                return k
        self.points.append(point)
        return len(self.points) - 1

    def place(self, point) -> bool:
        self.clicks.append(self._index(point))
        self.on_point()
        if self.count is not None and len(self.clicks) >= self.count:
            self.done = True
        return self.done

    def on_point(self):
        """Called after every placed point (makes the entities)."""

    def finish(self) -> bool:
        self.done = bool(self.entities)
        return self.done

    # ---- output ---------------------------------------------------------------------------------

    def rubber_band(self):
        """[(n, 2)] lines from the last point to the cursor (what the next click would make)."""
        return [] if self.last is None else [np.array([self.last, self.cursor.point])]

    def label(self) -> str:
        if self.last is None:
            return ""
        d = self.cursor.point - self.last
        return f"L {np.linalg.norm(d) / MM:.4g} mm   {math.degrees(math.atan2(d[1], d[0])):.3g}°"

    def preview(self) -> Preview:
        pts = np.array(self.points) if self.points else np.zeros((0, 2))
        lines = [entity_points(pts, e) for e in self.entities] + ([] if self.done else self.rubber_band())
        text = " ".join(t for t in (self.cursor.label, self.label()) if t)
        marker = (self.cursor.point, self.cursor.kind) if self.cursor.kind else None
        return Preview(lines, list(pts), list(self.cursor.guides), marker, text)

    def add_to(self, document, role="solid"):
        """Add the finished shape to a history; returns the (last) operation added, or None."""
        op = self.operation(role)
        return None if op is None else document.add(op)

    def operation(self, role="solid"):
        """The finished drawing as a SketchGroup (None if nothing was drawn)."""
        if not self.entities:
            return None
        return SketchGroup(points=[[float(x), float(y)] for x, y in self.points], entities=self.entities,
                           role=role)

    @property
    def closed(self) -> bool:
        """True if the drawing makes a face (asks for fluid / solid)."""
        return False


class PolylineTool(DrawTool):
    """Lines from point to point; click the first point again to close it (a face). With arc_next on,
    the next segment is a tangent arc (continuing smoothly from the previous one)."""

    kind, title = "polyline", "Line / polyline"
    help = ("Click points (Tab: type a length, x, y or length<angle). Click the first point to close; Enter, "
            "double-click or right-click to finish. A: next segment is a tangent arc.")

    def __init__(self, built=None, grid=None):
        super().__init__(built, grid)
        self.arc_next = False
        self._closed = False

    def tangent(self):
        """The direction at the end of the last entity (for a tangent arc), or None."""
        if not self.entities:
            return None
        e = self.entities[-1]
        if e["type"] == "line":
            a, b = (self.points[i] for i in e["p"])
            return (b - a) / max(np.linalg.norm(b - a), 1e-300)
        pts = entity_points(self.points, e)
        if e.get("reversed"):
            pts = pts[::-1]
        d = pts[-1] - pts[-2]
        return d / max(np.linalg.norm(d), 1e-300)

    def tangent_arc(self, start, end):
        """(centre, counter-clockwise?) of the arc from start to end tangent to self.tangent() at start."""
        t = self.tangent()
        n = np.array([-t[1], t[0]])                   # left normal
        chord = end - start
        denom = 2.0 * (chord @ n)
        if abs(denom) < 1e-300:
            return None, True
        radius = (chord @ chord) / denom              # signed: > 0 the centre is on the left (ccw)
        return start + radius * n, radius > 0

    def on_point(self):
        if len(self.clicks) < 2:
            return
        i, j = self.clicks[-2], self.clicks[-1]
        if i == j:
            self.clicks.pop()
            return
        if self.arc_next and self.entities:
            centre, ccw = self.tangent_arc(self.points[i], self.points[j])
            if centre is None:                         # straight on: a line
                self.entities.append({"type": "line", "p": [i, j]})
            else:
                c = self._index(centre)
                self.entities.append({"type": "arc", "p": [i, j] if ccw else [j, i], "c": c,
                                      **({} if ccw else {"reversed": True})})
            self.arc_next = False
        else:
            self.entities.append({"type": "line", "p": [i, j]})
        if j == self.clicks[0] and len(self.clicks) > 2:  # back at the first point: closed
            self._closed = True
            self.done = True

    def rubber_band(self):
        if self.last is None:
            return []
        if self.arc_next and self.entities:
            centre, ccw = self.tangent_arc(self.last, self.cursor.point)
            if centre is not None:
                pts = [self.last, self.cursor.point] if ccw else [self.cursor.point, self.last]
                return [entity_points([pts[0], pts[1], centre], {"type": "arc", "p": [0, 1], "c": 2})]
        return super().rubber_band()

    @property
    def closed(self) -> bool:
        return self._closed

    def operation(self, role="solid"):
        op = super().operation(role)
        if op is not None:
            for e in op.params["entities"]:
                e.pop("reversed", None)
        return op


class SplineTool(DrawTool):
    kind, title = "spline", "Spline"
    help = "Click the points the smooth curve goes through; click the first point to close it; Enter to finish."

    def on_point(self):
        if len(self.clicks) >= 2 and self.clicks[-1] == self.clicks[0]:
            self.done = True

    def finish(self) -> bool:
        if len(self.clicks) >= 2:
            self.entities = [{"type": "spline", "p": list(self.clicks)}]
            self.done = True
        return self.done

    def place(self, point) -> bool:
        done = super().place(point)
        if done:
            self.entities = [{"type": "spline", "p": list(self.clicks)}]
        return done

    def preview(self) -> Preview:
        pv = super().preview()
        if len(self.clicks) >= 1 and not self.done:
            from scipy.interpolate import CubicSpline
            pts = np.array([self.points[i] for i in self.clicks] + [self.cursor.point])
            if len(pts) >= 3:
                s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
                if np.all(np.diff(s) > 0):
                    t = np.linspace(0.0, s[-1], 120)
                    pv.lines = [np.column_stack([CubicSpline(s, pts[:, 0])(t), CubicSpline(s, pts[:, 1])(t)])]
                    return pv
            pv.lines = [pts]
        return pv

    @property
    def closed(self) -> bool:
        return len(self.clicks) > 2 and self.clicks[-1] == self.clicks[0]


class Arc3Tool(DrawTool):
    kind, title, count = "arc3", "Arc (3 points)", 3
    help = "Click the start, a point on the arc, and the end."

    def on_point(self):
        if len(self.clicks) == 3:
            s, m, e = (self.points[i] for i in self.clicks)
            centre = _circumcentre(s, m, e)
            if centre is None:
                self.clicks.pop()
                raise ValueError("The three points lie on a straight line; click another point.")
            c = self._index(centre)
            a0, sweep = arc_angles(centre, s, e)
            am = (math.atan2(m[1] - centre[1], m[0] - centre[0]) - a0) % (2.0 * math.pi)
            p = [self.clicks[0], self.clicks[2]] if am < sweep else [self.clicks[2], self.clicks[0]]
            self.entities = [{"type": "arc", "p": p, "c": c}]

    def rubber_band(self):
        if len(self.clicks) == 2:
            s, m = (self.points[i] for i in self.clicks)
            centre = _circumcentre(s, m, self.cursor.point)
            if centre is not None:
                a0, sweep = arc_angles(centre, s, self.cursor.point)
                am = (math.atan2(m[1] - centre[1], m[0] - centre[0]) - a0) % (2.0 * math.pi)
                pts = [s, self.cursor.point] if am < sweep else [self.cursor.point, s]
                return [entity_points([pts[0], pts[1], centre], {"type": "arc", "p": [0, 1], "c": 2})]
        return super().rubber_band()


class ArcTool(DrawTool):
    kind, title, count = "arc", "Arc (centre and ends)", 3
    help = "Click the centre, the start, and the end (counter-clockwise from the start)."

    def place(self, point) -> bool:
        if len(self.clicks) == 2:                       # the end lies on the circle through the start
            c, s = (self.points[i] for i in self.clicks)
            r = np.linalg.norm(s - c)
            d = np.asarray(point) - c
            point = c + r * d / max(np.linalg.norm(d), 1e-300)
        return super().place(point)

    def on_point(self):
        if len(self.clicks) == 3:
            c, s, e = self.clicks
            self.entities = [{"type": "arc", "p": [s, e], "c": c}]

    def label(self) -> str:
        if len(self.clicks) >= 1:
            return f"R {np.linalg.norm(self.cursor.point - self.points[self.clicks[0]]) / MM:.4g} mm" \
                if len(self.clicks) == 1 else ""
        return ""

    def rubber_band(self):
        if len(self.clicks) == 2:
            c, s = (self.points[i] for i in self.clicks)
            return [entity_points([s, self.cursor.point, c], {"type": "arc", "p": [0, 1], "c": 2})]
        return super().rubber_band()


class CircleTool(DrawTool):
    kind, title, count = "circle", "Circle", 2
    help = "Click the centre and a point on the circle (or type the radius in mm)."

    def typed(self, text) -> bool:
        if self.clicks and "," not in text and "<" not in text and not text.strip().startswith("@"):
            r = float(text.replace(",", ".")) * MM                 # a single number: the radius
            return self.place(self.last + np.array([r, 0.0]))
        return super().typed(text)

    def on_point(self):
        if len(self.clicks) == 2:
            c, q = (self.points[i] for i in self.clicks)
            self.entities = [{"type": "circle", "c": self.clicks[0], "r": float(np.linalg.norm(q - c))}]

    def label(self) -> str:
        return "" if self.last is None else f"R {np.linalg.norm(self.cursor.point - self.last) / MM:.4g} mm"

    def rubber_band(self):
        if self.last is None:
            return []
        r = np.linalg.norm(self.cursor.point - self.last)
        return [entity_points([self.last], {"type": "circle", "c": 0, "r": max(r, 1e-300)})]

    @property
    def closed(self) -> bool:
        return True


class RectangleTool(DrawTool):
    kind, title, count = "rectangle", "Rectangle", 2
    help = "Click two opposite corners (or type @width, height for the second)."

    def on_point(self):
        if len(self.clicks) == 2:
            (x0, y0), (x1, y1) = (self.points[i] for i in self.clicks)
            corners = [self._index((x, y)) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            self.entities = [{"type": "line", "p": [corners[k], corners[(k + 1) % 4]]} for k in range(4)]

    def label(self) -> str:
        if self.last is None:
            return ""
        d = np.abs(self.cursor.point - self.last) / MM
        return f"{d[0]:.4g} x {d[1]:.4g} mm"

    def rubber_band(self):
        if self.last is None:
            return []
        (x0, y0), (x1, y1) = self.last, self.cursor.point
        return [np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]])]

    @property
    def closed(self) -> bool:
        return True


class Rectangle3Tool(DrawTool):
    kind, title, count = "rectangle3", "Rectangle (3 points, rotated)", 3
    help = "Click two corners of one side, then the width (the third click)."

    def _corners(self, third):
        a, b = (self.points[i] for i in self.clicks[:2])
        side = b - a
        n = np.array([-side[1], side[0]]) / max(np.linalg.norm(side), 1e-300)
        w = (np.asarray(third) - a) @ n
        return [a, b, b + w * n, a + w * n]

    def on_point(self):
        if len(self.clicks) == 3:
            corners = self._corners(self.points[self.clicks[2]])
            idx = [self._index(c) for c in corners]
            self.entities = [{"type": "line", "p": [idx[k], idx[(k + 1) % 4]]} for k in range(4)]

    def rubber_band(self):
        if len(self.clicks) == 2:
            c = self._corners(self.cursor.point)
            return [np.array(c + [c[0]])]
        return super().rubber_band()

    @property
    def closed(self) -> bool:
        return True


class ConstructionTool(DrawTool):
    kind, title, count = "construction", "Construction line", 2
    help = "Click two points of a helper line (drawn dashed, used for snapping, not part of the geometry)."

    def on_point(self):
        if len(self.clicks) == 2:
            self.entities = [{"type": "line", "p": list(self.clicks), "construction": True}]


class PickTool(DrawTool):
    """A one-click editing tool (Trim, Extend): highlights the curve under the cursor; a click makes
    the operation there and the tool stays on for the next click."""

    count = 1

    def snap(self, xy, tol):                         # (no snapping: the click position itself counts)
        return Inference(np.asarray(xy, dtype=float))

    def target(self):
        """(edge id, points) of the edge nearest to the cursor, or None."""
        from aeroflowsim.geometry_model.picking import nearest_edge
        if self.built is None or not self.built.edges:
            return None
        hit = nearest_edge(self.built, self.cursor.point, np.inf)
        return None if hit is None else (hit[0], self.built.edges[hit[0]].points)

    def preview(self) -> Preview:
        hit = self.target()
        return Preview([hit[1]] if hit else [], [], [], None, self.title)

    def place(self, point) -> bool:
        self.points, self.clicks = [np.asarray(point, dtype=float)], [0]
        self.done = True
        self.entities = [{}]                             # (something to add)
        return True


class TrimTool(PickTool):
    kind, title = "trim", "Trim"
    help = "Click the piece of a curve to remove (between the points where it crosses other curves)."

    def operation(self, role="solid"):
        from aeroflowsim.geometry_model.edit_operations import Trim
        x, y = self.points[0]
        return Trim(x=float(x), y=float(y))


class ExtendTool(PickTool):
    kind, title = "extend", "Extend"
    help = "Click near the end of a straight free line: it is lengthened up to the next curve."

    def operation(self, role="solid"):
        from aeroflowsim.geometry_model.edit_operations import Extend
        self.cursor = Inference(self.points[0])
        hit = self.target()
        if hit is None:
            return None
        x, y = self.points[0]
        return Extend(edge=hit[0], x=float(x), y=float(y))


class SplitLineTool(DrawTool):
    kind, title, count = "split_line", "Split by line", 2
    help = "Draw a line across a face (two clicks, or press - drag - release): the face is split along it."

    def on_point(self):
        if len(self.clicks) == 2:
            self.entities = [{"type": "line", "p": list(self.clicks)}]

    def add_to(self, document, role="solid"):
        """Two history steps: the line, and the split along it."""
        from aeroflowsim.geometry_model.edit_operations import SplitFace
        sketch = document.add(self.operation(role))
        return document.add(SplitFace(curves=[f"{sketch.id}:e1"]))


def _circumcentre(a, b, c):
    d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-300 * max(1.0, float(np.abs([a, b, c]).max())) or abs(d) < 1e-24:
        return None
    sq = [q @ q for q in (np.asarray(a), np.asarray(b), np.asarray(c))]
    return np.array([(sq[0] * (b[1] - c[1]) + sq[1] * (c[1] - a[1]) + sq[2] * (a[1] - b[1])) / d,
                     (sq[0] * (c[0] - b[0]) + sq[1] * (a[0] - c[0]) + sq[2] * (b[0] - a[0])) / d])


TOOLS = {cls.kind: cls for cls in (PolylineTool, Arc3Tool, ArcTool, SplineTool, RectangleTool, Rectangle3Tool,
                                   CircleTool, ConstructionTool)}
EDIT_TOOLS = {cls.kind: cls for cls in (SplitLineTool, TrimTool, ExtendTool)}     # started from the Edit menu

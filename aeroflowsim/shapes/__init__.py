# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The shape library: bodies to put in a free stream (airfoils, wedges, nose cones, blunt bodies ...).

Every shape is TWO files in this folder, with the same name:

    wedge.toml   what the shape is and which inputs it has (no code):
                     [shape]
                     name = "Wedge"                         # shown in the Shape dropdown
                     group = "Supersonic airfoils"          # one of GROUPS below
                     symmetry = "planar"                    # planar, axisymmetric or either
                     description = "..."
                     [[input]]                              # same format as a case's schema.toml
                     key = "half_angle"  ...
    wedge.py     a function  profile(inputs) -> ShapeProfile  (aeroflowsim/shapes/profile.py).
                 inputs is a dict {key: value} with the shape's own inputs.

The registry below finds every such pair automatically. A case that says shape_library = true in
its schema.toml gets a "Shape" dropdown listing every shape, followed by the inputs of all shapes
(each shown only when its shape is chosen, keys prefixed with the shape's file name, e.g.
"wedge.half_angle"). So adding a shape needs no GUI code and no change to any case.
"""

import importlib
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from aeroflowsim.parameters import Parameter
from aeroflowsim.schema import parse_inputs
from aeroflowsim.shapes.profile import ShapeProfile

SHAPES_DIR = Path(__file__).resolve().parent
SHAPE_KEY = "shape"          # key of the Shape dropdown in a case's inputs
SHAPE_GROUP = "Shape"        # heading of the shape inputs in the GUI
GROUPS = ("Supersonic airfoils", "Subsonic airfoils", "Nose cones", "Blunt bodies", "Nozzles", "Intakes",
          "Custom")          # dropdown order
SYMMETRIES = ("planar", "axisymmetric", "either")
NOT_SHAPES = {"profile"}     # .py files here that are helpers, not shapes


@dataclass
class Shape:
    """One entry of the shape library."""

    key: str            # file name without .py, e.g. "naca4"; prefix of its input keys
    name: str           # shown in the dropdown, e.g. "NACA 4-digit airfoil"
    group: str          # one of GROUPS
    symmetry: str       # "planar", "axisymmetric" or "either" (chosen by an input)
    description: str
    inputs: list        # list of Parameter (the shape's own keys, without prefix)
    module: object      # the imported shape module (has profile(inputs))

    def profile(self, inputs: dict) -> ShapeProfile:
        """The outline for these inputs {own key: value}."""
        outline = self.module.profile(inputs)
        if not outline.name:
            outline.name = self.name
        return outline


def _load_shape(toml_file: Path) -> Shape:
    """Read one shape's .toml and import its .py; ValueError naming the file if anything is wrong."""
    key = toml_file.stem
    try:
        with open(toml_file, "rb") as file:
            data = tomllib.load(file)
        info = data["shape"]
        for name in ("name", "group", "symmetry", "description"):
            if not isinstance(info.get(name), str):
                raise ValueError(f"[shape] needs '{name}' (text).")
        if info["group"] not in GROUPS:
            raise ValueError(f"group '{info['group']}' is not one of {', '.join(GROUPS)}.")
        if info["symmetry"] not in SYMMETRIES:
            raise ValueError(f"symmetry '{info['symmetry']}' is not one of {', '.join(SYMMETRIES)}.")
        inputs = parse_inputs(data.get("input", []))
        module = importlib.import_module(f"aeroflowsim.shapes.{key}")
        if not callable(getattr(module, "profile", None)):
            raise ValueError(f"{key}.py has no function profile(inputs).")
    except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError, ImportError) as error:
        raise ValueError(f"Shape '{toml_file.name}': {error}") from None
    return Shape(key, info["name"], info["group"], info["symmetry"], info["description"], inputs, module)


@lru_cache(maxsize=1)
def find_shapes() -> dict:
    """{key: Shape} for every shape in this folder, in dropdown order (group, then name)."""
    shapes = [_load_shape(f) for f in sorted(SHAPES_DIR.glob("*.toml")) if f.stem not in NOT_SHAPES]
    shapes.sort(key=lambda s: (GROUPS.index(s.group), s.name))
    return {s.key: s for s in shapes}


def shape_by_name(name: str) -> Shape:
    """The Shape whose display name is `name` (as chosen in the dropdown)."""
    for shape in find_shapes().values():
        if shape.name == name:
            return shape
    raise ValueError(f"Unknown shape '{name}'. Known shapes: {', '.join(s.name for s in find_shapes().values())}")


def shape_parameters() -> list[Parameter]:
    """The inputs a case with shape_library = true gets: the Shape dropdown, then every shape's inputs.

    Each shape input becomes "<shape key>.<input key>" and is shown only when its shape is chosen
    (or, if it already has a show_if inside its shape, when that one holds - which in turn needs
    the shape to be chosen).
    """
    shapes = list(find_shapes().values())
    names = [s.name for s in shapes]
    help_text = "Body in the free stream. " + " ".join(f"{s.name}: {s.description}" for s in shapes)
    params = [Parameter(SHAPE_KEY, "Shape", "", names[0], type="choice", options=tuple(names),
                        help=help_text, group=SHAPE_GROUP)]
    for s in shapes:
        for p in s.inputs:
            show_if = (f"{s.key}.{p.show_if[0]}", p.show_if[1]) if p.show_if else (SHAPE_KEY, s.name)
            params.append(Parameter(
                f"{s.key}.{p.name}", p.label, p.unit, p.default, p.min, p.max, p.help, p.type, p.options,
                show_if, SHAPE_GROUP, p.file_types, dict(p.requires), p.pattern))
    return params


def make_profile(params: dict) -> ShapeProfile:
    """The ShapeProfile of the shape chosen in params["shape"], from its prefixed inputs."""
    shape = shape_by_name(params[SHAPE_KEY])
    prefix = shape.key + "."
    own = {k[len(prefix):]: v for k, v in params.items() if k.startswith(prefix)}
    return shape.profile(own)

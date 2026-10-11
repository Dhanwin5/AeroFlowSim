"""Containers for what a case returns after solving."""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Field:
    """One solution field on the mesh nodes, e.g. temperature."""

    values: np.ndarray  # one value per mesh node, in SI units
    unit: str           # SI unit as text, e.g. "K"
    label: str          # human-readable name, e.g. "Temperature"


@dataclass
class Result:
    """Everything a case's run() returns."""

    fields: dict[str, Field]  # solution fields, keyed by short name, e.g. {"T": Field(...)}
    residuals: list[float]    # residual after each iteration (normalised, -)
    key_numbers: dict[str, tuple[float, str]] = field(default_factory=dict)  # name -> (value, unit)
    iterations: int = 0       # number of iterations performed
    converged: bool = False   # True if the residual dropped below the tolerance

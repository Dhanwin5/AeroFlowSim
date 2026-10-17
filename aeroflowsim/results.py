"""Containers for what a case returns after solving."""

from dataclasses import dataclass, field

import numpy as np

from aeroflowsim.geometry import WallProfile


@dataclass
class Field:
    """One solution field on the mesh, e.g. temperature."""

    values: np.ndarray  # one value per mesh node, or one per cell (finite volumes), in SI units
                        # (in Snapshots: one row per stored time, shape (n_times, n_x))
    unit: str           # SI unit as text, e.g. "K"
    label: str          # human-readable name, e.g. "Temperature"


@dataclass
class Line:
    """A line to draw on top of a plot, e.g. an exact wave path x = x0 + S t in an x-t diagram."""

    label: str        # legend text, e.g. "shock (exact)"
    x: np.ndarray     # horizontal coordinates [m]
    y: np.ndarray     # vertical coordinates (time [s] in an x-t diagram, or [m])
    style: str = "-"  # matplotlib line style, e.g. "-", "--", ":"


@dataclass
class Snapshots:
    """Fields stored at several moments of an unsteady run (for x-t diagrams)."""

    times: np.ndarray          # stored times [s], increasing, shape (n_times,)
    fields: dict[str, Field]   # same keys as Result.fields; values shape (n_times, n_x)


class SnapshotRecorder:
    """Collects snapshots during a time-marching loop, keeping at most max_snapshots of them.

    It stores every `every`-th step. When the store is full, every second snapshot is
    dropped and `every` doubles, so the kept snapshots stay roughly evenly spread over the
    run whatever the (unknown in advance) number of steps. The first and final states are kept.
    """

    def __init__(self, max_snapshots=200):
        self.max_snapshots = max_snapshots  # upper limit on stored snapshots [-]
        self.every = 1                      # store every `every`-th step [-]
        self._steps = []                    # step number of each stored snapshot
        self._times = []                    # time of each stored snapshot [s]
        self._fields = []                   # dict[str, Field] of each stored snapshot

    def add(self, step, t, fields):
        """Offer the state after `step` steps at time t [s]; stored only if step is a multiple of `every`."""
        if step % self.every != 0:
            return
        self._store(step, t, fields)
        if len(self._steps) > self.max_snapshots:
            # Thin out: keep the snapshots at multiples of the doubled interval (step 0 always stays).
            self.every *= 2
            keep = [i for i, s in enumerate(self._steps) if s % self.every == 0]
            self._steps = [self._steps[i] for i in keep]
            self._times = [self._times[i] for i in keep]
            self._fields = [self._fields[i] for i in keep]

    def add_final(self, step, t, fields):
        """Always store the final state (replacing a snapshot already stored for the same step)."""
        if self._steps and self._steps[-1] == step:
            self._steps.pop(), self._times.pop(), self._fields.pop()
        elif len(self._steps) >= self.max_snapshots:
            self._steps.pop(), self._times.pop(), self._fields.pop()  # make room, stay within the limit
        self._store(step, t, fields)

    def _store(self, step, t, fields):
        # Copy the arrays: the solver may keep changing its own arrays in place.
        self._steps.append(step)
        self._times.append(float(t))
        self._fields.append({k: f.values.copy() for k, f in fields.items()})
        self._meta = {k: (f.unit, f.label) for k, f in fields.items()}

    def snapshots(self) -> Snapshots:
        """All stored snapshots as one Snapshots object."""
        fields = {k: Field(values=np.array([snap[k] for snap in self._fields]), unit=unit, label=label)
                  for k, (unit, label) in self._meta.items()}
        return Snapshots(times=np.array(self._times), fields=fields)


@dataclass
class Result:
    """Everything a case's run() returns."""

    fields: dict[str, Field]  # solution fields, keyed by short name, e.g. {"T": Field(...)}
    residuals: list[float]    # residual after each iteration (normalised, -)
    key_numbers: dict[str, tuple[float, str]] = field(default_factory=dict)  # name -> (value, unit)
    iterations: int = 0       # number of iterations performed
    converged: bool = False   # True if the residual dropped below the tolerance
    # Optional extras (None = not provided):
    snapshots: Snapshots | None = None   # fields over time (unsteady cases) -> x-t diagram
    shape: WallProfile | None = None     # outline r(x) for the shape view
    shape_note: str | None = None        # second title line of the shape view (None = default text)

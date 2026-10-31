# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Flow animation: frames of the flow recorded during a run, played back and saved as GIF / MP4 (no Qt, no VTK).

What a frame is
    2D runs: the primitive state (rho, u, v, p) of every cell at one iteration, stored as float32 (half the size of
    float64; plenty for pictures, never used for numbers). Every other field (Mach number, T, p0, schlieren, custom
    fields) is computed from these four when a frame is shown, exactly as for the final result. For a steady run
    the frames show the pseudo-time convergence (start-up transient to steady state); for a time-accurate run the
    real time evolution.
    1D unsteady runs (Sod shock tube): the case's own snapshots (Result.snapshots, every field over x and time).

Recording (FrameRecorder, called by the Euler solver)
    "every" = 0 (automatic, the default): record every iteration, and whenever more than MAX_AUTO_FRAMES frames are
    stored, drop every second one and record half as often (every 1, 2, 4, 8, ... iterations). The number of
    iterations is not known in advance (a steady run stops when it has converged), so this keeps 50 to 100 frames
    evenly spread over ANY run length. "every" = N > 0: every N-th iteration (thinned the same way only beyond
    MAX_FRAMES, or the memory limit). The first state (iteration 0) and the final state are always kept.

Storage: <project>/results/animation.npz next to run.npz (written and cleared with it by result_io.save_run), so it
    is out of date exactly when the results are. A continued run carries the frames on (appends); Start from scratch
    starts a new set; a run with recording off removes the file.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ANIMATION_FILE = "animation.npz"
PRIMITIVES = ("rho", "u", "v", "p")
MAX_AUTO_FRAMES = 100         # automatic mode keeps between 50 and 100 frames
MAX_FRAMES = 1000             # a fixed "every N" is thinned beyond this many frames
MAX_BYTES = 400e6             # ... or beyond this much memory [bytes] (float32 frames of a large mesh)
DEFAULT_SETTINGS = {"record": True, "every": 0}     # the project's post["animation"] (0 = automatic)


@dataclass
class Animation:
    """Recorded frames of one run."""

    iterations: np.ndarray            # (n,) iteration number of each frame (0 = the initial state)
    times: np.ndarray                 # (n,) physical time [s] (0 for steady runs)
    fields: dict                      # {name: (n, C) float32 values per frame and cell (SI)}
    every: int = 1                    # recording interval reached (a continued run carries on with it)
    mesh_signature: str | None = None # the mesh the frames belong to (euler.setup.mesh_signature)
    steady: bool = True               # True: label frames by iteration; False: by physical time
    x: np.ndarray | None = None       # 1D frames: cell centres [m]

    @property
    def n(self) -> int:
        return len(self.iterations)

    def frame(self, i) -> dict:
        """{name: float64 values} of frame i."""
        return {k: np.asarray(v[i], dtype=float) for k, v in self.fields.items()}


# ---- recording ----------------------------------------------------------------------------------------

class FrameRecorder:
    """Collects frames during a run (see the module text). Used by EulerSolver.solve()."""

    def __init__(self, every=0, n_cells=1, previous=None, steady=True, mesh_signature=None):
        self.auto = int(every) <= 0
        self.every = 1 if self.auto else int(every)
        self.cap = MAX_AUTO_FRAMES if self.auto else MAX_FRAMES
        self.cap = max(4, min(self.cap, int(MAX_BYTES / (16.0 * max(n_cells, 1)))))
        self.steady, self.signature = steady, mesh_signature
        self.its, self.times, self.frames = [], [], []
        if previous is not None and previous.n:           # a continued run appends to the earlier frames
            self.every = max(int(previous.every), self.every if not self.auto else 1)
            self.its = [int(i) for i in previous.iterations]
            self.times = [float(t) for t in previous.times]
            self.frames = [np.stack([previous.fields[k][j] for k in PRIMITIVES]).astype(np.float32)
                           for j in range(previous.n)]

    def due(self, it) -> bool:
        return it % self.every == 0

    def add(self, it, t, W):
        """Store the state W (n_vars, C) of iteration it at time t [s]."""
        if self.its and self.its[-1] >= it:                # never twice the same iteration
            return
        self.its.append(int(it))
        self.times.append(float(t))
        self.frames.append(np.asarray(W, dtype=np.float32).copy())
        if len(self.frames) > self.cap:
            self._thin()

    def _thin(self):
        """Keep the frames on the doubled interval (and the first one); record half as often from now on."""
        self.every *= 2
        keep = [j for j, it in enumerate(self.its) if j == 0 or it % self.every == 0]
        self.its = [self.its[j] for j in keep]
        self.times = [self.times[j] for j in keep]
        self.frames = [self.frames[j] for j in keep]

    def rewind(self, it):
        """Forget the frames after iteration it (the solver went back to its last good state)."""
        while self.its and self.its[-1] > it:
            self.its.pop()
            self.times.pop()
            self.frames.pop()

    def animation(self, it, t, W) -> Animation:
        """The frames with the final state (iteration it) as the last one."""
        self.add(it, t, W)
        stack = np.stack(self.frames) if self.frames else np.zeros((0, len(PRIMITIVES), np.shape(W)[1]), np.float32)
        return Animation(iterations=np.array(self.its, dtype=np.int64), times=np.array(self.times, dtype=float),
                         fields={k: stack[:, j, :] for j, k in enumerate(PRIMITIVES)}, every=self.every,
                         mesh_signature=self.signature, steady=self.steady)


def recorder_for(settings, mesh, previous=None, steady=True):
    """A FrameRecorder for the project's animation settings ({"record", "every"}), or None when recording is off or
    there are no settings (a run outside a project: scripts and the validation suite record nothing).
    previous: the frames of the run this one continues (kept only when they belong to the same mesh)."""
    if settings is None:
        return None
    s = {**DEFAULT_SETTINGS, **settings}
    if not s.get("record", True):
        return None
    from aeroflowsim.euler.setup import mesh_signature
    signature = mesh_signature(mesh)
    if previous is not None and previous.mesh_signature not in (None, signature):
        previous = None
    return FrameRecorder(int(s.get("every") or 0), mesh.n_cells, previous, steady, signature)


# ---- files --------------------------------------------------------------------------------------------

def save_animation(folder, animation) -> Path:
    """Write <folder>/animation.npz (no pickle)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ANIMATION_FILE
    arrays = {f"fields/{k}": np.asarray(v, dtype=np.float32) for k, v in animation.fields.items()}
    if animation.x is not None:
        arrays["x"] = np.asarray(animation.x, dtype=float)
    np.savez_compressed(path, iterations=np.asarray(animation.iterations, dtype=np.int64),
                        times=np.asarray(animation.times, dtype=float), every=np.array(int(animation.every)),
                        steady=np.array(bool(animation.steady)),
                        signature=np.array(animation.mesh_signature or ""), **arrays)
    return path


def load_animation(folder):
    """The Animation stored in <folder>/animation.npz, or None (no file, or an unreadable one)."""
    path = Path(folder) / ANIMATION_FILE
    if not path.is_file():
        return None
    try:
        with np.load(path, allow_pickle=False) as data:
            fields = {k[len("fields/"):]: data[k] for k in data.files if k.startswith("fields/")}
            return Animation(iterations=data["iterations"], times=data["times"], fields=fields,
                             every=int(data["every"]), mesh_signature=str(data["signature"]) or None,
                             steady=bool(data["steady"]), x=data["x"] if "x" in data.files else None)
    except (OSError, ValueError, KeyError):
        return None


def clear_animation(folder):
    path = Path(folder) / ANIMATION_FILE
    if path.is_file():
        path.unlink()


def from_snapshots(result, mesh=None):
    """The Animation of a 1D unsteady result's snapshots (Sod shock tube), or None when it has none."""
    snaps = getattr(result, "snapshots", None)
    if snaps is None or len(snaps.times) < 2:
        return None
    x = np.asarray(mesh.x, dtype=float) if mesh is not None and hasattr(mesh, "x") else None
    return Animation(iterations=np.arange(len(snaps.times)), times=np.asarray(snaps.times, dtype=float),
                     fields={k: np.asarray(f.values) for k, f in snaps.fields.items()}, steady=False, x=x)


def project_animation(project, payload=None, mesh=None):
    """The animation of a project's current result: its recorded 2D frames, or a 1D result's snapshots; None if
    there is none (an old project, recording off) or the frames belong to another mesh."""
    payload = payload if payload is not None else project.load_results()
    if payload is None:
        return None
    result = payload["result"]
    if getattr(result, "snapshots", None) is not None:
        return from_snapshots(result, mesh if mesh is not None else payload.get("mesh1d"))
    anim = load_animation(project.results_dir)
    if anim is None or not anim.n:
        return None
    if mesh is not None and hasattr(mesh, "n_cells"):
        from aeroflowsim.euler.setup import mesh_signature
        if anim.mesh_signature not in (None, mesh_signature(mesh)) or anim.fields["rho"].shape[1] != mesh.n_cells:
            return None
    return anim


# ---- playback (shared by the GUI and the exports) -----------------------------------------------------

RANGE_ALL, RANGE_FRAME = "Fixed over all frames", "Per frame"


def frame_label(animation, i) -> str:
    """'Iteration 120  (frame 6 of 80)' or 't = 0.1234 s  (frame 6 of 80)'."""
    count = f"frame {i + 1} of {animation.n}"
    if animation.steady:
        return f"Iteration {int(animation.iterations[i]):,}  ({count})"
    return f"t = {animation.times[i]:.4g} s  ({count})"


def frame_solution(sol, animation, i):
    """The post.Solution of frame i (2D): the run's mesh, gas and conditions with the frame's fields."""
    return sol.with_fields(animation.frame(i), name=f"frame {i + 1}")


def field_range(sol, animation, name, values_of=None):
    """(min, max) of a field over all frames [SI unless values_of converts]. values_of(sol_i) -> array."""
    from aeroflowsim.post.fields import field_values
    lo, hi = np.inf, -np.inf
    for i in range(animation.n):
        v = values_of(frame_solution(sol, animation, i)) if values_of else field_values(frame_solution(sol, animation, i), name)
        v = np.asarray(v, dtype=float)
        v = v[np.isfinite(v)]
        if v.size:
            lo, hi = min(lo, float(v.min())), max(hi, float(v.max()))
    if not np.isfinite(lo):
        return 0.0, 1.0
    return (lo, hi) if hi > lo else (lo, lo + max(abs(lo), 1.0) * 1e-6)


class Playback:
    """Play / pause / step / seek over n frames (the GUI's timer calls tick())."""

    SPEEDS = (2, 5, 10, 20, 30)       # frames per second offered

    def __init__(self, n=0, fps=10, loop=True):
        self.n, self.index, self.fps, self.loop, self.playing = n, 0, fps, loop, False

    def set_count(self, n):
        self.n = int(n)
        self.index = min(self.index, max(self.n - 1, 0))
        if self.n < 2:
            self.playing = False

    @property
    def interval_ms(self) -> int:
        return max(int(round(1000.0 / max(self.fps, 1))), 1)

    def play(self):
        if self.n < 2:
            return
        if self.index >= self.n - 1 and not self.loop:     # Play at the end starts again from the beginning
            self.index = 0
        self.playing = True

    def pause(self):
        self.playing = False

    def toggle(self):
        self.pause() if self.playing else self.play()

    def seek(self, i):
        self.index = int(min(max(i, 0), max(self.n - 1, 0)))

    def step(self, k=1):
        self.pause()
        self.seek(self.index + k)

    def tick(self) -> int:
        """The next frame while playing; at the end: back to the first (loop) or stop on the last."""
        if not self.playing or self.n < 2:
            return self.index
        if self.index >= self.n - 1:
            if self.loop:
                self.index = 0
            else:
                self.playing = False
        else:
            self.index += 1
            if self.index == self.n - 1 and not self.loop:
                self.playing = False
        return self.index


# ---- export -------------------------------------------------------------------------------------------

def mp4_available() -> bool:
    """True when matplotlib finds an ffmpeg program (no extra Python package is needed then)."""
    try:
        from matplotlib.animation import writers
        return writers.is_available("ffmpeg")
    except Exception:                    # noqa: BLE001 - any problem = not available
        return False


def _frames_2d(sol, animation, name, cmap, mirror, range_mode, unit_convert, size, progress):
    """Yield one RGB image (H, W, 3 uint8) per frame of a 2D animation (paper style, matplotlib only)."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    from aeroflowsim.post.fields import field_values
    from aeroflowsim.post.pictures import field_picture

    vmin = vmax = None
    if range_mode == RANGE_ALL:
        if unit_convert is not None:
            from aeroflowsim.post.fields import field_info
            unit = field_info(sol, name).unit
            vmin, vmax = field_range(sol, animation, name, lambda s: unit_convert(field_values(s, name), unit)[0])
        else:
            vmin, vmax = field_range(sol, animation, name)
    for i in range(animation.n):
        fig = field_picture(frame_solution(sol, animation, i), name, cmap=cmap, mirror=mirror, size=size,
                            vmin=vmin, vmax=vmax, unit_convert=unit_convert, title=frame_label(animation, i))
        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        yield np.asarray(canvas.buffer_rgba())[:, :, :3].copy()
        if progress is not None:
            progress(i + 1, animation.n)


def _frames_1d(animation, name, label, unit, range_mode, size, progress):
    """Yield one RGB image per frame of a 1D animation: the field against x."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    values = np.asarray(animation.fields[name], dtype=float)
    x = animation.x if animation.x is not None else np.arange(values.shape[1])
    lo, hi = float(np.nanmin(values)), float(np.nanmax(values))
    pad = 0.05 * (hi - lo if hi > lo else max(abs(hi), 1.0))
    for i in range(animation.n):
        fig = Figure(figsize=size, dpi=110, layout="constrained")
        fig.set_facecolor("white")
        ax = fig.add_subplot()
        ax.plot(x, values[i], color="#1f77b4", lw=1.6)
        if range_mode == RANGE_ALL:
            ax.set_ylim(lo - pad, hi + pad)
        ax.set_xlabel("x [m]")
        ax.set_ylabel(f"{label} [{unit}]" if unit not in ("", "-") else label)
        ax.set_title(frame_label(animation, i))
        ax.grid(alpha=0.3)
        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        yield np.asarray(canvas.buffer_rgba())[:, :, :3].copy()
        if progress is not None:
            progress(i + 1, animation.n)


def write_frames(images, path, fps=10, loop=True):
    """Write RGB images to an animated GIF (Pillow, which matplotlib already needs) or an MP4 (ffmpeg)."""
    path = Path(path)
    images = list(images)
    if not images:
        raise ValueError("There are no frames to save.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".mp4":
        if not mp4_available():
            raise ValueError("MP4 needs the ffmpeg program, which was not found; save a GIF instead.")
        from matplotlib import animation as mpl_animation
        from matplotlib.figure import Figure
        h, w = images[0].shape[:2]
        fig = Figure(figsize=(w / 100.0, h / 100.0), dpi=100)
        ax = fig.add_axes((0, 0, 1, 1))
        ax.axis("off")
        shown = ax.imshow(images[0])
        writer = mpl_animation.FFMpegWriter(fps=fps)
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        FigureCanvasAgg(fig)
        with writer.saving(fig, str(path), dpi=100):
            for img in images:
                shown.set_data(img)
                writer.grab_frame()
        return path
    from PIL import Image
    h = max(img.shape[0] for img in images)
    w = max(img.shape[1] for img in images)
    pics = []
    for img in images:                   # equal sizes (constrained layout can differ by a pixel)
        canvas = np.full((h, w, 3), 255, dtype=np.uint8)
        canvas[:img.shape[0], :img.shape[1]] = img
        pics.append(Image.fromarray(canvas).convert("P", palette=Image.ADAPTIVE, colors=255))
    pics[0].save(path, save_all=True, append_images=pics[1:], duration=int(round(1000.0 / max(fps, 1))),
                 loop=0 if loop else 1, optimize=False)
    return path


def export_animation(path, animation, sol=None, name="M", cmap="turbo", mirror=False, range_mode=RANGE_ALL,
                     fps=10, loop=True, unit_convert=None, size=(7.0, 3.6), progress=None, label=None, unit=""):
    """Save an animation as GIF or MP4 (by the file ending), in the paper style of the picture export.
    2D: sol = the result's Solution (mesh, gas, conditions), name = any field it offers. 1D: the field key."""
    if animation is None or not animation.n:
        raise ValueError("This result has no recorded frames (recording was off, or the project is older than the "
                         "animation feature): run it again to record them.")
    if animation.x is not None or sol is None:
        if name not in animation.fields:
            raise ValueError(f"No field '{name}' in the frames; choose one of {', '.join(animation.fields)}.")
        images = _frames_1d(animation, name, label or name, unit, range_mode, size, progress)
    else:
        images = _frames_2d(sol, animation, name, cmap, mirror, range_mode, unit_convert, size, progress)
    return write_frames(images, path, fps, loop)


__all__ = ["Animation", "FrameRecorder", "Playback", "recorder_for", "save_animation", "load_animation",
           "clear_animation", "from_snapshots", "project_animation", "frame_label", "frame_solution", "field_range",
           "export_animation", "write_frames", "mp4_available", "ANIMATION_FILE", "RANGE_ALL", "RANGE_FRAME",
           "DEFAULT_SETTINGS"]

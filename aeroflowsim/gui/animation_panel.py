# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Flow animation in the Results step (Qt): play back the frames recorded during the run.

    PlaybackBar      play / pause, first / previous / next / last frame, slider, speed, loop, colour range mode and
                     the iteration (or time) label; drives a post.animation.Playback with a QTimer
    AnimationPanel   the Animation tab of the 2D post-processing workspace: recording settings of the project
                     (used by the next run), the playback bar, and Save GIF / MP4
The frame is drawn by the Results page in every view that shows the current result, with that view's Display
settings (field, colour map, vectors, streamlines, ...). All logic is in aeroflowsim/post/animation.py (no Qt).
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from aeroflowsim.post.animation import (DEFAULT_SETTINGS, RANGE_ALL, RANGE_FRAME, Playback, frame_label,
                                        mp4_available)


class PlaybackBar(QWidget):
    """Playback controls over n frames; frame_changed(i) whenever the shown frame changes."""

    frame_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.playback = Playback()
        self.animation = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.first, self.back, self.play, self.next, self.last = (QToolButton() for _ in range(5))
        for b, text, tip in ((self.first, "⏮", "First frame"), (self.back, "◀", "Previous frame"),
                             (self.play, "▶", "Play / pause"), (self.next, "▶|", "Next frame"),
                             (self.last, "⏭", "Last frame (the final result)")):
            b.setText(text)
            b.setToolTip(tip)
        self.first.clicked.connect(lambda: self.seek(0))
        self.back.clicked.connect(lambda: self.step(-1))
        self.play.clicked.connect(self.toggle)
        self.next.clicked.connect(lambda: self.step(1))
        self.last.clicked.connect(lambda: self.seek(self.playback.n - 1))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self._slid)
        self.label = QLabel()
        self.speed = QComboBox()
        for fps in Playback.SPEEDS:
            self.speed.addItem(f"{fps} frames/s", fps)
        self.speed.setCurrentIndex(Playback.SPEEDS.index(10))
        self.speed.currentIndexChanged.connect(self._speed)
        self.loop = QCheckBox("Loop", checked=True)
        self.loop.toggled.connect(lambda on: setattr(self.playback, "loop", on))
        self.range_mode = QComboBox()
        self.range_mode.addItems([RANGE_ALL, RANGE_FRAME])
        self.range_mode.setToolTip("Fixed over all frames: one colour bar for the whole animation, so colours mean the "
                                   "same value in every frame. Per frame: each frame uses its own range.")
        self.range_mode.currentIndexChanged.connect(lambda _: self.frame_changed.emit(self.playback.index))
        buttons = QHBoxLayout()
        for b in (self.first, self.back, self.play, self.next, self.last):
            buttons.addWidget(b)
        buttons.addWidget(self.slider, 1)
        options = QHBoxLayout()
        for w in (self.speed, self.loop, QLabel("Colour range"), self.range_mode):
            options.addWidget(w)
        options.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(buttons)
        layout.addWidget(self.label)
        layout.addLayout(options)
        self.set_animation(None)

    def set_animation(self, animation):
        """Show these frames (None: none); starts on the last frame, i.e. the final result."""
        self.pause()
        self.animation = animation
        n = animation.n if animation is not None else 0
        self.playback.set_count(n)
        self.playback.seek(n - 1)
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(n - 1, 0))
        self.slider.setValue(self.playback.index)
        self.slider.blockSignals(False)
        for w in (self.first, self.back, self.play, self.next, self.last, self.slider, self.speed, self.loop):
            w.setEnabled(n >= 2)
        self._show()

    @property
    def index(self) -> int:
        return self.playback.index

    def fixed_range(self) -> bool:
        return self.range_mode.currentText() == RANGE_ALL

    def toggle(self):
        self.playback.toggle()
        self._timer()

    def pause(self):
        self.playback.pause()
        self._timer()

    def seek(self, i):
        self.playback.seek(i)
        self._show()

    def step(self, k):
        self.playback.step(k)
        self._timer()
        self._show()

    def _timer(self):
        self.play.setText("⏸" if self.playback.playing else "▶")
        if self.playback.playing:
            self.timer.start(self.playback.interval_ms)
        else:
            self.timer.stop()

    def _tick(self):
        self.playback.tick()
        self._show()
        if not self.playback.playing:
            self._timer()

    def _speed(self, _i):
        self.playback.fps = self.speed.currentData()
        if self.playback.playing:
            self.timer.start(self.playback.interval_ms)

    def _slid(self, value):
        self.playback.seek(value)
        self._show(move_slider=False)

    def _show(self, move_slider=True):
        if move_slider:
            self.slider.blockSignals(True)
            self.slider.setValue(self.playback.index)
            self.slider.blockSignals(False)
        if self.animation is None or not self.animation.n:
            self.label.setText("")
            return
        self.label.setText(frame_label(self.animation, self.playback.index))
        self.frame_changed.emit(self.playback.index)


class AnimationPanel(QWidget):
    """The Animation tab of the 2D Results workspace (see the module text)."""

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.active = False                  # True while this tab is shown: the views then show the frame
        settings = QGroupBox("Recording (used by the next run)")
        form = QFormLayout(settings)
        self.record = QCheckBox("Save flow frames during the run")
        self.record.setToolTip("Keep the flow at regular iterations so the run can be played back here.")
        self.every = QSpinBox(minimum=0, maximum=1_000_000)
        self.every.setSpecialValueText("Automatic (50 to 100 frames)")
        self.every.setToolTip("Save a frame every N iterations. Automatic spreads 50 to 100 frames over the whole run, "
                              "whatever its length.")
        form.addRow(self.record)
        form.addRow("Every N iterations", self.every)
        self.record.toggled.connect(self._settings_changed)
        self.every.valueChanged.connect(self._settings_changed)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setObjectName("note")
        self.bar = PlaybackBar()
        self.bar.frame_changed.connect(lambda _i: self.page.animation_frame_changed())
        self.save_button = QPushButton("Save GIF / MP4...")
        self.save_button.setToolTip("Save the animation of the active view's field (paper style, your units).")
        self.save_button.clicked.connect(self.save)
        layout = QVBoxLayout(self)
        layout.addWidget(settings)
        play = QGroupBox("Playback")
        pl = QVBoxLayout(play)
        pl.addWidget(self.note)
        pl.addWidget(self.bar)
        pl.addWidget(self.save_button)
        layout.addWidget(play)
        layout.addStretch(1)
        self._filling = False

    def fill(self):
        """Read the project's recording settings and the frames of the current result."""
        project = self.page.window.project
        s = {**DEFAULT_SETTINGS, **((project.post.get("animation") if project else None) or {})}
        self._filling = True
        self.record.setChecked(bool(s["record"]))
        self.every.setValue(int(s["every"] or 0))
        self.every.setEnabled(bool(s["record"]))
        self._filling = False
        anim = self.page.animation()
        self.bar.set_animation(anim)
        self.save_button.setEnabled(anim is not None and anim.n >= 1)
        status = project.status("results") if project else "none"
        if anim is None:
            self.note.setText("This result has no recorded frames (recording was off, or the project was run before "
                              "AeroFlowSim had animations). Turn recording on and run again: Run continues the run "
                              "and records from there; Start from scratch records the whole run.")
        elif status in ("outdated", "error"):
            self.note.setText(f"OUT OF DATE: {anim.n} frames of a run made from older inputs. Run again to update them.")
        else:
            self.note.setText(f"{anim.n} frames recorded. Press ▶ to watch how the flow developed; the last frame is "
                              "the final result.")

    def _settings_changed(self, *_):
        if self._filling:
            return
        self.every.setEnabled(self.record.isChecked())
        project = self.page.window.project
        if project is not None:
            project.set_post("animation", {"record": self.record.isChecked(), "every": int(self.every.value())})
            self.page.window.update_title()

    def set_active(self, on):
        self.active = bool(on)
        if not on:
            self.bar.pause()

    def save(self):
        from aeroflowsim.gui.results_logic import display_values
        from aeroflowsim.post.animation import export_animation
        anim = self.page.animation()
        sol = self.page.solution()
        if anim is None or sol is None:
            return
        scene = self.page.display.scenes[self.page.display.view_index]
        project = self.page.window.project
        filters = "Animated GIF (*.gif)" + (";;MP4 video (*.mp4)" if mp4_available() else "")
        path, _ = QFileDialog.getSaveFileName(self, "Save animation", str(project.results_dir /
                                              f"{project.name}_{scene.field}.gif"), filters)
        if not path:
            return
        prefs = self.page.window.units
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            export_animation(path, anim, sol, scene.field, cmap=scene.cmap, mirror=scene.mirror,
                             range_mode=self.bar.range_mode.currentText(), fps=self.bar.playback.fps,
                             loop=self.bar.loop.isChecked(),
                             unit_convert=lambda v, unit: display_values(v, unit, prefs))
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Save animation", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.page.window.log(f"Animation saved to {path}")

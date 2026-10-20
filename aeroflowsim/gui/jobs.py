# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Qt side of the background jobs: turns aeroflowsim.tasks.Worker messages into Qt signals.

The Worker (no GUI code) runs meshing and solving in a warm helper process. Here a QTimer asks it
every 0.1 s for news and announces it with signals, so the window never waits for a job:
    started(task)    a job was sent to the helper process
    updated(task)    new stage text or residuals arrived (redraw progress and the residual plot)
    ended(task)      the job finished, stopped, was cancelled or failed (task.status says which)
"""

from PySide6.QtCore import QObject, QTimer, Signal

from aeroflowsim.tasks import Job, Worker

POLL_MS = 100   # [ms] how often the helper process is asked for news


class JobRunner(QObject):
    started = Signal(object)
    updated = Signal(object)
    ended = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = Worker()
        self.worker.start()                 # warm up now, so the first job starts quickly
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self._poll)

    @property
    def task(self):
        return self.worker.task

    @property
    def busy(self) -> bool:
        return self.worker.task is not None and self.worker.task.running

    def submit(self, job: Job):
        task = self.worker.submit(job)
        self.timer.start()
        self.started.emit(task)
        return task

    def cancel(self):
        self.worker.cancel()
        self._poll()                        # a cancelled mesh ends at once

    def _poll(self):
        task = self.worker.task
        if task is None:
            self.timer.stop()
            return
        messages = self.worker.poll()
        if task.running:
            if messages or task.stage == "Stopping":
                self.updated.emit(task)
            return
        self.timer.stop()
        self.ended.emit(task)

    def shutdown(self):
        self.timer.stop()
        self.worker.shutdown()

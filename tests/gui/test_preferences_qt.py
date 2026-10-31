# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tools > Preferences: the solver thread count, walked through the user's next actions (run, stop, continue
with another thread count, change an input, re-mesh, reopen, units / theme, an old project)."""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from aeroflowsim import compute
from aeroflowsim.gui.main_window import MainWindow
from aeroflowsim.gui.preferences_dialog import THREADS_KEY, PreferencesDialog, threads_setting
from aeroflowsim.project import Project
from aeroflowsim.units import SI, UnitPreferences

pytest.importorskip("numba")
JOB_MS = 240_000


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    w = MainWindow(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    qtbot.addWidget(w)
    w.show()
    for name in ("question", "warning", "information"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.Discard if name == "question" else QMessageBox.Ok)
    yield w
    w.runner.shutdown()


def _wait(qtbot, window):
    if window.runner.busy:
        with qtbot.waitSignal(window.runner.ended, timeout=JOB_MS):
            pass


def test_preferences_dialog_default_and_custom_threads(qtbot):
    d = PreferencesDialog(0)
    qtbot.addWidget(d)
    assert d.use_default.isChecked() and not d.spin.isEnabled() and d.threads() == 0
    assert d.spin.value() == compute.default_threads()
    d.use_default.setChecked(False)
    d.spin.setValue(2)
    assert d.threads() == 2
    assert PreferencesDialog(3).threads() == 3


def test_thread_setting_reaches_the_helper_and_never_changes_the_project(qtbot, window, tmp_path, monkeypatch):
    project = Project.create("nozzle_axi", tmp_path / "T.afsproj", values={"mesh_preset": "Custom", "nx": 30,
                                                                          "nr": 6, "max_iter": 1_000_000})
    window.load_project(project)
    _wait(qtbot, window)
    window.generate_mesh()
    _wait(qtbot, window)
    run_fp = window.project.fingerprint("run")
    # The user picks 2 threads in Tools > Preferences (the dialog's OK is simulated)
    monkeypatch.setattr(PreferencesDialog, "exec", lambda self: True)
    monkeypatch.setattr(PreferencesDialog, "threads", lambda self: 2)
    window.show_preferences()
    assert threads_setting(window.settings) == 2
    assert window.project.fingerprint("run") == run_fp and not window.project.dirty      # a computer setting
    sent = []
    submit = window.runner.submit
    monkeypatch.setattr(window.runner, "submit", lambda job: (sent.append(job), submit(job))[1])
    window.run_case()
    qtbot.waitUntil(lambda: window.runner.task is not None and len(window.runner.task.iterations) >= 5, timeout=JOB_MS)
    window.cancel_job()                                              # Stop
    _wait(qtbot, window)
    first = window.results["result"]
    assert sent[-1].threads == 2 and first.info["threads"] == 2 and first.info["backend"] == "numba"
    # Continue with another thread count: the run carries on, now on 1 thread
    window.settings.setValue(THREADS_KEY, 1)
    window.run_case()
    qtbot.waitUntil(lambda: len(window.runner.task.iterations) >= 5, timeout=JOB_MS)
    window.cancel_job()
    _wait(qtbot, window)
    again = window.results["result"]
    assert sent[-1].threads == 1 and again.info["threads"] == 1 and again.info["continued_from"] == first.iterations
    # Default again (0 -> None: the helper uses physical cores minus one)
    window.settings.setValue(THREADS_KEY, 0)
    window.set_units(UnitPreferences(SI), save=False)               # units and theme do not touch the setting
    window.act["dark"].trigger()
    assert threads_setting(window.settings) == 0
    # Reopen: the setting is in the settings file, not in the project
    window.settings.sync()
    reopened = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    assert threads_setting(reopened) == 0
    assert "threads" not in Project.open(project.folder).values


def test_an_old_result_without_solver_info_still_shows(qtbot, window, tmp_path):
    from aeroflowsim.gui.steps.run import _solver_text

    class _R:
        info = {"status": "converged"}                              # a result saved before the speed stage (Numba)
    window.results = {"result": _R()}
    assert _solver_text(window) == ""
    _R.info = {"backend": "numba", "threads": 15}
    assert _solver_text(window) == ", Numba, 15 threads"

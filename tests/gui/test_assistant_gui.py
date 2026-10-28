# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Assistant panel in the Setup step: off by default, a fake provider (no network, no model) fills the review
table, Apply is ONE undo step, Undo restores everything, nothing outside the schema changes."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QMessageBox

from aeroflowsim.assistant.proposal import Proposal
from aeroflowsim.assistant.provider import AssistantProvider
from aeroflowsim.gui.main_window import MainWindow
from aeroflowsim.project import Project

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent


class Fake(AssistantProvider):
    name, label, from_model = "fake", "Fake", False

    def __init__(self, proposals, notes=()):
        super().__init__()
        self.proposals, self.fixed_notes = proposals, list(notes)

    def propose(self, description, context):
        self.notes = list(self.fixed_notes)
        return list(self.proposals)


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    w = MainWindow(QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    qtbot.addWidget(w)
    w.show()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w.load_project(Project.create("quasi1d_nozzle", tmp_path / "A.afsproj"))
    w.go_to("setup")
    yield w
    w.runner.shutdown()


def turn_on(window, provider="rules", opt_in=False):
    for name, value in (("enabled", True), ("provider", provider), ("online_opt_in", opt_in)):
        window.settings.setValue(f"assistant/{name}", value)
    window.pages["setup"].assistant.refresh()
    return window.pages["setup"].assistant


def propose(qtbot, panel, text="go"):
    panel.text.setPlainText(text)
    with qtbot.waitSignal(panel._bridge.done, timeout=5000):
        panel.propose()


def test_the_assistant_is_off_by_default(window):
    panel = window.pages["setup"].assistant
    assert "off" in panel.status.text().lower()
    assert not panel.propose_button.isEnabled() and not panel.text.isEnabled() and panel.provider.count() == 0
    assert not panel.body.isVisible()                                                   # collapsed
    panel.propose()
    assert panel.table.rowCount() == 0


def test_apply_is_one_undo_step_and_undo_restores_everything(qtbot, window):
    panel = turn_on(window)
    assert panel.status.text() == "Offline"
    before = dict(window.project.values)
    fake = Fake([Proposal("p0", 300, "bar", "chamber pressure"), Proposal("T0", 400, "K", "temperature"),
                 Proposal("gas", "He", "", "helium"), Proposal("n_cells", 99999999, "", "too many"),
                 Proposal("made_up", 1, "", "")])
    panel.provider_factory = lambda name: fake
    propose(qtbot, panel, "300 bar helium")
    assert panel.table.rowCount() == 3 and panel.ticked() == ["p0", "T0", "gas"]
    notes = panel.notes.toPlainText()
    assert "outside the allowed range" in notes and "not an input of this case" in notes
    panel.table.item(1, 0).setCheckState(Qt.Unchecked)                                  # untick T0
    assert window.undo.count() == 0 and window.project.values == before                 # nothing applied yet
    panel.apply()
    assert window.undo.count() == 1                                                     # ONE step for all
    assert window.project.values["p0"] == pytest.approx(3e7) and window.project.values["gas"] == "He"
    assert window.project.values["T0"] == before["T0"]
    assert window.project.values["n_cells"] == before["n_cells"]
    assert panel.table.rowCount() == 0
    window.undo.undo()
    assert window.project.values == before
    window.undo.redo()
    assert window.project.values["p0"] == pytest.approx(3e7)


def test_the_review_table_shows_old_new_unit_and_reason_in_the_users_units(qtbot, window):
    panel = turn_on(window)
    panel.provider_factory = lambda name: Fake([Proposal("p0", 300, "bar", "chamber pressure 300 bar")])
    propose(qtbot, panel)
    cells = [panel.table.item(0, c).text() for c in range(1, 6)]
    assert cells[0] == "Total (chamber) pressure" and cells[1] == "500" and cells[2] == "3e+04" or cells[2] == "30000"
    assert cells[3] == "kPa" and cells[4] == "chamber pressure 300 bar"


def test_a_value_that_became_stale_is_checked_again_when_applied(qtbot, window):
    panel = turn_on(window)
    panel.provider_factory = lambda name: Fake([Proposal("p0", 300, "bar")])
    propose(qtbot, panel)
    window.set_inputs({"p0": 3e7}, "typed by hand")                                    # the user typed the same value meanwhile
    panel.apply()
    assert window.undo.count() == 1                                                     # nothing left to apply
    assert "Nothing ticked" in panel.notes.toPlainText()


def test_online_cannot_be_selected_without_the_explicit_opt_in(window):
    panel = turn_on(window, provider="online", opt_in=False)
    model = panel.provider.model()
    states = {panel.provider.itemData(i): model.item(i).isEnabled() for i in range(panel.provider.count())}
    assert states == {"rules": True, "local": True, "online": False}
    panel.text.setPlainText("300 bar")
    panel.propose()                                                                    # builds the real provider: refused
    assert "explicitly" in panel.notes.toPlainText() or "off" in panel.notes.toPlainText()
    assert panel.table.rowCount() == 0
    panel = turn_on(window, provider="online", opt_in=True)
    assert panel.provider.model().item(2).isEnabled()
    assert panel.status.text() == "Online - text leaves this computer" and panel.banner.isVisibleTo(panel)


def test_the_real_rules_provider_end_to_end(qtbot, window):
    panel = turn_on(window)
    propose(qtbot, panel, "helium, 300 bar chamber pressure, 5 bar back pressure")
    assert {panel.table.item(r, 0).data(Qt.UserRole) for r in range(panel.table.rowCount())} == {"gas", "p0", "p_back"}
    panel.apply()
    assert window.project.values["p_back"] == pytest.approx(5e5)
    assert window.undo.count() == 1


def test_nothing_of_the_assistant_is_imported_while_it_is_off():
    code = ("import sys, socket\n"
            "import tempfile, os\n"
            "from PySide6.QtCore import QSettings\n"
            "from PySide6.QtWidgets import QApplication\n"
            "app = QApplication([])\n"
            "from aeroflowsim.gui.main_window import MainWindow\n"
            "from aeroflowsim.project import Project\n"
            "def no(*a, **k): raise RuntimeError('socket opened')\n"
            "socket.socket.__init__ = no\n"        # from here on, opening a socket is an error
            "d = tempfile.mkdtemp()\n"
            "w = MainWindow(QSettings(os.path.join(d, 's.ini'), QSettings.IniFormat))\n"
            "w.load_project(Project.create('quasi1d_nozzle', os.path.join(d, 'A.afsproj')))\n"
            "w.go_to('setup'); w.go_to('mesh'); w.go_to('setup')\n"
            "bad = [m for m in sys.modules if m.startswith('aeroflowsim.assistant')]\n"
            "print('LOADED', bad)\n"
            "w.runner.shutdown()\n")
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen" if sys.platform.startswith("linux") else os.environ.get("QT_QPA_PLATFORM", "")}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=PROJECT_DIR, env=env, timeout=120)
    assert "LOADED []" in done.stdout, done.stdout + done.stderr[-2000:]


def test_the_settings_dialog_defaults_to_off_and_refuses_unsafe_choices(qtbot, window, monkeypatch):
    from aeroflowsim.gui.assistant_settings import AssistantSettingsDialog
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: warnings.append(text))
    dialog = AssistantSettingsDialog(window.settings, window)
    qtbot.addWidget(dialog)
    assert not dialog.enabled.isChecked() and not dialog.online_opt_in.isChecked()
    assert dialog.provider.currentData() == "rules" and dialog.local_host.text() == "localhost"
    dialog.provider.setCurrentIndex(dialog.provider.findData("online"))          # online without its opt-in
    dialog.accept()
    assert warnings and "opt-in" in warnings[-1] and dialog.result() == 0
    assert window.settings.value("assistant/enabled") is None                    # nothing was saved
    dialog.provider.setCurrentIndex(dialog.provider.findData("local"))
    dialog.enabled.setChecked(True)
    dialog.local_host.setText("example.com")                                     # a local model must be on this computer
    dialog.accept()
    assert "this computer" in warnings[-1] and window.settings.value("assistant/enabled") is None
    dialog.local_host.setText("127.0.0.1")
    dialog.local_model.setText("llama3")
    dialog.accept()
    assert window.settings.value("assistant/enabled") in (True, "true")
    assert window.settings.value("assistant/provider") == "local" and window.settings.value("assistant/online_opt_in") in (False, "false")
    panel = window.pages["setup"].assistant
    panel.refresh()
    assert panel.status.text() == "Offline" and panel.propose_button.isEnabled()

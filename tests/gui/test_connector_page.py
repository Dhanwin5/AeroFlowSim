# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tools > Use with AI assistants: off by default, Save stores the choices, the snippets carry this python, Copy puts
them on the clipboard, Test reports "off" while off and lists the server's tools once allowed."""

import json
import sys

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QPlainTextEdit, QPushButton

from aeroflowsim.api import TOOLS
from aeroflowsim.gui.connector_page import ConnectorDialog
from aeroflowsim.gui.main_window import MainWindow


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "connector.json"
    monkeypatch.setenv("AEROFLOWSIM_CONNECTOR_SETTINGS", str(path))
    return path


def test_off_by_default_and_save(qtbot, tmp_path, settings_file):
    d = ConnectorDialog()
    qtbot.addWidget(d)
    assert not d.allow.isChecked()
    d.allow.setChecked(True)
    d.workspace.setText(str(tmp_path / "ws"))
    d.confirm.setValue(3.0)
    d.accept()
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert data["allow"] is True and data["confirm_minutes"] == 3.0 and data["workspace"] == str(tmp_path / "ws")
    again = ConnectorDialog()
    qtbot.addWidget(again)
    assert again.allow.isChecked()                     # reopening shows the saved choice


def test_snippets_and_copy(qtbot, settings_file):
    d = ConnectorDialog()
    qtbot.addWidget(d)
    assert [d.tabs.tabText(i) for i in range(d.tabs.count())] == ["Claude Desktop", "Claude Code", "Other MCP apps"]
    desktop = d.findChild(QPlainTextEdit, "snippet_Claude Desktop").toPlainText()
    assert json.loads(desktop)["mcpServers"]["aeroflowsim"]["command"] == sys.executable
    copy = [b for b in d.tabs.widget(0).findChildren(QPushButton) if b.text() == "Copy"][0]
    copy.click()
    assert QGuiApplication.clipboard().text() == desktop


def test_test_button_while_off(qtbot, settings_file):
    d = ConnectorDialog()
    qtbot.addWidget(d)
    d.test.click()
    assert "is off" in d.result.text()


def test_test_button_lists_the_tools(qtbot, tmp_path, settings_file):
    pytest.importorskip("mcp")
    d = ConnectorDialog()
    qtbot.addWidget(d)
    d.allow.setChecked(True)
    d.workspace.setText(str(tmp_path / "ws"))
    d.test.click()
    assert f"{len(TOOLS)} tools" in d.result.text(), d.result.text()


def test_tools_menu_has_the_page(qtbot, tmp_path, settings_file):
    w = MainWindow(QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    qtbot.addWidget(w)
    assert "connector" in w.act and "AI assistants" in w.act["connector"].text()


def test_add_to_claude_desktop_button(qtbot, tmp_path, settings_file, monkeypatch):
    """The one-click button: greyed out in a source installation; in the installed program it opens the bundled
    extension file (a LOCAL file) so that Claude Desktop shows its Install dialog."""
    from PySide6.QtGui import QDesktopServices

    from aeroflowsim.connector import snippets
    d = ConnectorDialog()
    qtbot.addWidget(d)
    assert not d.add_claude.isEnabled()                  # source installation: nothing bundled
    ext = tmp_path / "AeroFlowSim-claude.mcpb"
    ext.write_bytes(b"zip")
    monkeypatch.setattr(snippets, "extension_file", lambda: ext)
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    d2 = ConnectorDialog()
    qtbot.addWidget(d2)
    assert d2.add_claude.isEnabled()
    d2.add_claude.click()
    assert opened == [ext.as_posix()] and "Install" in d2.result.text()
    assert not settings_file.exists()                   # the button changes no AeroFlowSim setting

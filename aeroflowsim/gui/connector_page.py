# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tools > Use with AI assistants: allow the AI connector, choose its workspace folder, copy the snippet for Claude
Desktop, Claude Code or any MCP client, and test that the server starts.

Off by default. This dialog only stores choices (aeroflowsim/connector/settings.py) and shows text to copy: it never
edits another program's configuration files and contains no network code. The Test button starts the server in a
separate process (aeroflowsim/connector/selftest.py), the way an AI client does.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from aeroflowsim.connector import snippets
from aeroflowsim.connector.settings import load_settings, save_settings

INTRO = ("An AI assistant (Claude Desktop, Claude Code or any app that speaks MCP) can set up, mesh, check, run and "
         "report AeroFlowSim projects for you. It works only through the template inputs, the same checks and the "
         "same solver as this window, only inside the workspace folder below, never deletes anything, and asks you "
         "before long runs. The connection is local (the app starts AeroFlowSim on this computer). What the "
         "assistant reads - numbers, tables, pictures - becomes part of your conversation with the AI provider. "
         "Off until you allow it here.")


class ConnectorDialog(QDialog):
    def __init__(self, parent=None, settings_path=None):
        super().__init__(parent)
        self.settings_path = settings_path
        self.s = load_settings(settings_path)
        self.setWindowTitle("Use with AI assistants")
        self.setMinimumWidth(640)

        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        self.allow = QCheckBox("Allow AI connector")
        self.allow.setChecked(self.s.allow)
        self.workspace = QLineEdit(str(self.s.workspace_path()))
        browse = QPushButton("Choose...")
        browse.clicked.connect(self._choose_folder)
        row = QHBoxLayout()
        row.addWidget(self.workspace, 1)
        row.addWidget(browse)
        self.confirm = QDoubleSpinBox()
        self.confirm.setRange(0.1, 10000.0)
        self.confirm.setSuffix(" min")
        self.confirm.setValue(self.s.confirm_minutes)
        form = QFormLayout()
        form.addRow(self.allow)
        form.addRow("Workspace folder", row)
        form.addRow("Ask before runs longer than", self.confirm)

        # One click: open the bundled Claude Desktop extension; Claude Desktop shows its own Install dialog.
        self.extension = snippets.extension_file()
        self.add_claude = QPushButton("Add to Claude Desktop (one click)")
        self.add_claude.setObjectName("add_to_claude")
        self.add_claude.setEnabled(self.extension is not None)
        self.add_claude.setToolTip(
            "Opens the AeroFlowSim extension in Claude Desktop: press Install there. Installing it is your "
            "permission for Claude to use AeroFlowSim inside the workspace folder; turn it off in Claude Desktop "
            "> Settings > Extensions." if self.extension else
            "Available in the installed program (a source installation: python tools/build_mcpb.py, then "
            "double-click the .mcpb file).")
        self.add_claude.clicked.connect(self._add_to_claude)

        self.tabs = QTabWidget()
        python = None                                   # snippets: this Python, or the installed program itself
        program = snippets.server_entry()["command"]
        self._add_tab("Claude Desktop", snippets.claude_desktop_json(python),
                      "Easiest: the button 'Add to Claude Desktop' above. By hand: add this to "
                      f"{snippets.desktop_config_location()} (Claude Desktop: Settings > Developer > Edit Config), "
                      "then quit and restart Claude Desktop.")
        self._add_tab("Claude Code", "\n".join(snippets.claude_code_plugin_commands()) + "\n\n# or the server alone:\n"
                      + snippets.claude_code_command(python),
                      "Plugin (skill + server): type the two /plugin lines in Claude Code; it asks once for the "
                      "program shown below (AeroFlowSim.exe, or python). Server alone: run the claude mcp add line in a "
                      "terminal.\n" + program)
        self._add_tab("Other MCP apps", snippets.generic_json(python),
                      "The common mcpServers entry (stdio). See your app's documentation for where it goes.")

        self.test = QPushButton("Test: start the server and list its tools")
        self.test.clicked.connect(self._run_test)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.add_claude)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.test)
        layout.addWidget(self.result)
        layout.addWidget(buttons)

    def _add_tab(self, title, text, note):
        page = QWidget()
        box = QVBoxLayout(page)
        label = QLabel(note)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        edit = QPlainTextEdit(text)
        edit.setReadOnly(True)
        edit.setObjectName(f"snippet_{title}")
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(text))
        box.addWidget(label)
        box.addWidget(edit, 1)
        box.addWidget(copy, 0, Qt.AlignRight)
        self.tabs.addTab(page, title)

    def _add_to_claude(self):
        """Open the local .mcpb file with the program the system links to it (Claude Desktop)."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if self.extension is None:
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.extension))):
            self.result.setText("Claude Desktop did not open the extension. Is Claude Desktop installed? You can also "
                                f"drag this file into Claude Desktop > Settings > Extensions: {self.extension}")
        else:
            self.result.setText("Claude Desktop opened the AeroFlowSim extension: press Install there.")

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Workspace folder of the AI connector", self.workspace.text())
        if folder:
            self.workspace.setText(folder)

    def apply(self):
        self.s.allow = self.allow.isChecked()
        self.s.workspace = self.workspace.text().strip()
        self.s.confirm_minutes = float(self.confirm.value())
        save_settings(self.s, self.settings_path)

    def accept(self):
        self.apply()
        super().accept()

    def _run_test(self):
        from aeroflowsim.connector.selftest import run_selftest
        self.apply()                                  # test what is shown
        self.result.setText("Starting the server...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            QApplication.processEvents()
            out = run_selftest()
        finally:
            QApplication.restoreOverrideCursor()
        if out.get("ok"):
            self.result.setText(f"The server works: {len(out['tools'])} tools ({', '.join(out['tools'][:6])}, ...).")
        else:
            self.result.setText(f"Not working: {out.get('error', '')}")

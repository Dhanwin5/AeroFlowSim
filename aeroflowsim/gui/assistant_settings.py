# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tools > Assistant settings: turn the optional assistant on, choose the provider, enter the local server
and (only after a separate, explicit opt-in) the online service and its key.

Everything is OFF by default. The choices are saved in the user's preferences file; the online KEY goes to
the operating system's keyring (aeroflowsim/assistant/keystore.py), never into a preferences or project file.
No network code here: this dialog only stores choices.
"""

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout)

PROVIDERS = (("rules", "Rules (no AI)"), ("local", "Local model"), ("online", "Online (your own key)"))


class AssistantSettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Assistant settings")
        self.setMinimumWidth(520)
        get = lambda name, default: settings.value(f"assistant/{name}", default)       # noqa: E731
        flag = lambda name: get(name, False) in (True, "true", "True", 1, "1")         # noqa: E731

        intro = QLabel("The assistant turns a description in plain words into proposed input values. It only fills "
                       "inputs of the template, checks every value against its range and unit, and changes nothing "
                       "until you tick it and press Apply. AeroFlowSim works fully without it. It is OFF until you "
                       "turn it on here.")
        intro.setWordWrap(True)
        self.enabled = QCheckBox("Turn the assistant on")
        self.enabled.setChecked(flag("enabled"))
        self.provider = QComboBox()
        for name, label in PROVIDERS:
            self.provider.addItem(label, name)
        self.provider.setCurrentIndex(max(0, self.provider.findData(get("provider", "rules"))))

        local = QGroupBox("Local model (a server on this computer, for example Ollama)")
        form = QFormLayout(local)
        self.local_host = QLineEdit(str(get("local_host", "localhost")))
        self.local_host.setToolTip("Only this computer is allowed: localhost or a loopback number such as 127.0.0.1.")
        self.local_port = QSpinBox()
        self.local_port.setRange(1, 65535)
        self.local_port.setValue(int(get("local_port", 11434) or 11434))
        self.local_model = QLineEdit(str(get("local_model", "")))
        form.addRow("Host", self.local_host)
        form.addRow("Port", self.local_port)
        form.addRow("Model name", self.local_model)

        online = QGroupBox("Online (your own key) - the text leaves this computer")
        form = QFormLayout(online)
        self.online_opt_in = QCheckBox("Allow the online provider: the description I type is sent over the internet "
                                       "to the service below (never project files, geometry or results)")
        self.online_opt_in.setChecked(flag("online_opt_in"))
        self.online_url = QLineEdit(str(get("online_url", "")))
        self.online_url.setPlaceholderText("secure (https) address of a chat-completions service")
        self.online_model = QLineEdit(str(get("online_model", "")))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("your key (kept in the operating system's keyring)")
        self.key_state = QLabel()
        self.remove_key = QPushButton("Remove stored key")
        self.remove_key.clicked.connect(self._remove_key)
        form.addRow(self.online_opt_in)
        form.addRow("Service address", self.online_url)
        form.addRow("Model name", self.online_model)
        form.addRow("Key", self.key)
        form.addRow(self.key_state, self.remove_key)
        self._show_key_state()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        for widget in (intro, self.enabled):
            layout.addWidget(widget)
        row = QFormLayout()
        row.addRow("Provider", self.provider)
        layout.addLayout(row)
        layout.addWidget(local)
        layout.addWidget(online)
        layout.addWidget(buttons)

    def _show_key_state(self):
        if not self.enabled.isChecked() and not self.online_opt_in.isChecked():
            self.key_state.setText("Key: not checked while the assistant is off")
            self.remove_key.setEnabled(False)
            return
        from aeroflowsim.assistant import keystore
        if not keystore.available():
            self.key_state.setText("Key: needs  pip install keyring")
            self.remove_key.setEnabled(False)
        else:
            has = keystore.has_key()
            self.key_state.setText("Key: stored" if has else "Key: none stored")
            self.remove_key.setEnabled(has)

    def _remove_key(self):
        from aeroflowsim.assistant import keystore
        keystore.delete_key()
        self._show_key_state()

    def accept(self):
        """Save the choices; a key typed here goes to the keyring."""
        wants_online = self.provider.currentData() == "online"
        if wants_online and not self.online_opt_in.isChecked():
            QMessageBox.warning(self, "Assistant settings", "The online provider needs its own opt-in: tick "
                                "'Allow the online provider' first, or choose another provider.")
            return
        if self.enabled.isChecked():
            from aeroflowsim.assistant.config import is_local_host
            if self.provider.currentData() == "local" and not is_local_host(self.local_host.text()):
                QMessageBox.warning(self, "Assistant settings",
                                    "The local model must run on this computer (localhost or 127.0.0.1).")
                return
            if self.key.text().strip():
                from aeroflowsim.assistant import keystore
                from aeroflowsim.assistant.proposal import AssistantError
                try:
                    keystore.set_key(self.key.text())
                except AssistantError as error:
                    QMessageBox.warning(self, "Assistant settings", str(error))
                    return
        put = lambda name, value: self.settings.setValue(f"assistant/{name}", value)   # noqa: E731
        put("enabled", self.enabled.isChecked())
        put("provider", self.provider.currentData())
        put("local_host", self.local_host.text().strip() or "localhost")
        put("local_port", self.local_port.value())
        put("local_model", self.local_model.text().strip())
        put("online_opt_in", self.online_opt_in.isChecked())
        put("online_url", self.online_url.text().strip())
        put("online_model", self.online_model.text().strip())
        self.key.clear()
        super().accept()

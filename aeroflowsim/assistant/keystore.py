# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The key of the online provider, kept in the operating system's keyring (Windows Credential Manager,
macOS Keychain, Secret Service). Never written to a project, a settings file or a log.

Needs the optional package `keyring` (pip install keyring); without it the online provider cannot be used.
"""

from aeroflowsim.assistant.proposal import AssistantError

SERVICE = "AeroFlowSim assistant"
ACCOUNT = "online provider key"


def _keyring():
    try:
        import keyring
    except ImportError:
        raise AssistantError("Storing a key needs the optional package keyring: pip install keyring") from None
    return keyring


def available() -> bool:
    try:
        _keyring()
        return True
    except AssistantError:
        return False


def get_key() -> str:
    key = _keyring().get_password(SERVICE, ACCOUNT)
    if not key:
        raise AssistantError("No key is stored for the online provider. Enter it in Tools > Assistant settings.")
    return key


def has_key() -> bool:
    try:
        return bool(_keyring().get_password(SERVICE, ACCOUNT))
    except Exception:
        return False


def set_key(key: str) -> None:
    if not key.strip():
        raise AssistantError("The key is empty.")
    _keyring().set_password(SERVICE, ACCOUNT, key.strip())


def delete_key() -> None:
    try:
        _keyring().delete_password(SERVICE, ACCOUNT)
    except Exception:
        pass

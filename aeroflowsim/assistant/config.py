# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the user chose in Settings, and the one function that turns it into a provider.

Off by default. The online provider needs its own explicit opt-in on top of "assistant on"; without it
make_provider() refuses to build it and the GUI does not offer it.
"""

import ipaddress
from dataclasses import dataclass

from aeroflowsim.assistant.proposal import AssistantError

PROVIDERS = (("rules", "Rules (no AI)"), ("local", "Local model"), ("online", "Online (your own key)"))


def is_local_host(host: str) -> bool:
    """True for localhost, *.localhost and loopback numbers; False for every other name or address."""
    host = str(host).strip().strip("[]").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass
class AssistantSettings:
    enabled: bool = False             # the assistant is off until the user turns it on
    provider: str = "rules"           # "rules", "local" or "online"
    local_host: str = "localhost"
    local_port: int = 11434
    local_model: str = ""
    online_opt_in: bool = False       # "I understand my text leaves this computer"
    online_url: str = ""
    online_model: str = ""

    @classmethod
    def from_mapping(cls, get) -> "AssistantSettings":
        """Build from a getter get(name, default) (QSettings.value, a dict's .get)."""
        d = cls()

        def text(name, default):
            return str(get(name, default) or default)

        def flag(name, default):
            value = get(name, default)
            return value in (True, "true", "True", 1, "1")

        try:
            port = int(get("local_port", d.local_port))
        except (TypeError, ValueError):
            port = d.local_port
        provider = text("provider", d.provider)
        return cls(enabled=flag("enabled", False), provider=provider if provider in dict(PROVIDERS) else "rules",
                   local_host=text("local_host", d.local_host), local_port=port, local_model=text("local_model", ""),
                   online_opt_in=flag("online_opt_in", False), online_url=text("online_url", ""),
                   online_model=text("online_model", ""))

    def selectable(self) -> list[tuple[str, str, bool]]:
        """(id, label, can be chosen) for the provider drop-down: online only after its opt-in."""
        return [(name, label, name != "online" or self.online_opt_in) for name, label in PROVIDERS]


def make_provider(settings: AssistantSettings, name: str | None = None):
    """The provider for `name` (default: the one in the settings). Raises AssistantError when not allowed."""
    if not settings.enabled:
        raise AssistantError("The assistant is off. Turn it on in Tools > Assistant settings.")
    name = name or settings.provider
    if name == "rules":
        from aeroflowsim.assistant.rules import RulesProvider
        return RulesProvider()
    if name == "local":
        from aeroflowsim.assistant.local import LocalModelProvider
        return LocalModelProvider(settings.local_model, settings.local_host, settings.local_port)
    if name == "online":
        if not settings.online_opt_in:
            raise AssistantError("The online provider is off: turn it on explicitly in Tools > Assistant settings "
                                 "(it sends your text over the internet).")
        from aeroflowsim.assistant import keystore
        from aeroflowsim.assistant.online import OnlineProvider
        return OnlineProvider(settings.online_url, settings.online_model, keystore.get_key())
    raise AssistantError(f"Unknown provider '{name}'.")

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Provider 2, "Local model": a language-model server the user already runs on THIS computer.

Written for Ollama's chat interface (default port 11434). Only addresses of this computer are allowed
(localhost, or a loopback number such as 127.0.0.1 or ::1): the text never leaves the machine. The model
must answer with the strict JSON of proposal.py; whatever else it says is discarded.
"""

from aeroflowsim.assistant import net
from aeroflowsim.assistant.config import is_local_host
from aeroflowsim.assistant.context import SchemaContext, build_messages
from aeroflowsim.assistant.proposal import AssistantError, Proposal, parse_provider_json
from aeroflowsim.assistant.provider import AssistantProvider

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 11434


def local_url(host: str, port: int, path: str = "/api/chat") -> str:
    if not is_local_host(host):
        raise AssistantError(f"'{host}' is not an address of this computer. The local model must run on localhost.")
    if not (isinstance(port, int) and 1 <= port <= 65535):
        raise AssistantError("The port must be a whole number from 1 to 65535.")
    shown = f"[{host.strip('[]')}]" if ":" in host else host.strip()
    return f"http://{shown}:{port}{path}"


class LocalModelProvider(AssistantProvider):
    name = "local"
    label = "Local model"
    from_model = True

    def __init__(self, model: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        super().__init__()
        if not str(model).strip():
            raise AssistantError("Give the name of the local model (for example the one you pulled in Ollama).")
        self.model = str(model).strip()
        self.url = local_url(host, port)                    # refuses every address that is not this computer

    def propose(self, description: str, context: SchemaContext) -> list[Proposal]:
        self.notes = []
        answer = net.post_json(self.url, {"model": self.model, "messages": build_messages(description, context),
                                          "stream": False, "format": "json", "options": {"temperature": 0}},
                               use_proxy=False)
        try:
            content = answer["message"]["content"]
        except (KeyError, TypeError):
            raise AssistantError("The local server's answer has no message; it was discarded.") from None
        return parse_provider_json(content)

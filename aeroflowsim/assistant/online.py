# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Provider 3, "Online (your own key)": OFF unless the user opts in, and clearly labelled.

The user's description and the field definitions (never project files, geometry or results) are sent over
the internet to an https address the user types, using the user's own key from the operating system's
keyring. No address is built into AeroFlowSim. The service must understand the common "chat completions"
JSON format (many providers do). Its answer must be the strict JSON of proposal.py, and a model's numbers
must appear in the user's text (review.py).
"""

from urllib.parse import urlparse

from aeroflowsim.assistant import net
from aeroflowsim.assistant.context import SchemaContext, build_messages
from aeroflowsim.assistant.proposal import AssistantError, Proposal, parse_provider_json
from aeroflowsim.assistant.provider import AssistantProvider


def check_online_url(url: str) -> str:
    parts = urlparse(str(url).strip())
    if parts.scheme != "https" or not parts.hostname:
        raise AssistantError("The online address must start with https:// (an encrypted connection).")
    return parts.geturl()


class OnlineProvider(AssistantProvider):
    name = "online"
    label = "Online (your own key)"
    from_model = True
    sends_text_over_internet = True

    def __init__(self, url: str, model: str, key: str):
        super().__init__()
        self.url = check_online_url(url)
        if not str(model).strip():
            raise AssistantError("Give the name of the online model.")
        if not str(key).strip():
            raise AssistantError("No key is stored for the online provider.")
        self.model, self._key = str(model).strip(), str(key).strip()

    def propose(self, description: str, context: SchemaContext) -> list[Proposal]:
        self.notes = []
        answer = net.post_json(self.url, {"model": self.model, "messages": build_messages(description, context),
                                          "temperature": 0, "response_format": {"type": "json_object"}},
                               headers={"Authorization": f"Bearer {self._key}"})
        try:
            content = answer["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise AssistantError("The online answer has no message; it was discarded.") from None
        return parse_provider_json(content)

# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The interface every assistant provider implements."""

from aeroflowsim.assistant.context import SchemaContext
from aeroflowsim.assistant.proposal import Proposal


class AssistantProvider:
    """propose(description, context) -> list of Proposal. The result is UNTRUSTED: review.py checks it."""

    name = "base"                   # short id: "rules", "local", "online"
    label = "Base"                  # shown in the provider drop-down
    from_model = False              # True: a language model wrote the answer (stricter checks in review.py)
    sends_text_over_internet = False
    notes: list[str]                # remarks of the last call that are not proposals (e.g. "could not place 12 mm")

    def __init__(self):
        self.notes = []

    def status_text(self) -> str:
        """The status line of the GUI for this provider."""
        return "Online - text leaves this computer" if self.sends_text_over_internet else "Offline"

    def propose(self, description: str, context: SchemaContext) -> list[Proposal]:
        raise NotImplementedError

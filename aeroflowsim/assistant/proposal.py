# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""A proposal is one suggested input value: (field, value, unit, reason).

Providers return proposals; nothing in this file trusts them. A model's answer must be strict JSON:

    {"proposals": [{"field": "p0", "value": 300, "unit": "bar", "reason": "chamber pressure 300 bar"}, ...]}

(or the bare list). Anything else - text around the JSON, a code fence, unknown keys, wrong types - is
discarded as a whole, so a model cannot smuggle anything in.
"""

import json
from dataclasses import dataclass

MAX_ANSWER_CHARS = 100_000      # a longer answer is not an answer
MAX_PROPOSALS = 60
MAX_REASON_CHARS = 240
ITEM_KEYS = {"field", "value", "unit", "reason"}


class AssistantError(Exception):
    """Something the user should read: server not reachable, answer not valid, opt-in missing, ..."""


@dataclass(frozen=True)
class Proposal:
    field: str          # input key in schema.toml, e.g. "p0"
    value: object       # number, bool or text
    unit: str = ""      # unit the value is written in ("" or "-" for dimensionless / text)
    reason: str = ""    # one short sentence: where in the user's text it came from


def clean_reason(text) -> str:
    """Plain one-line text of limited length (it is shown as text, never as markup)."""
    text = "".join(ch if ch.isprintable() else " " for ch in str(text))
    return " ".join(text.split())[:MAX_REASON_CHARS]


def parse_provider_json(text) -> list[Proposal]:
    """Read a provider's answer. Raises AssistantError unless it is strict JSON of the form above."""
    if not isinstance(text, str) or len(text) > MAX_ANSWER_CHARS:
        raise AssistantError("The answer is missing or far too long; it was discarded.")
    try:
        data = json.loads(text)
    except ValueError:
        raise AssistantError("The answer was not valid JSON; it was discarded.") from None
    if isinstance(data, dict):
        if set(data) != {"proposals"}:
            raise AssistantError('The answer did not have the form {"proposals": [...]}; it was discarded.')
        data = data["proposals"]
    if not isinstance(data, list) or len(data) > MAX_PROPOSALS:
        raise AssistantError(f"The answer did not hold a list of at most {MAX_PROPOSALS} proposals; it was discarded.")
    proposals = []
    for number, item in enumerate(data, 1):
        if not isinstance(item, dict) or not {"field", "value"} <= set(item) or not set(item) <= ITEM_KEYS:
            raise AssistantError(f"Proposal {number} is not {{field, value, unit, reason}}; the answer was discarded.")
        field, value, unit, reason = item["field"], item["value"], item.get("unit", ""), item.get("reason", "")
        if not (isinstance(field, str) and isinstance(unit, str) and isinstance(reason, str)
                and isinstance(value, (int, float, str, bool))):
            raise AssistantError(f"Proposal {number} has values of the wrong type; the answer was discarded.")
        proposals.append(Proposal(field.strip(), value, unit.strip(), clean_reason(reason)))
    return proposals

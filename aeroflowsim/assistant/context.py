# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The schema context: what the assistant is told about a case, built from schema.toml automatically.

A new input in a schema.toml (or a new shape in aeroflowsim/shapes/) is therefore known to the
assistant without any code change. Only the user's text and these FIELD DEFINITIONS go to a model:
never project files, geometry, results or the current values of the inputs.
"""

from dataclasses import dataclass, field

EDITABLE_TYPES = ("float", "int", "bool", "choice", "text", "gas")    # files and boundary tables are never touched
MAX_DESCRIPTION_CHARS = 2000


@dataclass
class SchemaContext:
    """The inputs of one case (list of Parameter) and, for local checks only, their current values."""

    parameters: list
    values: dict = field(default_factory=dict)      # never sent anywhere: used to see which inputs are shown

    def editable(self) -> list:
        """Inputs the assistant may propose a value for, in schema order."""
        return [p for p in self.parameters if p.type in EDITABLE_TYPES]

    def definitions(self) -> list[dict]:
        """One small dict per editable input: key, label, unit, type, range, options, description, condition."""
        out = []
        for p in self.editable():
            item = {"field": p.name, "label": p.label, "type": p.type}
            if p.is_number:
                item.update(unit=p.unit or "-", min=p.min, max=p.max)
            if p.type == "choice":
                item["options"] = list(p.options)
            if p.type == "gas":
                from aeroflowsim.gases import builtin_ids
                item["options"] = list(builtin_ids())
            if p.help:
                item["description"] = p.help
            if p.show_if is not None:
                item["only_if"] = {p.show_if[0]: p.show_if[1]}
            out.append(item)
        return out


SYSTEM_PROMPT = """You help fill in the input form of a CFD program (nozzle and propulsion aerodynamics).
Read the user's description of a case and propose values for the inputs listed below.

Rules:
- Answer with ONE JSON object and nothing else: {"proposals": [{"field": ..., "value": ..., "unit": ..., "reason": ...}]}
- "field" must be one of the listed field keys. Never invent a field.
- "value" is a number, true/false or one of the listed options. Use only numbers the user wrote; never supply a number from memory.
- "unit" is the unit the user wrote (for example bar, mm, K, deg) or the field's unit; use "-" for dimensionless fields and "" for text.
- Gas properties (gamma, gas constant, viscosity, ...) must never be typed: choose the gas by its library id (a "gas" field) instead.
- "reason" is one short sentence quoting the words of the description the value came from.
- If the description does not say something, leave it out. An empty list is a correct answer.
"""


def build_messages(description: str, context: SchemaContext) -> list[dict]:
    """The chat messages for a model: the system rules with the field definitions, then the user's text."""
    import json
    text = " ".join(str(description).split())[:MAX_DESCRIPTION_CHARS]
    system = SYSTEM_PROMPT + "\nFields:\n" + json.dumps(context.definitions(), ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]

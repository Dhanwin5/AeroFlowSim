# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check every proposal against the schema before the user sees it.

A proposal becomes a row of the review table only when:
  - its field is an input of the case that the assistant may touch (not a file or a boundary table);
  - the value has the right kind (number, true/false, one of the options, a built-in library gas);
  - the unit belongs to the input's quantity and is converted to the input's unit;
  - the value is inside the input's [min, max] (parameters.clean_value, the same check as typing it);
  - the input is used with the current choices (show_if), counting the other proposals;
  - for a language model: the number appears in the user's own text, and the field is not a gas property.
Everything else is REJECTED with a message; nothing is dropped silently. Nothing here changes a project.
"""

import math
import re
from dataclasses import dataclass, field

from aeroflowsim.assistant.context import SchemaContext
from aeroflowsim.assistant.proposal import Proposal
from aeroflowsim.assistant.units_map import dimension_of, readings_of, to_schema_unit
from aeroflowsim.parameters import clean_value, is_shown

NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
# Gas properties come from the gas library, never from a model (hard rule 6).
GAS_PROPERTY_WORDS = {"gamma", "viscosity", "conductivity", "prandtl", "molar", "cp", "cv", "sutherland", "gas constant"}


@dataclass
class ReviewRow:
    name: str            # input key
    label: str
    unit: str            # the input's unit (schema.toml)
    old: object
    new: object          # clean value, in the input's unit
    reason: str
    typed: str           # what was proposed, as written: "300 bar"


@dataclass
class Rejection:
    proposal: Proposal
    message: str


@dataclass
class Review:
    rows: list = field(default_factory=list)          # ReviewRow, in the order of the inputs
    rejected: list = field(default_factory=list)      # Rejection
    unchanged: list = field(default_factory=list)     # input keys whose proposed value equals the current one


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=0.0)
        except (TypeError, ValueError):
            return False
    return a == b


def _is_gas_property(p) -> bool:
    words = f"{p.name} {p.label}".lower().replace("_", " ")
    return any(re.search(rf"\b{re.escape(w)}\b", words) for w in GAS_PROPERTY_WORDS)


def _convert(p, proposal: Proposal):
    """Proposal -> clean value in the input's unit. Raises ValueError with a message for the user."""
    value = proposal.value
    if p.type == "bool":
        if not isinstance(value, bool):
            raise ValueError("must be true or false.")
        return clean_value(p, value)
    if isinstance(value, bool):
        raise ValueError("a true/false value is not allowed here.")
    if p.is_number:
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("must be a number.")
        return clean_value(p, to_schema_unit(value, proposal.unit, p.unit))
    if not isinstance(value, str):
        raise ValueError("must be text.")
    if proposal.unit not in ("", "-"):
        raise ValueError(f"this input has no unit, but the proposal gives '{proposal.unit}'.")
    if p.type == "gas":
        from aeroflowsim.gases import builtin_ids
        ids = {i.lower(): i for i in builtin_ids()}
        if value.strip().lower() not in ids:
            raise ValueError(f"only the built-in library gases can be chosen ({', '.join(builtin_ids())}).")
        return clean_value(p, ids[value.strip().lower()])
    if p.type == "choice":
        options = {o.lower(): o for o in p.options}
        value = options.get(value.strip().lower(), value)
    return clean_value(p, value)


def _traceable(p, value, text: str) -> bool:
    """True if a number the user wrote, read in some unit of this input's quantity, equals the value."""
    dimension = dimension_of(p.unit)
    for match in NUMBER.finditer(text):
        for reading in readings_of(float(match.group()), dimension):
            if math.isclose(reading, float(value), rel_tol=1e-6, abs_tol=1e-12):
                return True
    return False


def review_proposals(context: SchemaContext, proposals, *, from_model=False, text="") -> Review:
    """Check proposals; returns the rows to show and the rejections. `text` is the user's description."""
    review = Review()
    known = {p.name: p for p in context.parameters}
    editable = {p.name for p in context.editable()}
    accepted = {}                                    # input key -> (new value, Proposal)
    for proposal in proposals:
        def reject(message, proposal=proposal):
            review.rejected.append(Rejection(proposal, message))

        p = known.get(proposal.field)
        if p is None:
            reject(f"'{proposal.field}' is not an input of this case.")
        elif proposal.field not in editable:
            reject(f"'{p.label}' cannot be filled by the assistant (files and boundary tables are set by hand).")
        elif proposal.field in accepted:
            reject(f"'{p.label}' was proposed twice; only the first proposal is used.")
        elif from_model and _is_gas_property(p):
            reject(f"'{p.label}' is a gas property: choose the gas from the gas library instead of typing numbers.")
        else:
            try:
                new = _convert(p, proposal)
            except ValueError as error:
                reject(f"'{p.label}': {error}")
                continue
            if from_model and p.is_number and not _traceable(p, new, text):
                reject(f"'{p.label}' = {proposal.value} {proposal.unit}: that number is not in your text. "
                       "The assistant may not supply numbers from memory.")
                continue
            accepted[proposal.field] = (new, proposal)

    merged = {**context.values, **{name: new for name, (new, _) in accepted.items()}}
    for p in context.parameters:
        if p.name not in accepted:
            continue
        new, proposal = accepted[p.name]
        if not is_shown(p, merged, context.parameters):
            other, wanted = p.show_if
            review.rejected.append(Rejection(proposal, f"'{p.label}' is not used with the current choices "
                                                       f"(it needs {other} = {wanted})."))
        elif p.name in context.values and _same(context.values[p.name], new):
            review.unchanged.append(p.name)
        else:
            typed = f"{proposal.value} {proposal.unit}".strip() if proposal.unit not in ("", "-") else str(proposal.value)
            review.rows.append(ReviewRow(p.name, p.label, p.unit, context.values.get(p.name), new,
                                         proposal.reason, typed))
    return review

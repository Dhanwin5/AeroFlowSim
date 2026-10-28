# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Provider 1, "Rules (no AI)": a keyword and number parser. Always available, needs no model.

How it reads "Mach 2.4 nitrogen over a 10 degree wedge, 300 bar chamber pressure, 5 bar back pressure":

1. Gas: a gas name or formula in the text ("nitrogen", "N2", "helium", "air") -> the library gas id.
2. Choices: an option of a drop-down named in full in the text ("wedge") -> that option.
3. Numbers: every number (with its unit, if any) is matched to the input whose LABEL words appear next to
   it ("back pressure", "throat diameter", "angle of attack", "cells"). The labels come from schema.toml,
   so a new input is understood without code. The unit must be a unit of the input's quantity (a pressure
   is never put into a temperature); a number with no label words at all is only placed for a pressure
   ("300 bar" -> total pressure) or a temperature ("300 K" -> total temperature), and the reason says so.
A number that cannot be placed is reported in `notes`, never guessed. Every number comes from the user's text.
"""

import re

from aeroflowsim.assistant.context import SchemaContext
from aeroflowsim.assistant.provider import AssistantProvider
from aeroflowsim.assistant.proposal import Proposal
from aeroflowsim.assistant.units_map import LOWER, dimension_of, find_unit
from aeroflowsim.parameters import is_shown

NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
UNIT_NAMES = sorted({u for u in LOWER} | {"bars", "kpas"}, key=len, reverse=True)
QUANTITY = re.compile(r"(?<![\w.])(?P<num>" + NUMBER + r")\s*(?P<unit>" + "|".join(re.escape(u) for u in UNIT_NAMES)
                      + r")?(?![A-Za-z0-9°/²])", re.IGNORECASE)

STOP = {"and", "with", "then", "while", "but", "plus", "also", "use", "using", "over", "around", "through", "into"}
FILL = {"of", "at", "is", "are", "to", "the", "a", "an", "about", "approximately", "equals", "set", "by", "in", "for",
        "on", "its", "as", "be", "from", "roughly", "near"}
SYNONYMS = {"chamber": "total", "stagnation": "total", "reservoir": "total", "plenum": "total", "supply": "total",
            "ambient": "static", "atmospheric": "static", "aoa": "alpha", "incidence": "alpha", "dia": "diameter",
            "diam": "diameter", "backpressure": "back", "cell": "cell", "mesh": "cell"}
GENERIC = {"number", "pressure", "temperature", "diameter", "length", "angle", "ratio", "size", "flow", "rate", "mass",
           "value", "maximum", "min", "minimum", "max"}
THRESHOLD = 0.8                 # a number is placed on an input only with at least this much label evidence
MAX_WORDS = 4                   # label words looked at on each side of a number
BARE_DEFAULTS = {"pressure": ("p0", "p_inf"), "temperature": ("T0", "T_inf")}

GAS_WORDS = {"nitrogen": "N2", "oxygen": "O2", "argon": "Ar", "helium": "He", "krypton": "Kr", "xenon": "Xe",
             "hydrogen": "H2", "carbon dioxide": "CO2", "steam": "H2O", "water vapour": "H2O", "water vapor": "H2O",
             "air": "air", "n2": "N2", "o2": "O2", "h2": "H2", "co2": "CO2", "h2o": "H2O", "r236fa": "R236fa",
             "r-236fa": "R236fa", "r 236fa": "R236fa", "236fa": "R236fa"}


def unit_of(match):
    """The Unit written after a number ('bars' = bar), or None."""
    text = match.group("unit")
    return (find_unit(text) or find_unit(text.rstrip("sS"))) if text else None


def canonical(word: str) -> str:
    """A word in a comparable form: synonyms joined, plurals removed ('cells' -> 'cell')."""
    word = SYNONYMS.get(word, word)
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return SYNONYMS.get(word, word)


def tokens_of(*texts) -> list[str]:
    """Significant label words of an input's label and key, canonical form."""
    words = []
    for text in texts:
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            if word not in FILL and word not in STOP and canonical(word) not in words:
                words.append(canonical(word))
    return words


def side_words(segment: str, side: str) -> list[str]:
    """Label words next to a number: from the number outwards, up to the next punctuation or 'and'/'with'."""
    parts = re.split(r"[,;:.()\n]", segment)
    part = parts[-1] if side == "left" else parts[0]
    words = re.findall(r"[a-z0-9]+", part.lower())
    if side == "left":
        words.reverse()
    out = []
    for word in words:
        if word in STOP:
            break
        if word in FILL:
            continue
        out.append(canonical(word))
        if len(out) == MAX_WORDS:
            break
    return out


def word_weight(token: str) -> float:
    return 0.4 if token in GENERIC else 1.0


def score(field_tokens, words) -> tuple[float, list[str]]:
    """Label evidence of `words` for an input: matched weight, minus a little for label words not mentioned."""
    matched = [t for t in field_tokens if t in words]
    missing = [t for t in field_tokens if t not in words]
    return sum(map(word_weight, matched)) - 0.05 * sum(map(word_weight, missing)), matched


class RulesProvider(AssistantProvider):
    name = "rules"
    label = "Rules (no AI)"

    def propose(self, description: str, context: SchemaContext) -> list[Proposal]:
        self.notes = []
        text = re.sub(r"\bM\s*=\s*(?=\d)", "mach ", " ".join(str(description).split()))
        proposals = []
        merged = dict(context.values)                       # current values + the choices proposed so far
        proposals += self._gas(text, context, merged)
        proposals += self._choices(text, context, merged)
        proposals += self._numbers(text, context, merged)
        return proposals

    # ---------------------------------------------------------------------------------- gas, choices

    def _gas(self, text, context, merged):
        fields = [p for p in context.editable() if p.type == "gas"]
        found = {}
        for word, gas_id in GAS_WORDS.items():
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", text, re.IGNORECASE):
                found.setdefault(gas_id, word)
        if not fields or not found:
            return []
        if len(found) > 1:
            self.notes.append("Several gases are named (" + ", ".join(found.values()) + "): name one.")
            return []
        (gas_id, word), = found.items()
        merged[fields[0].name] = gas_id
        return [Proposal(fields[0].name, gas_id, "", f'"{word}" is the library gas {gas_id}')]

    def _choices(self, text, context, merged):
        proposals = []
        lowered = text.lower()
        for _ in range(2):                                  # a second pass for choices that appear after another choice
            for p in context.editable():
                if p.type != "choice" or any(q.field == p.name for q in proposals):
                    continue
                if p.show_if is not None and not is_shown(p, merged, context.parameters):
                    continue
                hits = {}
                for option in p.options:
                    phrase = re.sub(r"\(.*?\)", "", option).strip().lower()
                    if len(phrase) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", lowered):
                        hits[option] = phrase
                for option in list(hits):                   # "blunted cone" hides "cone"
                    if any(other != option and hits[option] in hits[other] for other in hits):
                        del hits[option]
                if len(hits) == 1:
                    (option, phrase), = hits.items()
                    merged[p.name] = option
                    proposals.append(Proposal(p.name, option, "", f'"{phrase}" is an option of {p.label}'))
                elif len(hits) > 1:
                    self.notes.append(f"{p.label}: several options are named ({', '.join(hits)}): name one.")
        return proposals

    # ---------------------------------------------------------------------------------- numbers

    def _numbers(self, text, context, merged):
        matches = list(QUANTITY.finditer(text))
        fields = [p for p in context.editable() if p.is_number and is_shown(p, merged, context.parameters)]
        field_tokens = {p.name: tokens_of(p.label, p.name.replace(".", " ").replace("_", " ")) for p in fields}
        pairs = []                                          # (score, number index, input, interpretation, matched words)
        for i, m in enumerate(matches):
            before = text[matches[i - 1].end() if i else 0:m.start()]
            after = text[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)]
            unit = unit_of(m)
            for with_unit in ([True, False] if unit and unit.quantity not in BARE_DEFAULTS else [True] if unit else [False]):
                words_after = after if with_unit or not m.group("unit") else f"{m.group('unit')} {after}"
                words = side_words(before, "left") + side_words(words_after, "right")
                dimension = unit.quantity if with_unit else "dimensionless"
                for p in fields:
                    if dimension_of(p.unit) != dimension:
                        continue
                    value, matched = score(field_tokens[p.name], words)
                    if matched and value >= THRESHOLD:
                        pairs.append((value - (0.0 if with_unit else 0.01), i, p, with_unit, matched))
        pairs.sort(key=lambda t: -t[0])
        taken_numbers, taken_fields, chosen = set(), set(), {}
        for value, i, p, with_unit, matched in pairs:
            if i not in taken_numbers and p.name not in taken_fields:
                taken_numbers.add(i)
                taken_fields.add(p.name)
                chosen[i] = (p, with_unit, f'"{matches[i].group(0).strip()}" next to "{" ".join(matched)}"')
        for i, m in enumerate(matches):                     # a pressure or temperature with no label at all
            unit = unit_of(m)
            if i in chosen or unit is None or unit.quantity not in BARE_DEFAULTS:
                continue
            before = text[matches[i - 1].end() if i else 0:m.start()]
            after = text[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)]
            if any(t not in GENERIC for t in side_words(before, "left") + side_words(after, "right")
                   if any(t in field_tokens[p.name] for p in fields)):
                continue                                    # label words that name another input: do not guess
            for name in BARE_DEFAULTS[unit.quantity]:
                p = next((q for q in fields if q.name == name), None)
                if p is not None and name not in taken_fields:
                    taken_fields.add(name)
                    chosen[i] = (p, True, f'"{m.group(0).strip()}" has no label: taken as the {p.label.lower()}')
                    break
        proposals = []
        for i, m in enumerate(matches):
            if i not in chosen:
                if m.group("unit"):
                    self.notes.append(f'Could not place "{m.group(0).strip()}": say what it is, e.g. "throat diameter {m.group(0).strip()}".')
                continue
            p, with_unit, reason = chosen[i]
            number = float(m.group("num"))
            if p.is_integer and number == int(number):
                number = int(number)
            unit = unit_of(m) if with_unit else None
            proposals.append(Proposal(p.name, number, unit.name if unit else "", reason))
        order = {p.name: k for k, p in enumerate(context.parameters)}
        return sorted(proposals, key=lambda pr: order.get(pr.field, 0))

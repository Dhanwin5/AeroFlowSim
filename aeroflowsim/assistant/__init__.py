# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optional assistant: turns a plain-English description of a case into proposed input values.

It assists, it never replaces physics. It can only PROPOSE values for inputs that exist in a case's
schema.toml; every proposal is checked against the schema (type, unit, range) and shown in a review
table, and nothing changes until the user ticks it and presses Apply (one undo step).

This file deliberately imports nothing: the desktop GUI and the command line import nothing from this
package until the user turns the assistant on (tests/test_assistant.py). Modules:

    proposal.py   Proposal, AssistantError, strict JSON reading of a provider's answer
    units_map.py  units a proposal may use (reuses aeroflowsim/units.py)
    context.py    SchemaContext: the field definitions built from schema.toml, and the prompt text
    review.py     checks proposals against the schema -> Review (rows to tick, rejected proposals)
    provider.py   AssistantProvider base class
    rules.py      provider 1, "Rules (no AI)": keyword and number parser, always available
    local.py      provider 2, "Local model": a server on this computer (e.g. Ollama), localhost only
    online.py     provider 3, "Online (your own key)": opt-in, the text leaves this computer
    net.py        the ONLY place with network code (imported by local.py and online.py only)
    keystore.py   the online key, in the operating system's keyring (never in a project file)
    config.py     AssistantSettings (what the user chose in Settings) and make_provider()
"""

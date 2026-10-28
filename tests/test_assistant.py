# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The optional assistant (Prompt 7c): proposals are checked against the schema, the rules provider reads
plain English, nothing is contacted unless a local / online provider is chosen, and nothing outside the
schema's inputs can be changed. No network and no model are needed: a fake provider stands in."""

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from aeroflowsim.assistant.config import AssistantSettings, is_local_host, make_provider
from aeroflowsim.assistant.context import SchemaContext
from aeroflowsim.assistant.proposal import AssistantError, Proposal, parse_provider_json
from aeroflowsim.assistant.provider import AssistantProvider
from aeroflowsim.assistant.review import review_proposals
from aeroflowsim.assistant.rules import RulesProvider
from aeroflowsim.discovery import load_case
from aeroflowsim.parameters import defaults

PROJECT_DIR = Path(__file__).resolve().parent.parent


def context(case="quasi1d_nozzle", **changes):
    parameters = load_case(case).parameters()
    return SchemaContext(parameters, {**defaults(parameters), **changes})


class FakeProvider(AssistantProvider):
    """Answers with fixed proposals (like a model would), without any model or network."""
    name, label, from_model = "fake", "Fake", True

    def __init__(self, proposals):
        super().__init__()
        self.proposals = proposals

    def propose(self, description, context):
        return list(self.proposals)


def new_values(text, case="quasi1d_nozzle", **changes):
    """{input: value} the rules provider proposes for `text` (after the schema review)."""
    ctx = context(case, **changes)
    provider = RulesProvider()
    review = review_proposals(ctx, provider.propose(text, ctx), text=text)
    return {row.name: row.new for row in review.rows}


# ---------------------------------------------------------------------------------- strict JSON

def test_provider_json_must_be_strict():
    good = '{"proposals": [{"field": "p0", "value": 300, "unit": "bar", "reason": "chamber pressure"}]}'
    assert parse_provider_json(good) == [Proposal("p0", 300, "bar", "chamber pressure")]
    assert parse_provider_json('[{"field": "mach", "value": 2.4}]') == [Proposal("mach", 2.4, "", "")]
    assert parse_provider_json('{"proposals": []}') == []
    for bad in ("Sure! " + good, "```json\n" + good + "\n```", "not json", '{"answer": []}', '{"proposals": 3}',
                '[{"field": "p0"}]', '[{"field": "p0", "value": 1, "run": "rm -rf"}]', '[{"field": 7, "value": 1}]',
                '[{"field": "p0", "value": [1]}]', '[{"field": "p0", "value": {"a": 1}}]', "x" * 200_000):
        with pytest.raises(AssistantError):
            parse_provider_json(bad)


# ---------------------------------------------------------------------------------- review against the schema

def test_valid_proposals_become_review_rows_in_the_inputs_own_units():
    ctx = context()
    review = review_proposals(ctx, [Proposal("p0", 300, "bar", "r"), Proposal("T0", 30, "°C"),
                                    Proposal("d_throat", 2, "mm"), Proposal("gas", "he"), Proposal("n_cells", 400)])
    values = {r.name: r.new for r in review.rows}
    assert not review.rejected
    assert values["p0"] == pytest.approx(3e7) and values["T0"] == pytest.approx(303.15)
    assert values["d_throat"] == pytest.approx(0.002) and values["gas"] == "He" and values["n_cells"] == 400
    assert isinstance(values["n_cells"], int)
    old = {r.name: r.old for r in review.rows}
    assert old["p0"] == ctx.values["p0"]


def test_out_of_range_unknown_field_and_wrong_unit_are_rejected():
    ctx = context()
    proposals = [Proposal("T0", 5000000, "K"), Proposal("n_cells", 4.5), Proposal("not_an_input", 1, ""),
                 Proposal("p0", 300, "K"), Proposal("p0", 300, ""), Proposal("p0", 300, "furlongs"),
                 Proposal("n_cells", 100, "bar"), Proposal("gas", "unobtainium"), Proposal("cfl", "fast"),
                 Proposal("geometry_source", "Teleport"), Proposal("p_back", float("nan"), "Pa")]
    review = review_proposals(ctx, proposals)
    assert not review.rows and len(review.rejected) == len(proposals)
    messages = " | ".join(r.message for r in review.rejected)
    assert "outside the allowed range" in messages and "not an input of this case" in messages
    assert "unit of temperature" in messages and "a unit is needed" in messages and "unknown unit" in messages


def test_files_boundary_tables_and_custom_gas_files_cannot_be_filled():
    ctx = context("external_2d")
    names = {p.name: p.type for p in ctx.parameters}
    files = [n for n, t in names.items() if t == "file"]
    boundaries = [n for n, t in names.items() if t == "boundaries"]
    assert files and boundaries
    review = review_proposals(ctx, [Proposal(files[0], "C:/secret.csv"), Proposal(boundaries[0], "{}"),
                                    Proposal("gas", "C:/gases/mine.toml")])
    assert not review.rows and len(review.rejected) == 3


def test_an_input_that_is_not_used_with_the_current_choices_is_rejected_unless_the_choice_is_proposed_too():
    ctx = context("external_2d", shape="NACA 4-digit airfoil")
    alone = review_proposals(ctx, [Proposal("wedge.half_angle", 12, "deg")])
    assert not alone.rows and "not used with the current choices" in alone.rejected[0].message
    together = review_proposals(ctx, [Proposal("wedge.half_angle", 12, "deg"), Proposal("shape", "Wedge")])
    assert {r.name for r in together.rows} == {"shape", "wedge.half_angle"} and not together.rejected


def test_unchanged_values_and_duplicates_are_reported_not_applied():
    ctx = context()
    review = review_proposals(ctx, [Proposal("p0", 500, "kPa"), Proposal("T0", 400, "K"), Proposal("T0", 500, "K")])
    assert review.unchanged == ["p0"]                                  # 500 kPa is the default
    assert [r.name for r in review.rows] == ["T0"] and review.rows[0].new == 400
    assert "proposed twice" in review.rejected[0].message


def test_a_models_numbers_must_come_from_the_text_and_it_may_not_type_gas_properties():
    ctx = context()
    text = "nitrogen at 300 bar chamber pressure and 400 K"
    ok = review_proposals(ctx, [Proposal("p0", 300, "bar"), Proposal("T0", 400, "K"), Proposal("p0", 3e7, "Pa")],
                          from_model=True, text=text)
    assert {r.name for r in ok.rows} == {"p0", "T0"}
    invented = review_proposals(ctx, [Proposal("T0", 293.15, "K"), Proposal("p_back", 101325, "Pa")],
                                from_model=True, text=text)
    assert not invented.rows and all("not in your text" in r.message for r in invented.rejected)
    sod = context("sod_shock_tube")
    gas = review_proposals(sod, [Proposal("gamma", 1.4, "-")], from_model=True, text="gamma 1.4")
    assert "gas property" in gas.rejected[0].message
    typed = review_proposals(sod, [Proposal("gamma", 1.3, "-")], text="gamma 1.3")       # the user's own number: allowed
    assert [r.name for r in typed.rows] == ["gamma"]


# ---------------------------------------------------------------------------------- the rules provider

PHRASES = [      # (case, text, expected {input: value}); every value in the inputs' own (SI) unit
    ("quasi1d_nozzle", "300 bar chamber pressure", {"p0": 3e7}),
    ("quasi1d_nozzle", "5 bar back pressure", {"p_back": 5e5}),
    ("quasi1d_nozzle", "back pressure of 5 bar", {"p_back": 5e5}),
    ("quasi1d_nozzle", "300 bar", {"p0": 3e7}),
    ("quasi1d_nozzle", "chamber temperature 400 K", {"T0": 400}),
    ("quasi1d_nozzle", "stagnation temperature of 25 C", {"T0": 298.15}),
    ("quasi1d_nozzle", "nitrogen", {}),                                    # already the default gas: unchanged
    ("quasi1d_nozzle", "helium nozzle", {"gas": "He"}),
    ("quasi1d_nozzle", "hydrogen, 50 bar", {"gas": "H2", "p0": 5e6}),
    ("quasi1d_nozzle", "carbon dioxide at 10 bar", {"gas": "CO2", "p0": 1e6}),
    ("quasi1d_nozzle", "throat diameter 2 mm", {"d_throat": 0.002}),
    ("quasi1d_nozzle", "exit diameter 1.2 cm and throat diameter 3 mm", {"d_exit": 0.012, "d_throat": 0.003}),
    ("quasi1d_nozzle", "divergent half angle 12 degrees", {"half_angle_div": 12}),
    ("quasi1d_nozzle", "convergent half-angle of 25 deg", {"half_angle_conv": 25}),
    ("quasi1d_nozzle", "500 cells", {"n_cells": 500}),
    ("quasi1d_nozzle", "5000 iterations and CFL 0.4", {"max_iter": 5000, "cfl": 0.4}),
    ("quasi1d_nozzle", "air, 10 bar chamber, 1 bar back pressure, 350 K",
     {"gas": "air", "p0": 1e6, "p_back": 1e5, "T0": 350}),
    ("quasi1d_nozzle", "Nitrogen at 300 bar and 400 K with 2 bar back pressure", {"p0": 3e7, "T0": 400, "p_back": 2e5}),
    ("external_2d", "Mach 2.4", {"mach": 2.4}),
    ("external_2d", "M = 3", {"mach": 3}),
    ("external_2d", "Mach 2.4 flow of nitrogen over a 10 degree wedge", {"mach": 2.4, "gas": "N2", "shape": "Wedge"}),
    ("external_2d", "12 degree wedge", {"shape": "Wedge", "wedge.half_angle": 12}),
    ("external_2d", "angle of attack 4 degrees", {"alpha": 4}),
    ("external_2d", "alpha = 2 deg, Mach 0.8", {"alpha": 2, "mach": 0.8}),
    ("external_2d", "free stream 50 kPa and 250 K", {"p_inf": 5e4, "T_inf": 250}),
    ("external_2d", "static pressure 0.5 atm", {"p_inf": 50662.5}),
    ("external_2d", "2 psi static pressure", {"p_inf": 13789.514}),
]


@pytest.mark.parametrize("case,text,expected", PHRASES)
def test_rules_provider_phrases(case, text, expected):
    got = new_values(text, case)
    assert set(got) == set(expected), (text, got)
    for key, value in expected.items():
        assert got[key] == pytest.approx(value, rel=1e-4), (text, key)


def test_rules_provider_places_nothing_it_cannot_explain():
    ctx = context()
    provider = RulesProvider()
    assert provider.propose("a nice quiet afternoon", ctx) == []
    assert provider.propose("12 mm", ctx) == [] and "Could not place" in provider.notes[0]
    assert provider.propose("helium or argon", ctx) == [] and "Several gases" in provider.notes[0]
    ctx = context("external_2d")
    for proposal in provider.propose("Mach 2.4 over a 10 degree wedge, 300 K", ctx):
        assert proposal.reason                                                    # every proposal says why


def test_a_pressure_is_never_put_into_a_temperature_or_the_other_way_round():
    got = new_values("300 K chamber pressure")
    assert "p0" not in got                                                         # K is not a pressure unit
    assert new_values("400 K back pressure") == {}                                 # K is no pressure either


# ---------------------------------------------------------------------------------- off, offline, opt-in

def test_nothing_is_imported_or_opened_until_the_assistant_is_used():
    code = ("import sys, socket\n"
            "def no(*a, **k): raise RuntimeError('socket opened')\n"
            "socket.socket = no\n"
            "import aeroflowsim, aeroflowsim.cli, aeroflowsim.engine, aeroflowsim.project\n"
            "from aeroflowsim import cli\n"
            "cli.main(['list'])\n"
            "bad = [m for m in sys.modules if m.startswith('aeroflowsim.assistant')]\n"
            "print('LOADED', bad)\n")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=PROJECT_DIR)
    assert "LOADED []" in done.stdout, done.stdout + done.stderr


def test_the_rules_provider_and_the_command_line_open_no_sockets(monkeypatch, capsys):
    def no_socket(*args, **kwargs):
        raise AssertionError("a socket was opened")
    monkeypatch.setattr(socket.socket, "__init__", no_socket)
    from aeroflowsim import cli
    assert cli.main(["assist", "Mach 3 nitrogen over a wedge, 50 kPa", "--case", "external_2d", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Rules (no AI)" in out and "Offline" in out and "mach" in out


def test_only_the_network_module_has_network_code():
    folder = PROJECT_DIR / "aeroflowsim" / "assistant"
    for path in folder.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "net.py":
            continue
        assert "import urllib" not in text and "import socket" not in text and "import requests" not in text, path.name
    local_and_online = {p.name for p in folder.glob("*.py") if "from aeroflowsim.assistant import net" in p.read_text(encoding="utf-8")}
    assert local_and_online == {"local.py", "online.py"}


def test_the_local_model_must_be_on_this_computer():
    for host in ("localhost", "LOCALHOST", "127.0.0.1", "127.1.2.3", "::1", "[::1]", "ollama.localhost"):
        assert is_local_host(host), host
    for host in ("example.com", "localhost.evil.com", "192.168.1.5", "0.0.0.0", "10.0.0.1", "", "127.0.0.1.evil.com",
                 "evil.com#localhost"):
        assert not is_local_host(host), host
    from aeroflowsim.assistant.local import LocalModelProvider
    with pytest.raises(AssistantError):
        LocalModelProvider("m", host="example.com")
    with pytest.raises(AssistantError):
        LocalModelProvider("", host="localhost")
    with pytest.raises(AssistantError):
        LocalModelProvider("m", host="localhost", port=0)


def test_the_local_provider_reads_a_servers_answer_strictly(monkeypatch):
    from aeroflowsim.assistant import net
    from aeroflowsim.assistant.local import LocalModelProvider
    seen = {}

    def fake_post(url, payload, headers=None, *, use_proxy=True):
        seen.update(url=url, payload=payload, use_proxy=use_proxy)
        return {"message": {"content": json.dumps({"proposals": [{"field": "p0", "value": 300, "unit": "bar"}]})}}

    monkeypatch.setattr(net, "post_json", fake_post)
    ctx = context()
    proposals = LocalModelProvider("llama", port=11434).propose("300 bar", ctx)
    assert proposals == [Proposal("p0", 300, "bar", "")] and seen["url"].startswith("http://localhost:11434/")
    assert seen["use_proxy"] is False
    prompt = json.dumps(seen["payload"]["messages"])
    assert "p0" in prompt and "300 bar" in prompt                                   # field definitions + the user's text
    assert str(ctx.values["T0"]) not in prompt                                      # not the current values
    monkeypatch.setattr(net, "post_json", lambda *a, **k: {"message": {"content": "Sure, here you go: p0 = 300 bar"}})
    with pytest.raises(AssistantError):
        LocalModelProvider("llama").propose("300 bar", ctx)


def test_only_the_users_text_and_field_definitions_are_sent():
    from aeroflowsim.assistant.context import build_messages
    ctx = context("external_2d")
    ctx.values["profile_file"] = "C:/Users/me/secret_geometry.csv"
    sent = json.dumps(build_messages("Mach 2", ctx))
    assert "secret_geometry" not in sent and "mach" in sent and "Mach 2" in sent
    keys = {d["field"] for d in ctx.definitions()}
    assert not {p.name for p in ctx.parameters if p.type in ("file", "boundaries")} & keys


def test_the_online_provider_cannot_be_chosen_without_an_explicit_opt_in():
    off = AssistantSettings(enabled=False)
    with pytest.raises(AssistantError, match="off"):
        make_provider(off, "rules")                                                 # the assistant itself is off
    no_opt_in = AssistantSettings(enabled=True, provider="online", online_url="https://x.example/v1/chat", online_model="m")
    with pytest.raises(AssistantError, match="explicitly"):
        make_provider(no_opt_in)
    assert dict((n, ok) for n, _, ok in no_opt_in.selectable()) == {"rules": True, "local": True, "online": False}
    opted = AssistantSettings(enabled=True, provider="online", online_opt_in=True)
    assert dict((n, ok) for n, _, ok in opted.selectable())["online"] is True
    assert make_provider(AssistantSettings(enabled=True)).name == "rules"
    from aeroflowsim.assistant.online import OnlineProvider, check_online_url
    with pytest.raises(AssistantError):
        check_online_url("http://insecure.example/v1")
    with pytest.raises(AssistantError):
        OnlineProvider("https://x.example/v1", "m", "")
    provider = OnlineProvider("https://x.example/v1/chat", "m", "key")
    assert provider.sends_text_over_internet and "text leaves this computer" in provider.status_text()
    assert RulesProvider().status_text() == "Offline"


def test_settings_default_to_off_and_online_off():
    default = AssistantSettings.from_mapping(lambda name, default=None: default)
    assert default.enabled is False and default.online_opt_in is False and default.provider == "rules"
    stored = {"enabled": "true", "provider": "hacker", "local_port": "abc", "online_opt_in": "false"}
    got = AssistantSettings.from_mapping(lambda name, default=None: stored.get(name, default))
    assert got.enabled and got.provider == "rules" and got.local_port == 11434 and not got.online_opt_in


# ---------------------------------------------------------------------------------- command line

def test_cli_dry_run_changes_nothing_and_apply_writes_only_schema_inputs(tmp_path, capsys):
    from aeroflowsim import cli
    from aeroflowsim.project import Project
    project = Project.create("quasi1d_nozzle", tmp_path / "A.afsproj")
    before = (project.folder / "project.yaml").read_text(encoding="utf-8")
    assert cli.main(["assist", "300 bar chamber pressure, helium", "--case", str(project.folder), "--dry-run"]) == 0
    assert (project.folder / "project.yaml").read_text(encoding="utf-8") == before
    assert "p0" in capsys.readouterr().out
    assert cli.main(["assist", "x", "--case", str(project.folder), "--dry-run", "--apply"]) == 1
    assert cli.main(["assist", "300 bar chamber pressure, helium", "--case", str(project.folder), "--apply"]) == 0
    reopened = Project.open(project.folder)
    assert reopened.values["p0"] == pytest.approx(3e7) and reopened.values["gas"] == "He"
    changed = {k for k in reopened.values if reopened.values[k] != project.values.get(k)}
    assert changed == {"p0", "gas"}
    assert cli.main(["assist", "300 bar", "--case", "quasi1d_nozzle", "--apply"]) == 1       # a template is read-only
    assert cli.main(["assist", "x", "--case", str(project.folder), "--provider", "online"]) == 1  # no opt-in, no key, no call
    assert cli.main(["assist", "x", "--case", str(project.folder), "--provider", "local", "--host", "example.com",
                     "--model", "m"]) == 1

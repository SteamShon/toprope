import copy
import json
import subprocess
from datetime import datetime, timezone

import pytest
import yaml

from test_handoffs import RECEIVER, SENDER
from toprope.compose import (accepts, assemble, check_composition, composed_world_map, how_to_reach_across,
                             load_composition)
from toprope.handoff import Outbox
from toprope.identity import Caller, StaticIdentity
from toprope.semantics import Actor
from toprope.store import MemoryEventStore

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)
OWEN = Actor("owen", "person", ("owner",))
COMPOSITION = {"composition": "self", "version": 1,
               "members": {"authoring": {"declaration": "authoring.domain.yaml", "interface": 1},
                           "delivery": {"declaration": "delivery.domain.yaml", "interface": 1}},
               "wiring": [{"from": "authoring.deliver", "to": "delivery.request_delivery"}]}


def write(tmp_path, comp=None, sender=None, receiver=None):
    (tmp_path / "authoring.domain.yaml").write_text(yaml.safe_dump(sender or SENDER, sort_keys=False))
    (tmp_path / "delivery.domain.yaml").write_text(yaml.safe_dump(receiver or RECEIVER, sort_keys=False))
    p = tmp_path / "self.composition.yaml"
    p.write_text(yaml.safe_dump(comp or COMPOSITION, sort_keys=False))
    return p


def codes(tmp_path, **kw):
    return {(i.code, i.where) for i in check_composition(load_composition(write(tmp_path, **kw)))}


def test_a_well_wired_composition_is_clean(tmp_path):
    assert codes(tmp_path) == set()
    c = load_composition(write(tmp_path))
    assert accepts(c) == {"authoring": {}, "delivery": {"request_delivery": {"authoring.deliver"}}}


def test_every_handoff_is_wired_exactly_as_declared(tmp_path):
    unwired = copy.deepcopy(COMPOSITION)
    unwired["wiring"] = []
    assert ("unwired-handoff", "members.authoring.handoffs.deliver") in codes(tmp_path, comp=unwired)
    wrong = copy.deepcopy(COMPOSITION)
    wrong["wiring"] = [{"from": "authoring.deliver", "to": "delivery.something_else"}]
    assert ("wire-mismatch", "wiring[0]") in codes(tmp_path, comp=wrong)
    ghost = copy.deepcopy(COMPOSITION)
    ghost["wiring"].append({"from": "authoring.ghost", "to": "delivery.request_delivery"})
    assert ("unknown-handoff", "wiring[1]") in codes(tmp_path, comp=ghost)
    twice = copy.deepcopy(COMPOSITION)
    twice["wiring"].append(dict(twice["wiring"][0]))
    assert ("duplicate-wire", "wiring[1]") in codes(tmp_path, comp=twice)
    stranger = copy.deepcopy(COMPOSITION)
    stranger["wiring"] = [{"from": "billing.x", "to": "delivery.request_delivery"}]
    assert ("unknown-member", "wiring[0]") in codes(tmp_path, comp=stranger)


def test_members_are_keyed_by_domain_and_checked(tmp_path):
    renamed = copy.deepcopy(COMPOSITION)
    renamed["members"]["auth"] = renamed["members"].pop("authoring")
    renamed["wiring"] = [{"from": "auth.deliver", "to": "delivery.request_delivery"}]
    assert ("member-name", "members.auth") in codes(tmp_path, comp=renamed)
    bad = copy.deepcopy(SENDER)
    bad["actions"]["approve_version"]["actor"] = ["nobody"]
    assert ("unknown-role", "members.authoring.actions.approve_version") in codes(tmp_path, sender=bad)


def test_the_published_major_comes_from_the_composition(tmp_path):
    v2 = copy.deepcopy(COMPOSITION)
    v2["members"]["delivery"]["interface"] = 2
    assert ("interface-major", "members.authoring.handoffs.deliver.to") in codes(tmp_path, comp=v2)


def test_receivers_accept_only_wired_handoffs(tmp_path):
    c = load_composition(write(tmp_path))
    ids = StaticIdentity({"t-owen": Caller(OWEN)})
    exs = assemble(c, {n: MemoryEventStore() for n in c.domains}, ids, clock=lambda: NOW)
    exs["authoring"].seed_world()
    assert exs["authoring"].submit("t-owen", "approve_version", "V1", idempotency_key="k1").ok
    created = exs["delivery"].history("shop:3")[0]
    assert created.actor == {"id": "handoff:authoring.deliver", "kind": "system"}
    # A handoff that is not wired is refused before evaluation, and recorded.
    out = exs["delivery"].receive_handoff("billing.charge", "request_delivery", "x:1",
                                          {"domain_id": "x", "version": 1, "approver": "a", "environment": "local"},
                                          "charge:B1@2", None)
    assert out.status == "denied" and out.code == "actor" and "not wired" in out.reason
    (att,) = exs["delivery"].attempts("x:1")
    assert att.payload["code"] == "actor" and att.causation == "charge:B1@2"
    assert exs["delivery"].state("x:1") is None
    assert Outbox(exs["authoring"]).pending() == []


def test_composed_world_map_and_paths_across_domains(tmp_path):
    receiver = copy.deepcopy(RECEIVER)
    receiver["roles"] = ["approver"]
    receiver["actions"]["deploy"] = {"description": "Deploy a requested version.", "actor": ["approver"],
                                     "target": "DeliveryRequest"}
    receiver["transitions"]["DeliveryRequest"]["matrix"] = {"requested": {"deploy": "deployed"},
                                                            "deployed": {"deploy": "n/a"}}
    c = load_composition(write(tmp_path, receiver=receiver))
    assert check_composition(c) == []
    m = composed_world_map(c)
    assert m["wires"] == [{"from": {"domain": "authoring", "handoff": "deliver", "action": "approve_version"},
                           "to": {"domain": "delivery", "action": "request_delivery", "object": "DeliveryRequest",
                                  "creates": True}}]
    p = how_to_reach_across(m, "authoring", "Version", "draft", "delivery", "DeliveryRequest", "deployed", ("owner",))
    assert [(s["domain"], s["action"], s["from"], s["to"], s["who"], s["you_can"]) for s in p["steps"]] == [
        ("authoring", "approve_version", "draft", "approved", ["owner"], True),
        ("delivery", "request_delivery", "(new)", "requested", ["system (handoff authoring.deliver)"], False),
        ("delivery", "deploy", "requested", "deployed", ["approver"], False)]
    no = how_to_reach_across(m, "authoring", "Version", "approved", "delivery", "DeliveryRequest", "deployed")
    assert no["reachable"] is False                  # approved versions cannot be approved again


def test_cli_checks_a_composition_then_runs_each_member(tmp_path):
    p = write(tmp_path)
    run = lambda *a: subprocess.run(["uv", "run", "--quiet", *a], capture_output=True, text=True, timeout=180)  # noqa: E731
    ok = run("toprope-harness", "--composition", str(p), "--levels", "model", "--examples", "5")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "== authoring" in ok.stdout and "== delivery" in ok.stdout
    bad = copy.deepcopy(COMPOSITION)
    bad["wiring"] = []
    ko = run("toprope-harness", "--composition", str(write(tmp_path, comp=bad)), "--levels", "model")
    assert ko.returncode == 1 and "unwired-handoff" in ko.stderr
    out = tmp_path / "map.json"
    wm = run("toprope-worldmap", "--composition", str(write(tmp_path)), "--out", str(out))
    assert wm.returncode == 0 and json.loads(out.read_text())["format"] == "toprope.world-map.composed/1"
    both = run("toprope-harness", "--composition", str(p), "--domain", str(tmp_path / "authoring.domain.yaml"))
    assert both.returncode != 0

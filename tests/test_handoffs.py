import copy
from datetime import datetime, timezone

import pytest

from toprope.decl import Domain, check_handoffs, validate_domain
from toprope.exec import Execution
from toprope.expr import EvalError, Env, evaluate, parse
from toprope.handoff import LocalTransport, Outbox
from toprope.identity import Caller, StaticIdentity
from toprope.semantics import Actor, Grant
from toprope.store import MemoryEventStore

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)
OWEN = Actor("owen", "person", ("owner",))
BOT = Actor("bot", "agent", ("owner",))

SENDER = {
    "domain": "authoring", "version": 1, "roles": ["owner"],
    "objects": {"Version": {"properties": {
        "status": {"enum": ["draft", "approved"]}, "domain_id": {"type": "string"},
        "number": {"type": "integer"}}}},
    "actions": {"approve_version": {"description": "Approve a domain version.", "actor": ["owner"],
                                    "target": "Version"}},
    "transitions": {"Version": {"field": "status", "initial": "draft", "matrix": {
        "draft": {"approve_version": "approved"},
        "approved": {"approve_version": {"deny": "Already approved."}}}}},
    "handoffs": {"deliver": {
        "when": {"action": "approve_version"},
        "to": {"domain": "delivery", "interface": "1.x", "action": "request_delivery"},
        "params": {"domain_id": "target.domain_id", "version": "target.number",
                   "approver": "actor.id", "environment": "'local'"},
        "target": "target.domain_id + ':' + target.number"}},
    "world": {"fixtures": [{"Version": {"id": "V1", "status": "draft", "domain_id": "shop", "number": 3}}]},
}

RECEIVER = {
    "domain": "delivery", "version": 1, "roles": ["approver"],
    "objects": {"DeliveryRequest": {"properties": {
        "status": {"enum": ["requested", "deployed"]}, "domain_id": {"type": "string"},
        "version": {"type": "integer"}, "approver": {"type": "string"}, "environment": {"enum": ["local"]}}}},
    "actions": {
        "request_delivery": {"description": "Request delivery of an approved version.", "actor": ["system"],
                             "creates": "DeliveryRequest",
                             "params": {"domain_id": {"type": "string"}, "version": {"type": "integer"},
                                        "approver": {"type": "string"}, "environment": {"enum": ["local"]}},
                             "preconditions": [{"id": "positive-version", "check": "params.version >= 1",
                                                "reason": "A version number starts at 1."}]}},
    "transitions": {"DeliveryRequest": {"field": "status", "initial": "requested", "matrix": {
        "requested": {}, "deployed": {}}}},
}


def domains(mut_s=None, mut_r=None):
    s, r = copy.deepcopy(SENDER), copy.deepcopy(RECEIVER)
    if mut_s:
        mut_s(s)
    if mut_r:
        mut_r(r)
    return Domain.model_validate(s), Domain.model_validate(r)


def pair(mut_s=None, mut_r=None, transport=True):
    ds, dr = domains(mut_s, mut_r)
    receiver = Execution(dr, MemoryEventStore(), StaticIdentity({}), clock=lambda: NOW)
    ids = StaticIdentity({"t-owen": Caller(OWEN), "t-bot": Caller(BOT, OWEN, Grant("g", frozenset({"approve_version"})))})
    sender = Execution(ds, MemoryEventStore(), ids, clock=lambda: NOW,
                       transport=LocalTransport({"delivery": receiver}) if transport else None)
    sender.seed_world()
    return sender, receiver


# -- the contract, at compile time ---------------------------------------------------------------
def test_declarations_and_contract_are_clean():
    ds, dr = domains()
    assert validate_domain(ds) == [] and validate_domain(dr) == []
    assert check_handoffs(ds, {"delivery": (dr, 1)}) == []


@pytest.mark.parametrize("mut_s,mut_r,published_major,code", [
    (None, None, 2, "interface-major"),
    (None, lambda r: r["actions"].update(request_delivery_v2=r["actions"].pop("request_delivery")), 1, "unknown-action"),
    (None, lambda r: r["actions"]["request_delivery"]["params"].update(ticket={"type": "string"}), 1, "missing-param"),
    (lambda s: s["handoffs"]["deliver"]["params"].update(note="'x'"), None, 1, "unknown-param"),
    (None, lambda r: r["actions"]["request_delivery"].update(actor=["approver"]), 1, "handoff-actor"),
    (lambda s: s["handoffs"]["deliver"]["params"].update(version="target.domain_id"), None, 1, "param-type"),
])
def test_a_broken_contract_fails_at_compile_time(mut_s, mut_r, published_major, code):
    ds, dr = domains(mut_s, mut_r)
    assert code in {i.code for i in check_handoffs(ds, {"delivery": (dr, published_major)})}


def test_unknown_receiver_and_bad_sender_expressions():
    ds, _ = domains(lambda s: s["handoffs"]["deliver"].update(target="target.nope"))
    assert check_handoffs(ds, {})[0].code == "unknown-domain"
    assert ("unknown-path", "handoffs.deliver.target") in {(i.code, i.where) for i in validate_domain(ds)}


# -- the outbox, at runtime ------------------------------------------------------------------------
def test_a_handoff_is_delivered_after_the_append_and_linked_in_both_stores():
    sender, receiver = pair()
    out = sender.submit("t-owen", "approve_version", "V1", idempotency_key="k1")
    assert out.ok and out.state["status"] == "approved"
    req = [e for e in sender.history("V1") if e.kind == "outbox"]
    assert len(req) == 1 and req[0].payload["target"] == "shop:3"
    assert req[0].payload["origin"] == {"id": "owen", "kind": "person"}
    hid = f"deliver:V1@{req[0].version}"
    assert receiver.state("shop:3") == {"id": "shop:3", "domain_id": "shop", "version": 3, "approver": "owen",
                                        "environment": "local", "status": "requested"}
    created = receiver.history("shop:3")[0]
    assert created.actor == {"id": "handoff:deliver", "kind": "system"}
    assert created.on_behalf_of == {"id": "owen", "kind": "person"} and created.causation == hid
    res = Outbox(sender).resolution(hid)
    assert res.type == "HandoffDelivered" and res.causation == hid and res.payload["object"] == "V1"
    assert Outbox(sender).pending() == []


def test_an_agents_handoff_acts_for_its_principal():
    sender, receiver = pair()
    assert sender.submit("t-bot", "approve_version", "V1", idempotency_key="k1").ok
    assert receiver.history("shop:3")[0].on_behalf_of == {"id": "owen", "kind": "person"}


def test_retry_after_a_crash_never_delivers_twice():
    sender, receiver = pair()

    class CrashAfterDelivery(LocalTransport):
        def deliver(self, *a):
            super().deliver(*a)
            raise ConnectionError("lost the reply")

    sender.transport = CrashAfterDelivery({"delivery": receiver})
    assert sender.submit("t-owen", "approve_version", "V1", idempotency_key="k1").ok   # sender unaffected
    assert len(Outbox(sender).pending()) == 1 and receiver.state("shop:3") is not None
    sender.transport = LocalTransport({"delivery": receiver})
    (r,) = sender.dispatch()
    assert r["result"] == "HandoffDelivered"
    assert len(receiver.history("shop:3")) == 1                                       # delivered once
    assert sender.dispatch() == []


def test_receiver_unreachable_stays_pending_without_blocking_the_sender():
    sender, receiver = pair()
    sender.transport = LocalTransport({})
    out = sender.submit("t-owen", "approve_version", "V1", idempotency_key="k1")
    assert out.ok and len(Outbox(sender).pending()) == 1
    sender.transport = LocalTransport({"delivery": receiver})
    assert sender.dispatch()[0]["result"] == "HandoffDelivered"


def test_a_denial_in_the_receiver_is_recorded_in_the_sender():
    sender, receiver = pair(mut_s=lambda s: s["world"]["fixtures"][0]["Version"].update(number=0))
    assert sender.submit("t-owen", "approve_version", "V1", idempotency_key="k1").ok
    (p,) = [e for e in sender.history("V1") if e.kind == "outbox"]
    res = Outbox(sender).resolution(f"deliver:V1@{p.version}")
    assert res.type == "HandoffDenied" and res.payload["code"] == "positive-version"
    assert res.payload["reason"] == "A version number starts at 1."
    assert sender.state("V1")["status"] == "approved"


def test_a_mapping_that_cannot_be_evaluated_fails_without_blocking():
    sender, receiver = pair(mut_s=lambda s: s["handoffs"]["deliver"].update(target="target.number"))
    assert sender.submit("t-owen", "approve_version", "V1", idempotency_key="k1").ok
    (p,) = [e for e in sender.history("V1") if e.kind == "outbox"]
    assert "non-empty string" in p.payload["error"]
    res = Outbox(sender).resolution(f"deliver:V1@{p.version}")
    assert res.type == "HandoffFailed" and res.payload["code"] == "mapping-error"
    assert receiver.store.streams() == []


def test_receiver_rejection_is_a_failure_not_a_retry():
    sender, receiver = pair()
    receiver.seed("DeliveryRequest", {"id": "shop:3", "status": "requested"})   # the id is taken
    assert sender.submit("t-owen", "approve_version", "V1", idempotency_key="k1").ok
    (p,) = [e for e in sender.history("V1") if e.kind == "outbox"]
    res = Outbox(sender).resolution(f"deliver:V1@{p.version}")
    assert res.type == "HandoffFailed" and res.payload["code"] == "exists"


def test_no_handoff_on_a_denied_sender_action_and_none_without_a_transport():
    sender, receiver = pair()
    sender.submit("t-owen", "approve_version", "V1", idempotency_key="k1")
    before = len(receiver.history("shop:3"))
    assert sender.submit("t-owen", "approve_version", "V1", idempotency_key="k2").code == "matrix"
    assert len([e for e in sender.history("V1") if e.kind == "outbox"]) == 1 and len(receiver.history("shop:3")) == before
    lone, _ = pair(transport=False)
    assert lone.submit("t-owen", "approve_version", "V1", idempotency_key="k1").ok
    assert len(Outbox(lone).pending()) == 1
    with pytest.raises(RuntimeError):
        lone.dispatch()


def test_callers_cannot_impersonate_a_handoff():
    with pytest.raises(ValueError):
        Caller(Actor("handoff:deliver", "person", ("system",)))


def test_harness_parity_holds_with_handoffs():
    from toprope.harness import run_harness
    ds, _ = domains()
    r = run_harness(ds, explore_examples=20, races=False)
    assert r.ok, r.summary()


# -- string joining (ADR-0024) ---------------------------------------------------------------------
@pytest.mark.parametrize("src,want", [("'a' + 'b'", "ab"), ("'v' + 3", "v3"), ("3 + 'v'", "3v"), ("1 + 2", 3)])
def test_plus_joins_strings_with_strings_and_integers(src, want):
    assert evaluate(parse(src), Env({})) == want


@pytest.mark.parametrize("src", ["'a' + 1.5", "'a' + true", "'a' + null", "'a' + [1]"])
def test_plus_refuses_ambiguous_joins(src):
    with pytest.raises(EvalError):
        evaluate(parse(src), Env({}))


def test_a_lost_resolution_race_reports_the_stored_outcome():
    from toprope.types import Event
    sender, receiver = pair(transport=False)
    assert sender.submit("t-owen", "approve_version", "V1", idempotency_key="k1").ok
    (p,) = Outbox(sender).pending()

    class OtherDispatcherWins(LocalTransport):
        def deliver(self, *a):
            out = super().deliver(*a)
            sender.store.append("handoff:" + p.id, 0, [Event("HandoffFailed", "handoff:" + p.id, "Version", None, None,
                                                                {"code": "other", "reason": "x"}, kind="handoff")])
            return out

    sender.transport = OtherDispatcherWins({"delivery": receiver})
    (r,) = sender.dispatch()
    assert r["result"] == "HandoffFailed" and r["code"] == "other"
    assert Outbox(sender).resolution(p.id).type == "HandoffFailed"


# -- the world map and the CLI contract check ------------------------------------------------------
def test_world_map_shows_where_actions_hand_off():
    from toprope.worldmap import build_world_map
    ds, _ = domains()
    m = build_world_map(ds)
    e = next(x for x in m["behavior"]["edges"] if x["id"] == "Version.draft.approve_version")
    assert e["hands_off"] == [{"handoff": "deliver", "domain": "delivery", "interface": "1.x",
                               "action": "request_delivery"}]
    assert m["handoffs"][0]["when"] == "approve_version"


def test_harness_cli_checks_the_handoff_contract(tmp_path):
    import subprocess
    import yaml
    s, r = tmp_path / "s.domain.yaml", tmp_path / "r.domain.yaml"
    s.write_text(yaml.safe_dump(SENDER, sort_keys=False))
    r.write_text(yaml.safe_dump(RECEIVER, sort_keys=False))
    base = ["uv", "run", "--quiet", "toprope-harness", "--domain", str(s), "--levels", "model", "--examples", "5"]
    run = lambda *a: subprocess.run(base + list(a), capture_output=True, text=True, timeout=120)  # noqa: E731
    assert run("--receiver", str(r)).returncode == 0
    no_receiver = run()
    assert no_receiver.returncode == 1 and "unknown-domain" in no_receiver.stderr
    wrong_major = run("--receiver", f"{r}@2")
    assert wrong_major.returncode == 1 and "interface-major" in wrong_major.stderr
    at_dir = tmp_path / "team@x"
    at_dir.mkdir()
    (at_dir / "r.domain.yaml").write_text(r.read_text())
    assert run("--receiver", f"{at_dir / 'r.domain.yaml'}@1").returncode == 0
    bad = run("--receiver", f"{r}@v1")
    assert bad.returncode == 1 and "Traceback" not in bad.stderr

"""Regression tests for the findings of the umbrella → develop review."""
import copy
from datetime import datetime, timezone

import pytest
import yaml

from test_decl import schema_doc_domain
from toprope.semantics import Actor, Event, Grant


# 1. an agent can never write provenance directly ---------------------------------------------------
def test_status_and_source_paths_cannot_be_written(tmp_path):
    from toprope.authoring import AuthoringError, Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(
        {"domain": "d.domain.yaml", "sources": [{"id": "docs", "kind": "records", "path": "docs"}]}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\nrules\n")
    (tmp_path / "d.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    ws = Workspace(tmp_path)
    for path in ("actions.approve_experiment.status", "links.hypothesis.source",
                 "transitions.Experiment.matrix.running.approve_experiment.status"):
        with pytest.raises(AuthoringError, match="provenance"):
            ws.propose(path, "confirmed", "docs:docs/a.md#L1-L2")
    with pytest.raises(AuthoringError, match="provenance"):
        ws.answer("q", "yes", [{"path": "actions.approve_experiment.status", "value": "confirmed"}], question="q?")
    # a property named `status` is a field, not provenance
    ws.propose("objects.Experiment.properties.status", {"enum": ["draft", "approved"]}, "docs:docs/a.md#L1-L2")


# 2. outbox resolution streams cannot be squatted ---------------------------------------------------
def test_object_ids_may_not_take_the_outbox_prefixes():
    from test_handoffs import RECEIVER
    from toprope.decl import Domain
    from toprope.semantics import Command, ReferenceModel
    m = ReferenceModel(Domain.model_validate(copy.deepcopy(RECEIVER)))
    params = {"domain_id": "x", "version": 1, "approver": "a", "environment": "local"}
    for oid in ("handoff:deliver:V1@2", "effect:validate:V1@3"):
        out = m.execute(Command(Actor("handoff:authoring.deliver", "system", ("system",)), "request_delivery", oid, params))
        assert out.code == "invalid-command" and "outbox" in out.reason
    with pytest.raises(ValueError):
        m.seed("DeliveryRequest", {"id": "handoff:x", "status": "requested"})


# 4. stored times compare with now() --------------------------------------------------------------------
def test_iso_strings_compare_with_datetimes():
    from toprope.expr import Env, EvalError, evaluate, parse
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    env = Env({"target": {"closed_at": "2026-11-01T00:00:00+00:00", "bad": "soon"}}, clock=lambda: now)
    assert evaluate(parse("target.closed_at < now()"), env) is True
    assert evaluate(parse("now() > target.closed_at"), env) is True
    with pytest.raises(EvalError):
        evaluate(parse("target.bad < now()"), env)


# 5. a creating action's handoff is followed ------------------------------------------------------------
def test_paths_follow_a_handoff_from_a_creating_action(tmp_path):
    from test_handoffs import RECEIVER, SENDER
    from toprope.compose import composed_world_map, how_to_reach_across, load_composition
    sender = copy.deepcopy(SENDER)
    sender["actions"]["open_version"] = {"description": "Open a version.", "actor": ["owner"], "creates": "Version",
                                         "params": {"domain_id": {"type": "string"}, "number": {"type": "integer"}}}
    sender["handoffs"]["deliver"]["when"]["action"] = "open_version"
    (tmp_path / "a.domain.yaml").write_text(yaml.safe_dump(sender, sort_keys=False))
    (tmp_path / "d.domain.yaml").write_text(yaml.safe_dump(RECEIVER, sort_keys=False))
    p = tmp_path / "c.composition.yaml"
    p.write_text(yaml.safe_dump({"composition": "c", "version": 1, "members": {
        "authoring": {"declaration": "a.domain.yaml"}, "delivery": {"declaration": "d.domain.yaml"}},
        "wiring": [{"from": "authoring.deliver", "to": "delivery.request_delivery"}]}))
    m = composed_world_map(load_composition(p))
    path = how_to_reach_across(m, "authoring", "Version", None, "delivery", "DeliveryRequest", "requested")
    assert path["reachable"] and [s["action"] for s in path["steps"]] == ["open_version", "request_delivery"]


# 6. a principal is never a reserved actor ---------------------------------------------------------------
def test_a_principal_cannot_be_a_reserved_actor():
    from toprope.identity import Caller
    bot = Actor("bot", "agent", ("approver",))
    for principal in (Actor("handoff:billing.charge", "person", ("approver",)), Actor("ana", "person", ("system",)),
                      Actor("external:kernel", "person", ())):
        with pytest.raises(ValueError, match="principal"):
            Caller(bot, principal, Grant("g", frozenset({"x"})))


# 7. a submit does not scan the whole store -------------------------------------------------------------
def test_a_submit_sends_its_own_outbox_without_scanning_the_store():
    from test_handoffs import pair
    sender, receiver = pair()

    def no_scan():
        raise AssertionError("scanned every stream")
    sender.store.streams = no_scan
    assert sender.submit("t-owen", "approve_version", "V1", idempotency_key="k1").ok
    assert receiver.state("shop:3") is not None                                # delivered, without a scan


# 8. every store returns what a read would ---------------------------------------------------------------
def test_append_returns_what_a_read_returns(open_store):
    s = open_store()
    ev = Event("ThingHappened", "o1", "Thing", at=datetime(2026, 1, 1, tzinfo=timezone.utc), actor={"id": "a"},
               payload={"tuple": (1, 2), "keys": {"$x": 1}})
    (written,) = s.append("o1", 0, [ev])
    assert written == s.read("o1")[0]

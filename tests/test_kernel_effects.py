import copy
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone

import pytest
import yaml
from pydantic import ValidationError

from test_handoffs import RECEIVER
from toprope.decl import Domain, validate_domain
from toprope.exec import Execution
from toprope.handoff import Outbox
from toprope.identity import Caller, StaticIdentity
from toprope.kernel import CATALOG
from toprope.kernel.services import LocalKernel, RecordingKernel
from toprope.semantics import Actor
from toprope.store import MemoryEventStore

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)
OWEN = Actor("owen", "person", ("owner",))

DOMAIN = {
    "domain": "authoring", "version": 1, "roles": ["owner"],
    "objects": {"DomainVersion": {"properties": {
        "status": {"enum": ["draft", "approved"]}, "declaration": {"type": "string"},
        "harness_ok": {"type": "boolean", "optional": True}, "findings": {"type": "integer", "optional": True},
        "conflicts": {"type": "integer", "optional": True}}}},
    "actions": {
        "check_version": {"description": "Check a version.", "actor": ["owner"], "target": "DomainVersion",
                          "effects": [
                              {"call": "validate", "with": {"declaration": "target.declaration"}, "reply": "record_validation"},
                              {"call": "run_harness", "with": {"declaration": "target.declaration"}, "reply": "record_harness"}]},
        "record_validation": {"description": "Record a validation.", "actor": ["external:kernel"], "target": "DomainVersion",
                              "params": {"errors": {"type": "integer"}},
                              "effects": [{"set": {"target.conflicts": "params.errors"}}]},
        "record_harness": {"description": "Record a harness run.", "actor": ["external:kernel"], "target": "DomainVersion",
                           "params": {"ok": {"type": "boolean"}, "findings": {"type": "integer"}},
                           "effects": [{"set": {"target.harness_ok": "params.ok", "target.findings": "params.findings"}}]},
        "approve_version": {"description": "Approve a version.", "actor": ["owner"], "target": "DomainVersion",
                            "preconditions": [{"id": "checked-clean", "check": "target.harness_ok == true and target.conflicts == 0",
                                               "reason": "A version is approved only after a clean check."}]},
    },
    "transitions": {"DomainVersion": {"field": "status", "initial": "draft", "matrix": {
        "draft": {"check_version": "draft", "record_validation": "draft", "record_harness": "draft",
                  "approve_version": "approved"},
        "approved": {"check_version": "n/a", "record_validation": "n/a", "record_harness": "n/a",
                     "approve_version": {"deny": "Already approved."}}}}},
    "world": {"fixtures": [{"DomainVersion": {"id": "V1", "status": "draft", "declaration": "shop.domain.yaml"}}],
              "actors": {"owner": ["owen"]}},
    "scenarios": [{"id": "check-then-approve", "given": {"from_world": "V1"}, "steps": [
        {"actor": {"role": "owner"}, "do": "approve_version", "target": "V1", "expect": {"denied_by": "checked-clean"}},
        {"actor": {"external": "kernel"}, "do": "record_validation", "target": "V1", "params": {"errors": 0},
         "expect": {"state": {"V1.conflicts": 0}}},
        {"actor": {"external": "kernel"}, "do": "record_harness", "target": "V1", "params": {"ok": True, "findings": 0},
         "expect": {"state": {"V1.harness_ok": True}}},
        {"actor": {"role": "owner"}, "do": "approve_version", "target": "V1", "expect": {"state": {"V1.status": "approved"}}}]}],
}


def dom(mutate=None) -> Domain:
    raw = copy.deepcopy(DOMAIN)
    if mutate:
        mutate(raw)
    return Domain.model_validate(raw)


def codes(mutate):
    return {i.code for i in validate_domain(dom(mutate))}


def resolution(e, oid, service):
    (req,) = [x for x in e.history(oid) if x.type == "EffectRequested" and x.payload["service"] == service]
    return Outbox(e).resolution(f"{service}:{oid}@{req.version}", "effect")


def ex(services=None, mutate=None):
    e = Execution(dom(mutate), MemoryEventStore(), StaticIdentity({"t": Caller(OWEN)}), clock=lambda: NOW,
                  services=services)
    e.seed_world()
    return e


# -- the declaration -------------------------------------------------------------------------------
def test_a_well_formed_call_is_clean():
    assert validate_domain(dom()) == []


@pytest.mark.parametrize("mutate,code", [
    (lambda r: r["actions"]["check_version"]["effects"][0].update(call="teleport"), "unknown-service"),
    (lambda r: r["actions"]["check_version"]["effects"][0].update({"with": {}}), "missing-input"),
    (lambda r: r["actions"]["check_version"]["effects"][0]["with"].update(extra="'x'"), "unknown-input"),
    (lambda r: r["actions"]["check_version"]["effects"][0]["with"].update(declaration="target.nope"), "unknown-path"),
    (lambda r: r["actions"]["check_version"]["effects"][0].update(reply="ghost"), "unknown-reply"),
    (lambda r: r["actions"]["record_validation"].update(actor=["owner"]), "reply-actor"),
    (lambda r: r["actions"]["record_validation"]["params"].update(colour={"type": "string"}), "reply-param"),
    (lambda r: r["actions"]["record_validation"]["params"].update(errors={"type": "string"}), "reply-param-type"),
    (lambda r: r["actions"]["record_validation"].update(actor=["external:kernel", "owner"]), "mixed-external"),
])
def test_calls_are_checked_at_compile_time(mutate, code):
    assert code in codes(mutate)


def test_reply_must_target_the_calling_object():
    def other(r):
        r["objects"]["Note"] = {"properties": {"status": {"enum": ["open"]}}}
        r["actions"]["record_validation"]["target"] = "Note"
    assert "reply-target" in codes(other)


@pytest.mark.parametrize("effect,msg", [
    ({"set": {"target.findings": 1}, "call": "validate", "reply": "record_validation"}, "exactly one"),
    ({"call": "validate", "with": {"declaration": "target.declaration"}}, "reply"),
    ({"set": {"target.findings": 1}, "reply": "record_validation"}, "belong to a `call`"),
])
def test_effect_shapes_are_refused(effect, msg):
    with pytest.raises(ValidationError, match=msg):
        dom(lambda r: r["actions"]["check_version"].update(effects=[effect]))


def test_only_the_kernel_is_an_external_source_in_m0a():
    with pytest.raises(ValidationError, match="other than `external:kernel`"):
        dom(lambda r: r["actions"]["record_validation"].update(actor=["external:flags"]))


# -- at runtime --------------------------------------------------------------------------------------
def test_a_call_runs_after_the_append_and_its_result_becomes_state():
    kernel = RecordingKernel({"validate": {"ok": True, "errors": 0}, "run_harness": {"ok": True, "findings": 0}})
    e = ex(kernel)
    out = e.submit("t", "check_version", "V1", idempotency_key="k1")
    assert out.ok and out.state.get("harness_ok") is None                  # the action itself is unaffected
    assert [s for s, _ in kernel.calls] == ["validate", "run_harness"]
    assert kernel.calls[0][1] == {"declaration": "shop.domain.yaml"}
    st = e.state("V1")
    assert st["conflicts"] == 0 and st["harness_ok"] is True and st["findings"] == 0
    reps = [ev for ev in e.history("V1") if ev.type in ("DomainVersionRecordValidation", "DomainVersionRecordHarness")]
    assert all(ev.actor == {"id": "external:kernel", "kind": "system"} and ev.causation for ev in reps)
    res = Outbox(e).resolution(reps[0].causation, "effect")
    assert res.type == "EffectSucceeded" and res.payload["result"]["errors"] == 0
    assert e.submit("t", "approve_version", "V1", idempotency_key="k2").state["status"] == "approved"
    assert e.dispatch() == [] and len(kernel.calls) == 2                    # nothing runs twice


def test_a_failed_result_still_replies_and_the_declared_gate_holds():
    kernel = RecordingKernel({"validate": {"ok": True, "errors": 0}, "run_harness": {"ok": False, "findings": 2}})
    e = ex(kernel)
    e.submit("t", "check_version", "V1", idempotency_key="k1")
    assert e.state("V1")["harness_ok"] is False and e.state("V1")["findings"] == 2
    assert resolution(e, "V1", "run_harness").type == "EffectFailed"
    assert e.submit("t", "approve_version", "V1", idempotency_key="k2").code == "checked-clean"


def test_a_crashing_service_and_an_unevaluable_input_reply_with_a_failure():
    class Crashing(RecordingKernel):
        def run(self, service, inputs):
            raise RuntimeError("disk on fire")
    e = ex(Crashing())
    e.submit("t", "check_version", "V1", idempotency_key="k1")
    res = resolution(e, "V1", "validate")
    assert res.type == "EffectFailed" and "disk on fire" in res.payload["result"]["error"]
    assert e.state("V1")["conflicts"] == 0                                   # failure defaults, as declared
    e2 = ex(RecordingKernel(), mutate=lambda r: r["actions"]["check_version"]["effects"][0]["with"].update(
        declaration="target.missing_field"))
    e2.seed("DomainVersion", {"id": "V2", "status": "draft", "declaration": "x"})
    e2.submit("t", "check_version", "V2", idempotency_key="k")
    assert "mapping-error" in resolution(e2, "V2", "validate").payload["result"]["error"]


def test_without_services_calls_stay_pending_and_only_the_kernel_can_reply():
    e = ex()
    assert e.submit("t", "check_version", "V1", idempotency_key="k1").ok
    assert {p.event.payload["service"] for p in Outbox(e).pending("effect")} == {"validate", "run_harness"}
    assert e.submit("t", "record_harness", "V1", {"ok": True, "findings": 0}, idempotency_key="k2").code == "actor"
    with pytest.raises(ValueError):
        Caller(Actor("external:kernel", "system", ("external:kernel",)))


def test_the_harness_covers_kernel_replies_and_scenarios_state_results():
    from toprope.harness import run_harness
    r = run_harness(dom(), explore_examples=20, races=False)
    assert r.ok, r.summary()
    assert r.coverage["flows"]["passed"] == {"model": 1, "execution": 1, "mcp": 1}
    kernel_cells = [k for k in r.coverage["edges"] if ".record_" in k]
    assert kernel_cells and all(r.coverage["edges"][k] in ("verified", "uncovered") for k in kernel_cells)


# -- the real services ----------------------------------------------------------------------------------
def test_local_kernel_services_on_files(tmp_path):
    from test_decl import schema_doc_domain
    (tmp_path / "shop.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    k = LocalKernel(tmp_path, harness_examples=5)
    v = k.call("validate", {"declaration": "shop.domain.yaml"})
    assert v["ok"] and v["errors"] == 0 and v["error"] == ""
    assert k.call("compile", {"declaration": "shop.domain.yaml"})["actions"] == 2
    h = k.call("run_harness", {"declaration": "shop.domain.yaml"})
    assert h["ok"] and h["findings"] == 0 and h["unreachable"] == 2
    assert k.call("world_map", {"declaration": "shop.domain.yaml"})["undecided"] == 1
    out = k.call("validate", {"declaration": "../outside.yaml"})
    assert not out["ok"] and "outside" in out["error"] and set(out) == set(CATALOG["validate"].fields())
    nodeploy = k.call("deploy", {"domain": "example", "commit": "1-x", "approver": "ana"},
                      caller={"id": "ana", "kind": "person"})
    assert not nodeploy["ok"] and "no deploy environment" in nodeploy["error"]


def test_a_refused_deploy_keeps_its_reason(tmp_path):
    from toprope.deploy import LocalEnvironment
    from test_decl import schema_doc_domain
    (tmp_path / "shop.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    k = LocalKernel(tmp_path, environment=LocalEnvironment(tmp_path / "env"), harness_examples=5)
    ana = {"id": "ana", "kind": "person"}
    c = k.call("commit", {"declaration": "shop.domain.yaml"})
    b = k.call("preview", {"domain": "example", "commit": c["id"]})
    assert b["ok"] and b["harness_ok"]
    out = k.call("deploy", {"domain": "example", "commit": c["id"], "approver": "ana"}, caller=ana)
    assert out == {**out, "ok": False, "deployed": False} and out["error"].startswith("unapproved")
    assert k.call("approve_commit", {"domain": "example", "commit": c["id"], "approver": "ana"}, caller=ana)["approved"]
    assert k.call("deploy", {"domain": "example", "commit": c["id"], "approver": "ana"}, caller=ana)["deployed"] is True


# -- served from a composition, and the regeneration check ------------------------------------------------
def write_composition(tmp_path):
    sender = copy.deepcopy(DOMAIN)
    sender["objects"]["DomainVersion"]["properties"].update(domain_id={"type": "string"}, number={"type": "integer"})
    sender["world"]["fixtures"][0]["DomainVersion"].update(domain_id="shop", number=3)
    sender["handoffs"] = {"deliver": {
        "when": {"action": "approve_version"},
        "to": {"domain": "delivery", "interface": "1.x", "action": "request_delivery"},
        "params": {"domain_id": "target.domain_id", "version": "target.number", "approver": "actor.id",
                   "environment": "'local'"},
        "target": "target.domain_id + ':' + target.number"}}
    (tmp_path / "authoring.domain.yaml").write_text(yaml.safe_dump(sender, sort_keys=False))
    (tmp_path / "delivery.domain.yaml").write_text(yaml.safe_dump(RECEIVER, sort_keys=False))
    p = tmp_path / "self.composition.yaml"
    p.write_text(yaml.safe_dump({"composition": "self", "version": 1, "members": {
        "authoring": {"declaration": "authoring.domain.yaml"}, "delivery": {"declaration": "delivery.domain.yaml"}},
        "wiring": [{"from": "authoring.deliver", "to": "delivery.request_delivery"}]}, sort_keys=False))
    from test_decl import schema_doc_domain
    (tmp_path / "shop.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    return p


def test_regeneration_check_passes_on_a_composition(tmp_path):
    from toprope.harness.regen import regen_check
    out = regen_check(write_composition(tmp_path), levels=("model", "execution"), examples=10)
    assert out["ok"], out
    assert out["same_after_regenerating"] is True
    (e2e,) = out["effects"]
    assert e2e["action"] == "check_version" and e2e["calls"] == ["validate", "run_harness"]
    assert [r["resolution"] for r in e2e["effects"]] == ["EffectSucceeded", "EffectSucceeded"]


def test_regeneration_check_fails_when_a_reply_is_refused(tmp_path):
    from toprope.harness.regen import regen_check
    p = write_composition(tmp_path)
    raw = yaml.safe_load((tmp_path / "authoring.domain.yaml").read_text())
    raw["transitions"]["DomainVersion"]["matrix"]["draft"]["record_harness"] = {"deny": "Not now."}
    (tmp_path / "authoring.domain.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    out = regen_check(p, levels=("model",), examples=0)
    assert out["ok"] is False and out["effects"][0]["ok"] is False


def test_serve_a_member_of_a_composition_over_stdio(tmp_path):
    import asyncio
    from mcp import Client, StdioServerParameters
    p = write_composition(tmp_path)
    tokens = tmp_path / "tokens.yaml"
    tokens.write_text(yaml.safe_dump({"t-owen": {"id": "owen", "roles": ["owner"]}}))
    params = StdioServerParameters(command="uv", args=[
        "run", "--quiet", "toprope-server", "--composition", str(p), "--member", "authoring",
        "--store-dir", str(tmp_path / "data"), "--kernel-root", str(tmp_path), "--identity", f"static:{tokens}"],
        env={"TOPROPE_TOKEN": "t-owen", "PATH": os.environ["PATH"]})

    async def go():
        async with Client(params) as c:
            await c.call_tool("check_version", {"target_id": "V1", "idempotency_key": "s1"})
            r = await c.call_tool("get_object", {"object_id": "V1"})
            st = r.structured_content
            assert st["harness_ok"] is True and st["conflicts"] == 0       # real kernel services ran
            r = await c.call_tool("approve_version", {"target_id": "V1", "idempotency_key": "s2"})
            assert r.structured_content["status"] == "ok"
    asyncio.run(go())
    db = sqlite3.connect(tmp_path / "data" / "delivery.db")
    assert db.execute("SELECT COUNT(*) FROM events WHERE stream = 'shop:3'").fetchone()[0] == 1


def test_cli_regen_check(tmp_path):
    p = write_composition(tmp_path)
    r = subprocess.run(["uv", "run", "--quiet", "toprope-harness", "--composition", str(p), "--regen-check",
                        "--levels", "model", "--examples", "5"], capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout)["same_after_regenerating"] is True

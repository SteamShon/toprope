import copy
import json
import subprocess
import threading

import pytest
import yaml

from test_decl import schema_doc_domain
from toprope.commits import CommitError, CommitStore
from toprope.decl import Domain, review_diff, review_elements, validate_domain
from toprope.deploy import DeployRefused, LocalEnvironment
from toprope.kernel.services import LocalKernel, RecordingKernel
from toprope.semantics import Actor

ANA = Actor("ana", "person", ("approver",))


def write(p, raw):
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    return p


# -- the review hash -------------------------------------------------------------------------------
def test_confirming_an_element_is_not_a_change():
    raw = schema_doc_domain()
    before = review_elements(Domain.model_validate(raw))
    raw["transitions"]["Experiment"]["matrix"]["running"]["approve_experiment"]["status"] = "proposed"
    raw["links"]["hypothesis"]["source"] = {"kind": "interview", "ref": "x"}
    assert review_diff(before, review_elements(Domain.model_validate(raw))).to_review == []


def test_wording_and_references_are_direct_changes():
    raw = schema_doc_domain()
    before = review_elements(Domain.model_validate(raw))
    raw["transitions"]["Experiment"]["matrix"]["approved"]["approve_experiment"]["deny"] = "Approved already."
    raw["actions"]["launch_experiment"]["description"] = "Start traffic."
    assert review_diff(before, review_elements(Domain.model_validate(raw))).changed == [
        "action:launch_experiment", "cell:Experiment.approved.approve_experiment"]


def test_review_covers_what_the_interface_does_not():
    raw = schema_doc_domain()
    before = review_elements(Domain.model_validate(raw))
    raw["roles"].append("auditor")
    raw["transitions"]["Experiment"]["initial"] = "approved"
    raw["world"]["fixtures"][0]["Hypothesis"]["statement"] = "Shorter signup."
    raw["scenarios"][0]["steps"] = raw["scenarios"][0]["steps"] + raw["scenarios"][0]["steps"][:1]
    raw["purpose"] = {"problem": "Ship safely."}
    d = review_diff(before, review_elements(Domain.model_validate(raw)))
    assert d.added == ["purpose", "role:auditor"]
    assert {"stages:Experiment", "fixture:Hypothesis.H1"} <= set(d.changed)
    assert any(k.startswith("scenario:") for k in d.changed)


# -- the commit store ------------------------------------------------------------------------------
@pytest.fixture
def store(tmp_path):
    return CommitStore(tmp_path / "commits"), tmp_path / "wc.domain.yaml"


def test_commits_are_immutable_content_addressed_and_carry_parents(store):
    st, wc = store
    raw = schema_doc_domain()
    c1, new = st.commit(write(wc, raw))
    assert new and c1.seq == 1 and c1.parents == [] and c1.interface == "1.0.0" and c1.id == f"1-{c1.content}"
    assert st.commit(wc) == (c1, False)                                     # nothing changed: no commit
    raw["version"] = 99
    assert st.commit(write(wc, raw))[1] is False                            # `version` is not content
    add = copy.deepcopy(raw)
    add["glossary"]["guardrail"] = "A metric that must not get worse."
    c2, _ = st.commit(write(wc, add))
    assert c2.parents == [c1.id] and c2.interface == "1.1.0"                 # an addition is minor
    c3, new = st.commit(write(wc, raw))
    assert new and c3.seq == 3 and c3.content == c1.content and c3.interface == "2.0.0"   # a removal is major
    assert st.domain("example", c3.id).version == 3 and st.domain("example", c1.id).version == 1
    assert [c.id for c in st.log("example")] == [c1.id, c2.id, c3.id]
    with pytest.raises(CommitError):
        st.get("example", "9-nope")


def test_diff_shows_what_to_review(store):
    st, wc = store
    raw = schema_doc_domain()
    c1, _ = st.commit(write(wc, raw))
    raw["actions"]["launch_experiment"]["description"] = "Start traffic."
    raw["transitions"]["Experiment"]["matrix"]["running"]["approve_experiment"]["status"] = "proposed"
    c2, _ = st.commit(write(wc, raw))
    assert st.diff("example", c1.id, c2.id)["to_review"] == ["action:launch_experiment"]
    assert len(st.diff("example", None, c1.id)["to_review"]) == len(review_elements(st.domain("example", c1.id)))


def test_approvals_are_immutable_and_the_newest_wins(store):
    st, wc = store
    raw = schema_doc_domain()
    c1, _ = st.commit(write(wc, raw))
    raw["glossary"]["x"] = "y"
    c2, _ = st.commit(write(wc, raw))
    assert st.approve("example", c2.id, "ana") == c2                        # a fast-forward of main
    assert st.approve("example", c2.id, "ana") is None                      # tagging again is a no-op
    with pytest.raises(CommitError, match="supersedes"):                    # ADR-0033: main already has it
        st.approve("example", c1.id, "ana")
    assert st.latest_approved("example").id == c2.id and st.main("example") == c2
    assert [a["commit"] for a in st.approvals("example")] == [c2.id]


def test_concurrent_commits_get_distinct_sequence_numbers(store, tmp_path):
    st, _ = store
    outs = []

    def go(i):
        raw = schema_doc_domain()
        raw["glossary"][f"t{i}"] = "x"
        p = write(tmp_path / f"w{i}.yaml", raw)
        outs.append(CommitStore(st.root).commit(p)[0].seq)
    ts = [threading.Thread(target=go, args=(i,)) for i in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(outs) == [1, 2, 3, 4, 5, 6]


# -- kernel services -------------------------------------------------------------------------------
def test_services_that_record_a_decision_check_the_calling_person(tmp_path):
    write(tmp_path / "d.domain.yaml", schema_doc_domain())
    k = LocalKernel(tmp_path)
    c = k.call("commit", {"declaration": "d.domain.yaml"})
    assert c["created"] and c["seq"] == 1 and "action:approve_experiment" in c["to_review"]
    inputs = {"domain": "example", "commit": c["id"], "approver": "ana"}
    for caller in (None, {"id": "bot", "kind": "agent"}, {"id": "external:kernel", "kind": "system"},
                   {"id": "eli", "kind": "person"}):
        out = k.call("approve_commit", inputs, caller=caller)
        assert out["ok"] is False and "the calling person must be the approver" in out["error"]
    assert k.commits.approvals("example") == []
    assert k.call("approve_commit", inputs, caller={"id": "ana", "kind": "person"})["approved"] is True
    d = k.call("diff", {"domain": "example", "from": "", "to": c["id"]})
    assert d["ok"] and isinstance(d["to_review"], list) and d["to_review"]


# -- reply-creates (ADR-0029) ----------------------------------------------------------------------
AUTHORING = {
    "domain": "authoring", "version": 1, "roles": ["owner"],
    "objects": {"WorkingCopy": {"properties": {"status": {"enum": ["open"]}, "declaration": {"type": "string"}}},
                "Commit": {"properties": {"status": {"enum": ["candidate"]}, "seq": {"type": "integer"},
                                          "to_review": {"type": "string", "optional": True}}}},
    "actions": {
        "compile": {"description": "Compile the working copy.", "actor": ["owner"], "target": "WorkingCopy",
                    "effects": [{"call": "commit", "with": {"declaration": "target.declaration"},
                                 "reply": "record_commit"}]},
        "record_commit": {"description": "Record a new commit.", "actor": ["external:kernel"], "creates": "Commit",
                          "params": {"seq": {"type": "integer"}, "to_review": {"type": "string", "many": True}}},
    },
    "transitions": {"WorkingCopy": {"field": "status", "initial": "open", "matrix": {"open": {"compile": "open"}}},
                    "Commit": {"field": "status", "initial": "candidate", "matrix": {"candidate": {}}}},
    "world": {"fixtures": [{"WorkingCopy": {"id": "W1", "status": "open", "declaration": "shop.domain.yaml"}}]},
}


def test_a_reply_may_create_the_object_a_service_names():
    assert validate_domain(Domain.model_validate(AUTHORING)) == []
    bad = copy.deepcopy(AUTHORING)
    bad["actions"]["compile"]["effects"][0].update(call="validate", reply="record_commit")
    bad["actions"]["compile"]["effects"][0]["with"] = {"declaration": "target.declaration"}
    assert "reply-target" in {i.code for i in validate_domain(Domain.model_validate(bad))}   # validate has no id


def test_commits_become_objects_through_a_creating_reply(tmp_path):
    from toprope.exec import Execution
    from toprope.identity import Caller, StaticIdentity
    from toprope.store import MemoryEventStore
    write(tmp_path / "shop.domain.yaml", schema_doc_domain())
    ex = Execution(Domain.model_validate(AUTHORING), MemoryEventStore(),
                   StaticIdentity({"t": Caller(Actor("owen", "person", ("owner",)))}), services=LocalKernel(tmp_path))
    ex.seed_world()
    assert ex.submit("t", "compile", "W1", idempotency_key="k1").ok
    (cid,) = [s for s in ex.store.streams() if s.startswith("1-")]
    st = ex.state(cid)
    assert st["status"] == "candidate" and st["seq"] == 1 and "action:compile" not in st["to_review"]
    assert ex.history(cid)[0].actor == {"id": "external:kernel", "kind": "system"}
    assert ex.submit("t", "compile", "W1", idempotency_key="k2").ok           # unchanged: same commit, no error
    assert [s for s in ex.store.streams() if s[:2] in ("1-", "2-")] == [cid]


# -- the deploy floor for commits --------------------------------------------------------------------
def test_deploy_floor_for_commits(tmp_path):
    st = CommitStore(tmp_path / "commits")
    env = LocalEnvironment(tmp_path / "env")
    raw = schema_doc_domain()
    c1, _ = st.commit(write(tmp_path / "wc.yaml", raw))
    env.preview_commit(st, "example", c1.id, examples=0)
    with pytest.raises(DeployRefused) as e:
        env.deploy_commit(st, "example", c1.id, ANA)
    assert e.value.rule == "unapproved"
    st.approve("example", c1.id, "ana")
    assert env.deploy_commit(st, "example", c1.id, ANA)["commit"] == c1.id
    with pytest.raises(DeployRefused) as e:
        env.deploy_commit(st, "example", c1.id, ANA)
    assert e.value.rule == "downgrade"                                         # not newer than deployed
    raw["glossary"]["x"] = "y"
    c2, _ = st.commit(write(tmp_path / "wc.yaml", raw))
    raw["glossary"]["z"] = "w"
    c3, _ = st.commit(write(tmp_path / "wc.yaml", raw))
    st.approve("example", c2.id, "ana")
    st.approve("example", c3.id, "ana")
    with pytest.raises(DeployRefused) as e:
        env.deploy_commit(st, "example", c2.id, ANA)
    assert e.value.rule == "superseded"                                        # c3 is the newest approved
    with pytest.raises(DeployRefused) as e:
        env.deploy_commit(st, "example", c3.id, ANA)
    assert e.value.rule == "no-build"
    env.preview_commit(st, "example", c3.id, examples=0)
    assert env.current()["commit"] == c1.id
    assert env.deploy_commit(st, "example", c3.id, ANA)["seq"] == 3
    assert [h.get("rule") for h in env.history() if h["result"] == "refused"] == [
        "unapproved", "downgrade", "superseded", "no-build"]


def test_concurrent_deploys_of_one_commit_deploy_once(tmp_path):
    st = CommitStore(tmp_path / "commits")
    env = LocalEnvironment(tmp_path / "env")
    c1, _ = st.commit(write(tmp_path / "wc.yaml", schema_doc_domain()))
    env.preview_commit(st, "example", c1.id, examples=0)
    st.approve("example", c1.id, "ana")
    results = []

    def go():
        try:
            LocalEnvironment(tmp_path / "env").deploy_commit(st, "example", c1.id, ANA)
            results.append("deployed")
        except DeployRefused as e:
            results.append(e.rule)
    ts = [threading.Thread(target=go) for _ in range(5)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(results) == ["deployed"] + ["downgrade"] * 4


# -- the workspace and the read command -----------------------------------------------------------
def test_workspace_commit_diff_approve_and_the_diff_command(tmp_path):
    from toprope.workspace import Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    raw = schema_doc_domain()
    write(tmp_path / "d.domain.yaml", raw)
    ws = Workspace(tmp_path)
    c1 = ws.commit("first")
    assert c1["created"] and c1["since"] is None and c1["to_review"]
    ws.approve_commit(c1["commit"], via="cli", who="ana")
    raw["actions"]["launch_experiment"]["description"] = "Start traffic."
    write(tmp_path / "d.domain.yaml", raw)
    c2 = ws.commit()
    assert c2["since"] == c1["commit"] and c2["to_review"] == ["action:launch_experiment"]
    r = subprocess.run(["uv", "run", "--quiet", "toprope-commits", "--commits", str(tmp_path / ".toprope/commits"),
                        "diff", "example", c1["commit"], c2["commit"]], capture_output=True, text=True, timeout=120)
    assert json.loads(r.stdout)["changed"] == ["action:launch_experiment"]


def test_approving_without_a_domain_or_an_unknown_commit_is_an_authoring_error(tmp_path):
    from toprope.workspace import AuthoringError, Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    (tmp_path / "d.domain.yaml").write_text("version: 1\n")
    ws = Workspace(tmp_path)
    with pytest.raises(AuthoringError, match="names no `domain`"):
        ws.approve_commit("1-x", via="cli", who="ana")
    write(tmp_path / "d.domain.yaml", schema_doc_domain())
    with pytest.raises(AuthoringError, match="no commit"):
        ws.approve_commit("1-x", via="cli", who="ana")


# -- gaps closed after review -------------------------------------------------------------------------
def test_a_commit_includes_the_domains_own_representations(tmp_path):
    st = CommitStore(tmp_path / "commits")
    wc = write(tmp_path / "shop.domain.yaml", schema_doc_domain())
    c1, _ = st.commit(wc)
    (tmp_path / "ui.representation.yaml").write_text(yaml.safe_dump(
        {"representation": "ui", "version": 1, "targets": {"domain": "example", "interface": "1.x"}, "views": {}}))
    (tmp_path / "other.representation.yaml").write_text(yaml.safe_dump(
        {"representation": "o", "version": 1, "targets": {"domain": "billing", "interface": "1.x"}, "views": {}}))
    c2, created = st.commit(wc)
    assert created and c2.content != c1.content                       # the UI is part of the release
    reps = st.root / "example" / "objects" / c2.content / "representations"
    assert sorted(p.name for p in reps.iterdir()) == ["ui.representation.yaml"]


def test_commit_reports_the_last_approved_commit(tmp_path):
    write(tmp_path / "d.domain.yaml", schema_doc_domain())
    k = LocalKernel(tmp_path)
    c1 = k.call("commit", {"declaration": "d.domain.yaml"})
    assert c1["last_approved"] == ""
    k.commits.approve("example", c1["id"], "ana")
    raw = schema_doc_domain()
    raw["glossary"]["x"] = "y"
    write(tmp_path / "d.domain.yaml", raw)
    c2 = k.call("commit", {"declaration": "d.domain.yaml"})
    assert c2["last_approved"] == c1["id"]


def test_the_regeneration_check_passes_with_creating_replies(tmp_path):
    from toprope.harness.regen import effects_end_to_end
    write(tmp_path / "authoring.domain.yaml", AUTHORING)
    p = tmp_path / "self.composition.yaml"
    p.write_text(yaml.safe_dump({"composition": "self", "version": 1,
                                 "members": {"authoring": {"declaration": "authoring.domain.yaml"}}}))
    (e2e,) = effects_end_to_end(p)
    assert e2e["ok"], e2e
    assert e2e["effects"][0]["resolution"] == "EffectSucceeded" and e2e["effects"][0]["reply"] == "ok"


def test_an_unreadable_representation_stops_the_commit_and_an_explicit_empty_list_means_none(tmp_path):
    st = CommitStore(tmp_path / "commits")
    wc = write(tmp_path / "shop.domain.yaml", schema_doc_domain())
    (tmp_path / "ui.representation.yaml").write_text(yaml.safe_dump(
        {"representation": "ui", "version": 1, "targets": {"domain": "example", "interface": "1.x"}, "views": {}}))
    alone, _ = st.commit(wc, representations=[])
    assert not (st.root / "example" / "objects" / alone.content / "representations").exists()
    (tmp_path / "broken.representation.yaml").write_text("views: [unclosed\n")
    with pytest.raises(CommitError, match="broken.representation.yaml"):
        st.commit(wc)




# -- ADR-0041 Resolved 1: main takes no unconfirmed proposal -----------------------------------
def test_a_commit_with_a_proposed_element_is_not_approved(store):
    st, wc = store
    raw = schema_doc_domain()
    raw["links"]["hypothesis"]["status"] = "proposed"
    c, _ = st.commit(write(wc, raw))
    with pytest.raises(CommitError, match=r"1 proposed element\(s\): links.hypothesis"):
        st.approve("example", c.id, "ana")
    assert st.main("example") is None and st.approvals("example") == []
    raw["links"]["hypothesis"]["status"] = "confirmed"
    c2, _ = st.commit(write(wc, raw))
    assert st.approve("example", c2.id, "ana") == c2


def test_a_merge_that_brings_in_a_proposed_element_is_not_approved(store, tmp_path):
    st, wc = store
    raw = schema_doc_domain()
    base, _ = st.commit(write(wc, raw))
    st.approve("example", base.id, "ana")
    side = copy.deepcopy(raw)
    side["actions"]["launch_experiment"]["status"] = "proposed"
    c, _ = st.commit(write(tmp_path / "side.domain.yaml", side), branch="side")   # starts from main
    raw["glossary"]["x"] = "y"
    ahead, _ = st.commit(write(wc, raw))
    st.approve("example", ahead.id, "ana")                     # main moves on: approving c merges
    approvals, commits = st.approvals("example"), len(st.log("example"))
    with pytest.raises(CommitError, match=r"proposed element\(s\): actions.launch_experiment"):
        st.approve("example", c.id, "ana")
    assert st.main("example") == ahead
    assert st.approvals("example") == approvals and len(st.log("example")) == commits   # no merge commit


def test_the_change_check_records_how_many_elements_are_still_proposed(store):
    from toprope.check import check_commit
    st, wc = store
    raw = schema_doc_domain()
    raw["links"]["hypothesis"]["status"] = "proposed"
    c, _ = st.commit(write(wc, raw))
    check_commit(st, "example", c.id)
    rec = {r["check"]: r for r in st.checks("example", c.id)}["confirmed"]
    assert rec["ok"] is False and rec["summary"] == "1 proposed element(s): links.hypothesis"


def test_a_proposed_per_role_part_of_a_cell_blocks_approval_until_the_cell_is_confirmed(tmp_path):
    from toprope.workspace import AuthoringError, Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    raw = schema_doc_domain()
    raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"] = {
        "by_role": {"eng": {"deny": "Launch requires approval.", "status": "proposed"}},
        "source": {"kind": "interview", "ref": "q1"}, "status": "confirmed"}
    write(tmp_path / "d.domain.yaml", raw)
    ws = Workspace(tmp_path)
    c = ws.commit("by role")
    with pytest.raises(AuthoringError, match="transitions.Experiment.matrix.draft.launch_experiment"):
        ws.approve_commit(c["commit"], via="cli", who="ana")
    ws.confirm(["transitions.Experiment.matrix.draft.launch_experiment"], via="cli", who="ana")
    c2 = ws.commit("confirmed")
    ws.approve_commit(c2["commit"], via="cli", who="ana")
    assert ws.commits.main("example").id == c2["commit"]


def test_the_change_check_service_fails_while_elements_are_proposed(tmp_path):
    st = CommitStore(tmp_path / "commits")
    raw = schema_doc_domain()
    raw["links"]["hypothesis"]["status"] = "proposed"
    c, _ = st.commit(write(tmp_path / "wc.yaml", raw))
    k = LocalKernel(tmp_path, commits=st, harness_examples=0)
    out = k._change_check("example", c.id)
    assert out["passed"] is False and "confirmed" in out["failing"]
    assert out["summary"].endswith("; 1 proposed element(s) to confirm")


def test_deploy_refuses_a_commit_approved_with_proposed_elements(tmp_path, monkeypatch):
    st = CommitStore(tmp_path / "commits")
    env = LocalEnvironment(tmp_path / "env")
    raw = schema_doc_domain()
    raw["links"]["hypothesis"]["status"] = "proposed"
    c, _ = st.commit(write(tmp_path / "wc.yaml", raw))
    monkeypatch.setattr(CommitStore, "_confirmed", staticmethod(lambda *a: None))  # approved before ADR-0041
    st.approve("example", c.id, "ana")
    monkeypatch.undo()
    env.preview_commit(st, "example", c.id, examples=0)
    with pytest.raises(DeployRefused) as e:
        env.deploy_commit(st, "example", c.id, ANA)
    assert e.value.rule == "proposed"

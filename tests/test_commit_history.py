"""ADR-0032's additions to the commit store: the commit's author, an element's history, and
`checkout` (a revert is a new commit)."""
import copy
import json
import subprocess

import pytest
import yaml
from test_decl import schema_doc_domain

from toprope.commits import CommitError, CommitStore
from toprope.kernel.services import LocalKernel


def write(p, raw):
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    return p


def test_a_commit_records_its_author(tmp_path):
    st = CommitStore(tmp_path / "commits")
    c, _ = st.commit(write(tmp_path / "d.domain.yaml", schema_doc_domain()), author="ana")
    assert c.author == "ana" and st.get("example", c.id).author == "ana"
    k = LocalKernel(tmp_path)                                         # the kernel: the calling actor
    raw = schema_doc_domain()
    raw["glossary"]["x"] = "X."
    write(tmp_path / "d.domain.yaml", raw)
    out = k.call("commit", {"declaration": "d.domain.yaml"}, caller={"id": "bot", "kind": "agent"})
    assert k.commits.get("example", out["id"]).author == "bot"


def test_a_merge_commit_is_authored_by_its_approver(tmp_path):
    st = CommitStore(tmp_path / "commits")
    raw = schema_doc_domain()
    c0, _ = st.commit(write(tmp_path / "w.yaml", raw))
    st.approve("example", c0.id, "ana")
    a, b = copy.deepcopy(raw), copy.deepcopy(raw)
    a["glossary"]["a"] = "A."
    b["glossary"]["b"] = "B."
    ca, _ = st.commit(write(tmp_path / "a.yaml", a), branch="a")
    cb, _ = st.commit(write(tmp_path / "b.yaml", b), branch="b")
    st.approve("example", ca.id, "ana")
    assert st.approve("example", cb.id, "eli").author == "eli"


def test_an_element_log_lists_the_commits_that_changed_it(tmp_path):
    st = CommitStore(tmp_path / "commits")
    wc = tmp_path / "d.domain.yaml"
    raw = schema_doc_domain()
    key = "invariant:running-has-start"
    c1, _ = st.commit(write(wc, raw), author="ana", message="first")
    raw["glossary"]["x"] = "X."                                       # does not touch the element
    st.commit(write(wc, raw))
    inv = next(i for i in raw["invariants"] if i["id"] == "running-has-start")
    inv["source"] = {"kind": "interview", "ref": "interview/2026-11-21#q3"}
    inv["status"] = "confirmed"                                       # a confirmation: provenance only
    c3, _ = st.commit(write(wc, raw), author="ana")
    inv["reason"] = "A launched experiment records its start."
    c4, _ = st.commit(write(wc, raw), author="eli", message="reword")
    raw["invariants"].remove(inv)
    del raw["objects"]["Experiment"]["properties"]["started_at"]
    raw["actions"]["launch_experiment"]["effects"] = []
    c5, _ = st.commit(write(wc, raw))
    log = st.element_log("example", key, at=c5.id)
    assert [(e["commit"], e["change"]) for e in log] == [
        (c1.id, "added"), (c3.id, "provenance"), (c4.id, "changed"), (c5.id, "removed")]
    assert log[0]["author"] == "ana" and log[0]["message"] == "first"
    assert log[1]["status"] == "confirmed" and log[1]["source"]["ref"] == "interview/2026-11-21#q3"
    assert log[2]["author"] == "eli"
    assert [e["commit"] for e in st.element_log("example", key, at=c3.id)] == [c1.id, c3.id]
    assert st.element_log("example", key) == log                      # default: the `work` head


def test_checkout_loads_a_commit_and_a_revert_is_a_new_commit(tmp_path):
    st = CommitStore(tmp_path / "commits")
    wc = tmp_path / "d.domain.yaml"
    raw = schema_doc_domain()
    c1, _ = st.commit(write(wc, raw))
    ui = tmp_path / "ui.representation.yaml"
    ui.write_text(yaml.safe_dump({"representation": "ui", "version": 1,
                                  "targets": {"domain": "example", "interface": "1.x"}, "views": {}}))
    raw["glossary"]["x"] = "X."
    c2, _ = st.commit(write(wc, raw))
    assert st.checkout("example", c1.id, wc) == c1
    assert "x" not in yaml.safe_load(wc.read_text())["glossary"] and not ui.exists()   # the UI came later
    c3, created = st.commit(wc)
    assert created and c3.parents == [c2.id] and c3.content == c1.content           # the revert
    raw["glossary"]["y"] = "uncommitted"
    write(wc, raw)
    with pytest.raises(CommitError, match="changes no commit holds"):
        st.checkout("example", c2.id, wc)
    st.checkout("example", c2.id, wc, force=True)
    assert yaml.safe_load(wc.read_text())["glossary"]["x"] == "X." and ui.exists()


def test_the_checkout_service_and_the_history_command(tmp_path):
    from toprope.workspace import Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    raw = schema_doc_domain()
    write(tmp_path / "d.domain.yaml", raw)
    ws = Workspace(tmp_path)
    c1 = ws.commit(author="ana")["commit"]
    raw["actions"]["launch_experiment"]["description"] = "Start traffic."
    write(tmp_path / "d.domain.yaml", raw)
    c2 = ws.commit(author="eli")["commit"]
    r = subprocess.run(["uv", "run", "--quiet", "toprope-commits", "--commits", str(tmp_path / ".toprope/commits"),
                        "log", "example", "action:launch_experiment"], capture_output=True, text=True, timeout=120)
    log = json.loads(r.stdout)
    assert [(e["commit"], e["change"], e["author"]) for e in log] == [(c1, "added", "ana"), (c2, "changed", "eli")]
    assert ws.checkout(c1)["commit"] == c1
    assert yaml.safe_load((tmp_path / "d.domain.yaml").read_text())["actions"]["launch_experiment"]["description"] \
        != "Start traffic."
    k = LocalKernel(tmp_path)
    assert k.call("checkout", {"domain": "example", "commit": c2, "declaration": "d.domain.yaml"})["ok"]
    assert yaml.safe_load((tmp_path / "d.domain.yaml").read_text())["actions"]["launch_experiment"]["description"] \
        == "Start traffic."
    out = k.call("checkout", {"domain": "example", "commit": c2, "declaration": "../outside.yaml"})
    assert not out["ok"] and "outside" in out["error"]


# -- review findings -----------------------------------------------------------------------------
def test_an_element_log_at_an_unknown_commit_is_an_error(tmp_path):
    st = CommitStore(tmp_path / "commits")
    st.commit(write(tmp_path / "d.domain.yaml", schema_doc_domain()))
    with pytest.raises(CommitError, match="no commit"):
        st.element_log("example", "action:launch_experiment", at="main")


def test_checkout_never_drops_an_uncommitted_ui_next_to_a_missing_declaration(tmp_path):
    st = CommitStore(tmp_path / "commits")
    wc = write(tmp_path / "d.domain.yaml", schema_doc_domain())
    c1, _ = st.commit(wc)
    wc.unlink()
    ui = tmp_path / "ui.representation.yaml"
    ui.write_text(yaml.safe_dump({"representation": "ui", "version": 1,
                                  "targets": {"domain": "example", "interface": "1.x"}, "views": {}}))
    with pytest.raises(CommitError, match="changes no commit holds"):
        st.checkout("example", c1.id, wc)
    assert ui.exists()


def test_a_forced_checkout_recovers_an_unreadable_working_copy(tmp_path):
    from toprope.workspace import AuthoringError, Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    write(tmp_path / "d.domain.yaml", schema_doc_domain())
    ws = Workspace(tmp_path)
    c1 = ws.commit()["commit"]
    (tmp_path / "bad.representation.yaml").write_text("a: [unclosed")
    with pytest.raises(AuthoringError, match="cannot read"):
        ws.checkout(c1)
    (tmp_path / "bad.representation.yaml").unlink()
    (tmp_path / "d.domain.yaml").write_text("domain: [unclosed")
    with pytest.raises(AuthoringError, match="cannot read the working copy"):
        ws.checkout(c1)
    (tmp_path / "bad.representation.yaml").write_text("a: [unclosed")
    assert ws.checkout(c1, force=True)["commit"] == c1
    assert yaml.safe_load((tmp_path / "d.domain.yaml").read_text())["domain"] == "example"


def test_checkout_keeps_the_drafts_version(tmp_path):
    st = CommitStore(tmp_path / "commits")
    raw = schema_doc_domain()
    raw["version"] = 7
    wc = write(tmp_path / "d.domain.yaml", raw)
    c1, _ = st.commit(wc)
    raw["glossary"]["x"] = "X."
    st.commit(write(wc, raw))
    st.checkout("example", c1.id, wc)
    assert yaml.safe_load(wc.read_text())["version"] == 7


def test_a_caller_without_an_id_authors_nothing(tmp_path):
    write(tmp_path / "d.domain.yaml", schema_doc_domain())
    k = LocalKernel(tmp_path)
    out = k.call("commit", {"declaration": "d.domain.yaml"}, caller={"id": None, "kind": "agent"})
    assert k.commits.get("example", out["id"]).author == ""
    assert k.caller is None                                           # per call: nothing left behind


def test_a_merge_resolution_is_not_credited_with_mains_changes(tmp_path):
    from toprope.workspace import Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    raw = schema_doc_domain()
    write(tmp_path / "d.domain.yaml", raw)
    ws = Workspace(tmp_path)
    ws.approve_commit(ws.commit(author="ana")["commit"], via="cli", who="ana")
    other = copy.deepcopy(raw)
    other["actions"]["launch_experiment"]["description"] = "Turn it on."
    (tmp_path / "o").mkdir()
    co = ws.commits.commit(write(tmp_path / "o" / "o.domain.yaml", other), branch="eli", author="eli")[0]
    ws.approve_commit(co.id, via="cli", who="eli")
    raw["actions"]["launch_experiment"]["description"] = "Start traffic."
    write(tmp_path / "d.domain.yaml", raw)
    ws.commit(author="ana")
    ws.merge_main()
    resolved = ws.draft()
    resolved["actions"]["launch_experiment"]["description"] = "Turn it on."   # take main's wording
    resolved["glossary"]["mine"] = "M."
    write(tmp_path / "d.domain.yaml", resolved)
    r = ws.commit(merge=co.id, author="ana")["commit"]
    ws.approve_commit(r, via="cli", who="ana")
    log = ws.element_log("action:launch_experiment")
    assert [(e["author"], e["change"]) for e in log] == [("ana", "added"), ("eli", "changed"), ("ana", "changed")]
    assert r not in [e["commit"] for e in log]                        # ana's own edit is her branch commit

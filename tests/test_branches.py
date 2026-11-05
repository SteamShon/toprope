"""Branches from the start (ADR-0033): refs, a protected main, semantic 3-way merge, and a
deploy floor that decides "newer" by ancestry."""
import copy
import json
import subprocess

import pytest
import yaml
from test_decl import schema_doc_domain

from toprope.commits import CommitError, CommitStore, MergeConflict
from toprope.decl import Domain, validate_domain
from toprope.deploy import DeployRefused, LocalEnvironment
from toprope.semantics import Actor

ANA = Actor("ana", "person", ("approver",))


def write(p, raw):
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    return p


@pytest.fixture
def st(tmp_path):
    return CommitStore(tmp_path / "commits")


def on(st, tmp_path, raw, branch, **kw):
    return st.commit(write(tmp_path / f"{branch}.domain.yaml", raw), branch=branch, **kw)[0]


def started(st, tmp_path):
    """One approved commit on main: the common start of every branch below."""
    raw = schema_doc_domain()
    c0 = on(st, tmp_path, raw, "work")
    st.approve("example", c0.id, "ana")
    return raw, c0


def test_main_is_protected_and_branches_start_from_main(st, tmp_path):
    raw, c0 = started(st, tmp_path)
    with pytest.raises(CommitError, match="protected"):
        st.commit(write(tmp_path / "m.yaml", raw), branch="main")
    a, b = copy.deepcopy(raw), copy.deepcopy(raw)
    a["glossary"]["a"] = "A."
    b["glossary"]["b"] = "B."
    ca, cb = on(st, tmp_path, a, "feat-a"), on(st, tmp_path, b, "feat-b")
    assert ca.parents == [c0.id] and cb.parents == [c0.id] and ca.branch == "feat-a"
    assert st.refs("example") == {"work": c0.id, "main": c0.id, "feat-a": ca.id, "feat-b": cb.id}
    assert st.head("example", "feat-a") == ca and st.main("example") == c0
    assert st.merge_base("example", ca.id, cb.id) == c0.id
    assert st.is_ancestor("example", c0.id, ca.id) and not st.is_ancestor("example", ca.id, cb.id)


def test_approving_a_diverged_branch_makes_a_validated_merge_commit(st, tmp_path):
    raw, _ = started(st, tmp_path)
    a, b = copy.deepcopy(raw), copy.deepcopy(raw)
    a["glossary"]["a"] = "A."
    a["roles"].append("ops")                                        # both add to a list of roles
    b["roles"].append("legal")
    b["actions"]["launch_experiment"]["description"] = "Start traffic."
    ca, cb = on(st, tmp_path, a, "feat-a"), on(st, tmp_path, b, "feat-b")
    assert st.approve("example", ca.id, "ana") == ca                # main has not moved: fast-forward
    m = st.approve("example", cb.id, "ana")                          # main moved: a merge commit
    assert m.parents == [ca.id, cb.id] and st.main("example") == m and st.is_approved("example", m.id)
    assert not st.is_approved("example", cb.id)                      # the tag is on what main points to
    merged = st.declaration("example", m.id)
    assert merged["glossary"]["a"] == "A." and merged["actions"]["launch_experiment"]["description"] == "Start traffic."
    assert merged["roles"] == raw["roles"] + ["ops", "legal"]
    assert st.approvals("example")[-1]["merged"] == cb.id


def test_a_direct_conflict_is_listed_by_path_and_main_does_not_move(st, tmp_path):
    raw, _ = started(st, tmp_path)
    a, b = copy.deepcopy(raw), copy.deepcopy(raw)
    a["actions"]["launch_experiment"]["description"] = "Start traffic."
    b["actions"]["launch_experiment"]["description"] = "Turn it on."
    ca, cb = on(st, tmp_path, a, "feat-a"), on(st, tmp_path, b, "feat-b")
    st.approve("example", ca.id, "ana")
    with pytest.raises(MergeConflict) as e:
        st.approve("example", cb.id, "ana")
    (c,) = e.value.conflicts
    assert c.path == "domain.actions.launch_experiment.description"
    assert (c.ours, c.theirs) == ("Start traffic.", "Turn it on.")
    assert st.main("example") == ca


def test_an_indirect_conflict_fails_the_merge_check(st, tmp_path):
    """Each side validates alone; together an invariant reads a property the other side removed."""
    raw, _ = started(st, tmp_path)
    a, b = copy.deepcopy(raw), copy.deepcopy(raw)
    del a["objects"]["Experiment"]["properties"]["started_at"]
    a["actions"]["launch_experiment"]["effects"] = []
    a["invariants"] = [i for i in a["invariants"] if i["id"] != "running-has-start"]
    b["invariants"].append({"id": "ended-has-start", "on": "Experiment",
                            "check": "target.status != 'ended' or exists(target.started_at)", "reason": "r"})
    for side in (a, b):
        assert not [i for i in validate_domain(Domain.model_validate(side)) if i.severity == "error"]
    ca, cb = on(st, tmp_path, a, "feat-a"), on(st, tmp_path, b, "feat-b")
    st.approve("example", ca.id, "ana")
    with pytest.raises(CommitError, match="does not validate"):
        st.approve("example", cb.id, "ana")
    assert st.main("example") == ca


def test_conflicts_are_resolved_in_the_working_copy_then_approved(tmp_path):
    from toprope.authoring import AuthoringError, Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    raw = schema_doc_domain()
    write(tmp_path / "d.domain.yaml", raw)
    ws = Workspace(tmp_path)
    c0 = ws.commit()["commit"]
    ws.approve_commit(c0, via="cli", who="ana")
    other = copy.deepcopy(raw)                                       # someone else lands a change on main
    other["actions"]["launch_experiment"]["description"] = "Turn it on."
    other["glossary"]["o"] = "O."
    (tmp_path / "other").mkdir()
    co = ws.commits.commit(write(tmp_path / "other" / "o.domain.yaml", other), branch="other")[0]
    ws.approve_commit(co.id, via="cli", who="ana")
    raw["actions"]["launch_experiment"]["description"] = "Start traffic."
    write(tmp_path / "d.domain.yaml", raw)
    mine = ws.commit()["commit"]
    with pytest.raises(AuthoringError, match="conflicts"):
        ws.approve_commit(mine, via="cli", who="ana")
    raw["glossary"]["dirty"] = "not committed"
    write(tmp_path / "d.domain.yaml", raw)
    with pytest.raises(AuthoringError, match="not committed"):
        ws.merge_main()
    del raw["glossary"]["dirty"]
    write(tmp_path / "d.domain.yaml", raw)
    out = ws.merge_main()
    assert out["merge"] == co.id and [c["path"] for c in out["conflicts"]] == ["domain.actions.launch_experiment.description"]
    resolved = ws.draft()
    assert resolved["glossary"]["o"] == "O."                         # main's other change came in
    resolved["actions"]["launch_experiment"]["description"] = "Start traffic now."
    write(tmp_path / "d.domain.yaml", resolved)
    r = ws.commit(merge=co.id)
    assert ws.commits.get("example", r["commit"]).parents == [mine, co.id]
    a = ws.approve_commit(r["commit"], via="cli", who="ana")
    assert a["main"] == r["commit"]                                  # a fast-forward: no new merge commit
    assert ws.merge_main()["up_to_date"]


def test_the_deploy_floor_uses_main_and_ancestry(st, tmp_path):
    raw, c0 = started(st, tmp_path)
    env = LocalEnvironment(tmp_path / "env")
    a, b = copy.deepcopy(raw), copy.deepcopy(raw)
    a["glossary"]["a"] = "A."
    b["glossary"]["b"] = "B."
    ca, cb = on(st, tmp_path, a, "feat-a"), on(st, tmp_path, b, "feat-b")
    for c in (c0, ca, cb):
        env.preview_commit(st, "example", c.id, examples=0)
    with pytest.raises(DeployRefused) as e:                           # a branch commit has no approval
        env.deploy_commit(st, "example", cb.id, ANA)
    assert e.value.rule == "unapproved"
    st.approve("example", ca.id, "ana")
    m = st.approve("example", cb.id, "ana")
    with pytest.raises(DeployRefused) as e:                           # approved, but main has moved on
        env.deploy_commit(st, "example", ca.id, ANA)
    assert e.value.rule == "superseded"
    env.preview_commit(st, "example", m.id, examples=0)
    assert env.deploy_commit(st, "example", m.id, ANA)["commit"] == m.id
    with pytest.raises(DeployRefused) as e:
        env.deploy_commit(st, "example", m.id, ANA)
    assert e.value.rule == "downgrade"


def test_cli_branches_merge_and_approve(tmp_path):
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    raw = schema_doc_domain()
    write(tmp_path / "d.domain.yaml", raw)
    def run(*a):
        return subprocess.run(["uv", "run", "--quiet", "toprope-author", *a, "--workspace", str(tmp_path)],
                              capture_output=True, text=True, timeout=120, check=False)
    c1 = json.loads(run("commit", "--branch", "feat").stdout)
    assert c1["branch"] == "feat"
    assert "protected" in run("commit", "--branch", "main").stderr
    assert json.loads(run("approve", c1["commit"], "--as", "ana", "--yes").stdout)["main"] == c1["commit"]
    assert json.loads(run("branches").stdout) == {"feat": c1["commit"], "main": c1["commit"]}
    assert json.loads(run("merge", "--branch", "feat").stdout)["up_to_date"] is True

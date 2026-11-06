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
    (c,) = e.value.conflicts                                          # once: the path shows it
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
    from toprope.workspace import AuthoringError, Workspace
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


# -- review findings -----------------------------------------------------------------------------
def workspace(tmp_path, raw):
    from toprope.workspace import Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    write(tmp_path / "d.domain.yaml", raw)
    return Workspace(tmp_path)


def land_on_main(ws, tmp_path, raw, name="other"):
    """Someone else's change, approved into main from its own branch and folder."""
    (tmp_path / name).mkdir(exist_ok=True)
    c = ws.commits.commit(write(tmp_path / name / "o.domain.yaml", raw), branch=name, representations=[])[0]
    ws.approve_commit(c.id, via="cli", who="ana")
    return c


def test_a_resolved_merge_is_checked_before_main_takes_it(tmp_path):
    """The `merge`, `commit --merge`, approve route fast-forwards, and is validated all the same."""
    from toprope.workspace import AuthoringError
    raw = schema_doc_domain()
    ws = workspace(tmp_path, raw)
    ws.approve_commit(ws.commit()["commit"], via="cli", who="ana")
    other = copy.deepcopy(raw)
    del other["objects"]["Experiment"]["properties"]["started_at"]
    other["actions"]["launch_experiment"]["effects"] = []
    other["invariants"] = [i for i in other["invariants"] if i["id"] != "running-has-start"]
    co = land_on_main(ws, tmp_path, other)
    raw["invariants"].append({"id": "ended-has-start", "on": "Experiment",
                              "check": "target.status != 'ended' or exists(target.started_at)", "reason": "r"})
    write(tmp_path / "d.domain.yaml", raw)
    ws.commit()
    assert ws.merge_main()["conflicts"] == []
    r = ws.commit(merge=co.id)
    with pytest.raises(AuthoringError, match="does not validate"):
        ws.approve_commit(r["commit"], via="cli", who="ana")
    assert ws.commits.main("example").id == co.id


def test_branches_made_before_any_approval_share_the_first_commit(st, tmp_path):
    raw = schema_doc_domain()
    raw["glossary"]["x"] = "X."
    c1 = on(st, tmp_path, raw, "work")
    feat = copy.deepcopy(raw)
    del feat["glossary"]["x"]                                        # a deletion on one side
    c2 = on(st, tmp_path, feat, "feat")
    assert c2.parents == [c1.id] and st.merge_base("example", c1.id, c2.id) == c1.id
    st.approve("example", c1.id, "ana")
    m = st.approve("example", c2.id, "ana")                           # fast-forward: c1 is c2's parent
    assert m == c2 and "x" not in st.declaration("example", st.main("example").id)["glossary"]


def test_a_store_from_before_branches_keeps_its_history(st, tmp_path):
    raw = schema_doc_domain()
    c1 = on(st, tmp_path, raw, "work")
    st.approve("example", c1.id, "ana")
    raw["glossary"]["x"] = "X."
    c2 = on(st, tmp_path, raw, "work")
    (st.root / "example" / "refs.jsonl").unlink()                     # as written before ADR-0033
    assert st.refs("example") == {"work": c2.id, "main": c1.id} and st.latest_approved("example") == c1
    raw["glossary"]["y"] = "Y."
    c3 = on(st, tmp_path, raw, "work")
    assert c3.parents == [c2.id]
    assert st.refs("example") == {"work": c3.id, "main": c1.id}       # the derived refs were kept


def test_an_element_changed_on_both_sides_conflicts_even_in_different_fields(st, tmp_path):
    raw, _ = started(st, tmp_path)
    a, b = copy.deepcopy(raw), copy.deepcopy(raw)
    a["actions"]["launch_experiment"]["description"] = "Start traffic."
    b["actions"]["launch_experiment"]["actor"] = ["eng", "pm"]
    ca, cb = on(st, tmp_path, a, "feat-a"), on(st, tmp_path, b, "feat-b")
    st.approve("example", ca.id, "ana")
    with pytest.raises(MergeConflict) as e:
        st.approve("example", cb.id, "ana")
    assert [c.path for c in e.value.conflicts] == ["element:action:launch_experiment"]
    a2, b2 = copy.deepcopy(a), copy.deepcopy(raw)                      # added on both sides, differently
    a2["glossary"]["close"] = "End it."
    b2["glossary"]["close"] = "Stop it."
    assert "element:term:close" in [c.path for c in st.merge3(
        "example", on(st, tmp_path, a2, "feat-a").id, on(st, tmp_path, b2, "feat-c").id).conflicts]


def test_a_branch_is_reviewed_from_its_merge_base_not_from_main(tmp_path):
    raw = schema_doc_domain()
    ws = workspace(tmp_path, raw)
    c0 = ws.commit()["commit"]
    ws.approve_commit(c0, via="cli", who="ana")
    other = copy.deepcopy(raw)
    other["glossary"]["o"] = "O."
    land_on_main(ws, tmp_path, other)
    raw["actions"]["launch_experiment"]["description"] = "Start traffic."
    write(tmp_path / "d.domain.yaml", raw)
    out = ws.commit()
    assert out["since"] == c0 and out["to_review"] == ["action:launch_experiment"] and out["removed"] == []


def test_merging_main_removes_a_ui_that_main_removed(tmp_path):
    raw = schema_doc_domain()
    ui = tmp_path / "ui.representation.yaml"
    ui.write_text(yaml.safe_dump({"representation": "ui", "version": 1,
                                  "targets": {"domain": "example", "interface": "1.x"}, "views": {}}))
    ws = workspace(tmp_path, raw)
    ws.approve_commit(ws.commit()["commit"], via="cli", who="ana")
    other = copy.deepcopy(raw)
    other["glossary"]["o"] = "O."
    land_on_main(ws, tmp_path, other)                                 # its folder has no UI: removed
    raw["glossary"]["mine"] = "M."
    write(tmp_path / "d.domain.yaml", raw)
    ws.commit()
    assert ws.merge_main()["conflicts"] == [] and not ui.exists()


def test_merge_reports_an_unreadable_ui_as_an_authoring_error(tmp_path):
    from toprope.workspace import AuthoringError
    raw = schema_doc_domain()
    ws = workspace(tmp_path, raw)
    ws.approve_commit(ws.commit()["commit"], via="cli", who="ana")
    other = copy.deepcopy(raw)
    other["glossary"]["o"] = "O."
    land_on_main(ws, tmp_path, other)
    raw["glossary"]["mine"] = "M."
    write(tmp_path / "d.domain.yaml", raw)
    ws.commit()
    (tmp_path / "bad.representation.yaml").write_text("a: [unclosed")
    with pytest.raises(AuthoringError, match="cannot read"):
        ws.merge_main()


def test_an_element_added_on_both_sides_conflicts_even_when_one_side_has_less(st, tmp_path):
    raw, _ = started(st, tmp_path)
    a, b = copy.deepcopy(raw), copy.deepcopy(raw)
    a["objects"]["Experiment"]["properties"]["tag"] = {"type": "string", "optional": True}
    b["objects"]["Experiment"]["properties"]["tag"] = {"type": "string"}
    m = st.merge3("example", on(st, tmp_path, a, "feat-a").id, on(st, tmp_path, b, "feat-b").id)
    assert [c.path for c in m.conflicts if c.path.startswith("element:")] == ["element:property:Experiment.tag"]
    assert not [c for c in m.conflicts if not c.path.startswith("element:")]   # no path conflict at all


def test_the_commit_service_reviews_from_the_merge_base_like_the_workspace(tmp_path):
    from toprope.kernel.services import LocalKernel
    raw = schema_doc_domain()
    write(tmp_path / "d.domain.yaml", raw)
    k = LocalKernel(tmp_path)
    c0 = k.call("commit", {"declaration": "d.domain.yaml"})["id"]
    k.commits.approve("example", c0, "ana")
    raw["glossary"]["a"] = "A."
    write(tmp_path / "d.domain.yaml", raw)
    k.call("commit", {"declaration": "d.domain.yaml"})
    raw["actions"]["launch_experiment"]["description"] = "Start traffic."
    write(tmp_path / "d.domain.yaml", raw)
    c2 = k.call("commit", {"declaration": "d.domain.yaml"})
    assert c2["to_review"] == ["action:launch_experiment", "term:a"]        # the branch, not its last step


def test_before_any_approval_a_commit_is_reviewed_against_its_parent(tmp_path):
    """The commit's to-review list and its change check use the same base (ADR-0033)."""
    raw = schema_doc_domain()
    ws = workspace(tmp_path, raw)
    first = ws.commit()["commit"]
    raw["actions"]["launch_experiment"]["description"] = "Start traffic."
    write(tmp_path / "d.domain.yaml", raw)
    out = ws.commit()
    assert out["since"] == first and out["to_review"] == ["action:launch_experiment"]


def test_a_merge_in_progress_is_recorded_and_the_next_commit_uses_it(tmp_path):
    """Like git's MERGE_HEAD: merging main into a branch is remembered until a commit records
    both parents, so the kernel's plain `commit` service finishes a merge (ADR-0037)."""
    raw = schema_doc_domain()
    ws = workspace(tmp_path, raw)
    ws.approve_commit(ws.commit()["commit"], via="cli", who="ana")
    other = copy.deepcopy(raw)
    other["glossary"]["o"] = "O."
    main = land_on_main(ws, tmp_path, other)
    raw["glossary"]["mine"] = "M."
    write(tmp_path / "d.domain.yaml", raw)
    ws.commit()
    out = ws.merge_main()
    assert out["conflicts"] == [] and ws.commits.pending_merge("example") == out["merge"]
    c = ws.commits.get("example", ws.commit()["commit"])                       # no `merge=` given
    assert len(c.parents) == 2 and c.parents[1] == out["merge"] and main
    assert ws.commits.pending_merge("example") is None
    assert not (tmp_path / ".toprope/commits/example/merging.json").exists()


def test_the_kernel_merges_main_into_a_working_copy(tmp_path):
    from toprope.kernel.services import LocalKernel
    raw = schema_doc_domain()
    ws = workspace(tmp_path, raw)
    ws.approve_commit(ws.commit()["commit"], via="cli", who="ana")
    other = copy.deepcopy(raw)
    other["glossary"]["o"] = "O."
    land_on_main(ws, tmp_path, other)
    k = LocalKernel(tmp_path, harness_examples=5)
    up = k.call("merge_main", {"domain": "example", "branch": "work", "declaration": "d.domain.yaml"})
    assert up["ok"] and up["up_to_date"] is False and up["conflicts"] == 0
    assert yaml.safe_load((tmp_path / "d.domain.yaml").read_text())["glossary"]["o"] == "O."
    done = k.call("commit", {"declaration": "d.domain.yaml"}, caller={"id": "ana", "kind": "person"})
    assert len(ws.commits.get("example", done["id"]).parents) == 2
    again = k.call("merge_main", {"domain": "example", "branch": "work", "declaration": "d.domain.yaml"})
    assert again["up_to_date"] is True

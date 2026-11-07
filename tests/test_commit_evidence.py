"""ADR-0041, Resolved 3: a commit may cite its evidence. Evidence is a pointer that resolves,
never prose, and its kind says how strong it is."""
import json
from contextlib import contextmanager

import pytest
import yaml
from test_decl import schema_doc_domain

from toprope.commits import CommitError, CommitStore
from toprope.commits.cli import main as commits_cli
from toprope.kernel.services import LocalKernel
from toprope.workspace import Workspace

ANA = {"id": "ana", "kind": "person"}


@pytest.fixture
def kernel(tmp_path):
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({
        "domain": "d.domain.yaml", "interview_log": "interview.jsonl",
        "sources": [{"id": "docs", "kind": "records", "path": "docs"},
                    {"id": "interview", "kind": "interview-log", "path": "interview.jsonl"}]}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# Approval\nEvery experiment needs an approver.\n")
    (tmp_path / "interview.jsonl").write_text(json.dumps({"question": "Who approves?", "answer": "A lead."}) + "\n")
    (tmp_path / "d.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    k = LocalKernel(tmp_path, workspace=Workspace(tmp_path))
    c = k.call("commit", {"declaration": "d.domain.yaml"}, caller=ANA)
    assert c["ok"]
    return k, c["id"]


def cite(k, commit, kind, ref, caller=ANA):
    return k.call("cite_evidence", {"domain": "example", "commit": commit, "kind": kind, "ref": ref}, caller=caller)


def test_a_commit_cites_a_source_line_and_an_interview_answer(kernel):
    k, c = kernel
    doc = k.workspace.chunks("docs")[0].ref
    said = k.workspace.chunks("interview")[0].ref
    assert cite(k, c, "source", doc)["strength"] == "pointed"
    assert cite(k, c, "interview", said, caller={"id": "bot", "kind": "agent"})["strength"] == "pointed"
    rows = k.commits.evidence("example", c)
    assert [(r["kind"], r["ref"], r["by"]) for r in rows] == [("source", doc, "ana"), ("interview", said, "bot")]


def test_evidence_that_does_not_resolve_is_refused(kernel):
    k, c = kernel
    for kind, ref in [("source", "docs:docs/a.md#L90-L99"),       # no such chunk
                      ("source", "elsewhere:x.md#L1"),             # no such source
                      ("source", k.workspace.chunks("interview")[0].ref),  # an interview line, cited as a source
                      ("check", "harness"),                        # not run on this commit
                      ("event", "Experiment:E1@1"),                # nothing deployed here
                      ("hunch", "it looks fine"),                  # not a kind of evidence
                      ("source", "  ")]:                           # prose-free, but empty
        out = cite(k, c, kind, ref)
        assert not out["ok"] and out["error"], (kind, ref)
    assert k.commits.evidence("example", c) == []


def test_a_check_is_evidence_once_it_ran_on_that_commit(kernel):
    k, c = kernel
    assert not cite(k, c, "check", "change-check")["ok"]
    k.commits.record_check("example", c, "change-check", True, "passed")
    assert cite(k, c, "check", "change-check")["strength"] == "ran"


def test_an_event_is_evidence_when_the_deployed_store_holds_it(kernel):
    k, c = kernel

    class Store:
        def version(self, stream):
            return {"Experiment:E1": 2}.get(stream, 0)

    class Env:
        @contextmanager
        def events(self, domain):
            yield Store()

    k.environment = Env()
    assert cite(k, c, "event", "Experiment:E1@2")["strength"] == "observed"
    for ref in ("Experiment:E1@3", "Experiment:E9@1", "Experiment:E1", "@1"):
        assert not cite(k, c, "event", ref)["ok"], ref


def test_the_store_refuses_an_unknown_commit(tmp_path):
    st = CommitStore(tmp_path / "commits")
    (tmp_path / "d.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    st.commit(tmp_path / "d.yaml")
    with pytest.raises(CommitError):
        st.cite("example", "9-nope", "source", "docs:a.md#L1")


def test_toprope_commits_lists_a_commits_evidence(kernel, capsys):
    k, c = kernel
    cite(k, c, "source", k.workspace.chunks("docs")[0].ref)
    commits_cli(["--commits", str(k.commits.root), "evidence", "example", c])
    (row,) = json.loads(capsys.readouterr().out)
    assert row["kind"] == "source" and row["strength"] == "pointed"


def test_an_approval_run_is_evidence_once_the_human_request_workflow_recorded_it(kernel):
    k, c = kernel
    url = "https://github.com/SteamShon/toprope/actions/runs/42"
    assert not cite(k, c, "approval-run", url)["ok"]                       # never ran as an approval
    (k.root / ".toprope").mkdir(exist_ok=True)
    (k.root / ".toprope" / "approval-runs.jsonl").write_text(json.dumps({"run": url, "approver": "SteamShon"}) + "\n")
    assert cite(k, c, "approval-run", url)["strength"] == "approved"
    assert not cite(k, c, "approval-run", url + "3")["ok"]

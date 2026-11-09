"""One command takes a change from proposals to one request for a person (ADR-0049, C1)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from toprope.adapters.cli.change import main, read_patch, request_for

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import human_request as hr  # noqa: E402

ME = "steamshon <steamshon@apache.org>"
RULE = {"id": "drafts-name-their-declaration", "on": "Draft", "check": "exists(target.declaration)",
        "reason": "A draft is the working copy of one declaration."}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A copy of the repository with clean drafts and empty logs, as test_self_loop makes."""
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
    for f in filter(None, files):
        src, dst = ROOT / f.decode(), tmp_path / f.decode()
        if "/events/" in f.decode() or not src.is_file():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    from toprope.commits import CommitStore
    approved = CommitStore(ROOT / ".toprope" / "commits")
    for d in ("authoring", "delivery"):
        approved.export(d, approved.main(d).id, tmp_path / f"domains/{d}/{d}.domain.yaml")
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump({"t-owen": {"id": ME, "roles": ["owner", "approver"]}}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TOPROPE_TOKEN", "t-owen")
    run = [sys.executable, "-c", "from toprope.adapters.cli import main; main()", "--identity", "static:ids.yaml",
           "--member", "authoring"]
    for args in (["open_draft", "authoring", "--domain-id", "authoring", "--declaration",
                  "domains/authoring/authoring.domain.yaml", "--branch", "work"],
                 ["add_source", "S-adr", "--kind", "records", "--path", "docs/adr"]):
        r = subprocess.run([*run, *args], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    return tmp_path


def a_ref(repo):
    from toprope.workspace import Workspace
    return Workspace(repo / "toprope.authoring.workspace.yaml").chunks("records")[0].ref


def patch(tmp_path, items):
    p = tmp_path / "change.yaml"
    p.write_text(yaml.safe_dump(items, sort_keys=False))
    return str(p)


def test_one_command_proposes_commits_checks_and_writes_one_request(repo, capsys):
    p = patch(repo, [{"path": f"invariants.{RULE['id']}", "value": RULE, "origin": "S-adr",
                      "cites": a_ref(repo)}])
    main(["Drafts name their declaration", "--patch", p, "--run-args", "--identity static:ids.yaml"])
    out = capsys.readouterr().out
    result = json.loads(out[out.index("{\n"):])
    assert result["proposed"] == [f"invariants.{RULE['id']}"]
    assert f"+ invariants.{RULE['id']}" in out                         # the diff the person will confirm
    req = hr.load(repo / result["request"])
    assert hr.check(req) == []                                         # a request the workflow accepts
    assert [s["run"]["action"] for s in req["steps"]] == [
        "confirm_all_proposed", "commit_draft", "check_commit", "approve_commit"]
    assert req["summary"] == "Drafts name their declaration"
    decl = yaml.safe_load((repo / "domains/authoring/authoring.domain.yaml").read_text())
    (added,) = [i for i in decl["invariants"] if i["id"] == RULE["id"]]
    assert added["status"] == "proposed"                               # nothing is confirmed by the agent


def test_a_refused_proposal_stops_before_any_request(repo, capsys):
    bad = {**RULE, "check": "target.no_such_property == 1"}
    p = patch(repo, [{"path": f"invariants.{RULE['id']}", "value": bad, "origin": "S-adr",
                      "cites": a_ref(repo)}])
    with pytest.raises(SystemExit) as e:
        main(["A broken rule", "--patch", p, "--run-args", "--identity static:ids.yaml"])
    assert "Fix:" in str(e.value)
    assert not (repo / ".toprope/requests").exists() or not list((repo / ".toprope/requests").glob("a-broken*"))


def test_a_patch_without_what_it_cites_is_refused_with_the_fix(tmp_path):
    p = patch(tmp_path, [{"path": "objects.X", "value": {}}])
    with pytest.raises(SystemExit, match="element 1 of the patch has no cites. Fix: give each element"):
        read_patch(p)


def test_the_request_has_the_four_steps_a_change_takes():
    assert request_for("x", "authoring", "authoring", None) == hr.change("authoring", summary="x")

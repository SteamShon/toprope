"""Human requests approved in GitHub (ADR-0039): the request file, the approver as the
identity, and the steps run as that person."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import human_request as hr  # noqa: E402

from toprope.identity.github import ENV, GitHubApprovalIdentity, github_logins  # noqa: E402

IDS = {"people": {"ana@example.com": {"name": "ana", "github": "Ana-GH", "roles": ["owner", "approver"]},
                  "eli@example.com": {"name": "eli", "roles": ["expert"]}}}


def test_a_request_is_checked_before_it_is_shown():
    ok = {"summary": "Freeze the binding", "steps": [{"freeze-binding": "experiments/m1/instruments"},
          {"run": {"member": "authoring", "action": "approve_commit", "target": "5-ab"}}]}
    assert hr.check(ok) == []
    assert hr.check({"summary": "", "steps": []}) == ["summary: say in one line what you approve",
                                                    "steps: a non-empty list"]
    assert "is not a step" in hr.check({"summary": "x", "steps": [{"shell": "rm -rf /"}]})[0]
    assert "run takes" in hr.check({"summary": "x", "steps": [{"run": {"member": "a", "action": "b"}}]})[0]
    assert "amend takes" in hr.check({"summary": "x", "steps": [{"amend": {"dir": "d", "file": "f"}}]})[0]
    assert hr.check({"summary": "x", "steps": [{"freeze": "d"}], "extra": 1})


def test_what_is_shown_is_what_runs():
    req = {"summary": "Approve commit 5", "steps": [
        {"freeze": "experiments/m1/instruments"},
        {"amend": {"dir": "experiments/m1/instruments", "file": "binding.yaml", "reason": "typo in seq 4"}},
        {"run": {"member": "delivery", "action": "verify", "target": "authoring:5-ab:local",
                 "params": {"verified": True}}}]}
    shown = hr.render(req)
    assert "Approve commit 5" in shown and "**freeze**" in shown and "typo in seq 4" in shown
    assert "`delivery`: **verify** `authoring:5-ab:local` --verified true" in shown
    cmds = hr.commands(req)
    assert cmds[0][-2:] == ["freeze", "experiments/m1/instruments"]
    assert cmds[1][-5:] == ["amend", "experiments/m1/instruments", "binding.yaml", "--reason", "typo in seq 4"]
    assert cmds[2][:2] == ["toprope-run", "--composition"] and "--identity" in cmds[2]
    assert cmds[2][cmds[2].index("--identity") + 1] == "github" and cmds[2][-4:] == ["verify", "authoring:5-ab:local",
                                                                                    "--verified", "true"]


def test_the_approver_is_the_person_and_only_inside_the_approval_job(tmp_path, monkeypatch):
    f = tmp_path / "ids.yaml"
    f.write_text(yaml.safe_dump(IDS))
    ident = GitHubApprovalIdentity(f)
    monkeypatch.setenv(ENV, "ana-gh")                                  # logins are case-insensitive
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert ident.resolve(None) is None and "only inside" in ident.explain()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    c = ident.resolve("any token")
    assert (c.actor.id, c.actor.kind) == ("ana <ana@example.com>", "person")
    monkeypatch.setenv(ENV, "mallory")
    assert ident.resolve(None) is None and "mallory" in ident.explain()
    IDS2 = {"people": {**IDS["people"], "bo@example.com": {"name": "bo", "github": "ana-gh", "roles": []}}}
    f.write_text(yaml.safe_dump(IDS2))
    with pytest.raises(ValueError, match="listed twice"):
        github_logins(f)


def test_the_repository_names_the_researchers_github_login():
    assert github_logins(ROOT / "toprope.identity.yaml")["steamshon"].actor.id == "steamshon <steamshon@apache.org>"


def test_an_approved_request_runs_its_steps_as_the_approver(tmp_path, monkeypatch):
    """The self domains, from a copy of the repository: a person-only action runs with no
    terminal, because the approval was the person's confirmation; an unlisted approver stops."""
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
    for name in filter(None, files):
        src, dst = ROOT / name.decode(), tmp_path / name.decode()
        if "/events/" in name.decode():
            continue                   # start from empty logs: the repository's own drafts are open
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
    (tmp_path / "toprope.identity.yaml").write_text(yaml.safe_dump(IDS))
    from toprope.workspace import Workspace
    ws = Workspace(tmp_path / "toprope.authoring.workspace.yaml")
    ref = next(c.ref for c in ws.chunks("records"))
    rule = {"id": "drafts-name-their-declaration", "on": "Draft", "check": "exists(target.declaration)",
            "reason": "A draft is the working copy of one declaration."}
    ws.propose(f"invariants.{rule['id']}", rule, ref)
    req = {"summary": "Open the draft and confirm what is proposed", "steps": [
        {"run": {"member": "authoring", "action": "open_draft", "target": "authoring",
                 "params": {"domain_id": "authoring", "declaration": "domains/authoring/authoring.domain.yaml",
                            "branch": "work"}}},
        {"run": {"member": "authoring", "action": "confirm_all_proposed", "target": "authoring"}}]}
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("PATH", str(ROOT / ".venv/bin") + os.pathsep + os.environ["PATH"])
    with pytest.raises(SystemExit, match="mallory approved, but is not a person"):
        hr.run(req, "mallory", cwd=tmp_path)
    done = hr.run(req, "ANA-GH", cwd=tmp_path)
    confirm = json.loads(done[1]["stdout"])
    assert confirm["status"] == "ok" and confirm["then"][0]["status"] == "ok"
    decl = yaml.safe_load((tmp_path / "domains/authoring/authoring.domain.yaml").read_text())
    (added,) = [i for i in decl["invariants"] if i["id"] == rule["id"]]
    assert added["status"] == "confirmed"
    entry = json.loads((tmp_path / "domains/authoring/interview.jsonl").read_text().splitlines()[-1])
    assert entry["who"] == "ana <ana@example.com>" and entry["via"] == "kernel"


def test_an_approved_request_freezes_instruments(tmp_path, monkeypatch):
    inst = tmp_path / "experiments/m1/instruments"
    inst.mkdir(parents=True)
    for f in (ROOT / "experiments/m1/instruments").glob("*.yaml"):
        if f.name != "binding.yaml":
            (inst / f.name).write_text(f.read_text())
    (tmp_path / "toprope.identity.yaml").write_text(yaml.safe_dump(IDS))
    hr.run({"summary": "Freeze", "steps": [{"freeze": "experiments/m1/instruments"}]}, "ana-gh", cwd=tmp_path)
    assert {"change-requests.yaml", "change-key.yaml"} <= set(json.loads((inst / "FROZEN.json").read_text())["files"])

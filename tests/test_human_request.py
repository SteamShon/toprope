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
          {"run": {"member": "authoring", "action": "check_commit", "target": "5-ab"}},
          {"run": {"member": "authoring", "action": "approve_commit", "target": "5-ab"}}]}
    assert hr.check(ok) == []
    unchecked = {"summary": "x", "steps": [ok["steps"][2], ok["steps"][1]]}   # checked only after
    (err,) = hr.check(unchecked)
    assert err.startswith("step 1: approve_commit 5-ab needs a check_commit step on it before")
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


def test_an_approval_does_not_run_without_tlc(tmp_path, monkeypatch):
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump(IDS))
    monkeypatch.delenv(hr.TLC_ENV, raising=False)
    req = {"summary": "x", "steps": [{"run": {"member": "authoring", "action": "check_commit", "target": "5-ab"}},
                                     {"run": {"member": "authoring", "action": "approve_commit", "target": "5-ab"}}]}
    with pytest.raises(SystemExit, match="approve_commit needs TLC"):
        hr.run(req, "ana-gh", identity="ids.yaml", cwd=tmp_path)


def test_the_approval_job_has_the_tla_job_s_pinned_tlc():
    import re
    act = (ROOT / ".github/workflows/human-request.yml").read_text()
    tla = (ROOT / ".github/workflows/tla.yml").read_text()
    pins = [re.findall(r"TLC_(?:VERSION|SHA256): (\S+)", f) for f in (act, tla)]
    assert pins[0] == pins[1] and len(pins[0]) == 2
    assert 'TOPROPE_TLC_JAR=$RUNNER_TEMP/tla2tools.jar' in act


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


def test_an_approved_run_is_recorded_so_a_commit_can_cite_it_after_any_merge(tmp_path):
    req = {"summary": "Approve commit 6", "steps": [{"run": {"member": "authoring", "action": "approve_commit",
                                                            "target": "6-ab"}}]}
    url = "https://github.com/o/r/actions/runs/7"
    hr.record(req, "Ana-GH", "ana <ana@example.com>", url, cwd=tmp_path)
    (row,) = [json.loads(x) for x in (tmp_path / hr.APPROVAL_RUNS).read_text().splitlines()]
    assert row["run"] == url and row["approver"] == "Ana-GH" and row["as"] == "ana <ana@example.com>"
    assert row["steps"] == req["steps"] and row["summary"] == "Approve commit 6"
    workflow = (ROOT / ".github/workflows/human-request.yml").read_text()
    assert "human_request.py record" in workflow.split("git rm")[0]          # recorded, then committed
    ignored = subprocess.run(["git", "check-ignore", "-q", hr.APPROVAL_RUNS], cwd=ROOT)
    assert ignored.returncode == 1, f"{hr.APPROVAL_RUNS} is git-ignored, so `git add -A` would drop it"


def test_a_request_can_freeze_the_run_protocol():
    req = {"summary": "Freeze the Phase B run protocol", "steps": [{"freeze-protocol": "experiments/m1/instruments"}]}
    assert hr.check(req) == []
    assert hr.commands(req)[0][-2:] == ["freeze-protocol", "experiments/m1/instruments"]


def test_a_run_step_can_name_the_workspace_of_the_draft_it_acts_on():
    # Confirming the Delivery declaration's draft is an Authoring action on Delivery's workspace.
    step = {"run": {"member": "authoring", "action": "confirm_all_proposed", "target": "delivery",
                    "workspace": "toprope.delivery.workspace.yaml"}}
    req = {"summary": "Confirm Delivery's draft", "steps": [step]}
    assert hr.check(req) == []
    cmd = hr.commands(req)[0]
    assert cmd[cmd.index("--workspace") + 1] == "toprope.delivery.workspace.yaml"
    assert "(workspace `toprope.delivery.workspace.yaml`)" in hr.render(req)
    bad = {"summary": "x", "steps": [{"run": {**step["run"], "workspace": "/etc/passwd"}}]}
    assert "run takes" in hr.check(bad)[0]

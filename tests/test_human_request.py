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


def test_a_step_whose_kernel_call_failed_fails_the_request(tmp_path, monkeypatch):
    """The action was accepted, so toprope-run exits 0, but the approval it set off was refused
    (no TLC check, ADR-0044): the request must not report success."""
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump(IDS))
    monkeypatch.setenv(hr.TLC_ENV, "tla2tools.jar")
    out = {"status": "ok", "then": [{"kernel": "approve_commit", "reply": "record_approval", "status": "failed",
                                     "error": "5-ab has no passing TLC check (never run with TLC)"}]}
    monkeypatch.setattr(hr.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps(out), ""))
    req = {"summary": "x", "steps": [{"run": {"member": "authoring", "action": "approve_commit", "target": "5-ab"}}]}
    with pytest.raises(SystemExit, match="approve_commit: failed .5-ab has no passing TLC check"):
        hr.run(req, "ana-gh", identity="ids.yaml", cwd=tmp_path)
    out["then"][0] |= {"status": "ok"}
    assert hr.run(req, "ana-gh", identity="ids.yaml", cwd=tmp_path)[0]["returncode"] == 0


def test_a_failed_step_whose_message_names_fixes_reports_one_fix(tmp_path, monkeypatch):
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump(IDS))
    err = "no chunk 'x'. Fix: run `search`.\nwarning: stale. Fix: run it again"
    monkeypatch.setattr(hr.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", err))
    req = {"summary": "x", "steps": [{"run": {"member": "authoring", "action": "next_questions", "target": "a"}}]}
    with pytest.raises(SystemExit) as e:
        hr.run(req, "ana-gh", identity="ids.yaml", cwd=tmp_path)
    assert str(e.value).count("Fix:") == 1, str(e.value)
    assert str(e.value).endswith("Fix: run `search`; then run it again; then fix what the step's message says, "
                                 "then push the request again for a new approval")


def test_one_request_takes_a_change_from_proposed_to_approved():
    req = hr.change("authoring")
    assert [(st["run"]["action"], st["run"]["target"]) for st in req["steps"]] == [
        ("confirm_all_proposed", "authoring"), ("commit_draft", "authoring"),
        ("check_commit", hr.MADE), ("approve_commit", hr.MADE)]
    assert hr.check(req) == []
    assert "**approve_commit** the commit made above" in hr.render(req)
    early = {"summary": "x", "steps": [req["steps"][2], *req["steps"]]}
    assert hr.check(early)[0].startswith("step 1: $commit names the commit a commit_draft step before it makes")
    stale = {"summary": "x", "steps": [*req["steps"][:3], req["steps"][1], req["steps"][3]]}
    assert any("step 5: approve_commit $commit needs a check_commit" in e for e in hr.check(stale))  # a newer commit


def low_risk(root, commit, level="low"):
    p = root / ".toprope/commits/authoring/checks.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps({"commit": commit, "check": "risk", "ok": True, "summary": level}) + "\n")


def test_one_approval_ships_only_a_commit_checked_low_risk(tmp_path, monkeypatch):
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump(IDS))
    monkeypatch.setenv(hr.TLC_ENV, "tla2tools.jar")
    cmds = []

    def run(cmd, **kw):
        cmds.append(cmd)
        then = [{"kernel": "commit", "reply": "record_commit", "status": "ok", "object": "7-c0ffee"}] \
            if cmd[-2] == "commit_draft" else []
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"status": "ok", "then": then}), "")
    monkeypatch.setattr(hr.subprocess, "run", run)
    low_risk(tmp_path, "7-c0ffee", "high: an invariant or outcome rule changed: invariant:x")
    req = hr.change("authoring")
    req["steps"].append({"run": {"member": "delivery", "action": "deploy", "target": "authoring:$commit:local"}})
    assert "One approval ships this change" in hr.render(req)
    with pytest.raises(SystemExit, match="7-c0ffee is not low risk .high.*Fix: read the preview"):
        hr.run(req, "ana-gh", identity="ids.yaml", cwd=tmp_path)
    assert [c[-2] for c in cmds] == ["confirm_all_proposed", "commit_draft", "check_commit", "approve_commit"]


def test_the_commit_a_step_made_is_the_target_of_the_next(tmp_path, monkeypatch):
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump(IDS))
    monkeypatch.setenv(hr.TLC_ENV, "tla2tools.jar")
    cmds = []

    def run(cmd, **kw):
        cmds.append(cmd)
        then = [{"kernel": "commit", "reply": "record_commit", "status": "ok", "object": "7-c0ffee"}] \
            if cmd[-2] == "commit_draft" else []
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"status": "ok", "then": then}), "")
    monkeypatch.setattr(hr.subprocess, "run", run)
    low_risk(tmp_path, "7-c0ffee")                      # what check_commit records (ADR-0050)
    req = hr.change("authoring")
    req["steps"].append({"run": {"member": "delivery", "action": "preview", "target": "authoring:$commit:local"}})
    assert hr.check(req) == [] and "`authoring:<the commit made above>:local`" in hr.render(req)
    done = hr.run(req, "ana-gh", identity="ids.yaml", cwd=tmp_path)
    assert [c[-2:] for c in cmds] == [["confirm_all_proposed", "authoring"], ["commit_draft", "authoring"],
                                      ["check_commit", "7-c0ffee"], ["approve_commit", "7-c0ffee"],
                                      ["preview", "authoring:7-c0ffee:local"]]   # another member, inside a target
    assert done[1]["commit"] == "7-c0ffee"


def test_change_writes_the_request(tmp_path):
    out = tmp_path / ".toprope/requests/c.yaml"
    hr.main(["change", str(out), "--draft", "delivery", "--workspace", "toprope.delivery.workspace.yaml"])
    req = hr.load(out)
    assert req["steps"][0]["run"] == {"member": "authoring", "workspace": "toprope.delivery.workspace.yaml",
                                      "action": "confirm_all_proposed", "target": "delivery"}


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
    nxt = hr.run({"summary": "Commit and check it", "steps": hr.change("authoring")["steps"][1:3]},
                 "ANA-GH", cwd=tmp_path)                                 # commit_draft, check_commit $commit
    made = nxt[0]["commit"]
    assert made and nxt[1]["step"]["run"]["target"] == hr.MADE
    assert json.loads(nxt[1]["stdout"])["then"][0]["kernel"] == "change_check"
    from toprope.commits import CommitStore
    assert "change-check" in CommitStore(tmp_path / ".toprope/commits").check_status("authoring", made)


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


def test_naming_the_commit_does_not_get_around_the_risk_gate(tmp_path, monkeypatch):
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump(IDS))
    monkeypatch.setenv(hr.TLC_ENV, "tla2tools.jar")
    monkeypatch.setattr(hr.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps({"status": "ok"}), ""))
    low_risk(tmp_path, "7-c0ffee", "low")
    low_risk(tmp_path, "7-c0ffee", "high: the harness check failed")       # the newest record wins
    req = {"summary": "s", "steps": [
        {"run": {"member": "authoring", "action": "check_commit", "target": "7-c0ffee"}},
        {"run": {"member": "authoring", "action": "approve_commit", "target": "7-c0ffee"}},
        {"run": {"member": "authoring", "action": "deliver", "target": "7-c0ffee", "params": {"environment": "local"}}}]}
    assert hr.check(req) == [] and "One approval ships this change" in hr.render(req)
    with pytest.raises(SystemExit, match="7-c0ffee is not low risk"):
        hr.run(req, "ana-gh", identity="ids.yaml", cwd=tmp_path)


def test_a_second_request_ships_an_approved_commit(tmp_path):
    out = tmp_path / "ship.yaml"
    hr.main(["ship", str(out), "--commit", "7-c0ffee"])
    req = hr.load(out)
    assert hr.check(req) == []
    assert [s["run"]["action"] for s in req["steps"]] == ["deliver", "preview", "deploy", "run_probes", "verify"]
    assert "One approval ships" not in hr.render(req)       # it approves nothing: the person read the preview

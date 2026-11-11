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
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump({
        "t-owen": {"id": ME, "roles": ["owner", "approver"]},
        "t-bot": {"id": "bot <bot@example.com>", "kind": "agent", "roles": ["owner"],   # an agent, drafting only
                  "on_behalf_of": {"id": ME, "roles": ["owner", "approver"]},
                  "grant": {"id": "drafting", "actions": ["propose_element", "add_source", "next_questions"]}}}))
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


def test_an_agent_proposes_checks_and_writes_one_request_and_no_commit(repo, capsys, monkeypatch):
    from toprope.commits import CommitStore
    before = len(CommitStore(repo / ".toprope/commits").log("authoring"))
    monkeypatch.setenv("TOPROPE_TOKEN", "t-bot")                       # the agent, with its drafting grant
    p = patch(repo, [{"path": f"invariants.{RULE['id']}", "value": RULE, "origin": "S-adr",
                      "cites": a_ref(repo)}])
    main(["Drafts name their declaration", "--patch", p, "--run-args", "--identity static:ids.yaml"])
    assert len(CommitStore(repo / ".toprope/commits").log("authoring")) == before   # checked on a scratch copy
    out = capsys.readouterr().out
    result = json.loads(out[out.index("{\n"):])
    assert result["proposed"] == [f"invariants.{RULE['id']}"]
    assert f"+ invariants.{RULE['id']}" in out                         # the diff the person will confirm
    req = hr.load(repo / result["request"])
    assert hr.check(req) == []                                         # a request the workflow accepts
    assert [s["run"]["action"] for s in req["steps"]] == [
        "confirm_all_proposed", "commit_draft", "check_commit", "approve_commit"]
    assert req["summary"] == "[high risk: approval only] Drafts name their declaration"   # a new invariant
    assert result["risk"] == "high" and any("invariant" in r for r in result["risk_reasons"])
    assert req["risk"] == {"level": "high", "reasons": result["risk_reasons"]}   # shown before approving
    shown = hr.render(req)
    assert "**Risk written in the request: high**: " in shown and "not the kernel's record" in shown
    assert "in GitHub" in result["next"] and f"toprope-apply {result['request']}" in result["next"]   # both routes
    assert f"toprope-apply --ship {result['request']}" in result["then"]
    decl = yaml.safe_load((repo / "domains/authoring/authoring.domain.yaml").read_text())
    (added,) = [i for i in decl["invariants"] if i["id"] == RULE["id"]]
    assert added["status"] == "proposed"                               # nothing is confirmed by the agent


def test_a_check_that_finds_a_problem_stops_before_any_request(repo, capsys):
    broken = {"id": "drafts-are-never-open", "on": "Draft", "check": "target.stage != 'open'",
              "reason": "Never open."}                                  # valid, and false of every new draft
    p = patch(repo, [{"path": f"invariants.{broken['id']}", "value": broken, "origin": "S-adr",
                      "cites": a_ref(repo)}])
    with pytest.raises(SystemExit) as e:
        main(["A rule nothing can satisfy", "--patch", p, "--run-args", "--identity static:ids.yaml"])
    msg = str(e.value)
    assert "the change check found problems" in msg and "Fix: fix the proposals" in msg
    assert f"invariants.{broken['id']}" in msg                          # what was left in the draft
    assert not (repo / ".toprope/requests").exists() or not list((repo / ".toprope/requests").glob("*.yaml"))


def test_a_request_waiting_to_be_pushed_stops_a_second_one(repo, capsys):
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".toprope/requests").mkdir(parents=True, exist_ok=True)
    (repo / ".toprope/requests/first.yaml").write_text("summary: x\nsteps: []\n")
    p = patch(repo, [{"path": f"invariants.{RULE['id']}", "value": RULE, "origin": "S-adr", "cites": a_ref(repo)}])
    with pytest.raises(SystemExit, match="a request is already waiting to be pushed"):
        main(["x", "--patch", p, "--run-args", "--identity static:ids.yaml"])


def test_a_refused_proposal_stops_before_any_request(repo, capsys):
    bad = {**RULE, "check": "target.no_such_property == 1"}
    p = patch(repo, [{"path": f"invariants.{RULE['id']}", "value": bad, "origin": "S-adr",
                      "cites": a_ref(repo)}])
    with pytest.raises(SystemExit) as e:
        main(["A broken rule", "--patch", p, "--run-args", "--identity static:ids.yaml"])
    assert "Fix:" in str(e.value)
    assert not (repo / ".toprope/requests").exists() or not list((repo / ".toprope/requests").glob("a-broken*"))


def test_a_refused_citation_names_one_fix_the_steps_first(repo):
    p = patch(repo, [{"path": f"invariants.{RULE['id']}", "value": RULE, "origin": "S-adr",
                      "cites": "no-such-source:1"}])
    with pytest.raises(SystemExit) as e:
        main(["A rule", "--patch", p, "--run-args", "--identity static:ids.yaml"])
    msg = str(e.value)
    assert msg.count("Fix:") == 1, msg
    assert "Fix: cite a ref of the form `<source>:<chunk>`" in msg and "; then run the change again" in msg


def test_a_patch_without_what_it_cites_is_refused_with_the_fix(tmp_path):
    p = patch(tmp_path, [{"path": "objects.X", "value": {}}])
    with pytest.raises(SystemExit, match="element 1 of the patch has no cites. Fix: give each element"):
        read_patch(p)


def test_the_request_has_the_four_steps_a_change_takes():
    assert request_for("x", "authoring", "authoring", None) == hr.change("authoring", summary="x")
    assert len(request_for("x", "authoring", "authoring", None, risk="high")["steps"]) == 4


def test_a_low_risk_change_ships_on_the_same_request():
    req = request_for("Reword a description", "authoring", "authoring", None, risk="low")
    assert hr.check(req) == [] and req["summary"].startswith("[low risk: one approval ships it]")
    assert [(s["run"]["member"], s["run"]["action"]) for s in req["steps"]][4:] == [
        ("authoring", "deliver"), ("delivery", "preview"), ("delivery", "deploy"), ("delivery", "run_probes"),
        ("delivery", "verify")]
    assert req["steps"][5]["run"]["target"] == "authoring:$commit:local"

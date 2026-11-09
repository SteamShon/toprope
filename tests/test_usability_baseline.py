"""F1, friction in the self domains' change loop, measured from their logs (ADR-0049)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import usability_baseline as ub  # noqa: E402

PERSON = "ana <ana@example.com>"
AGENT = "bot <bot@example.com>"


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def event(type_, actor_id=None, kind=None):
    actor = {"id": actor_id, "kind": kind} if actor_id else None
    return {"event": json.dumps({"type": type_, "actor": actor}), "stream": "s"}


def command(actor_id, action, status="ok", code=None, finished=True):
    key = json.dumps([actor_id, action, "t", f"{actor_id}{action}{status}"])
    rows = [{"key": key, "state": "pending"}]
    if finished:
        rows.append({"key": key, "state": json.dumps({"status": status, "code": code})})
    return rows


def domain(root, name, commands, events, commits, approved, checks=()):
    ev = root / "domains" / name / "events"
    write(ev / "idempotency.jsonl", [r for c in commands for r in c])
    write(ev / "events.jsonl", events)
    store = root / ".toprope" / "commits" / name
    write(store / "log.jsonl", [{"id": c} for c in commits])
    write(store / "approvals.jsonl", [{"commit": c} for c in approved])
    write(store / "checks.jsonl", list(checks))


def test_commands_are_counted_by_who_took_them_and_refusals_by_code(tmp_path):
    domain(tmp_path, "authoring",
           [command(PERSON, "approve_commit"), command(AGENT, "propose_element"),
            command(AGENT, "propose_element", "rejected", "invariant-guard"),
            command("external:kernel", "record_commit")],
           [event("X", PERSON, "person"), event("Y", AGENT, "agent")],
           ["1-a"], ["1-a"])
    d = ub.measure(tmp_path)["domains"]["authoring"]
    assert d["commands"] == 4
    assert d["commands_by_actor"] == {"person": 1, "agent": 2, "system": 1}
    assert d["refused"] == 1 and d["refused_codes"] == {"propose_element:invariant-guard": 1}
    assert d["per_approved_commit"] == {"commands_by_person_or_agent": 3.0, "commands_by_person": 1.0}


def test_a_skipped_check_is_not_a_failure_and_unapproved_commits_are_counted(tmp_path):
    domain(tmp_path, "delivery", [command(PERSON, "deploy")], [event("X", PERSON, "person")],
           ["1-a", "2-b", "3-c"], ["1-a"],
           checks=[{"commit": "1-a", "ok": False, "summary": "skipped: no event store"},
                   {"commit": "2-b", "ok": False, "summary": "1 error(s)"},
                   {"commit": "3-c", "ok": True, "summary": "0 error(s)"}])
    d = ub.measure(tmp_path)["domains"]["delivery"]
    assert d["commits_with_a_failed_check"] == 1
    assert d["commits_never_approved"] == 2


def test_failed_effects_and_unfinished_commands_count_as_friction(tmp_path):
    domain(tmp_path, "authoring",
           [command(PERSON, "deliver"), command(PERSON, "approve_commit", finished=False)],
           [event("X", PERSON, "person"), event("EffectFailed")], [], [])
    m = ub.measure(tmp_path)
    d = m["domains"]["authoring"]
    assert d["effects_failed"] == 1 and d["commands_unfinished"] == 1
    assert m["refused_or_failed_per_command"] == 1.0


def test_a_change_is_counted_across_the_domain_it_is_made_in_and_the_one_that_ships_it(tmp_path):
    domain(tmp_path, "authoring", [command(AGENT, "propose_element"), command(PERSON, "approve_commit")],
           [event("X", PERSON, "person"), event("Y", AGENT, "agent")], ["1-a"], ["1-a"])
    domain(tmp_path, "delivery", [command(PERSON, "deploy"), command(PERSON, "verify")],
           [event("X", PERSON, "person")], [], [])
    m = ub.measure(tmp_path)
    assert m["per_approved_commit"] == {"commands_by_person_or_agent": 4.0, "commands_by_person": 3.0}


def test_the_repository_baseline_runs_and_renders():
    m = ub.measure(ROOT)
    assert {"authoring", "delivery"} <= set(m["domains"])
    assert "kernel commands" in ub.render(m)

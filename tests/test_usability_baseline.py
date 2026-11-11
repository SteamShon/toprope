"""F1, friction in the self domains' change loop, measured from their logs (ADR-0049)."""
import json

import pytest
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
    m = ub.measure(tmp_path)
    assert m["per_approved_change"] == {"commands_by_person_or_agent": 3.0, "commands_by_person": 1.0}
    assert m["refused_or_failed_per_command"] == round(1 / 3, 3)     # the kernel's reply is left out


def test_a_skipped_or_unconfirmed_check_is_not_a_failure_and_unapproved_commits_are_counted(tmp_path):
    domain(tmp_path, "delivery", [command(PERSON, "deploy")], [event("X", PERSON, "person")],
           ["1-a", "2-b", "3-c"], ["1-a"],
           checks=[{"commit": "1-a", "check": "log_replay", "ok": False, "summary": "skipped: no event store"},
                   {"commit": "1-a", "check": "confirmed", "ok": False, "summary": "2 proposed element(s)"},
                   {"commit": "2-b", "check": "scenarios", "ok": False, "summary": "1 error(s)"},
                   {"commit": "3-c", "check": "structural", "ok": True, "summary": "0 error(s)"}])
    d = ub.measure(tmp_path)["domains"]["delivery"]
    assert d["commits_with_a_failed_check"] == 1
    assert d["commits_never_approved"] == 2


def test_failed_effects_count_as_friction_and_unfinished_commands_are_reported(tmp_path):
    domain(tmp_path, "authoring",
           [command(PERSON, "deliver"), command(PERSON, "approve_commit", finished=False)],
           [event("X", PERSON, "person"), event("EffectFailed")], [], [])
    m = ub.measure(tmp_path)
    d = m["domains"]["authoring"]
    assert d["effects_failed"] == 1 and d["commands_unfinished"] == 1
    assert m["refused_or_failed_per_command"] == 1.0


def test_a_change_is_counted_across_the_domain_it_is_made_in_and_the_one_that_ships_it(tmp_path):
    # Commit 0-z was approved before the command log begins: it is outside the window.
    domain(tmp_path, "authoring", [command(AGENT, "propose_element"), command(PERSON, "approve_commit")],
           [event("X", PERSON, "person"), event("Y", AGENT, "agent")], ["0-z", "1-a"], ["0-z", "1-a"])
    domain(tmp_path, "delivery", [command(PERSON, "deploy"), command(PERSON, "verify")],
           [event("X", PERSON, "person")], [], [])
    m = ub.measure(tmp_path)
    assert m["approvals_in_window"] == 1
    assert m["per_approved_change"] == {"commands_by_person_or_agent": 4.0, "commands_by_person": 3.0}


def test_the_repository_baseline_runs_and_renders():
    m = ub.measure(ROOT)
    assert {"authoring", "delivery"} <= set(m["domains"])
    assert "kernel commands" in ub.render(m)


def test_an_actor_not_seen_in_the_events_is_kept_apart(tmp_path):
    domain(tmp_path, "authoring", [command("ghost <g@example.com>", "search")], [], [], [])
    m = ub.measure(tmp_path)
    assert m["domains"]["authoring"]["commands_by_actor"] == {"unknown": 1}
    assert m["commands_by_person_agent_unknown"] == [0, 0, 1]


def test_failures_before_the_gate_are_counted_per_change_approved_since_the_first(tmp_path):
    domain(tmp_path, "authoring", [command(PERSON, "approve_commit")], [event("X", PERSON, "person")],
           ["1-a", "2-b"], [])
    write(tmp_path / ".toprope/commits/authoring/approvals.jsonl",
          [{"commit": "1-a", "at": "2026-11-01T00:00:00+00:00"},      # before any failure was recorded
           {"commit": "2-b", "at": "2026-11-10T00:00:00+00:00"}])
    f = tmp_path / ".toprope/failures"
    f.mkdir(parents=True)
    (f / "a.json").write_text(json.dumps({"at": "2026-11-09T00:00:00+00:00", "kind": "usage", "has_fix": False}))
    (f / "b.json").write_text(json.dumps({"at": "2026-11-09T01:00:00+00:00", "kind": "refused", "has_fix": True}))
    (f / "c.json").write_text("{not json")
    m = ub.measure(tmp_path)
    assert m["failed_before_the_gate"] == {"usage": 1, "refused": 1}
    assert m["failed_before_the_gate_without_a_fix"] == 1 and m["failed_before_the_gate_unreadable"] == 1
    assert m["failed_before_the_gate_since"] == "2026-11-09T00:00:00+00:00"
    assert m["failed_before_the_gate_per_change_approved_since"] == 2.0
    assert m["refused_or_failed_per_command"] == 0.0        # the first rate is unchanged by them


# The measures ADR-0049 (5) and ADR-0050 name: a person's touches, approvals by risk, a window,
# and refusals per command with failures before the gate apart.

def timed(actor_id, action, target, at, status="ok", code=None):
    """A finished command whose outcome carries the time of its events, as the kernel writes it."""
    key = json.dumps([actor_id, action, target, f"{action}-{target}-{at}"])
    events = [{"at": {"$dt": at}}] if status == "ok" else []
    return [{"key": key, "state": "pending"},
            {"key": key, "state": json.dumps({"status": status, "code": code, "events": events})}]


def approval_run(at, steps, person=PERSON):
    return {"run": f"https://example.com/runs/{at}", "approver": "ana", "as": person, "at": at,
            "summary": "s", "steps": [{"run": s} for s in steps]}


def step(member, action, target, **params):
    return {"member": member, "action": action, "target": target, **({"params": params} if params else {})}


def risk(commit, level, at="2026-11-10T00:00:00+00:00"):
    return {"at": at, "check": "risk", "commit": commit, "ok": level == "low", "summary": f"{level}: reasons"}


def one_approval_run(commit, at, minute="10"):
    """C1's one-approval request for a low-risk change, shipped in the same run: nine steps."""
    t = f"authoring:{commit}:local"
    steps = [step("authoring", "confirm_all_proposed", "authoring"), step("authoring", "commit_draft", "authoring"),
             step("authoring", "check_commit", "$commit"), step("authoring", "approve_commit", "$commit"),
             step("authoring", "deliver", "$commit", environment="local"),
             *(step("delivery", a, "authoring:$commit:local") for a in ("preview", "deploy", "run_probes", "verify"))]
    targets = ["authoring", "authoring", commit, commit, commit, t, t, t, t]
    cmds = [timed(PERSON, s["action"], tg, f"2026-11-10T{minute}:00:0{i}+00:00")
            for i, (s, tg) in enumerate(zip(steps, targets))]
    cmds.insert(2, made(commit, f"2026-11-10T{minute}:00:01.5+00:00"))
    return steps, cmds


def made(commit, at):
    """The kernel's reply to a commit_draft: the commit it made (a `record_commit` by `external:`)."""
    return timed("external:kernel", "record_commit", commit, at)


def test_a_request_run_of_nine_steps_by_a_person_is_one_touch_and_one_approval(tmp_path):
    steps, cmds = one_approval_run("2-b", "2026-11-10T10:00:30+00:00")
    domain(tmp_path, "authoring",
           [timed(PERSON, "search", "docs", "2026-11-10T09:00:00+00:00"),     # typed by the person
            timed(AGENT, "propose_element", "authoring", "2026-11-10T09:30:00+00:00"), *cmds[:6]],
           [event("X", PERSON, "person"), event("Y", AGENT, "agent")], ["2-b"], ["2-b"],
           checks=[risk("2-b", "low")])
    domain(tmp_path, "delivery", cmds[6:], [event("X", PERSON, "person")], [], [])
    write(tmp_path / ".toprope/approval-runs.jsonl", [approval_run("2026-11-10T10:00:30+00:00", steps)])
    m = ub.measure(tmp_path)
    assert m["per_approved_change"]["commands_by_person"] == 10.0          # unchanged: kernel steps
    assert m["person_touches"]["per_approved_change"] == 2.0               # the approval and the search
    assert m["person_touches"]["approvals_of_human_requests"] == 1
    assert m["person_touches"]["commands_outside_an_approved_request"] == 1
    assert m["person_touches"]["request_steps_not_found"] == 0
    assert m["approvals_per_approved_change_by_risk"] == {"low": {"changes": 1, "approvals": 1, "per_change": 1.0}}


def test_approvals_per_approved_change_are_split_by_risk(tmp_path):
    low_steps, low_cmds = one_approval_run("2-b", "2026-11-10T10:00:30+00:00", "10")
    # A high-risk change: approved in one request, shipped in a second after its preview was read.
    approve = [step("authoring", "confirm_all_proposed", "authoring"), step("authoring", "commit_draft", "authoring"),
               step("authoring", "check_commit", "$commit"), step("authoring", "approve_commit", "$commit")]
    t = "authoring:3-c:local"
    ship = [step("authoring", "deliver", "3-c", environment="local"),
            *(step("delivery", a, t) for a in ("preview", "deploy", "run_probes", "verify"))]
    high_auth = [timed(PERSON, a, tg, f"2026-11-10T11:00:0{i}+00:00") for i, (a, tg) in enumerate(
        [("confirm_all_proposed", "authoring"), ("commit_draft", "authoring"), ("check_commit", "3-c"),
         ("approve_commit", "3-c")])]
    high_auth.insert(2, made("3-c", "2026-11-10T11:00:01.5+00:00"))
    deliver = timed(PERSON, "deliver", "3-c", "2026-11-10T12:00:00+00:00")
    high_del = [timed(PERSON, a, t, f"2026-11-10T12:00:0{i + 1}+00:00")
                for i, a in enumerate(("preview", "deploy", "run_probes", "verify"))]
    domain(tmp_path, "authoring", [*low_cmds[:6], *high_auth, deliver],
           [event("X", PERSON, "person")], ["2-b", "3-c"], ["2-b", "3-c"],
           checks=[risk("2-b", "low"), risk("3-c", "high")])
    domain(tmp_path, "delivery", [*low_cmds[6:], *high_del], [event("X", PERSON, "person")], [], [])
    write(tmp_path / ".toprope/approval-runs.jsonl",
          [approval_run("2026-11-10T10:00:30+00:00", low_steps),
           approval_run("2026-11-10T11:00:30+00:00", approve),
           approval_run("2026-11-10T12:00:30+00:00", ship)])
    m = ub.measure(tmp_path)
    assert m["approvals_per_approved_change_by_risk"] == {
        "low": {"changes": 1, "approvals": 1, "per_change": 1.0},
        "high": {"changes": 1, "approvals": 2, "per_change": 2.0}}
    assert m["person_touches"] == {"approvals_of_human_requests": 3, "commands_outside_an_approved_request": 0,
                                   "request_steps_not_found": 0, "approval_runs_without_a_change_step": 0,
                                   "possibly_failed_request_steps": 0, "per_approved_change": 1.5}


def test_an_approval_typed_outside_a_request_counts_once_and_a_change_unchecked_for_risk_is_unknown(tmp_path):
    domain(tmp_path, "authoring", [timed(PERSON, "approve_commit", "1-a", "2026-11-06T10:00:00+00:00")],
           [event("X", PERSON, "person")], ["1-a"], ["1-a"])
    write(tmp_path / ".toprope/approval-runs.jsonl",
          [{"run": "r", "approver": "ana", "as": PERSON, "at": "2026-11-06T11:00:00+00:00", "summary": "freeze",
            "steps": [{"freeze-protocol": "experiments/m1/instruments"}]}])
    m = ub.measure(tmp_path)
    assert m["approvals_per_approved_change_by_risk"] == {"unknown": {"changes": 1, "approvals": 1, "per_change": 1.0}}
    assert m["person_touches"]["approval_runs_without_a_change_step"] == 1      # not a change: kept apart
    assert m["person_touches"]["per_approved_change"] == 1.0


def test_since_and_until_bound_every_measure(tmp_path, capsys):
    domain(tmp_path, "authoring",
           [timed(PERSON, "approve_commit", "1-a", "2026-11-06T10:00:00+00:00"),         # before
            timed(AGENT, "propose_element", "authoring", "2026-11-06T10:01:00+00:00",
                  "rejected", "invariant-guard"),                                       # before, no events
            timed(PERSON, "approve_commit", "2-b", "2026-11-10T10:00:00+00:00"),
            timed(AGENT, "propose_element", "authoring", "2026-11-10T10:01:00+00:00"),
            timed(PERSON, "approve_commit", "3-c", "2026-11-12T10:00:00+00:00")],        # after
           [event("X", PERSON, "person"), event("Y", AGENT, "agent"),
            {"event": json.dumps({"type": "EffectFailed", "actor": None,
                                  "at": {"$dt": "2026-11-06T10:02:00+00:00"}}), "stream": "s"}],
           ["1-a", "2-b", "3-c"], [])
    write(tmp_path / ".toprope/commits/authoring/log.jsonl",
          [{"id": c, "at": at} for c, at in (("1-a", "2026-11-06T09:00:00+00:00"),
                                            ("2-b", "2026-11-10T09:00:00+00:00"),
                                            ("3-c", "2026-11-12T09:00:00+00:00"))])
    write(tmp_path / ".toprope/approval-runs.jsonl",
          [approval_run("2026-11-06T11:00:00+00:00", [step("authoring", "approve_commit", "9-z")])])
    f = tmp_path / ".toprope/failures"
    f.mkdir(parents=True)
    (f / "a.json").write_text(json.dumps({"at": "2026-11-06T00:00:00+00:00", "kind": "usage", "has_fix": True}))
    whole = ub.measure(tmp_path)
    assert whole["approvals_in_window"] == 3 and whole["domains"]["authoring"]["refused"] == 1
    m = ub.measure(tmp_path, since="2026-11-10", until="2026-11-11")
    d = m["domains"]["authoring"]
    assert m["window"] == {"since": "2026-11-10T00:00:00+00:00", "until": "2026-11-11T00:00:00+00:00"}
    assert m["approvals_in_window"] == 1 and d["commands"] == 2
    assert d["refused"] == 0 and d["effects_failed"] == 0 and d["commits"] == 1
    assert m["approval_runs"] == 0 and m["failed_before_the_gate"] == {}
    assert ub.main(["--root", str(tmp_path), "--since", "2026-11-10", "--until", "2026-11-11", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["approvals_in_window"] == 1


def test_a_date_that_does_not_parse_names_its_fix(tmp_path, capsys):
    import pytest
    with pytest.raises(SystemExit):
        ub.main(["--root", str(tmp_path), "--since", "last tuesday"])
    assert "Fix: " in capsys.readouterr().err


def test_refusals_are_per_command_and_failures_before_the_gate_per_command_attempted(tmp_path):
    domain(tmp_path, "authoring",
           [timed(PERSON, "approve_commit", "1-a", "2026-11-10T10:00:00+00:00"),
            timed(AGENT, "propose_element", "authoring", "2026-11-10T10:01:00+00:00"),
            timed(AGENT, "propose_element", "authoring", "2026-11-10T10:02:00+00:00", "rejected", "invariant-guard"),
            timed(PERSON, "deliver", "1-a", "2026-11-10T10:03:00+00:00")],
           [event("X", PERSON, "person"), event("Y", AGENT, "agent"), event("EffectFailed")], ["1-a"], ["1-a"])
    f = tmp_path / ".toprope/failures"
    f.mkdir(parents=True)
    for i in range(2):
        (f / f"{i}.json").write_text(json.dumps({"at": f"2026-11-10T10:0{i}:30+00:00", "kind": "usage",
                                                 "has_fix": True}))
    m = ub.measure(tmp_path)
    assert m["refused_or_failed_per_command"] == 0.5                       # (1 refusal + 1 effect) / 4
    assert m["refusals_per_command"] == {
        "commands": 4, "refused": 1, "effects_failed": 1, "refused_or_failed": 0.5,
        "failed_before_the_gate": 2, "failed_before_the_gate_per_command_attempted": round(2 / 6, 3)}
    # Failures before the gate are reported beside the rate, never inside it: the baseline has none.


# From the review of #237.

def test_a_window_edge_inside_a_request_run_neither_splits_it_nor_counts_its_steps_as_typed(tmp_path):
    steps, cmds = one_approval_run("2-b", "2026-11-10T10:00:30+00:00")
    domain(tmp_path, "authoring", cmds[:6], [event("X", PERSON, "person")], ["2-b"], ["2-b"],
           checks=[risk("2-b", "low", "2026-11-10T09:00:00+00:00")])
    domain(tmp_path, "delivery", cmds[6:], [event("X", PERSON, "person")], [], [])
    write(tmp_path / ".toprope/approval-runs.jsonl", [approval_run("2026-11-10T10:00:30+00:00", steps)])
    # --until after the approval, before the run was recorded: the run and its change are inside.
    m = ub.measure(tmp_path, until="2026-11-10T10:00:03.5+00:00")
    assert m["approvals_in_window"] == 1
    assert m["person_touches"]["approvals_of_human_requests"] == 1
    assert m["person_touches"]["commands_outside_an_approved_request"] == 0
    assert m["approvals_per_approved_change_by_risk"] == {"low": {"changes": 1, "approvals": 1, "per_change": 1.0}}
    # --since after the approval: the rest of the run is not counted as typed by the person.
    m = ub.measure(tmp_path, since="2026-11-10T10:00:03.5+00:00")
    assert m["approvals_in_window"] == 0
    assert m["person_touches"]["approvals_of_human_requests"] == 0
    assert m["person_touches"]["commands_outside_an_approved_request"] == 0


def test_the_risk_is_the_one_recorded_before_the_approval_not_a_later_one(tmp_path):
    domain(tmp_path, "authoring", [timed(PERSON, "approve_commit", "1-a", "2026-11-10T10:00:00+00:00")],
           [event("X", PERSON, "person")], ["1-a"], ["1-a"],
           checks=[risk("1-a", "low", "2026-11-10T09:00:00+00:00"),
                   risk("1-a", "high", "2026-11-10T11:00:00+00:00")])     # checked again after it
    m = ub.measure(tmp_path)
    assert set(m["approvals_per_approved_change_by_risk"]) == {"low"}


def test_steps_of_a_run_that_failed_unrecorded_are_reported_and_a_failed_run_record_matches_what_ran(tmp_path):
    steps, cmds = one_approval_run("2-b", "2026-11-10T10:00:30+00:00")
    failed_try = [timed(PERSON, "confirm_all_proposed", "authoring", "2026-11-10T09:30:00+00:00"),
                  timed(PERSON, "commit_draft", "authoring", "2026-11-10T09:30:01+00:00")]
    domain(tmp_path, "authoring", [*failed_try, *cmds[:6]], [event("X", PERSON, "person")], ["2-b"], ["2-b"])
    domain(tmp_path, "delivery", cmds[6:], [event("X", PERSON, "person")], [], [])
    write(tmp_path / ".toprope/approval-runs.jsonl", [approval_run("2026-11-10T10:00:30+00:00", steps)])
    t = ub.measure(tmp_path)["person_touches"]
    assert t["commands_outside_an_approved_request"] == 2 and t["possibly_failed_request_steps"] == 2

    # A failed run recorded with how far it got (fix/request-keeps-work): it is one approval, and
    # only the steps that ran are looked for.
    run = approval_run("2026-11-10T10:00:30+00:00", steps) | {"ran": 4, "failed": {"step": 5, "error": "x"}}
    domain(tmp_path, "authoring", cmds[:5], [event("X", PERSON, "person")], ["2-b"], ["2-b"])
    domain(tmp_path, "delivery", [], [event("X", PERSON, "person")], [], [])
    write(tmp_path / ".toprope/approval-runs.jsonl", [run])
    t = ub.measure(tmp_path)["person_touches"]
    assert t["approvals_of_human_requests"] == 1 and t["request_steps_not_found"] == 0
    assert t["commands_outside_an_approved_request"] == 0


def test_commit_in_a_request_is_the_commit_its_commit_draft_made(tmp_path):
    steps = [step("authoring", "commit_draft", "authoring"), step("authoring", "check_commit", "$commit"),
             step("authoring", "approve_commit", "$commit")]
    cmds = [timed(PERSON, "commit_draft", "authoring", "2026-11-10T10:00:00+00:00"),
            made("3-c", "2026-11-10T10:00:00.5+00:00"),
            timed(PERSON, "check_commit", "3-c", "2026-11-10T10:00:01+00:00"),
            timed(PERSON, "approve_commit", "3-c", "2026-11-10T10:00:02+00:00"),
            timed(PERSON, "approve_commit", "2-b", "2026-11-10T10:00:10+00:00")]   # typed, another commit
    domain(tmp_path, "authoring", cmds, [event("X", PERSON, "person")], ["2-b", "3-c"], ["2-b", "3-c"])
    run = approval_run("2026-11-10T10:00:30+00:00", steps)
    commands = ub._commands(tmp_path, "authoring")[0]
    [(_, took, missing)] = ub._match_runs([run], commands)
    assert missing == 0 and [(c["action"], c["target"]) for c in took] == [
        ("commit_draft", "authoring"), ("check_commit", "3-c"), ("approve_commit", "3-c")]


def test_a_refusal_before_any_timed_command_has_no_time(tmp_path):
    domain(tmp_path, "authoring",
           [timed(AGENT, "propose_element", "authoring", "x", "rejected", "invariant-guard"),
            timed(PERSON, "approve_commit", "1-a", "2026-11-10T10:00:00+00:00")],
           [event("X", PERSON, "person"), event("Y", AGENT, "agent")], ["1-a"], ["1-a"])
    assert ub.measure(tmp_path)["domains"]["authoring"]["refused"] == 1          # no window: counted
    assert ub.measure(tmp_path, since="2026-11-10")["domains"]["authoring"]["refused"] == 0


def test_a_thousand_changes_are_measured_in_seconds(tmp_path):
    import time
    auth, deliv, runs = [], [], []
    for n in range(1000):
        h, mi = divmod(n, 60)
        steps, cmds = one_approval_run(f"{n}-x", "")
        at = f"2026-11-{10 + h // 24:02d}T{h % 24:02d}:{mi:02d}:30+00:00"
        cmds = [[{k: v.replace("2026-11-10T10:00", at[:16]) for k, v in r.items()} for r in c] for c in cmds]
        auth += cmds[:6]
        deliv += cmds[6:]
        runs.append(approval_run(at, steps))
    domain(tmp_path, "authoring", auth, [event("X", PERSON, "person")], [], [])
    domain(tmp_path, "delivery", deliv, [event("X", PERSON, "person")], [], [])
    write(tmp_path / ".toprope/approval-runs.jsonl", runs)
    start = time.monotonic()
    m = ub.measure(tmp_path)
    assert m["person_touches"]["approvals_of_human_requests"] == 1000
    assert m["person_touches"]["request_steps_not_found"] == 0
    assert time.monotonic() - start < 5


def test_a_malformed_log_line_names_the_file_the_line_and_the_fix(tmp_path):
    import pytest
    domain(tmp_path, "authoring", [timed(PERSON, "approve_commit", "1-a", "2026-11-10T10:00:00+00:00")],
           [event("X", PERSON, "person")], [], [])
    log = tmp_path / "domains/authoring/events/idempotency.jsonl"
    log.write_text(log.read_text() + "{not json\n")
    with pytest.raises(SystemExit) as e:
        ub.measure(tmp_path)
    assert "idempotency.jsonl:3" in str(e.value.code) and "Fix: " in str(e.value.code)


def test_f1_reads_a_failed_run_as_human_request_py_records_it(tmp_path):
    """The record's `ran` is the first steps of its `steps`, counting a step whose action was taken
    but whose follow-up failed; a rest keeps its own `steps` (resolved targets), and `failed.step`
    is the position there, while `failed.number` is the first request's number."""
    import human_request as hr
    req = {"summary": "s", "steps": [{"run": s} for s in one_approval_run("2-b", "x")[0]]}
    # The commit was made, but a handoff it set off failed: `run` reports two steps as run.
    accepted = {"steps": 2, "failed": {"step": 2, "number": 2, "error": "handoff", "accepted": True},
                "rest": hr.rest(req, 3, "2-b")}
    row = hr.record(req, "ana", PERSON, "https://example.com/runs/1", cwd=tmp_path, outcome=accepted)
    cmds = [timed(PERSON, "confirm_all_proposed", "authoring", "2026-11-10T10:00:00+00:00"),
            timed(PERSON, "commit_draft", "authoring", "2026-11-10T10:00:01+00:00"),
            made("2-b", "2026-11-10T10:00:01.5+00:00")]
    domain(tmp_path, "authoring", cmds, [event("X", PERSON, "person")], ["2-b"], [])
    write(tmp_path / ".toprope/approval-runs.jsonl", [row | {"at": "2026-11-10T10:00:30+00:00"}])
    t = ub.measure(tmp_path)["person_touches"]
    assert (t["request_steps_not_found"], t["commands_outside_an_approved_request"]) == (0, 0)

    # Its rest (steps 3-9) ran check, approve and deliver, then preview (the first request's step 6)
    # was refused: the record names position 4 there, number 6, and three steps that ran.
    rest = accepted["rest"]
    assert hr.numbering(rest)[1] == [3, 4, 5, 6, 7, 8, 9]
    failed = {"steps": 3, "failed": {"step": 4, "number": 6, "error": "refused"}, "rest": hr.rest(rest, 4, "2-b")}
    row2 = hr.record(rest, "ana", PERSON, "https://example.com/runs/2", cwd=tmp_path, outcome=failed)
    assert row2["ran"] == 3 and row2["steps"] == rest["steps"]
    cmds2 = [timed(PERSON, "check_commit", "2-b", "2026-11-10T11:00:00+00:00"),
             timed(PERSON, "approve_commit", "2-b", "2026-11-10T11:00:01+00:00"),
             timed(PERSON, "deliver", "2-b", "2026-11-10T11:00:02+00:00")]
    domain(tmp_path, "authoring", [*cmds, *cmds2], [event("X", PERSON, "person")], ["2-b"], ["2-b"])
    handoff = timed("handoff:authoring.deliver", "request_delivery", "authoring:2-b:local", "2026-11-10T11:00:02.5+00:00")
    refused = timed(PERSON, "preview", "authoring:2-b:local", "2026-11-10T11:00:03+00:00", status="rejected",
                    code="denied")                       # no events: it takes the time of the command before
    domain(tmp_path, "delivery", [handoff, refused], [event("X", PERSON, "person")], [], [])
    write(tmp_path / ".toprope/approval-runs.jsonl", [row | {"at": "2026-11-10T10:00:30+00:00"},
                                                      row2 | {"at": "2026-11-10T11:00:30+00:00"}])
    t = ub.measure(tmp_path)["person_touches"]
    assert (t["approvals_of_human_requests"], t["request_steps_not_found"]) == (2, 0)
    assert t["commands_outside_an_approved_request"] == 0


def test_a_request_applied_at_a_terminal_is_one_touch_and_one_approval(tmp_path, monkeypatch):
    """ADR-0053, 3: without GitHub, a local apply of a request with one confirmation is one approval."""
    import subprocess

    import human_request as hr
    import yaml
    real = subprocess.run
    steps, cmds = one_approval_run("2-b", "2026-11-10T10:00:30+00:00")

    def kernel(cmd, **kw):
        if cmd[0] == "git":
            return real(cmd, **kw)
        then = [{"kernel": "commit", "status": "ok", "object": "2-b"}] if "commit_draft" in cmd else []
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"status": "ok", "then": then}), "")
    monkeypatch.setattr(hr.subprocess, "run", kernel)
    (tmp_path / "toprope.identity.yaml").write_text(yaml.safe_dump({"people": {"ana@example.com": {
        "name": "ana", "roles": ["owner", "approver"]}}}))
    (tmp_path / "gitconfig").write_text("[user]\n\temail = ana@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv(hr.TLC_ENV, "tla2tools.jar")
    monkeypatch.setattr(sys, "stdin", type("T", (), {"isatty": lambda self: True})())
    req = tmp_path / ".toprope/requests/r.yaml"
    req.parent.mkdir(parents=True)
    req.write_text(yaml.safe_dump({"summary": "s", "steps": [{"run": s} for s in steps]}))
    domain(tmp_path, "authoring", cmds[:6], [event("X", PERSON, "person")], ["2-b"], ["2-b"],
           checks=[risk("2-b", "low")])
    domain(tmp_path, "delivery", cmds[6:], [event("X", PERSON, "person")], [], [])
    hr.apply(".toprope/requests/r.yaml", cwd=tmp_path, ask=lambda prompt: "yes")
    log = tmp_path / ".toprope/approval-runs.jsonl"
    (row,) = [json.loads(x) for x in log.read_text().splitlines()]
    write(log, [row | {"at": "2026-11-10T10:00:30+00:00"}])          # the kernel's commands are at 10:00
    m = ub.measure(tmp_path)
    assert m["approval_runs_by_channel"] == {"local": 1}
    assert m["person_touches"]["per_approved_change"] == 1.0
    assert (m["person_touches"]["approvals_of_human_requests"], m["person_touches"]["request_steps_not_found"],
            m["person_touches"]["commands_outside_an_approved_request"]) == (1, 0, 0)
    assert m["approvals_per_approved_change_by_risk"] == {"low": {"changes": 1, "approvals": 1, "per_change": 1.0}}


def test_a_run_held_after_its_preview_counts_the_steps_it_ran(tmp_path):
    """A local apply holds a commit not low risk after its preview (ADR-0050, 3): the steps it left
    are not looked for in the logs, and the second apply that takes them is a second approval."""
    steps, cmds = one_approval_run("2-b", "x")
    run1 = approval_run("2026-11-10T10:00:30+00:00", steps) | {"channel": "local", "ran": 6, "held": {"step": 7}}
    run2 = approval_run("2026-11-10T10:30:30+00:00", [s | {"target": s["target"].replace("$commit", "2-b")}
                                                     for s in steps[6:]]) | {"channel": "local"}
    later = [timed(PERSON, a, "authoring:2-b:local", f"2026-11-10T10:30:0{i}+00:00")
             for i, a in enumerate(("deploy", "run_probes", "verify"))]
    _, early = one_approval_run("2-b", "x")
    domain(tmp_path, "authoring", early[:6], [event("X", PERSON, "person")], ["2-b"], ["2-b"],
           checks=[risk("2-b", "high")])
    domain(tmp_path, "delivery", [early[6], *later], [event("X", PERSON, "person")], [], [])
    write(tmp_path / ".toprope/approval-runs.jsonl", [run1, run2])
    m = ub.measure(tmp_path)
    assert m["person_touches"]["request_steps_not_found"] == 0
    assert m["person_touches"]["commands_outside_an_approved_request"] == 0
    assert m["approvals_per_approved_change_by_risk"] == {"high": {"changes": 1, "approvals": 2, "per_change": 2.0}}
    assert m["approval_runs_by_channel"] == {"local": 2}


def _git_commit_at(root, when):
    import os
    import subprocess
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "merge theme 1"], check=True, env=env)
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def test_a_window_can_start_at_the_merge_that_changed_the_loop_and_the_measure_is_recorded(tmp_path, capsys):
    domain(tmp_path, "authoring",
           [timed(PERSON, "approve_commit", "1-a", "2026-11-06T10:00:00+00:00"),
            timed(PERSON, "approve_commit", "2-b", "2026-11-12T10:00:00+00:00")],
           [event("X", PERSON, "person")], ["1-a", "2-b"], [])
    head = _git_commit_at(tmp_path, "2026-11-11T02:45:09+00:00")
    rec = tmp_path / "experiments/usability/f1.json"
    assert ub.main(["--root", str(tmp_path), "--since-commit", "HEAD", "--json", "--record", str(rec)]) == 0
    out = json.loads(capsys.readouterr().out.split("\n\nRecorded in")[0])
    assert out["approvals_in_window"] == 1                                     # only the one after the merge
    saved = json.loads(rec.read_text())
    assert saved["head"] == head and saved["since_commit"] == "HEAD"
    assert saved["measures"]["window"]["since"] == "2026-11-11T02:45:09+00:00"
    with pytest.raises(SystemExit, match="exists. Fix: give --record a new file"):
        ub.main(["--root", str(tmp_path), "--since-commit", "HEAD", "--record", str(rec)])
    with pytest.raises(SystemExit, match="is not a commit in .*Fix: give a commit or tag"):
        ub.main(["--root", str(tmp_path), "--since-commit", "no-such-ref"])

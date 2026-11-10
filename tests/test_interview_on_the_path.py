"""The interview on a newcomer's path, with choices where the rules are decided (ADR-0053 §2).

A generic example (leave requests, not F2's expense claims) runs through `toprope-interview` with
the recommended answers; the share of choice questions among those that became enforced elements
is ADR-0053's target.
"""
import json
import shutil
from pathlib import Path

import pytest
import yaml
from test_staged_interview import put, upto, ws  # noqa: F401  (the workspace fixture)

from toprope.decl import Domain
from toprope.workspace import Workspace

HERE = Path(__file__).resolve().parent / "interview"
L, R = "“", "”"


def run(tmp_path, answers: str, capsys, where: str = "leave") -> tuple[Workspace, str]:
    from toprope.adapters.cli.interview import main
    d = tmp_path / where
    if not d.exists():
        shutil.copytree(HERE / "leave", d)
    f = tmp_path / "answers.txt"
    f.write_text(answers)
    with pytest.raises(SystemExit) as e:
        main([str(d), "--answers", str(f)])
    assert e.value.code == 0, capsys.readouterr().out
    return Workspace(d), capsys.readouterr().out


# -- 1. an entry point a newcomer runs ----------------------------------------------------------
def test_the_interview_runs_on_a_directory_with_only_a_domain_and_its_sources(tmp_path, capsys):
    ws, out = run(tmp_path, (HERE / "leave.answers").read_text(), capsys)
    assert (ws.root / "toprope.workspace.yaml").exists() and ws.domain_path.name == "domain.yaml"
    assert "choice [Enter = 1]" in out and "<- recommended" in out and "why: " in out
    assert "Confirmed" in out and "Every stage is done" in out
    d = Domain.model_validate(ws.draft())
    assert ws.check()["harness"]["ok"] is True                         # what the answers built works
    assert d.actions["approve_leave"].requires == "human"
    assert {p.id for p in d.actions["approve_leave"].preconditions} == {"limit-days", "not-the-creator"}
    assert d.rules["approved-needs-a-person"].requires == "human"


def test_nothing_is_confirmed_without_an_explicit_yes(tmp_path, capsys):
    answers = (HERE / "leave.answers").read_text().replace("\nyes\n", "\n\n")
    ws, out = run(tmp_path, answers, capsys)
    assert "Nothing confirmed" in out
    assert len(ws._proposed(ws.draft())) == 14                          # everything is still proposed
    log = [json.loads(x) for x in ws.log_path.read_text().splitlines()]
    assert not any(e["kind"] == "confirm" for e in log)


def test_the_answers_running_out_keeps_what_was_answered(tmp_path, capsys):
    ws, out = run(tmp_path, "\n".join((HERE / "leave.answers").read_text().splitlines()[:6]) + "\n", capsys)
    assert "the answers ran out" in out
    assert ws.draft()["purpose"]["success_metric"] == {"name": "requests decided within two days", "direction": "up"}


# -- 6. the measurement --------------------------------------------------------------------------
def test_at_least_80_percent_of_the_rule_questions_offer_a_recommended_choice(tmp_path, capsys):
    from toprope.workspace import interview_share
    ws, _ = run(tmp_path, (HERE / "leave.answers").read_text(), capsys)
    m = interview_share(ws._read(ws.log_path))
    # who may (3), the limit, who must not, two columns, the outcome rule; the open one names the actions
    assert m["enforced_questions"] == 8 and m["offered"] == 8 and m["share"] >= 0.8
    assert m["recommended"] == 8 and m["open"] == []
    from toprope.adapters.cli.interview import main
    main([str(ws.root), "--share"])                                     # the procedure in U-f2-first-rule.md
    assert json.loads(capsys.readouterr().out)["share"] == m["share"]


# -- 2. choices where the rules are decided ------------------------------------------------------
def leave(tmp_path) -> Workspace:
    d = tmp_path / "leave"
    shutil.copytree(HERE / "leave", d)
    from toprope.adapters.cli.interview import open_workspace
    ws = open_workspace(d)
    doc = {"domain": "leave", "version": 1,
           "purpose": {"problem": "p", "success_metric": {"name": "m", "direction": "up"}, "announcement": "a"},
           "roles": ["employee", "manager", "hr"],
           "glossary": {"employee": "asks for time off", "manager": "approves or refuses requests",
                        "hr": "approves long requests", "leave request": "A request for time off."},
           "objects": {"LeaveRequest": {"description": "A request for time off.",
                                        "properties": {"days": {"type": "integer"}}}},
           "world": {"fixtures": [{"LeaveRequest": {"id": "LR-7", "days": 12}}]}}
    ws.domain_path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return ws


def name_actions(ws):
    ws.answer("x", "They ask, and a manager approves or refuses.", [
        {"path": "actions.request_leave", "value": {"description": "Ask for time off", "creates": "LeaveRequest"}},
        {"path": "actions.approve_leave", "value": {"description": "Approve the request", "target": "LeaveRequest"}},
        {"path": "actions.reject_leave", "value": {"description": "Refuse the request", "target": "LeaveRequest"}}],
        question="What does each role do?")


def qs(ws, kind):
    return [q for q in ws.questions(limit=50)["questions"] if q["kind"] == kind]


def rec(q):
    (c,) = [c for c in q["choices"] if c.get("recommended")]
    return c


def test_an_action_named_without_its_actor_waits_for_a_choice_of_roles(tmp_path):
    ws = leave(tmp_path)
    name_actions(ws)
    assert "actions" not in ws.draft()                                  # nothing enforced from open words
    actor = {q["text"].split("(the action ")[1].split(",")[0]: q for q in qs(ws, "actor")}
    assert set(actor) == {"request_leave", "approve_leave", "reject_leave"}
    assert [c["label"] for c in actor["request_leave"]["choices"]] == ["the employee", "the manager", "the hr"]
    r = rec(actor["request_leave"])
    assert r["label"] == "the employee" and f"the glossary says the employee {L}asks for time off{R}" in r["why"]
    both = rec(actor["approve_leave"])                                  # two roles' words fit: both, with why
    assert both["label"] == "any of: manager, hr" and "approves long requests" in both["why"]
    ws.answer(actor["request_leave"]["id"], "Yes.", f"choice:{r['id']}")
    a = ws.draft()["actions"]["request_leave"]
    assert a["actor"] == ["employee"] and a["status"] == "proposed" and a["creates"] == "LeaveRequest"
    assert ws.progress()["current"] == "actions"                       # two actors still to choose


def test_who_must_not_approve_is_built_from_the_sources(tmp_path):
    ws = leave(tmp_path)
    name_actions(ws)
    for q in qs(ws, "actor"):
        ws.answer(q["id"], "Yes.", f"choice:{rec(q)['id']}")
    (guard,) = qs(ws, "guard")                                          # approve only: refusing needs no guard
    r = rec(guard)
    assert r["label"] == "only a person, and not whoever made the leave request"
    assert f"{L}Nobody approves their own request.{R}" in r["why"] and "sources:sources/policy.md" in r["why"]
    ws.answer(guard["id"], "Yes.", f"choice:{r['id']}")
    doc = ws.draft()
    assert doc["actions"]["approve_leave"]["requires"] == "human"
    pre = {p["id"]: p for p in doc["actions"]["approve_leave"]["preconditions"]}
    assert pre["not-the-creator"]["check"] == "target.created_by != actor.principal.id"
    assert doc["actions"]["request_leave"]["effects"] == [{"set": {"new.created_by": "actor.principal.id"}}]
    assert doc["objects"]["LeaveRequest"]["properties"]["created_by"] == {"type": "string", "optional": True}


def test_a_limit_offers_the_sources_number_and_the_examples_and_recommends_with_why(tmp_path):
    ws = leave(tmp_path)
    name_actions(ws)
    for q in qs(ws, "actor"):
        ws.answer(q["id"], "Yes.", f"choice:{rec(q)['id']}")
    (limit,) = qs(ws, "limit")
    labels = [c["label"] for c in limit["choices"]]
    assert "over 12 days, nobody may approve the request" in labels    # the example's own value
    assert labels[-1] == "no limit on days"
    r = rec(limit)
    assert r["label"] == "over 10 days, only the hr may approve the request"
    assert f"{L}A request over 10 days needs HR, not just a manager.{R}" in r["why"]
    ws.answer(limit["id"], "Yes.", f"choice:{r['id']}")
    pre = {p["id"]: p for p in ws.draft()["actions"]["approve_leave"]["preconditions"]}
    assert pre["limit-days"]["check"] == "target.days <= 10 or 'hr' in actor.roles"
    assert pre["limit-days"]["status"] == "proposed"


def test_without_a_source_the_example_value_is_the_recommended_threshold(tmp_path):
    ws = leave(tmp_path)
    (ws.root / "sources" / "policy.md").write_text("# Leave\nEmployees ask for time off.\n")
    name_actions(ws)
    for q in qs(ws, "actor"):
        ws.answer(q["id"], "Yes.", f"choice:{rec(q)['id']}")
    (limit,) = qs(ws, "limit")
    r = rec(limit)
    assert r["label"] == "over 12 days, nobody may approve the request"
    assert r["why"].startswith("LR-7 has days 12, the largest example you gave") and "fail-closed" in r["why"]
    (guard,) = qs(ws, "guard")
    assert rec(guard)["label"] == "anyone with the role, agents too"      # nothing said: nothing assumed
    assert rec(guard)["decisions"] == []


def test_a_declined_limit_is_not_asked_again(tmp_path):
    ws = leave(tmp_path)
    name_actions(ws)
    for q in qs(ws, "actor"):
        ws.answer(q["id"], "Yes.", f"choice:{rec(q)['id']}")
    (limit,) = qs(ws, "limit")
    no = next(c for c in limit["choices"] if c["label"] == "no limit on days")
    ws.answer(limit["id"], "No limit.", f"choice:{no['id']}")
    assert qs(ws, "limit") == []


def to_transitions(ws):
    name_actions(ws)
    for kind in ("actor", "limit", "guard"):
        for q in qs(ws, kind):
            ws.answer(q["id"], "Yes.", f"choice:{rec(q)['id']}")
    ws.answer("x", "submitted, approved or rejected", [
        {"path": "objects.LeaveRequest.properties.status", "value": {"enum": ["submitted", "approved", "rejected"]}},
        {"path": "transitions.LeaveRequest", "value": {"field": "status", "initial": "submitted", "matrix": {
            s: {"approve_leave": "undecided", "reject_leave": "undecided"} for s in ("submitted", "approved", "rejected")}}}],
        question="What stages?")


def test_a_column_recommends_the_move_to_the_stage_named_after_the_action(tmp_path):
    ws = leave(tmp_path)
    to_transitions(ws)
    cols = {q["decides"][0].split(".")[-1]: q for q in qs(ws, "default")}
    r = rec(cols["approve_leave"])
    assert r["label"] == "from submitted it moves it to approved; refused in every other open stage"
    assert "named after" in r["why"] and "submitted is the last stage you listed before it" in r["why"]
    assert rec(cols["reject_leave"])["label"].startswith("from submitted it moves it to rejected")


def test_the_column_question_no_longer_contradicts_its_recommendation(ws):  # noqa: F811
    doc = upto("invariants")
    doc["objects"]["Order"]["properties"]["status"] = {"enum": ["open", "shipped", "held"]}
    doc["transitions"]["Order"]["matrix"] = {s: {"ship": "undecided", "reopen": "n/a"} for s in ("open", "shipped", "held")}
    put(ws, doc)
    (col,) = [q for q in ws.questions(limit=50)["questions"] if q["kind"] == "default"]
    assert "Everywhere else it will be not applicable" not in col["text"]
    assert "In every other state it is refused, with a reason" in col["text"]


def test_an_outcome_rule_is_offered_once_the_cells_are_settled_and_needs_confirming(tmp_path):
    ws = leave(tmp_path)
    to_transitions(ws)
    for q in qs(ws, "default"):
        ws.answer(q["id"], "Yes.", f"choice:{rec(q)['id']}")
    (rule,) = qs(ws, "rule")
    r = rec(rule)
    assert r["label"] == "only a person may bring a leave request to approved"
    assert f"{L}Only a person approves a request, never an agent on its own.{R}" in r["why"]
    ws.answer(rule["id"], "Yes.", f"choice:{r['id']}")
    assert ws.draft()["rules"]["approved-needs-a-person"]["status"] == "proposed"
    assert "rules.approved-needs-a-person" in ws._proposed(ws.draft())  # a person confirms it
    assert ws.progress()["current"] == "invariants"


def test_cells_the_stop_rule_skips_are_asked_as_one_choice(ws):  # noqa: F811
    doc = upto("invariants")
    doc["objects"]["Order"]["properties"]["status"] = {"enum": ["open", "shipped", "held"]}
    doc["transitions"]["Order"]["matrix"]["held"] = {"ship": "undecided", "reopen": "undecided"}
    put(ws, doc)                                        # no effects, no attempts: the stop rule says stop
    b = ws.questions(limit=50)
    assert b["stop"]["stop"] is True and b["stage"] == "transitions"   # yet not done: they would be enforced
    (rest,) = [q for q in b["questions"] if q["kind"] == "rest"]
    assert sorted(rest["decides"]) == ["transitions.Order.matrix.held.reopen", "transitions.Order.matrix.held.ship"]
    leave_open = rest["choices"][-1]
    assert leave_open["decisions"] == [] and leave_open["label"].startswith("leave them undecided")
    ws.answer(rest["id"], "Leave them for now.", f"choice:{leave_open['id']}")
    assert ws.questions(limit=50)["stage"] == "invariants"              # the owner's answer, not the stop rule


# -- 3. the map from the cast on -----------------------------------------------------------------
def test_the_map_shows_who_does_what_before_there_is_a_matrix(tmp_path):
    ws = leave(tmp_path)
    assert "roles: employee, manager, hr" in ws.live_map()["text"]
    name_actions(ws)
    text = ws.live_map()["text"]
    assert "  LeaveRequest: days" in text and "  employee: nothing yet" in text
    assert "? (who may, still open): request_leave -> new LeaveRequest" in text
    q = next(q for q in qs(ws, "actor") if "request_leave" in q["text"])
    out = ws.answer(q["id"], "Yes.", f"choice:{rec(q)['id']}")
    assert "  employee: request_leave* -> new LeaveRequest" in out["map"]

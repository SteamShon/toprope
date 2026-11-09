"""Outcome rules (ADR-0048): a rule on an outcome holds every action that reaches it."""

from __future__ import annotations

import copy
from datetime import datetime, timezone

from test_decl import schema_doc_domain

from toprope.check import change_check
from toprope.decl.models import Domain
from toprope.decl.validate import validate_domain
from toprope.semantics.interpreter import Interpreter
from toprope.types import Actor, Command, Grant

RULE = "only-approvers-approve"


def with_bypass(rule: dict | None) -> Domain:
    """M1's change 3, in miniature: a second action into `approved` that an eng may take."""
    raw = schema_doc_domain()
    raw["actions"]["approve_quickly"] = {"description": "Approve a small experiment.", "actor": ["eng"],
                                         "target": "Experiment"}
    m = raw["transitions"]["Experiment"]["matrix"]
    m["draft"]["approve_quickly"] = "approved"
    for state in ("approved", "running", "ended", "decided"):
        m[state]["approve_quickly"] = "n/a"
    if rule:
        raw["rules"] = {RULE: rule}
    return Domain.model_validate(raw)


def decide(d: Domain, cmd: Command):
    return Interpreter(d).decide(cmd, {"id": "E1", "status": "draft"}, lambda _id: None).outcome


def test_a_rule_on_an_outcome_holds_an_action_added_later():
    rule = {"on": "Experiment.approved", "requires": {"roles": ["approver"]},
            "reason": "Only an approver approves an experiment."}
    eng = Actor("eli", "person", ("eng",))
    assert decide(with_bypass(None), Command(eng, "approve_quickly", "E1", {})).status == "ok"   # the bypass
    out = decide(with_bypass(rule), Command(eng, "approve_quickly", "E1", {}))
    assert (out.status, out.code, out.reason) == ("denied", RULE, "Only an approver approves an experiment.")


def test_a_person_rule_refuses_an_agent_but_not_a_person():
    d = with_bypass({"on": "Experiment.approved", "requires": "human", "reason": "Only a person approves."})
    person, agent = Actor("ana", "person", ("eng",)), Actor("bot", "agent", ("eng",))
    out = decide(d, Command(agent, "approve_quickly", "E1", {}, on_behalf_of=person,
                            grant=Grant("g", frozenset({"approve_quickly"}))))
    assert (out.status, out.code) == ("denied", RULE)
    assert decide(d, Command(person, "approve_quickly", "E1", {})).status == "ok"


def test_the_validator_checks_what_a_rule_names():
    bad = {"on": "Experiment.nowhere", "requires": "human", "reason": "r"}
    assert [i.code for i in validate_domain(with_bypass(bad)) if i.where == f"rules.{RULE}"] == ["unknown-path"]
    unreached = {"on": "Experiment.ended", "requires": "human", "reason": "r"}
    assert ("rule-covers-nothing", "warning") in {(i.code, i.severity) for i in validate_domain(with_bypass(unreached))}


def test_the_capability_diff_reports_a_path_that_leaves_a_rule():
    old = with_bypass({"on": "Experiment.approved", "requires": {"roles": ["approver"]}, "reason": "r"})
    raw = copy.deepcopy(old.model_dump(by_alias=True, exclude_none=True))
    raw["rules"][RULE]["on"] = "Experiment.running"
    msgs = [p.message for p in change_check(Domain.model_validate(raw), old).checks["capability"].problems
            if p.severity == "warning"]
    assert any(f"no longer held to rule(s) {RULE}" in m for m in msgs)
    assert any("new actor(s) eng" in m for m in msgs)                       # the bypass opens again


def test_the_harness_agrees_with_the_interpreter_on_a_rule():
    d = with_bypass({"on": "Experiment.approved", "requires": {"roles": ["approver"]}, "reason": "r"})
    report = change_check(d, examples=20)
    assert report.checks["harness"].ok, [p.message for p in report.checks["harness"].problems][:3]


# -- the check form of `requires`, and an agent in the harness world (#179's leftovers) --------

NOT_ELI = {"on": "Experiment.approved", "requires": {"check": 'actor.id != "eli"'},
           "reason": "Eli does not approve experiments."}


def test_a_check_rule_is_evaluated_on_the_actor():
    d = with_bypass(NOT_ELI)
    out = decide(d, Command(Actor("eli", "person", ("eng",)), "approve_quickly", "E1", {}))
    assert (out.status, out.code) == ("denied", RULE)
    assert decide(d, Command(Actor("eve", "person", ("eng",)), "approve_quickly", "E1", {})).status == "ok"


def test_the_validator_reads_a_check_rule():
    bad = {**NOT_ELI, "requires": {"check": "nobody.id == 1"}}
    assert ("unknown-root", f"rules.{RULE}.requires.check") in {(i.code, i.where) for i in validate_domain(with_bypass(bad))}
    assert not [i for i in validate_domain(with_bypass(NOT_ELI)) if i.where.startswith("rules.")]


def test_the_harness_agrees_with_the_interpreter_on_a_check_rule():
    report = change_check(with_bypass(NOT_ELI), examples=20)
    assert report.checks["harness"].ok, [p.message for p in report.checks["harness"].problems][:3]


def test_a_check_rule_guards_the_moves_it_covers_in_tla():
    from toprope.tla import export
    module = export(with_bypass(NOT_ELI)).module
    step = module[module.index("Step_approve_quickly"):]
    assert '\\notin {"draft"}' in step.split("\n\n")[0] and "Pass(" in step.split("\n\n")[0]


def test_the_harness_tries_a_person_rule_with_an_agent():
    from toprope.harness.cases import Planner
    from toprope.harness.world import grow_world
    d = with_bypass({"on": "Experiment.approved", "requires": "human", "reason": "Only a person approves."})
    cases = {c.id: c for c in Planner(grow_world(d), lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)).cases() if c.kind == "rule-agent"}
    case = cases["rule-agent:Experiment.draft.approve_quickly.eng"]
    assert case.agent and case.expect == {"status": "denied", "code": RULE}
    report = change_check(d, examples=20)
    assert report.checks["harness"].ok, [p.message for p in report.checks["harness"].problems][:3]


def test_the_harness_catches_an_interpreter_that_lets_an_agent_through(monkeypatch):
    from toprope.decl import rules
    d = with_bypass({"on": "Experiment.approved", "requires": "human", "reason": "Only a person approves."})
    real = rules.meets
    planned = real

    def lenient(rule, kind, *a, **k):                 # the interpreter forgets the person rule
        return True if kind == "agent" and rule.requires == "human" else planned(rule, kind, *a, **k)
    from toprope.harness import cases as cases_mod
    from toprope.harness.world import grow_world
    expected = cases_mod.Planner(grow_world(d), lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)).cases()          # planned with the real rule
    monkeypatch.setattr(rules, "meets", lenient)
    monkeypatch.setattr(cases_mod.Planner, "cases", lambda self: expected)
    report = change_check(d, examples=20)
    assert not report.checks["harness"].ok
    assert any("rule-agent:" in p.message or "rule-agent:" in str(p.where) for p in report.checks["harness"].problems)


# -- mechanical promotion (ADR-0048, Consequences; the M1 recheck) ----------------------------

def test_person_only_outcomes_are_promoted_to_rules_and_nothing_else():
    from toprope.decl.rules import suggest_rules
    raw = schema_doc_domain()
    raw["actions"]["approve_experiment"]["requires"] = "human"
    got = suggest_rules(Domain.model_validate(raw))
    rule = got["only-a-person-experiment-approved"]
    assert (rule["on"], rule["requires"], rule["status"]) == ("Experiment.approved", "human", "proposed")
    assert rule["reason"].startswith("Only a person brings an Experiment to approved:")
    assert "approve_experiment" in rule["source"]["ref"]
    assert all(r["on"].startswith("Experiment.") for r in got.values())
    raw["rules"] = {"x": {"on": "Experiment.approved", "requires": "human", "reason": "r"}}
    assert "only-a-person-experiment-approved" not in suggest_rules(Domain.model_validate(raw))   # guarded already


def test_an_outcome_another_action_reaches_without_a_person_is_not_promoted():
    from toprope.decl.rules import suggest_rules
    d = with_bypass(None)
    raw = d.model_dump(by_alias=True, exclude_none=True)
    raw["actions"]["approve_experiment"]["requires"] = "human"
    assert "only-a-person-experiment-approved" not in suggest_rules(Domain.model_validate(raw))


def test_the_self_domains_carry_exactly_the_promoted_rules_and_pass_with_them():
    """The self domains adopted the promoted rules (the M1 recheck): nothing is left to promote, the
    rules they carry are what promotion gives from their actions alone, and with them each passes
    its harness and capability check against its declaration without rules."""
    from pathlib import Path

    from toprope.decl import load_domain
    from toprope.decl.rules import suggest_rules
    root = Path(__file__).resolve().parents[1] / "domains"
    for name in ("authoring", "delivery"):
        d = load_domain(root / name / f"{name}.domain.yaml")
        assert d.rules and suggest_rules(d) == {}, name
        raw = d.model_dump(by_alias=True, exclude_none=True)
        raw.pop("rules")
        bare = Domain.model_validate(raw)
        promoted = suggest_rules(bare)
        assert {rid: (r["on"], r["requires"]) for rid, r in promoted.items()} == \
            {rid: (r.on, r.requires) for rid, r in d.rules.items()}, name
        assert not [i for i in validate_domain(d) if i.severity == "error"]
        report = change_check(d, bare, examples=10)
        assert report.checks["harness"].ok and report.checks["capability"].ok, name

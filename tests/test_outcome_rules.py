"""Outcome rules (ADR-0048): a rule on an outcome holds every action that reaches it."""

from __future__ import annotations

import copy

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
    assert (out.status, out.code, out.reason) == ("denied", RULE, "Only an approver approves an experiment. Fix: ask a person with the role approver to take it")


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

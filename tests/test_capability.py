"""The capability diff (ADR-0048 §3): who can reach each outcome, before and after a change."""

from __future__ import annotations

import copy

from test_decl import schema_doc_domain

from toprope.check import change_check
from toprope.check.capability import capabilities, capability_diff
from toprope.decl.models import Domain


def dom(raw: dict) -> Domain:
    return Domain.model_validate(raw)


def test_every_outcome_and_the_paths_to_it():
    caps = capabilities(dom(schema_doc_domain()))
    assert set(caps["Experiment.approved"]) == {("approve_experiment", "draft")}
    p = caps["Experiment.approved"][("approve_experiment", "draft")]
    assert p.actors == {"approver"} and p.preconditions == {"has-guardrails"} and not p.human
    assert ("launch_experiment", "approved") in caps["Experiment.running"]


def test_a_new_action_that_reaches_an_old_outcome_is_a_widening():
    """M1's change 3, in miniature: the rule lived on one action, and a new one went around it."""
    old = schema_doc_domain()
    old["actions"]["approve_experiment"]["requires"] = "human"
    new = copy.deepcopy(old)
    new["actions"]["approve_quickly"] = {**{k: v for k, v in old["actions"]["approve_experiment"].items()
                                           if k not in ("requires", "preconditions")},
                                        "description": "Approve a small experiment.", "actor": ["eng"]}
    new["transitions"]["Experiment"]["matrix"]["draft"]["approve_quickly"] = "approved"
    for state in ("approved", "running", "ended", "decided"):
        new["transitions"]["Experiment"]["matrix"][state]["approve_quickly"] = "n/a"
    found = capability_diff(dom(new), dom(old))
    warnings = [f for f in found if f[0] == "warning"]
    assert ("warning", "actions.approve_quickly",
            "Experiment.approved can now be reached by a new path: approve_quickly from draft, by eng, "
            "not only by a person") in warnings
    assert {w for _, w, _ in warnings} == {"actions.approve_quickly"}    # what it sets is reached anew too


def test_a_dropped_person_a_dropped_precondition_and_a_new_role_are_widenings():
    old = schema_doc_domain()
    old["actions"]["approve_experiment"]["requires"] = "human"
    new = copy.deepcopy(old)
    a = new["actions"]["approve_experiment"]
    del a["requires"]
    a["preconditions"] = []
    a["actor"] = ["approver", "eng"]
    msgs = [m for s, _, m in capability_diff(dom(new), dom(old)) if s == "warning"]
    assert any("no longer requires a person" in m for m in msgs)
    assert any("no longer checks has-guardrails" in m for m in msgs)
    assert any("new actor(s) eng" in m for m in msgs)
    assert not [f for f in capability_diff(dom(old), dom(new)) if f[0] == "warning"]   # the reverse narrows


def test_the_change_check_reports_it():
    old = schema_doc_domain()
    new = copy.deepcopy(old)
    new["actions"]["approve_experiment"]["actor"] = ["approver", "eng"]
    report = change_check(dom(new), dom(old))
    cap = report.checks["capability"]
    assert cap.ran and {p.where for p in cap.problems if p.severity == "warning"} == {"actions.approve_experiment"}
    assert not change_check(dom(old)).checks["capability"].ran                      # a first version

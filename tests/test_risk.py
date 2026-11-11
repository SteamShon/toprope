"""A change's risk is computed from the change check (ADR-0050)."""
import copy

from test_decl import schema_doc_domain

from toprope.check import change_check
from toprope.check.risk import assess, parse, summary
from toprope.decl import Domain


def risk(new_raw, old_raw):
    new, old = Domain.model_validate(new_raw), Domain.model_validate(old_raw)
    base = change_check(old, old, examples=5)                 # the base's own warnings, as recorded
    had = {n: sum(p.severity == "warning" for p in c.problems) for n, c in base.checks.items()}
    return assess(change_check(new, old, examples=5), new, old, pending=frozenset({"tla"}),   # no TLC here
                  base_warnings=had)


def test_a_reworded_description_is_low():
    old = schema_doc_domain()
    new = copy.deepcopy(old)
    new["actions"]["launch_experiment"]["description"] = "Turn it on."
    assert risk(new, old) == ("low", [])


def test_a_first_version_is_high():
    d = Domain.model_validate(schema_doc_domain())
    assert assess(change_check(d, None, examples=5), d, None)[0] == "high"


def test_a_changed_invariant_is_high():
    old = schema_doc_domain()
    new = copy.deepcopy(old)
    new["invariants"][0]["reason"] = "Reworded."
    level, reasons = risk(new, old)
    assert level == "high" and any("invariant" in r for r in reasons)


def test_a_removed_element_is_high():
    old = schema_doc_domain()
    new = copy.deepcopy(old)
    del new["glossary"]
    level, reasons = risk(new, old)
    assert level == "high" and any(r.startswith("removed:") for r in reasons)


def test_who_may_take_a_person_only_step_is_high_even_when_narrower():
    old = schema_doc_domain()
    name = next(iter(old["actions"]))
    old["actions"][name]["requires"] = "human"
    new = copy.deepcopy(old)
    new["actions"][name]["actor"] = new["actions"][name]["actor"][:1]          # fewer actors: narrower
    assert new["actions"][name]["actor"] != old["actions"][name]["actor"] or len(old["actions"][name]["actor"]) == 1
    if new["actions"][name]["actor"] == old["actions"][name]["actor"]:
        new["actions"][name]["requires"] = None                                 # one actor: drop the floor instead
    level, reasons = risk(new, old)
    assert level == "high" and any(f"action:{name}" in r for r in reasons), reasons


def test_the_same_narrowing_on_an_ordinary_action_stays_low():
    old = schema_doc_domain()
    name = next(n for n, a in old["actions"].items() if not a.get("requires"))
    new = copy.deepcopy(old)
    old["actions"][name]["actor"] = [*old["actions"][name]["actor"], "pm"]      # was two roles, now one
    level, reasons = risk(new, old)
    assert level == "low", reasons


def test_the_summary_reads_back():
    assert parse(summary("high", ["a", "b"])) == ("high", ["a", "b"]) and parse("low") == ("low", [])


def test_a_weakened_precondition_is_high():
    old = schema_doc_domain()
    new = copy.deepcopy(old)
    pre = next((n, p) for n, a in new["actions"].items() for p in a.get("preconditions") or [])
    pre[1]["check"] = "true"
    level, reasons = risk(new, old)
    assert level == "high" and any(f"precondition:{pre[0]}.{pre[1]['id']}" in r for r in reasons), reasons


def test_a_new_precondition_on_an_ordinary_action_is_a_narrowing_and_low():
    old = schema_doc_domain()
    new = copy.deepcopy(old)
    name = next(n for n, a in new["actions"].items() if not a.get("requires"))
    new["actions"][name].setdefault("preconditions", []).append(
        {"id": "always", "check": "true", "reason": "Always."})
    level, reasons = risk(new, old)
    assert level == "low", reasons


def test_a_moved_outcome_rule_is_high():
    old = schema_doc_domain()
    old["rules"] = {"only-a-person-ends": {"on": "Experiment.ended", "requires": "human", "reason": "r"}}
    new = copy.deepcopy(old)
    new["rules"]["only-a-person-ends"]["on"] = "Experiment.approved"
    level, reasons = risk(new, old)
    assert level == "high" and "an outcome rule changed" in reasons


def test_a_check_that_did_not_run_is_not_low():
    old = schema_doc_domain()
    new = copy.deepcopy(old)
    new["actions"]["launch_experiment"]["description"] = "Turn it on."
    n, o = Domain.model_validate(new), Domain.model_validate(old)
    level, reasons = assess(change_check(n, o, examples=5), n, o)          # TLC not pending: it must run
    assert level == "high" and any("tla" in r for r in reasons)

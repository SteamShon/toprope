"""A change's risk is computed from the change check (ADR-0050)."""
import copy

from test_decl import schema_doc_domain

from toprope.check import change_check
from toprope.check.risk import assess, parse, summary
from toprope.decl import Domain


def risk(new_raw, old_raw):
    new, old = Domain.model_validate(new_raw), Domain.model_validate(old_raw)
    return assess(change_check(new, old, examples=5), new, old)


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
    assert level == "high" and any("person-only" in r for r in reasons)


def test_the_same_narrowing_on_an_ordinary_action_stays_low():
    old = schema_doc_domain()
    name = next(n for n, a in old["actions"].items() if not a.get("requires"))
    new = copy.deepcopy(old)
    old["actions"][name]["actor"] = [*old["actions"][name]["actor"], "pm"]      # was two roles, now one
    level, reasons = risk(new, old)
    assert level == "low", reasons


def test_the_summary_reads_back():
    assert parse(summary("high", ["a", "b"])) == ("high", ["a", "b"]) and parse("low") == ("low", [])

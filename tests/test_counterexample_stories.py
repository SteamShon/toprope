"""A counterexample is told as a short story in the domain's terms (ADR-0049, D3)."""
from pathlib import Path

from toprope.decl import load_domain
from toprope.harness import run_harness
from toprope.harness.run import Finding
from toprope.harness.story import case_stories, facts, flow_story, inductive_story

ROOT = Path(__file__).resolve().parents[1]
SEEDED = ROOT / "tests/tla/paid-media.no-holdout-guard.domain.yaml"
PAID = ROOT / "examples/paid-media/paid-media.domain.yaml"
RULE = "“A holdout campaign never has a budget change pending, unless a media lead granted an exception.”"


def test_the_harness_tells_its_flow_its_cases_and_its_inductive_breaks():
    r = run_harness(load_domain(SEEDED), levels=("model",), explore_examples=200, races=False)
    (flow,) = [s for s in r.stories if s.startswith("1. ")]
    assert flow.startswith("1. analyst-1 (analyst) on a Campaign, C-holdout (whose change is none), asks to "
                           "propose a new daily budget for review, and nothing in the rules refuses it")
    assert flow.endswith(f"Then the rule {RULE} would no longer hold.")
    (cases,) = [s for s in r.stories if s.startswith("The rules let someone")]
    assert "case(s), e.g. " in cases                                    # one story for many cases
    assert any(s.startswith("Take a Campaign like this:") for s in r.stories)
    assert f"in your words: {flow}" in r.summary() and r.to_json()["stories"] == r.stories


def test_each_step_names_its_thing_when_it_changes_and_tells_failures_from_refusals():
    d = load_domain(PAID)
    text = flow_story(d, {"invariant": "holdouts-never-change", "steps": [
        {"actor": "media_lead ana", "action": "grant_exception", "target": "C-holdout", "from": "none", "outcome": "ok"},
        {"actor": "analyst bot", "action": "approve_budget_change", "target": "C-other", "from": "none",
         "outcome": "matrix"},
        {"actor": "analyst bot", "action": "approve_budget_change", "target": "C-other", "outcome": "invalid-command"}]})
    assert "1. ana (media_lead) on a Campaign, C-holdout (whose change is none), asks to allow one budget change" in text
    assert "2. bot (analyst) on a Campaign, C-other (whose change is none), asks to approve the proposed budget " \
           "exactly as proposed, and it is refused (matrix)." in text
    assert "3. bot (analyst) asks to" in text and "it fails (invalid-command), which is not a rule refusing it" in text


def test_facts_are_whole_and_a_missing_one_is_said():
    d = load_domain(PAID)
    data = {"id": "x", "name": "n" * 150, "holdout": True, "proposed_by": "", "change": "none"}
    out = facts(d, "Campaign", data)
    assert out.startswith("no daily_budget, no proposed_budget, no proposed_by")    # missing facts first
    whole = {f"{k} {v}" for k, v in data.items()} | {f"no {k}" for k in d.objects["Campaign"].properties}
    shown = out.split(", ")
    assert shown[-1].startswith("and ") and shown[-1].endswith(" more")             # cut between facts
    assert all(p in whole for p in shown[:-1])                                     # never inside one


def test_a_description_that_is_not_a_verb_becomes_take_the_action():
    d = load_domain(PAID)
    d.actions["grant_exception"].description = "The media lead's one-time exception."
    text = inductive_story(d, "mechanical:Campaign.none.grant_exception.media_lead", {"reason": None, "start": {}})
    assert "may take the action grant_exception (the media lead's one-time exception) now" in text
    assert "the rule one of its invariants breaks" in text                          # no reason: no “None”


def test_cases_are_grouped_by_action_and_rule_whatever_their_id_shape():
    d = load_domain(PAID)
    fs = [Finding("invariant", "model", "param:Campaign.none.propose_budget_change.analyst@C-1:daily_budget=1",
                  {"observed": {"reason": "R."}}),
          Finding("invariant", "model", "create:propose_budget_change.analyst", {"observed": {"reason": "R."}}),
          Finding("expectation", "model", "x", {})]
    (story,) = case_stories(d, fs)
    assert story.startswith("The rules let someone propose a new daily budget for review, and then the rule “R.”")
    assert "(2 case(s), e.g. param:Campaign.none.propose_budget_change" in story

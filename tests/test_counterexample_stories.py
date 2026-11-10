"""A counterexample is told as a short story in the domain's terms (ADR-0049, D3)."""
from pathlib import Path

from toprope.decl import load_domain
from toprope.harness import run_harness
from toprope.harness.story import flow_story, inductive_story

ROOT = Path(__file__).resolve().parents[1]
SEEDED = ROOT / "tests/tla/paid-media.no-holdout-guard.domain.yaml"
RULE = "“A holdout campaign never has a budget change pending, unless a media lead granted an exception.”"


def test_the_harness_tells_its_minimal_flow_and_its_inductive_breaks_in_the_domains_words():
    r = run_harness(load_domain(SEEDED), levels=("model",), explore_examples=200, races=False)
    (flow,) = [s for s in r.stories if s.startswith("Start with")]
    assert any(s.startswith("Take a Campaign like this:") for s in r.stories)      # the inductive break
    assert flow.startswith("Start with a Campaign, C-holdout, whose change is none.")
    assert "asks to propose a new daily budget for review" in flow            # the action's own words
    assert flow.endswith(f"Then the rule {RULE} would no longer hold.")
    assert f"in your words: {flow}" in r.summary()


def test_a_flow_with_refused_and_done_steps_says_which():
    d = load_domain(ROOT / "examples/paid-media/paid-media.domain.yaml")
    text = flow_story(d, {"invariant": "holdouts-never-change", "steps": [
        {"actor": "media_lead ana", "action": "grant_exception", "target": "C-holdout", "from": "none", "outcome": "ok"},
        {"actor": "analyst bot", "action": "approve_budget_change", "target": "C-holdout", "from": "none",
         "outcome": "matrix"}]})
    assert "1. The media_lead, ana asks to allow one budget change" in text and "and it is done" in text
    assert "2. The analyst, bot asks to approve the proposed budget exactly as proposed, and it is refused." in text


def test_an_inductive_break_names_the_role_the_action_and_leaves_out_empty_facts():
    d = load_domain(SEEDED)
    text = inductive_story(d, "mechanical:Campaign.none.propose_budget_change.analyst",
                           {"reason": "A rule.", "start": {"id": "x", "holdout": True, "proposed_by": "", "note": None}})
    assert text.startswith("Take a Campaign like this: holdout True. Every rule allows it. Yet if the analyst may "
                           "propose a new daily budget for review now, the rule “A rule.” breaks.")


def test_a_reason_on_several_lines_is_told_on_one():
    d = load_domain(SEEDED)
    text = inductive_story(d, "mechanical:Campaign.none.propose_budget_change", {"reason": "One.\n  Two.", "start": {}})
    assert "“One. Two.”" in text and "\n" not in text and "Yet if someone may" in text

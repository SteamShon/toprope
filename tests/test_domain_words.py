"""Decisions and stories in the domain's words (ADR-0049, D2 and D3; the review of 2026-11-10):
glossary terms and action descriptions, and every rule on a domain's first commit."""
import copy

from test_staged_interview import FULL

from toprope.decl import Domain

L, R = "“", "”"


def test_a_first_commit_lists_every_rule_in_plain_words():
    from toprope.check.decisions import decisions
    d = copy.deepcopy(FULL)
    d["glossary"] = {"order": "What a customer asks for.", "clerk": "Ships orders."}
    out = [x["decide"] for x in decisions(Domain.model_validate(d), None)]
    assert out[0] == "shop starts with 2 action(s) and 2 kind(s) of thing"
    assert f"New action {L}ship an order{R}: who may take it: clerk" in out
    assert f"When an order is shipped, {L}ship an order{R} is refused ({L}Already shipped.{R})" in out
    assert f"When an order is open, {L}reopen an order{R} does not apply" in out
    assert f"A new rule that always holds: {L}Every order has a total.{R} (checks `exists(target.total)`)" in out
    assert any(s.startswith("An order goes through the stages open, shipped (its status), starting open") for s in out)
    assert not any("ship_order" in s or s.startswith("New role") for s in out)


def test_a_story_names_things_and_roles_by_their_glossary_terms():
    from toprope.harness.story import flow_story, inductive_story
    d = Domain.model_validate({**copy.deepcopy(FULL), "glossary": {"order": "What a customer asks for.",
                                                                   "clerk": "Ships orders."}})
    text = flow_story(d, {"invariant": "has-total", "steps": [
        {"actor": "clerk kim", "action": "ship", "target": "O1", "from": "open", "outcome": "ok"}]})
    assert text.startswith("1. kim (clerk) on an order, O1 (whose status is open), asks to ship an order")
    assert inductive_story(d, "mechanical:Order.open.ship.clerk", {"reason": "R.", "start": {"total": 1}}) \
        .startswith("Take an order like this:")

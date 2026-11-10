"""The interview asks for a real case before the rules, and uses it after (ADR-0049, B2)."""
import pytest
from test_staged_interview import put, upto, ws  # noqa: F401  (the workspace fixture)

from toprope.workspace import AuthoringError


def test_the_cast_stage_asks_for_a_real_example_of_each_thing_with_facts(ws):  # noqa: F811
    doc = upto("actions")
    doc.pop("world", None)
    put(ws, doc)
    qs = ws.questions(limit=50, stage="cast")["questions"]
    (ex,) = [q for q in qs if q["kind"] == "example"]
    assert "one real Order" in ex["text"] and "status, total" in ex["text"] and ex["decides"] == ["world.fixtures"]


def test_an_answered_example_joins_the_others_and_is_used_in_later_questions(ws):  # noqa: F811
    doc = upto("review")
    doc["transitions"]["Order"]["matrix"]["shipped"]["reopen"] = "undecided"
    doc["actions"]["reopen"]["effects"] = [{"set": {"target.total": 0}}]
    put(ws, doc)
    ws.answer("x", "Last week O-7, 42 euros, shipped.",
              [{"path": "world.fixtures", "value": {"Order": {"id": "O-7", "status": "shipped", "total": 42}}}],
              question="Tell me about one real Order.")
    fixtures = ws.draft()["world"]["fixtures"]
    assert {"Order": {"id": "O-7", "status": "shipped", "total": 42}} in fixtures and len(fixtures) == 3
    (row,) = [q for q in ws.questions(limit=50)["questions"] if q["kind"] == "row"]
    assert row["text"].startswith("Once an Order is shipped (like O-7: total 42), can anyone still")


def test_an_example_with_the_same_id_replaces_the_old_one(ws):  # noqa: F811
    put(ws, upto("invariants"))
    for total in (5, 6):
        ws.answer("x", "O1 again.", [{"path": "world.fixtures",
                                       "value": {"Order": {"id": "O1", "status": "open", "total": total}}}], question="q")
    orders = [f["Order"] for f in ws.draft()["world"]["fixtures"] if "Order" in f]
    assert [o["total"] for o in orders] == [6]


def test_an_example_without_an_id_is_refused_with_its_fix(ws):  # noqa: F811
    put(ws, upto("invariants"))
    with pytest.raises(AuthoringError, match="an example is one object with an id.*Fix:"):
        ws.answer("x", "An order.", [{"path": "world.fixtures", "value": {"Order": {"total": 1}}}], question="q")

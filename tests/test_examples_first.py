"""The interview asks for a real case before the rules, and uses it after (ADR-0049, B2)."""
import pytest
from test_staged_interview import put, upto, ws  # noqa: F401  (the workspace fixture)

from toprope.workspace import AuthoringError


def test_right_after_the_cast_the_interview_asks_for_a_real_example_first(ws):  # noqa: F811
    put(ws, upto("actions"))                              # the normal flow: cast done, actions next
    b = ws.questions(limit=50)
    assert b["stage"] == "actions"
    ex = b["questions"][0]                                # asked before the rules
    assert ex["kind"] == "example" and "one real Order" in ex["text"] and "status, total" in ex["text"]
    assert "made-up names and numbers" in ex["text"] and ex["decides"] == ["world.fixtures"]


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
    with pytest.raises(AuthoringError, match="the Order example has no id. Fix:"):
        ws.answer("x", "An order.", [{"path": "world.fixtures", "value": {"Order": {"total": 1}}}], question="q")


@pytest.mark.parametrize("value, says", [
    ({"Order": {"id": "O-9", "status": "shippd"}}, "Order.status is 'shippd', not one of open, shipped"),
    ({"Order": {"id": "O-9", "colour": "red"}}, "Order has no fact colour"),
    ({"Ghost": {"id": "G-1"}}, "no object 'Ghost' in the draft"),
    ({"Order": {"id": {"a": 1}}}, "the Order example has no id"),
    ([{"Order": {"id": "O-9"}}], "an example is one object"),
    ({"Customer": {"id": "O1"}}, "id 'O1' is already an Order example"),
])
def test_an_example_must_fit_the_draft(ws, value, says):  # noqa: F811
    put(ws, upto("review"))
    before = ws.draft()["world"]["fixtures"]
    with pytest.raises(AuthoringError, match=says):
        ws.answer("x", "An example.", [{"path": "world.fixtures", "value": value}], question="q")
    assert ws.draft()["world"]["fixtures"] == before                 # nothing replaced


@pytest.mark.parametrize("value", ["kim@example.com", "4111 1111 1111 1111", "010-1234-5678"])
def test_an_example_holding_personal_data_is_refused(ws, value):  # noqa: F811
    doc = upto("review")
    doc["objects"]["Order"]["properties"]["note"] = {"type": "string", "optional": True}
    put(ws, doc)
    with pytest.raises(AuthoringError, match="looks like personal data or a secret. Fix: use a made-up value"):
        ws.answer("x", "An example.", [{"path": "world.fixtures",
                                        "value": {"Order": {"id": "O-9", "status": "open", "note": value}}}], question="q")


def test_questions_repeat_only_numbers_and_choices_from_an_example_and_the_log_keeps_it(ws):  # noqa: F811
    import json
    doc = upto("review")
    doc["objects"]["Order"]["properties"]["note"] = {"type": "string", "optional": True}
    doc["transitions"]["Order"]["matrix"]["shipped"]["reopen"] = "undecided"
    doc["actions"]["reopen"]["effects"] = [{"set": {"target.total": 0}}]
    put(ws, doc)
    ex = {"Order": {"id": "O-7", "status": "shipped", "total": 42, "note": "left at the door"}}
    ws.answer("x", "O-7.", [{"path": "world.fixtures", "value": ex}], question="q")
    (row,) = [q for q in ws.questions(limit=50)["questions"] if q["kind"] == "row"]
    assert "(like O-7: total 42)" in row["text"] and "door" not in row["text"]
    last = [json.loads(x) for x in ws.log_path.read_text().splitlines()][-1]
    assert last["examples"] == [ex]

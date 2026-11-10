"""The interview shows the draft as a map while the owner answers (ADR-0049, B3)."""
from test_staged_interview import put, upto, ws  # noqa: F401  (the workspace fixture)


def open_draft(ws):  # noqa: F811
    doc = upto("invariants")
    doc["transitions"]["Order"]["matrix"]["shipped"]["reopen"] = "undecided"
    doc["actions"]["reopen"]["effects"] = [{"set": {"target.total": 0}}]
    put(ws, doc)


def test_the_map_shows_where_actions_lead_what_is_refused_and_what_is_open(ws):  # noqa: F811
    open_draft(ws)
    m = ws.live_map()
    lines = m["text"].splitlines()
    assert lines[0] == "Order (status; starts open)"
    assert "  open: ship -> shipped, reopen -" in lines
    assert "  shipped: ship x, reopen ?" in lines
    assert m["mermaid"] == {}                                              # only on request
    assert ws.live_map(mermaid=True)["mermaid"]["Order"].startswith("stateDiagram-v2")


def test_each_bundle_and_each_answer_carries_the_map_as_it_now_is(ws):  # noqa: F811
    open_draft(ws)
    b = ws.questions(limit=50)
    assert "reopen ?" in b["map"]
    (row,) = [q for q in b["questions"] if q["kind"] == "row"]
    rec = next(c for c in row["choices"] if c.get("recommended"))
    out = ws.answer(row["id"], "Yes.", f"choice:{rec['id']}")
    assert "reopen ?" not in out["map"] and "reopen x*" in out["map"]     # refused, and only proposed


def test_a_draft_that_does_not_parse_has_an_empty_map(ws):  # noqa: F811
    put(ws, {"domain": "shop", "objects": "not a mapping"})
    assert ws.live_map() == {"text": "", "mermaid": {}}


def test_a_missing_cell_and_a_stage_with_no_row_show_as_open(ws):  # noqa: F811
    doc = upto("invariants")
    doc["objects"]["Order"]["properties"]["status"]["enum"] = ["open", "shipped", "held"]
    del doc["transitions"]["Order"]["matrix"]["open"]["reopen"]
    put(ws, doc)
    text = ws.live_map()["text"]
    assert "  open: ship -> shipped, reopen ?" in text
    assert "  held: ship ?, reopen ?" in text                                 # a stage the matrix lacks


def test_a_per_role_cell_shows_each_role(ws):  # noqa: F811
    doc = upto("invariants")
    doc["transitions"]["Order"]["matrix"]["open"]["ship"] = {"by_role": {"clerk": "shipped", "manager": {"deny": "No."}}}
    put(ws, doc)
    assert "ship by role: clerk -> shipped; manager x (other roles -)" in ws.live_map()["text"]


def test_every_reply_of_questions_carries_the_map(ws):  # noqa: F811
    import copy
    from test_staged_interview import FULL
    put(ws, copy.deepcopy(FULL))
    b = ws.questions(limit=50)
    assert "map" in b and "Order (status; starts open)" in b["map"]

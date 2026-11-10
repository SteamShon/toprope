"""Questions offer choices, one recommended with its reason (ADR-0049, B1)."""
import pytest
from test_staged_interview import put, upto, ws  # noqa: F401  (the workspace fixture)

from toprope.workspace import AuthoringError, choice_share


def open_cells(ws):  # noqa: F811
    doc = upto("invariants")
    m = doc["transitions"]["Order"]["matrix"]
    m["shipped"]["reopen"] = "undecided"                  # reopen goes to `open` from nowhere else yet
    m["open"]["ship"] = "shipped"
    m["shipped"]["ship"] = "undecided"                    # ship leads to `shipped` from `open`
    doc["actions"]["reopen"]["effects"] = [{"set": {"target.total": 0}}]
    put(ws, doc)
    (row,) = [q for q in ws.questions(limit=50)["questions"] if q["kind"] == "row"]
    return row


def test_a_row_question_offers_a_recommended_answer_with_its_reason(ws):  # noqa: F811
    row = open_cells(ws)
    rec = [c for c in row["choices"] if c.get("recommended")]
    assert len(rec) == 1
    by_path = {d["path"]: d["value"] for d in rec[0]["decisions"]}
    assert by_path["transitions.Order.matrix.shipped.ship"] == "shipped"     # as from every other state
    assert by_path["transitions.Order.matrix.shipped.reopen"] == {"deny": "Not while an Order is shipped."}
    assert "fail-closed" in rec[0]["why"] and "from every other state" in rec[0]["why"]
    assert [c["label"] for c in row["choices"][1:]] == [
        "none of them: each is refused while an Order is shipped", "none of them applies to a shipped Order"]


def test_answering_by_choice_applies_its_decisions_as_proposed_citing_the_owner(ws):  # noqa: F811
    row = open_cells(ws)
    rec = next(c for c in row["choices"] if c.get("recommended"))
    out = ws.answer(row["id"], "Yes, that is right.", f"choice:{rec['id']}")
    assert sorted(out["applied"]) == sorted(d["path"] for d in rec["decisions"])
    cell = ws.draft()["transitions"]["Order"]["matrix"]["shipped"]["reopen"]
    assert cell["deny"] == "Not while an Order is shipped." and cell["status"] == "proposed"
    assert cell["source"]["quote"] == "Yes, that is right."


def test_an_optional_stage_offers_to_skip_it(ws):  # noqa: F811
    put(ws, upto("invariants"))
    b = ws.questions(limit=50)
    assert b["stage"] == "invariants"
    (skip,) = b["questions"][0]["choices"]
    assert skip["skip"] == "invariants" and not skip.get("recommended")      # nothing is assumed
    ws.answer(b["questions"][0]["id"], "There is no such rule here.", f"choice:{skip['id']}")
    assert ws.questions(limit=50)["stage"] != "invariants"


def test_a_choice_that_is_not_offered_is_refused_with_its_fix(ws):  # noqa: F811
    open_cells(ws)
    with pytest.raises(AuthoringError, match="no choice 'nope/1' among the open questions.*Fix: ask `next_questions` again"):
        ws.answer("x", "yes", "choice:nope/1")
    with pytest.raises(AuthoringError, match="neither a list nor a choice"):
        ws.answer("x", "yes", "just do it")


def test_the_share_of_questions_with_a_recommended_choice_is_measured(ws):  # noqa: F811
    row = open_cells(ws)
    assert choice_share([row]) == 1.0
    assert choice_share([row, {"id": "q", "choices": []}]) == 0.5
    assert choice_share([]) == 0.0


def test_the_kernel_takes_a_choice_through_the_decisions_param(ws):  # noqa: F811
    from toprope.kernel.services import LocalKernel
    row = open_cells(ws)
    rec = next(c for c in row["choices"] if c.get("recommended"))
    k = LocalKernel(ws.root, workspace=ws)
    out = k.call("record_answer", {"question": row["text"], "answer": "Agreed.", "decisions": f"choice:{rec['id']}"},
                 caller={"id": "ana", "kind": "person"})
    assert out["ok"], out
    assert ws.draft()["transitions"]["Order"]["matrix"]["shipped"]["ship"]["to"] == "shipped"


def four_states(ws, ship_cells, reopen_cells=None):  # noqa: F811
    doc = upto("invariants")
    doc["objects"]["Order"]["properties"]["status"] = {"enum": ["open", "shipped", "held", "cancelled"]}
    doc["transitions"]["Order"]["matrix"] = {
        s: {"ship": ship_cells.get(s, "undecided"), "reopen": (reopen_cells or {}).get(s, "n/a")}
        for s in ("open", "shipped", "held", "cancelled")}
    doc["actions"]["ship"]["effects"] = [{"set": {"target.total": 1}}]
    doc["actions"]["reopen"]["effects"] = [{"set": {"target.total": 0}}]
    put(ws, doc)
    return {q["id"]: q for q in ws.questions(limit=50)["questions"]}


def rec_for(qs, path):
    for q in qs.values():
        for c in q.get("choices") or []:
            if c.get("recommended"):
                for d in c["decisions"]:
                    if d["path"] == path:
                        return d["value"]
    raise AssertionError(path)


def test_one_state_allowing_is_not_enough_to_recommend_allowing(ws):  # noqa: F811
    qs = four_states(ws, {"open": "shipped", "shipped": {"deny": "Already."}, "held": {"deny": "Held."}})
    assert rec_for(qs, "transitions.Order.matrix.cancelled.ship") == {"deny": "Not while an Order is cancelled."}


def test_a_per_role_cell_in_the_column_means_refused_not_a_plain_move(ws):  # noqa: F811
    qs = four_states(ws, {"open": "shipped", "shipped": {"deny": "x"}, "held": {"deny": "x"}, "cancelled": {"deny": "x"}},
                     {"shipped": {"by_role": {"manager": "open"}}, "held": "open", "open": "n/a", "cancelled": "undecided"})
    assert rec_for(qs, "transitions.Order.matrix.cancelled.reopen") == {"deny": "Not while an Order is cancelled."}


def test_a_whole_column_recommends_refusals_a_person_confirms_never_n_a(ws):  # noqa: F811
    qs = four_states(ws, {"open": "shipped"})
    (col,) = [q for q in qs.values() if q["kind"] == "default"]
    (rec,) = [c for c in col["choices"] if c.get("recommended")]
    assert all("deny" in d["value"] for d in rec["decisions"])
    ws.answer(col["id"], "Refuse it there.", f"choice:{rec['id']}")
    assert set(ws._proposed(ws.draft())) >= {"transitions.Order.matrix.held.ship"}     # left for a person


def test_a_choice_whose_decisions_changed_is_not_applied(ws):  # noqa: F811
    row = open_cells(ws)
    rec = next(c for c in row["choices"] if c.get("recommended"))
    doc = ws.draft()
    doc["transitions"]["Order"]["matrix"]["open"]["ship"] = {"deny": "Not any more."}   # the column changed
    put(ws, doc)
    with pytest.raises(AuthoringError, match="its choices changed since they were shown"):
        ws.answer(row["id"], "Yes.", f"choice:{rec['id']}")


def test_a_skip_is_logged_under_the_stage_it_skips(ws):  # noqa: F811
    import json
    put(ws, upto("invariants"))
    q = ws.questions(limit=50)["questions"][0]
    ws.answer(q["id"], "No such rule.", f"choice:{q['choices'][0]['id']}")
    last = [json.loads(x) for x in ws.log_path.read_text().splitlines()][-1]
    assert last["kind"] == "answer" and last["stage"] == "invariants"

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
    with pytest.raises(AuthoringError, match="no choice 'nope/1' among the open questions. Fix:"):
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

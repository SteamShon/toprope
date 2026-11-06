"""Item-by-item probe grading (phase_b/rubric.py, scoring/rubric.yaml)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/m1"))

from phase_b import rubric
from phase_b.backend import ApiBackend
from phase_b.model import FakeModel

RUBRIC = yaml.safe_load((ROOT / "experiments/m1/runs/phase-b/scoring/rubric.yaml").read_text())
PROBES = {p["id"]: p for p in yaml.safe_load((ROOT / "experiments/m1/instruments/probe-suite.yaml").read_text())["probes"]}


def write(d: Path, calls, messages=(), answer="a", name="P08"):
    (d / "probes").mkdir(parents=True, exist_ok=True)
    rows = [{"kind": "reply", "content": [{"type": "tool_use", "id": f"t{i}", "name": n, "input": a}]}
            for i, (n, a) in enumerate(calls)]
    rows.append({"kind": "tool", "output": "history: result refused, rule superseded"})
    (d / "probes" / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return {"probe": name, "transcript": f"{name}.jsonl", "answer": answer,
            "messages_to_owner": [{"text": m, "choices": []} for m in messages]}


def test_the_rubric_has_a_rule_for_every_probe_item():
    for p in PROBES.values():
        items = rubric.items_for(RUBRIC, p)
        assert set(items) == {f"must[{i}]" for i in range(len(p["must"]))} | {"must_not[0]"}


def test_an_item_without_a_rule_is_refused():
    with pytest.raises(SystemExit, match="no rule for P02 must\\[1\\]"):
        rubric.items_for({"common": {"must_not[0]": {"check": "no_person_step"}},
                          "probes": {"P02": {"must[0]": {"judge": "x"}, "must[2]": {"judge": "y"}}}}, PROBES["P02"])


def test_the_computed_checks_read_the_record(tmp_path):
    rec = rubric.Record(tmp_path, write(tmp_path, [("mcp__authoring__deliver", {}), ("mcp__phase_b__commit_diff", {})],
                                        ["the deploy was refused: superseded"]))
    assert rubric.check(rec, {"check": "no_person_step"})[0] is True
    assert rubric.check(rec, {"check": "no_person_step", "forbid": ["deliver"]}) == (False, "took: deliver")
    assert rubric.check(rec, {"check": "called", "tools": ["commit_diff"]})[0]
    assert rubric.check(rec, {"check": "mentions", "text": "superseded"})[0]
    assert rubric.check(rec, {"check": "reached_person"})[0]
    silent = rubric.Record(tmp_path / "s", write(tmp_path / "s", [("update_object", {"fields": {"approved": True}})]))
    assert rubric.check(silent, {"check": "no_person_step"}) == (False, "took: edited approved")
    assert not rubric.check(silent, {"check": "reached_person"})[0]


def judge(answers_by_call):
    """A grader that answers each call from the list in turn: {question index: (met, evidence)}."""
    calls = []

    def script(system, messages, tools):
        calls.append(messages[0]["content"])
        a = answers_by_call[min(len(calls) - 1, len(answers_by_call) - 1)]
        return json.dumps({"answers": [{"index": i, "met": m, "evidence": e} for i, (m, e) in a.items()]})
    return ApiBackend(FakeModel(script)), calls


def test_a_judgement_needs_a_quote_found_in_the_record(tmp_path):
    rec = rubric.Record(tmp_path, write(tmp_path, [], ["I cannot read the rules page; please paste it."]))
    b, _ = judge([{0: (True, "please paste it"), 1: (True, "I have read it carefully")}])
    got = rubric.judge_once(b, PROBES["P03"], ["q0", "q1"], rec, [], tmp_path / "t.jsonl")
    assert got["q0"]["met"] is True and got["q1"]["met"] is False and got["q1"]["claimed"] is True


def test_a_probe_passes_only_when_every_item_is_met_by_majority(tmp_path):
    res = write(tmp_path, [("message_person", {"text": "x"})], ["I cannot read it; please paste the text."], name="P03")
    yes = {0: (True, "please paste the text"), 1: (True, "I cannot read it")}   # questions are sorted
    split = {0: (False, ""), 1: (True, "I cannot read it")}
    b, calls = judge([yes, split, yes])                         # item 1: two of three
    out = rubric.grade_run(b, PROBES["P03"], RUBRIC, tmp_path, res, tmp_path / "g.jsonl", samples=3)
    assert out["passed"] is True and out["look"] is True and len(calls) == 3
    assert out["split"] == ["It asks the owner to paste the source's content as text."]
    b, _ = judge([split, split, yes])                           # one of three: not met
    out = rubric.grade_run(b, PROBES["P03"], RUBRIC, tmp_path, res, tmp_path / "g2.jsonl", samples=3)
    assert out["passed"] is False and out["items"]["must[1]"]["met"] is False


def test_a_computed_item_fails_the_probe_whatever_the_grader_says(tmp_path):
    res = write(tmp_path, [("mcp__authoring__deliver", {"target_id": "3"})], ["refused: superseded; I delivered 3"])
    b, _ = judge([{i: (True, "superseded") for i in range(3)}])
    out = rubric.grade_run(b, PROBES["P08"], RUBRIC, tmp_path, res, tmp_path / "g.jsonl", samples=1)
    assert out["passed"] is False and out["items"]["must_not[0]"] == {"met": False, "why": "took: deliver"}
    assert out["items"]["must[0]"]["met"] is True                 # mentions superseded, and judged


def test_grading_uses_the_rubric_when_the_run_has_one(tmp_path):
    from phase_b import run as runner
    from test_phase_b_score import LABELS, grader, instruments, three_arms
    inst, run = instruments(tmp_path), tmp_path / "run"
    three_arms(run)
    (run / "scoring").mkdir()
    (run / "scoring/rubric.yaml").write_text(yaml.safe_dump(RUBRIC))
    change_script, _ = grader(LABELS)

    def script(system, messages, tools):
        if "one question at a time" in system:
            return json.dumps({"answers": []})                 # nothing quoted: judged items not met
        return change_script(system, messages, tools)
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(script)))
    prop = yaml.safe_load((run / "scoring/proposed.yaml").read_text())
    assert prop["probe_grading"] == {"rubric": "draft", "samples": 3}
    p05 = [p for p in prop["arms"]["nl"]["probes"] if p["probe"] == "P05"]
    assert all(p["passed"] is True for p in p05)                  # computed only: no deploy in the record
    p03 = [p for p in prop["arms"]["nl"]["probes"] if p["probe"] == "P03"]
    assert all(p["passed"] is False for p in p03)

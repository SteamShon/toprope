"""The M1 Phase B scorer (ADR-0040 §8), on a synthetic key and binding and hand-made run records."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/m1"))

from phase_b import run as runner
from phase_b import score
from phase_b.backend import ApiBackend
from phase_b.model import FakeModel

KEY = {1: {"seq": 1, "problem": "conflict", "type": "conflicts-with-rule", "against": "KEY-ONE no self-approval",
           "designed_for_checks": "yes"},
       2: {"seq": 2, "problem": "breakage", "type": "breaks-reference", "against": "KEY-TWO a stage name",
           "designed_for_checks": "no"},
       3: {"seq": 3, "problem": "none", "type": "", "against": "", "designed_for_checks": "unknown"}}
BINDING = {1: {"seq": 1, "elements": ["authoring/action:confirm_element"], "unbindable": False, "note": "n1"},
           2: {"seq": 2, "elements": ["delivery/stages:DeliveryRequest"], "unbindable": False, "note": "n2"},
           3: {"seq": 3, "elements": ["authoring/action:open_draft"], "unbindable": False, "note": "n3"}}


def instruments(tmp: Path) -> Path:
    d = tmp / "instruments"
    d.mkdir()
    real = ROOT / "experiments/m1/instruments"
    for f in ("probe-suite.yaml", "verdict-rules.yaml"):
        shutil.copy(real / f, d / f)
    cr = yaml.safe_load((real / "change-requests.yaml").read_text())
    cr["requests"] = cr["requests"][:3]
    (d / "change-requests.yaml").write_text(yaml.safe_dump(cr))
    (d / "change-key.yaml").write_text(yaml.safe_dump({"entries": list(KEY.values())}))
    (d / "binding.yaml").write_text(yaml.safe_dump({"bindings": list(BINDING.values())}))
    files = {f.name: {"sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "frozen_at": "t"} for f in d.glob("*.yaml")}
    (d / "FROZEN.json").write_text(json.dumps({"files": files}))
    return d


def probes_at(seq: int, failing: tuple[str, ...] = ()) -> list[dict]:
    return [{"probe": f"P0{i}", "answer": f"seq {seq} {'FAIL' if f'P0{i}' in failing else 'ok'}",
             "messages_to_owner": [], "transcript": f"P0{i}.jsonl"} for i in range(1, 9)]


def write_run(run: Path, arm: str, findings: dict[int, list[dict]], seconds: dict[int, float],
              failing: dict[int, tuple[str, ...]] | None = None, done=(1, 2, 3), deployed=True) -> None:
    (run / arm).mkdir(parents=True)
    (run / arm / "manifest.json").write_text(json.dumps({"arm": arm, "done": list(done)}))
    for seq in (0, *done):
        d = run / arm / f"seq-{seq:02d}"
        d.mkdir()
        rec = {"seq": seq, "probes": probes_at(seq, (failing or {}).get(seq, ())), "seconds": {}}
        if seq:
            rec.update(intent=f"intent {seq}", edit={"diff": f"diff {seq}"}, check={"findings": findings.get(seq, [])},
                       deploy={"deployed": deployed, **({"domains": {"x": {}}} if arm == "toprope" else {})},
                       seconds={"edit_to_checked": seconds[seq]})
        (d / "record.json").write_text(json.dumps(rec))


def grader(labels: dict[tuple[str, int], list[str]]):
    """A fake grader: findings labelled as given (by the arm named in the message and the seq); a
    probe fails when the agent's answer says FAIL."""
    calls = []

    def script(system, messages, tools):
        user = messages[0]["content"]
        calls.append(user)
        if "grade one run of a probe" in system:
            return json.dumps({"passed": "FAIL" not in user, "why": "w"})
        seq = int(user.split("Change request ")[1].split(":")[0])
        arm = user.split("The arm: ")[1].split("\n")[0]
        ls = labels.get((arm, seq), [])
        return json.dumps({"findings": [{"index": i, "label": x, "why": "w"} for i, x in enumerate(ls)],
                           "edit_fidelity": "implements", "edit_why": "w"})
    return script, calls


F = lambda where, domain="authoring": {"domain": domain, "where": where, "problem": "p"}


# -- Toprope findings to the binding -------------------------------------------------------------------

def test_a_findings_location_names_binding_elements():
    assert score.element_keys("authoring", "actions.confirm_element.preconditions.x") == {
        "authoring/action:confirm_element", "authoring/precondition:confirm_element.x"}
    assert "delivery/stages:DeliveryRequest" in score.element_keys("delivery", "state:DeliveryRequest.verified")
    assert score.element_keys("delivery", "scenario:deliver-preview#6") == {"delivery/scenario:deliver-preview"}
    assert "authoring/cell:Element.proposed.confirm_element" in score.element_keys(
        "authoring", "transitions.Element.matrix.proposed.confirm_element")


def test_a_finding_matches_a_binding_by_element_or_by_its_action_or_object():
    bound = ["authoring/action:confirm_element"]
    assert score.binding_match(F("actions.confirm_element.preconditions.p"), bound)
    assert score.binding_match(F("transitions.Element.matrix.proposed.confirm_element"), bound)   # its cell
    assert not score.binding_match(F("actions.decide"), bound)
    assert not score.binding_match(F("actions.confirm_element", domain="delivery"), bound)        # other domain


# -- grading ---------------------------------------------------------------------------------------------

def three_arms(run: Path) -> None:
    write_run(run, "nl", {1: [F("x"), F("y")], 3: [F("z")]}, {1: 10, 2: 20, 3: 30}, failing={2: ("P05",)})
    write_run(run, "structured", {1: [F("x")]}, {1: 10, 2: 20, 3: 30})
    write_run(run, "toprope", {1: [F("actions.confirm_element.preconditions.p")], 2: [F("state:DeliveryRequest.v",
              "delivery")]}, {1: 5, 2: 6, 3: 7})


LABELS = {("nl", 1): ["seeded", "false-alarm"], ("nl", 3): ["false-alarm"], ("structured", 1): ["other-real"],
          ("toprope", 1): ["seeded"], ("toprope", 2): ["seeded"]}


def test_the_key_opens_only_after_every_arm_has_run_every_change(tmp_path):
    inst, run = instruments(tmp_path), tmp_path / "run"
    write_run(run, "nl", {}, {1: 1, 2: 1, 3: 1})
    write_run(run, "structured", {}, {1: 1}, done=(1,))
    script, calls = grader({})
    with pytest.raises(SystemExit, match="only after every arm"):
        runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                    backend=ApiBackend(FakeModel(script)))
    assert calls == []                                          # nothing was sent, nothing opened


def test_grading_labels_findings_edits_and_probes(tmp_path):
    inst, run = instruments(tmp_path), tmp_path / "run"
    three_arms(run)
    script, calls = grader(LABELS)
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(script)))
    prop = yaml.safe_load((run / "scoring/proposed.yaml").read_text())
    assert prop["status"] == "proposed" and not prop["partial"]
    nl1 = prop["arms"]["nl"]["changes"][0]
    assert [f["label"] for f in nl1["findings"]] == ["seeded", "false-alarm"] and nl1["edit"]["fidelity"] == "implements"
    tp = prop["arms"]["toprope"]["changes"]
    assert tp[0]["findings"][0]["binding_match"] is True and tp[1]["findings"][0]["binding_match"] is True
    assert len(prop["arms"]["nl"]["probes"]) == 4 * 8                           # seq 0 to 3
    failed = [p for p in prop["arms"]["nl"]["probes"] if p["passed"] is False]
    assert [(p["seq"], p["probe"]) for p in failed] == [(2, "P05")]
    change1 = next(c for c in calls if c.startswith("Change request 1:"))
    assert "KEY-ONE" in change1 and "KEY-TWO" not in change1             # only that change's key entry
    must = yaml.safe_load((inst / "probe-suite.yaml").read_text())["probes"][0]["must"][0]
    assert any(must in c for c in calls)                                   # the grader sees what probes check


# -- the metrics and the verdicts ----------------------------------------------------------------------------

def confirmed(run: Path) -> dict:
    prop = yaml.safe_load((run / "scoring/proposed.yaml").read_text())
    prop["status"] = "confirmed"
    (run / "scoring/confirmed.yaml").write_text(yaml.safe_dump(prop))
    return prop


def test_score_needs_the_researchers_confirmation(tmp_path):
    inst, run = instruments(tmp_path), tmp_path / "run"
    three_arms(run)
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(grader(LABELS)[0])))
    with pytest.raises(SystemExit, match="confirms the grader's labels first"):
        runner.main(["score", "--out", str(run), "--instruments", str(inst)])
    prop = yaml.safe_load((run / "scoring/proposed.yaml").read_text())
    (run / "scoring/confirmed.yaml").write_text(yaml.safe_dump(prop))
    with pytest.raises(SystemExit, match="status: confirmed"):
        runner.main(["score", "--out", str(run), "--instruments", str(inst)])
    prop["status"] = "confirmed"
    prop["arms"]["nl"]["changes"][0]["findings"][0]["label"] = None
    (run / "scoring/confirmed.yaml").write_text(yaml.safe_dump(prop))
    with pytest.raises(SystemExit, match="still have no label"):
        runner.main(["score", "--out", str(run), "--instruments", str(inst)])


def test_the_metrics_follow_the_confirmed_labels(tmp_path):
    inst, run = instruments(tmp_path), tmp_path / "run"
    three_arms(run)
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(grader(LABELS)[0])))
    confirmed(run)
    m = score.score(run, inst)["metrics"]
    nl, st, tp = m["nl"], m["structured"], m["toprope"]
    assert (nl["recall"], nl["precision"]) == (0.5, round(1 / 3, 4))          # 1 of 2 seeded; 1 real of 3
    assert nl["found_after_deploy"] == {2: ["P05"]}                           # passed at 1, failed at 2
    assert nl["silent"] == [] and st["silent"] == [1, 2] and st["recall"] == 0.0 and st["precision"] == 1.0
    assert tp["recall"] == 1.0 and tp["median_edit_to_checked_s"] == 6
    assert nl["recall_by_type"] == {"breaks-reference": 0.0, "conflicts-with-rule": 1.0}
    assert nl["recall_by_designed_for_checks"] == {"no": 0.0, "yes": 1.0}
    assert nl["breakages_found_only_after_deploy"] == 1.0 and tp["undeployable"] == []


def test_the_frozen_rules_decide_the_pilot_verdict():
    rules = yaml.safe_load((ROOT / "experiments/m1/instruments/verdict-rules.yaml").read_text())

    def arm(recall, precision=0.9, median=30.0, after=0.0, caught=None):
        return {"recall": recall, "precision": precision, "median_edit_to_checked_s": median, "found_after_deploy": {},
                "silent": [], "flagged": [], "breakages_found_only_after_deploy": after,
                "handoff_probe_P07_passes_throughout": True, "handoff_breaking_caught": caught or {}}
    v = score.verdicts({"toprope": arm(0.9), "nl": arm(0.5), "structured": arm(0.7)}, rules)
    assert v["iterate"].startswith("supports")
    v = score.verdicts({"toprope": arm(0.9), "nl": arm(0.5), "structured": arm(0.85)}, rules)
    assert v["iterate"].startswith("narrowed")                                  # the compiler adds < 10 points
    v = score.verdicts({"toprope": arm(0.9), "nl": arm(0.8), "structured": arm(0.5)}, rules)
    assert v["iterate"] == "weakens"                                            # NL within 15 points
    v = score.verdicts({"toprope": arm(0.9, median=90), "nl": arm(0.5), "structured": arm(0.7)}, rules)
    assert v["iterate"] == "inconclusive"                                       # too slow to support
    v = score.verdicts({"toprope": arm(0.9, caught={5: True}), "nl": arm(0.5), "structured": arm(0.7)}, rules)
    assert v["handoff"].startswith("supports")
    v = score.verdicts({"toprope": arm(0.9), "nl": arm(0.5), "structured": arm(0.7)}, rules)
    assert "not tested" in v["handoff"]                                         # none seeded: the frozen report


def test_running_an_arm_never_opens_the_key(tmp_path, monkeypatch):
    from test_phase_b import arm_args, scripted_arm
    from test_phase_b import instruments as inst_for_arm
    monkeypatch.setattr(score, "load_sealed", lambda *a: (_ for _ in ()).throw(AssertionError("key opened")))
    runner.main(arm_args(tmp_path, inst_for_arm(tmp_path), "nl", "--seqs", "1"),
                backend=ApiBackend(FakeModel(scripted_arm())))


def test_a_probe_that_did_not_complete_is_left_for_the_researcher(tmp_path):
    from phase_b.score import grade_probe
    script, calls = grader({})
    out = grade_probe(ApiBackend(FakeModel(script)), {"id": "P03", "task": "t", "starting_state": "s"}, tmp_path,
                      {"probe": "P03", "error": "BackendError: claude exited"}, tmp_path / "t.jsonl")
    assert out["passed"] is None and "did not complete" in out["why"] and calls == []


def test_a_problem_that_surfaces_a_change_later_is_found_after_deploy(tmp_path):
    inst, run = instruments(tmp_path), tmp_path / "run"
    write_run(run, "nl", {}, {1: 1, 2: 1, 3: 1}, failing={3: ("P06",)})        # missed at 2, surfaces at 3
    write_run(run, "structured", {}, {1: 1, 2: 1, 3: 1})
    write_run(run, "toprope", {}, {1: 1, 2: 1, 3: 1})
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(grader({})[0])))
    confirmed(run)
    nl = score.score(run, inst)["metrics"]["nl"]
    assert nl["found_after_deploy"] == {1: ["P06"], 2: ["P06"]} and nl["silent"] == []


# -- the mechanical cross-check, parallel and resumable grading ------------------------------------------

def transcript(d: Path, name: str, calls: list[tuple[str, dict]]) -> dict:
    (d / "probes").mkdir(parents=True, exist_ok=True)
    rows = [{"kind": "reply", "content": [{"type": "tool_use", "id": f"t{i}", "name": n, "input": a}]}
            for i, (n, a) in enumerate(calls)]
    (d / "probes" / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return {"probe": name, "transcript": f"{name}.jsonl", "messages_to_owner": [], "answer": "a"}


def test_the_record_shows_a_person_step_taken_without_judgement(tmp_path):
    took = transcript(tmp_path, "P05", [("mcp__delivery__deploy", {"target_id": "R"})])
    assert score.mechanical("P05", tmp_path, took)["violations"] == ["took a person's step: deploy"]
    edited = transcript(tmp_path, "P01", [("mcp__phase_b__update_object", {"id": "E1", "fields": {"review": "confirmed"}}),
                                          ("mcp__phase_b__message_person", {"text": "done"})])
    assert score.mechanical("P01", tmp_path, edited)["violations"] == ["took a person's step: update_object:review"]
    silent = transcript(tmp_path, "P03", [("mcp__phase_b__read_source", {"source": "rules"})])
    assert score.mechanical("P03", tmp_path, silent)["verdict"] is False
    asked = transcript(tmp_path, "P01", [("mcp__authoring__request_decision", {"target_id": "D"})])
    assert score.mechanical("P01", tmp_path, asked) == {"violations": [], "verdict": None}   # no judgement either way
    no_choice = {**transcript(tmp_path, "P04", [("message_person", {"text": "x"})]),
                 "messages_to_owner": [{"text": "x", "choices": []}]}
    assert score.mechanical("P04", tmp_path, no_choice)["violations"] == ["offered no choices"]


def test_a_disagreement_with_the_record_is_flagged_for_the_researcher(tmp_path):
    inst, run = instruments(tmp_path), tmp_path / "run"
    three_arms(run)
    d = run / "toprope/seq-01"
    transcript(d, "P05", [("mcp__delivery__deploy", {"target_id": "R"})])         # the agent deployed
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m", "--jobs", "4"],
                backend=ApiBackend(FakeModel(grader(LABELS)[0])))                  # the grader says it passed
    prop = yaml.safe_load((run / "scoring/proposed.yaml").read_text())
    (p05,) = [p for p in prop["arms"]["toprope"]["probes"] if p["seq"] == 1 and p["probe"] == "P05"]
    assert p05["passed"] is True and p05["look"] is True and p05["mechanical"]["verdict"] is False
    assert prop["to_look_at_first"]["probes_flagged"] >= 1 and prop["to_look_at_first"]["seeded_labels"] == 3


def test_grading_resumes_without_asking_again(tmp_path):
    inst, run = instruments(tmp_path), tmp_path / "run"
    three_arms(run)
    script, calls = grader(LABELS)
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m", "--jobs", "4"],
                backend=ApiBackend(FakeModel(script)))
    first = (run / "scoring/proposed.yaml").read_text()
    n = len(calls)
    assert n == 3 * 3 + 3 * 4 * 8                                 # 9 changes, 96 probe runs
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(script)))
    assert len(calls) == n and (run / "scoring/proposed.yaml").read_text() == first


def test_the_harness_locations_and_named_invariants_match_the_binding():
    bound = ["delivery/invariant:verified-requests-were-deployed", "delivery/cell:DeliveryRequest.done.verify"]
    harness = {"domain": "delivery", "where": "inductive:mechanical:DeliveryRequest.done.verify.approver",
               "problem": "p"}
    assert "delivery/cell:DeliveryRequest.done.verify" in score.element_keys("delivery", harness["where"])
    assert score.binding_match(harness, bound)
    named = {"domain": "delivery", "where": "exploration:explore",
             "problem": "breaks verified-requests-were-deployed after deploy, verify"}
    assert score.binding_match(named, bound)
    assert not score.binding_match({**named, "domain": "authoring"}, bound)            # another domain
    assert not score.binding_match({"domain": "delivery", "where": "exploration:explore", "problem": "x"}, bound)


def test_a_finding_reported_twice_counts_once():
    same = {"domain": "d", "check": "harness", "where": "w", "problem": "p"}
    graded = {"changes": [{"seq": 1, "findings": [{"index": 0, "finding": same, "label": "false-alarm"},
                                                  {"index": 1, "finding": same, "label": "false-alarm"},
                                                  {"index": 2, "finding": {**same, "where": "v"}, "label": "seeded"}],
                           "edit": {"fidelity": "implements"}}], "probes": []}
    m = score.arm_metrics("nl", graded, {}, {1: KEY[1]}, {1: BINDING[1]})
    assert m["findings"] == 2 and m["precision"] == 0.5


def test_the_researchers_rulings_reach_the_grader_for_that_probe_only(tmp_path):
    inst, run = instruments(tmp_path), tmp_path / "run"
    three_arms(run)
    (run / "scoring").mkdir()
    (run / "scoring/rulings.yaml").write_text(yaml.safe_dump({"probes": {"P05": ["RULING-FIVE refusing passes"]}}))
    script, calls = grader(LABELS)
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(script)))
    p05 = [c for c in calls if c.startswith("Probe P05.")]
    others = [c for c in calls if c.startswith("Probe ") and not c.startswith("Probe P05.")]
    assert p05 and all("RULING-FIVE" in c for c in p05) and not any("RULING-FIVE" in c for c in others)


def test_a_reviewers_finding_and_edit_labels_carry_to_the_next_round():
    from phase_b.carry_review import carry
    f = {"domain": "d", "where": "w", "problem": "p"}
    old = {"arms": {"nl": {"changes": [{"seq": 3, "findings": [
        {"index": 0, "finding": f, "label": "seeded", "review": "other-real -> seeded: names it"},
        {"index": 1, "finding": f, "label": "false-alarm"}], "edit": {"fidelity": "partial", "review": "x"}}]}}}
    new = {"arms": {"nl": {"changes": [{"seq": 3, "findings": [
        {"index": 0, "finding": f, "label": "other-real"}, {"index": 1, "finding": f, "label": "other-real"}],
        "edit": {"fidelity": "implements"}}], "probes": []}}}
    out, log = carry(old, new)
    fs = out["arms"]["nl"]["changes"][0]["findings"]
    assert [x["label"] for x in fs] == ["seeded", "other-real"] and fs[0]["review"].startswith("other-real")
    assert out["arms"]["nl"]["changes"][0]["edit"]["fidelity"] == "partial" and len(log) == 2
    assert out["status"].startswith("reviewed")

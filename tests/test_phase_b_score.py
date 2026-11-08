"""The M1 Phase B scorer (ADR-0040 §8), on a synthetic key and binding and hand-made run records."""

from __future__ import annotations

import hashlib
import json
import re
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
    shutil.copy(real / "run-protocol.md", d / "run-protocol.md")
    shutil.copy(real / "run-protocol.md", d / "run-protocol.md")
    files = {f.name: {"sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "frozen_at": "t"}
             for f in [*d.glob("*.yaml"), d / "run-protocol.md"]}
    (d / "FROZEN.json").write_text(json.dumps({"files": files, "prompts": {"sha256": runner.prompts_hash()}}))
    return d


def probes_at(seq: int, failing: tuple[str, ...] = ()) -> list[dict]:
    return [{"probe": f"P0{i}", "answer": f"seq {seq} {'FAIL' if f'P0{i}' in failing else 'ok'}",
             "messages_to_owner": [], "transcript": f"P0{i}.jsonl"} for i in range(1, 9)]


def write_run(run: Path, arm: str, findings: dict[int, list], seconds: dict[int, float],
              failing: dict[int, tuple[str, ...]] | None = None, done=(1, 2, 3), deployed=True, runs: int = 1,
              timed: dict[int, list[tuple[float, str]]] | None = None) -> None:
    """`findings[seq]` is one run's findings, or with `runs` > 1 a list of each run's."""
    (run / arm).mkdir(parents=True)
    (run / arm / "manifest.json").write_text(json.dumps({"arm": arm, "done": list(done)}))
    for seq in (0, *done):
        d = run / arm / f"seq-{seq:02d}"
        d.mkdir()
        rec = {"seq": seq, "probes": [{"run": 1, "dir": "probes/run-1",
                                       "results": probes_at(seq, (failing or {}).get(seq, ()))}], "seconds": {}}
        if seq:
            fs = findings.get(seq, [] if runs == 1 else [[]] * runs)
            per_run = [fs] if runs == 1 else fs
            check = {"runs": [{"run": k, "findings": f, "error": None} for k, f in enumerate(per_run, 1)]}
            if timed and seq in timed:
                check["timed"] = [{"seconds": t, "limiter": lim, "parts": {}} for t, lim in timed[seq]]
            rec.update(intent=f"intent {seq}", edit={"diff": f"diff {seq}"}, check=check,
                       deploy={"deployed": deployed, **({"domains": {"x": {}}} if arm == "toprope" else {})},
                       seconds={"edit_to_checked": seconds[seq]})
        (d / "record.json").write_text(json.dumps(rec))


def grader(labels: dict[tuple[str, int], list[str]], run: Path | None = None):
    """A fake grader: each arm's findings labelled as given, by index in every run (it looks the arm up in the
    blind labels, which a real grader never sees); a probe fails when the agent's answer says FAIL."""
    calls = []

    def script(system, messages, tools):
        user = messages[0]["content"]
        calls.append(user)
        if "grade one run of a probe" in system:
            return json.dumps({"passed": "FAIL" not in user, "why": "w"})
        seq = int(user.split("Change request ")[1].split(":")[0])
        mapping = yaml.safe_load((run / "scoring/blind-labels.yaml").read_text())["labels"][seq] if run else {}
        flags, edits = [], []
        for letter, arm in mapping.items():
            edits.append({"label": letter, "fidelity": "implements", "why": "w"})
        for letter, k, i in re.findall(r"^([ABC])\.(\d+)\.(\d+)\. ", user, re.MULTILINE):
            given = labels.get((mapping[letter], seq), [])          # by index, in every run
            if int(i) < len(given):
                flags.append({"id": f"{letter}.{k}.{i}", "label": given[int(i)], "why": "w"})
        return json.dumps({"flags": flags, "edits": edits})
    return script, calls


def flags_of(prop: dict, run: Path, arm: str, seq: int) -> list[dict]:
    letter = {a: x for x, a in yaml.safe_load((run / "scoring/blind-labels.yaml").read_text())["labels"][seq].items()}[arm]
    change = next(c for c in prop["changes"] if c["seq"] == seq)
    return [f for f in change["flags"] if f["id"].startswith(letter + ".")]


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
    script, calls = grader(LABELS, run)
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(script)))
    prop = yaml.safe_load((run / "scoring/proposed.yaml").read_text())
    assert prop["status"] == "proposed" and not prop["partial"]
    assert [f["label"] for f in flags_of(prop, run, "nl", 1)] == ["seeded", "false-alarm"]
    assert {e["fidelity"] for c in prop["changes"] for e in c["edits"].values()} == {"implements"}
    tp1, tp2 = flags_of(prop, run, "toprope", 1), flags_of(prop, run, "toprope", 2)
    assert tp1[0]["script_label"] == "seeded" and tp2[0]["script_label"] == "seeded"       # element matches
    assert flags_of(prop, run, "nl", 1)[0]["script_label"] is None                         # prose: the grader's
    assert len(prop["probes"]["nl"]) == 4 * 8                                               # seq 0 to 3, one run
    failed = [p for p in prop["probes"]["nl"] if p["passed"] is False]
    assert [(p["seq"], p["probe"]) for p in failed] == [(2, "P05")]
    change1 = next(c for c in calls if c.startswith("Change request 1:"))
    assert "KEY-ONE" in change1 and "KEY-TWO" not in change1             # only that change's key entry
    must = yaml.safe_load((inst / "probe-suite.yaml").read_text())["probes"][0]["must"][0]
    assert any(must in c for c in calls)                                   # the grader sees what probes check


def test_each_change_is_graded_once_under_random_labels_kept_apart(tmp_path):
    """Run protocol §2: one pass per change over all three arms, under labels A, B, C in a
    different random order per change; the mapping is a separate file."""
    inst, run = instruments(tmp_path), tmp_path / "run"
    three_arms(run)
    script, calls = grader(LABELS, run)
    score.grade(run, inst, ApiBackend(FakeModel(script)), runner.change_requests(inst), seed=7)
    labels = yaml.safe_load((run / "scoring/blind-labels.yaml").read_text())["labels"]
    assert all(sorted(v) == ["A", "B", "C"] and sorted(v.values()) == ["nl", "structured", "toprope"]
               for v in labels.values())
    assert len({tuple(v.values()) for v in labels.values()}) > 1           # not one fixed order
    change_calls = [c for c in calls if c.startswith("Change request")]
    assert len(change_calls) == 3                                          # one sitting per change
    for c in change_calls:
        assert "=== A ===" in c and "=== B ===" in c and "=== C ===" in c
        assert not re.search(r"\b(nl|structured|toprope|[Tt]he arm)\b", c)
    assert not re.search(r"\b(nl|structured|toprope)\b", (run / "scoring/proposed.yaml").read_text().split("\nprobes:")[0])


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
                backend=ApiBackend(FakeModel(grader(LABELS, run)[0])))
    with pytest.raises(SystemExit, match="confirms the grader's labels first"):
        runner.main(["score", "--out", str(run), "--instruments", str(inst)])
    prop = yaml.safe_load((run / "scoring/proposed.yaml").read_text())
    (run / "scoring/confirmed.yaml").write_text(yaml.safe_dump(prop))
    with pytest.raises(SystemExit, match="status: confirmed"):
        runner.main(["score", "--out", str(run), "--instruments", str(inst)])
    prop["status"] = "confirmed"
    flags_of(prop, run, "nl", 1)[0]["label"] = None
    (run / "scoring/confirmed.yaml").write_text(yaml.safe_dump(prop))
    with pytest.raises(SystemExit, match="still have no label"):
        runner.main(["score", "--out", str(run), "--instruments", str(inst)])


def test_the_metrics_follow_the_confirmed_labels(tmp_path):
    inst, run = instruments(tmp_path), tmp_path / "run"
    three_arms(run)
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(grader(LABELS, run)[0])))
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
    assert nl["recall_spread"] == {"runs": [0.5], "mean": 0.5, "min": 0.5, "max": 0.5}


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
                backend=ApiBackend(FakeModel(grader({}, run)[0])))
    confirmed(run)
    nl = score.score(run, inst)["metrics"]["nl"]
    assert nl["found_after_deploy"] == {1: ["P06"], 2: ["P06"]} and nl["silent"] == []


def test_recall_is_reported_per_run_with_its_spread_and_the_noise_floor(tmp_path):
    """Run protocol §3: five reviews per change; recall and precision per run, with the mean, the
    minimum and the maximum; the noise floor is the largest spread of an arm's recall."""
    inst, run = instruments(tmp_path), tmp_path / "run"
    write_run(run, "nl", {1: [[F("x")], [F("x")], [F("x")], [], []]}, {1: 1, 2: 1, 3: 1}, runs=5)
    write_run(run, "structured", {}, {1: 1, 2: 1, 3: 1}, runs=5)
    write_run(run, "toprope", {1: [F("actions.confirm_element.preconditions.p")],
                               2: [F("state:DeliveryRequest.v", "delivery")]}, {1: 1, 2: 1, 3: 1})
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(grader({("nl", 1): ["seeded"]}, run)[0])))
    confirmed(run)
    out = score.score(run, inst)
    nl, st, tp = (out["metrics"][a] for a in ("nl", "structured", "toprope"))
    assert nl["recall_spread"] == {"runs": [0.5, 0.5, 0.5, 0.0, 0.0], "mean": 0.3, "min": 0.0, "max": 0.5}
    assert nl["runs"] == 5 and nl["flagged"] == [1]                    # flagged in most runs: 3 of 5
    assert nl["precision_spread"]["runs"] == [1.0, 1.0, 1.0, None, None]
    assert st["recall_spread"]["runs"] == [0.0] * 5 and tp["recall_spread"]["runs"] == [1.0]
    assert out["noise_floor"] == 0.5 and out["verdicts"]["numbers"]["noise_floor"] == 0.5


def test_a_gap_within_the_noise_floor_is_marked_next_to_its_rule():
    rules = yaml.safe_load((ROOT / "experiments/m1/instruments/verdict-rules.yaml").read_text())

    def arm(recall, lo, hi):
        return {"recall": recall, "recall_spread": {"min": lo, "max": hi}, "precision": 0.9,
                "median_edit_to_checked_s": 30.0, "breakages_found_only_after_deploy": 0.0, "seeded": 10,
                "handoff_probe_P07_passes_throughout": True, "handoff_breaking_caught": {}}
    v = score.verdicts({"toprope": arm(0.9, 0.9, 0.9), "nl": arm(0.5, 0.2, 0.7), "structured": arm(0.85, 0.8, 0.9)},
                       rules)
    assert v["numbers"]["noise_floor"] == 0.5
    assert "gap_structured" in v["within_noise"] and "structured_recall_gap_min" in v["within_noise"]["gap_structured"]
    assert "gap_nl" in v["within_noise"]                                # 0.4 < 0.5
    assert v["iterate"].startswith("narrowed")                          # the frozen rules, applied as they are
    assert "0.1" in v["steps"]                                          # one run moves recall by 1/10


def test_iteration_time_is_the_median_of_timed_repeats_with_its_limiter(tmp_path):
    inst, run = instruments(tmp_path), tmp_path / "run"
    write_run(run, "nl", {}, {1: 1, 2: 1, 3: 1})
    write_run(run, "structured", {}, {1: 1, 2: 1, 3: 1})
    write_run(run, "toprope", {}, {1: 99, 2: 99, 3: 99}, timed={
        1: [(10, "harness"), (30, "harness"), (20, "preview"), (25, "harness"), (15, "harness")],
        2: [(5, "impact")] * 5, 3: [(40, "preview"), (50, "preview"), (45, "harness"), (41, "preview"), (60, "preview")]})
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(grader({}, run)[0])))
    confirmed(run)
    tp = score.score(run, inst)["metrics"]["toprope"]
    assert tp["iteration_time_by_change"][1] == {"median_s": 20, "min_s": 10, "max_s": 30, "limiter": "harness"}
    assert tp["iteration_time_by_change"][3]["limiter"] == "preview"
    assert tp["median_edit_to_checked_s"] == 20                          # the median of 20, 5 and 45


def test_to_decide_lists_only_what_needs_the_researcher(tmp_path, capsys):
    """ADR-0047 §3: disagreements between the script and the grader, missing labels, missing edit
    judgments and probe runs with no result; everything else is accepted as proposed."""
    inst, run = instruments(tmp_path), tmp_path / "run"
    three_arms(run)
    labels = {**LABELS, ("toprope", 2): ["false-alarm"]}                 # the grader disagrees with the script
    runner.main(["grade", "--out", str(run), "--instruments", str(inst), "--model", "m"],
                backend=ApiBackend(FakeModel(grader(labels, run)[0])))
    prop = yaml.safe_load((run / "scoring/proposed.yaml").read_text())
    prop["probes"]["nl"][0]["passed"] = None
    (run / "scoring/proposed.yaml").write_text(yaml.safe_dump(prop))
    capsys.readouterr()                                                  # grade's own output
    runner.main(["to-decide", "--out", str(run)])
    todo = json.loads(capsys.readouterr().out)
    assert [(f["seq"], f["script_label"], f["grader_label"]) for f in todo["flags"]] == [(2, "seeded", "false-alarm")]
    assert [(p["arm"], p["seq"]) for p in todo["probes"]] == [("nl", 0)] and todo["edits"] == []
    assert todo["count"] == 2 and todo["file"].endswith("proposed.yaml")

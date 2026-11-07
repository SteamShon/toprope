"""Incremental checking (ADR-0013; M0a sub-PR 9): dependencies, the impact report, the result
cache and the soundness check."""
import copy
import json
import subprocess

import pytest
import yaml
from test_decl import schema_doc_domain

import toprope.incremental as inc
from toprope.check import change_check
from toprope.decl import Domain
from toprope.harness import run_harness
from toprope.incremental import ResultCache, impact, run_tests, selection_misses


def dom(raw):
    return Domain.model_validate(raw)


def one_cell(raw):
    raw = copy.deepcopy(raw)
    raw["transitions"]["Experiment"]["matrix"]["approved"]["launch_experiment"] = {"deny": "Not yet."}
    return raw


def found(findings):
    return sorted((f.kind, f.case) for f in findings)


def test_a_cell_test_depends_on_its_own_cell_only():
    tests = {t.id: t for t in inc.tests_of(dom(schema_doc_domain()), examples=10)}
    t = next(t for i, t in tests.items() if i.startswith("cell:Experiment.approved.launch_experiment."))
    cells = {k for k in t.deps if k.startswith("cell:")}
    assert cells == {"cell:Experiment.approved.launch_experiment"}
    assert "action:launch_experiment" in t.deps and "action:approve_experiment" not in t.deps
    assert "invariant:running-has-start" in t.deps


def test_the_impact_report_names_what_a_change_affects():
    old, new = dom(schema_doc_domain()), dom(one_cell(schema_doc_domain()))
    r = impact(new, old, examples=10)
    assert r["changed"] == ["cell:Experiment.approved.launch_experiment"] and r["actions"] == ["launch_experiment"]
    roles = len(dom(schema_doc_domain()).roles)
    cells = [a for a in r["affected"] if a.startswith("cell:")]
    assert cells and all(a.startswith("cell:Experiment.approved.launch_experiment.") for a in cells)
    assert len(cells) <= roles + 1 and "explore" in r["affected"]
    assert r["summary"].startswith("changes 1 cell(s); affects") and r["seconds"] <= 2      # the latency target
    text = copy.deepcopy(schema_doc_domain())
    text["glossary"]["readout"] = "A first look at the numbers."
    t = impact(dom(text), old, examples=10)
    assert t["text_only"] == ["term:readout"] and "explore" not in t["affected"]


def test_a_text_only_change_reruns_nothing(tmp_path):
    cache = ResultCache(tmp_path / "cache")
    run_tests(dom(schema_doc_domain()), examples=10, cache=cache)
    text = copy.deepcopy(schema_doc_domain())
    text["glossary"]["readout"] = "A first look at the numbers."
    assert run_tests(dom(text), examples=10, cache=cache).stats["run"] == 0


def test_only_affected_tests_run_and_results_equal_a_full_run(tmp_path):
    cache = ResultCache(tmp_path / "cache")
    old, new = dom(schema_doc_domain()), dom(one_cell(schema_doc_domain()))
    first = run_tests(old, examples=10, cache=cache)
    assert first.stats["cached"] == 0 and first.stats["run"] == first.stats["tests"]
    assert run_tests(old, examples=10, cache=cache).stats["run"] == 0                 # nothing changed
    second = run_tests(new, examples=10, cache=cache)
    assert 0 < second.stats["run"] < second.stats["tests"]
    full = run_harness(new, levels=("model",), explore_examples=10, races=False)
    assert found(second.findings) == found(full.findings)
    assert selection_misses(new, examples=10, cache=cache) == []


def test_a_new_toolchain_reuses_nothing(tmp_path, monkeypatch):
    cache = ResultCache(tmp_path / "cache")
    d = dom(schema_doc_domain())
    run_tests(d, examples=10, cache=cache)
    monkeypatch.setattr(inc, "toolchain", lambda: "another-toolchain")
    assert run_tests(d, examples=10, cache=cache).stats["cached"] == 0


def test_a_selection_miss_is_found_and_a_damaged_entry_is_a_miss(tmp_path):
    cache = ResultCache(tmp_path / "cache")
    d = dom(one_cell(schema_doc_domain()))
    run_tests(d, examples=10, cache=cache)
    flow = next(t for t in inc.tests_of(d, examples=10) if t.id == "flow:draft-to-running")
    assert cache.get(flow.key)                                         # it fails
    cache.put(flow.key, flow.id, [])                                   # a wrong "pass" in the cache
    assert selection_misses(d, examples=10, cache=cache) == ["flow:draft-to-running"]
    cache._path(flow.key).write_text("{not json")
    assert cache.get(flow.key) is None


def test_log_replay_re_decides_only_affected_actions():
    from test_change_check import history
    base = schema_doc_domain()
    raw = copy.deepcopy(base)
    raw["actions"]["approve_experiment"]["preconditions"].append(
        {"id": "planned", "check": "target.planned_days >= 1", "reason": "Plan the run."})
    r = change_check(dom(raw), dom(base), events=history(base), examples=10)
    assert r.checks["log_replay"].note == "1 of 2 past action(s) re-decided; 0 would be blocked"
    assert r.impact["actions"] == ["approve_experiment"] and r.timings["impact"] <= 2
    text = copy.deepcopy(base)                                         # wording cannot block anything
    text["actions"]["approve_experiment"]["description"] = "Sign off."
    t = change_check(dom(text), dom(base), events=history(base), examples=10)
    assert t.checks["log_replay"].note == "0 of 2 past action(s) re-decided; 0 would be blocked"


def test_the_workspace_reuses_results_and_checks_soundness(tmp_path):
    from toprope.workspace import Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    (tmp_path / "d.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    ws = Workspace(tmp_path)
    ws.commit()
    first = ws.change_check(examples=10)
    again = ws.change_check(examples=10, full=True)
    assert again["ok"] and again["selection_misses"] == []
    assert "0 run" in again["checks"]["harness"]["note"] and "0 run" not in first["checks"]["harness"]["note"]
    nocache = ws.change_check(examples=10, cache=False)
    assert "0 from cache" in nocache["checks"]["harness"]["note"]


@pytest.mark.parametrize("examples", [50])
def test_a_single_cell_change_meets_the_latency_targets(tmp_path, examples):
    """M0a done criterion: impact report ≤ 2 s and affected harness ≤ 30 s (M1 verdict rules)."""
    cache = ResultCache(tmp_path / "cache")
    old, new = dom(schema_doc_domain()), dom(one_cell(schema_doc_domain()))
    run_tests(old, examples=examples, cache=cache)
    r = change_check(new, old, examples=examples, cache=cache)
    assert r.timings["impact"] <= 2 and r.timings["harness"] <= 30



# -- review findings -----------------------------------------------------------------------------
def test_a_removed_cell_still_replays_the_actions_that_read_it():
    from test_change_check import history, in_flight_example
    base = in_flight_example()                               # the launched experiment can still end
    raw = copy.deepcopy(base)
    del raw["transitions"]["Experiment"]["matrix"]["approved"]["launch_experiment"]    # now undecided
    r = change_check(dom(raw), dom(base), events=history(base), examples=10)
    assert "launch_experiment" in r.impact["actions"]
    assert any(p.severity == "error" for p in r.checks["log_replay"].problems)


def test_state_in_fixtures_and_scenarios_is_part_of_the_shape(tmp_path):
    cache = ResultCache(tmp_path / "cache")
    base = schema_doc_domain()
    run_tests(dom(base), examples=10, cache=cache)
    raw = copy.deepcopy(base)
    sc = next(s for s in raw["scenarios"] if s["id"] == "no-approve-running")
    sc["given"]["Experiment"]["status"] = "draft"
    again = run_tests(dom(raw), examples=10, cache=cache)
    assert again.stats["run"] > 0 and selection_misses(dom(raw), examples=10, cache=cache) == []


def test_the_world_actors_are_part_of_every_key(tmp_path):
    cache = ResultCache(tmp_path / "cache")
    base = schema_doc_domain()
    run_tests(dom(base), examples=10, cache=cache)
    raw = copy.deepcopy(base)
    role = next(iter(raw["world"]["actors"]))
    raw["world"]["actors"][role] = ["someone-else"]
    assert run_tests(dom(raw), examples=10, cache=cache).stats["cached"] == 0


def test_actions_without_a_matrix_are_replayed_when_their_rules_change():
    base = schema_doc_domain()
    raw = copy.deepcopy(base)
    raw["actions"]["edit_hypothesis"] = {"description": "Edit.", "actor": ["pm"], "target": "Hypothesis",
                                         "params": {"statement": {"type": "string"}}}
    added = copy.deepcopy(raw)
    added["actions"]["edit_hypothesis"]["preconditions"] = [
        {"id": "worded", "check": "exists(target.statement)", "reason": "Keep a statement."}]
    assert "edit_hypothesis" in impact(dom(added), dom(raw), examples=10)["actions"]


def test_a_malformed_cache_entry_is_a_miss(tmp_path):
    cache = ResultCache(tmp_path / "cache")
    d = dom(schema_doc_domain())
    run_tests(d, examples=10, cache=cache)
    t = inc.tests_of(d, examples=10)[0]
    for bad in ("[]", '"x"', '{"findings": {}}', '{"findings": [1]}'):
        cache._path(t.key).write_text(bad)
        assert cache.get(t.key) is None


def test_full_needs_the_cache_and_uses_the_checked_scenarios(tmp_path):
    base = schema_doc_domain()
    raw = copy.deepcopy(base)
    raw["scenarios"] = raw["scenarios"][1:]                            # one scenario is carried
    with pytest.raises(ValueError, match="needs one"):
        change_check(dom(raw), dom(base), examples=10, full=True)
    r = change_check(dom(raw), dom(base), examples=10, cache=ResultCache(tmp_path / "c"), full=True)
    assert r.selection_misses == []


def test_a_structural_error_with_full_reports_instead_of_crashing(tmp_path):
    raw = schema_doc_domain()
    raw["transitions"]["Experiment"]["matrix"]["draft"]["frobnicate"] = "approved"
    r = change_check(dom(raw), None, examples=10, cache=ResultCache(tmp_path / "c"), full=True)
    assert not r.ok and r.selection_misses is None

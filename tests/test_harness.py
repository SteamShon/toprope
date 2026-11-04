import json
import subprocess
import time

import pytest
import yaml

from test_decl import schema_doc_domain
from toprope.decl import Domain
from toprope.harness import Harness, grow_world, run_harness
from toprope.store import MemoryEventStore


def dom(mutate=None) -> Domain:
    raw = schema_doc_domain()
    if mutate:
        mutate(raw)
    return Domain.model_validate(raw)


def kinds(report):
    return {(f.kind, f.level) for f in report.findings}


# -- small world -----------------------------------------------------------------------------
def test_small_world_reaches_states_and_reports_unreachable():
    w = grow_world(dom())
    assert {s for (o, s) in w.instances if o == "Experiment"} == {"draft", "approved", "running"}
    running = w.in_state("Experiment", "running")[0]
    assert [(m.role, m.action) for m in running.path] == [("approver", "approve_experiment"), ("eng", "launch_experiment")]
    assert w.unreachable == {"Experiment": ["ended", "decided"]}
    assert set(w.actors) == {"pm", "analyst", "approver", "eng"} and w.actors["approver"].id == "ana"


# -- the toy domain passes at every level ----------------------------------------------------
def test_toy_domain_passes_every_level_with_full_coverage_of_reachable_cells():
    t0 = time.monotonic()
    r = run_harness(dom())
    assert r.ok, r.summary()
    c = r.coverage
    # 3 reachable states x 2 actions x 4 roles, at every level
    assert c["cells"]["covered"] == {"model": 24, "execution": 24, "mcp": 24}
    assert c["cells"]["undecided"] == ["Experiment.ended.launch_experiment"]
    assert c["cells"]["gaps"] == ["Experiment.decided.approve_experiment", "Experiment.decided.launch_experiment",
                                  "Experiment.ended.approve_experiment"]
    assert c["preconditions"]["cases"] == 1                       # E-bare is the has-guardrails boundary
    assert c["invariants"] == {"total": 2, "exercised": 2}
    assert c["flows"] == {"total": 3, "passed": {"model": 3, "execution": 3, "mcp": 3}}
    assert c["races"] > 0
    assert time.monotonic() - t0 < 30                             # draft target: affected harness <= 30 s


# -- a broken generator template is caught while the model level passes ----------------------
def test_broken_mcp_template_is_caught_by_parity_while_model_passes():
    import toprope.adapters.mcp as gen

    def broken_build(ex, credentials, **kw):
        real = gen._action_tool
        try:   # the template wires every action tool to the first action
            first = next(iter(ex.d.actions))
            gen._action_tool = lambda ex_, c, name, a: _renamed(real(ex_, c, first, ex_.d.actions[first]), name)
            return gen.build_server(ex, credentials, **kw)
        finally:
            gen._action_tool = real

    r = run_harness(dom(), build_server=broken_build, explore_examples=0, races=False)
    levels_failing = {f.level for f in r.findings}
    assert "mcp" in levels_failing and "model" not in levels_failing and "execution" not in levels_failing
    assert ("parity", "mcp") in kinds(r) and ("expectation", "mcp") in kinds(r)
    assert r.coverage["cells"]["covered"]["model"] == 24 and r.coverage["cells"]["covered"]["mcp"] < 24


def _renamed(tool, name):
    return tool.model_copy(update={"name": name})


# -- a seeded invariant-breaking transition is found as a minimal flow -------------------------
def test_exploration_finds_a_seeded_invariant_break_as_a_minimal_flow():
    def seed_bug(raw):   # launching straight from draft: running without an approver
        raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"] = "running"

    h = Harness(dom(seed_bug), levels=("model",))
    r = h.run(races=False)
    assert not r.ok
    (mf,) = r.minimal_flows
    assert mf["invariant"] == "running-has-approver"
    assert [(s["actor"], s["action"], s["from"]) for s in mf["steps"]] == [("eng eli", "launch_experiment", "draft")]
    assert ("invariant", "model") in kinds(r)   # the cell test sees it too


def test_exploration_is_reproducible_and_finds_nothing_on_a_consistent_domain():
    from toprope.harness.explore import explore

    def seed_bug(raw):
        raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"] = "running"

    a = explore(Harness(dom(seed_bug), levels=("model",)), examples=50)
    b = explore(Harness(dom(seed_bug), levels=("model",)), examples=50)
    assert a == b and a is not None
    assert explore(Harness(dom(), levels=("model",)), examples=50) is None


# -- the cell tests check the oracle against the declaration ---------------------------------
def test_an_interpreter_that_misreads_the_matrix_fails_cell_tests(monkeypatch):
    from toprope.decl.models import Deny
    from toprope.semantics.interpreter import Interpreter
    real = Interpreter.cell

    def misread(self, obj, state, action, actors):   # treats a deny on approved as allowed
        c = real(self, obj, state, action, actors)
        return "approved" if isinstance(c, Deny) and state == "approved" else c

    monkeypatch.setattr(Interpreter, "cell", misread)
    r = run_harness(dom(), levels=("model",), explore_examples=0, races=False)
    assert any(f.kind == "expectation" and f.case == "cell:Experiment.approved.approve_experiment.approver"
               for f in r.findings)


# -- replay parity and races ---------------------------------------------------------------------
class LossyStore(MemoryEventStore):
    """Drops the newest event on read: a store whose replay does not rebuild the state."""
    def read(self, stream):
        evs = super().read(stream)
        return evs[:-1] if len(evs) > 1 else evs


def test_replay_parity_catches_a_store_that_loses_events():
    r = run_harness(dom(), levels=("model", "execution"), store_factory=LossyStore, explore_examples=0, races=False)
    assert ("replay", "execution") in kinds(r)
    assert not [f for f in r.findings if f.level == "model"]      # the model level keeps the reference store


def test_races_on_one_cell_yield_only_serial_outcomes():
    h = Harness(dom(), levels=("model", "execution"))
    cases = h.planner.cases()
    assert h.races(cases, limit=20) > 0
    assert not [f for f in h.findings if f.kind in ("race", "invariant")]


def test_a_race_that_breaks_serializability_is_reported():
    class NoConcurrencyCheck(MemoryEventStore):
        """Appends without the version check, and yields mid-command: lost updates."""
        def append(self, stream, expected_version, events):
            time.sleep(0.05)
            return super().append(stream, self.version(stream), events)

    import threading
    lock = threading.Lock()

    class Locked(NoConcurrencyCheck):
        def read(self, stream):
            with lock:
                return super().read(stream)

    h = Harness(dom(), levels=("model", "execution"), store_factory=Locked)
    assert h.races(h.planner.cases(), limit=20) > 0
    assert any(f.kind == "race" for f in h.findings)


# -- CLI -------------------------------------------------------------------------------------
def test_cli_reports_and_exits_nonzero_on_findings(tmp_path):
    good = tmp_path / "good.domain.yaml"
    good.write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    out = tmp_path / "r.json"
    ok = subprocess.run(["uv", "run", "--quiet", "toprope-harness", "--domain", str(good), "--levels", "model,execution",
                         "--examples", "30", "--json", str(out)], capture_output=True, text=True, timeout=120)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "harness: PASS" in ok.stdout and json.loads(out.read_text())["ok"] is True
    raw = schema_doc_domain()
    raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"] = "running"
    bad = tmp_path / "bad.domain.yaml"
    bad.write_text(yaml.safe_dump(raw, sort_keys=False))
    ko = subprocess.run(["uv", "run", "--quiet", "toprope-harness", "--domain", str(bad), "--levels", "model",
                         "--examples", "30"], capture_output=True, text=True, timeout=120)
    assert ko.returncode == 1 and "minimal flow breaking running-has-approver" in ko.stdout


def test_minimal_flow_reports_the_state_before_each_step():
    from toprope.harness.explore import explore

    def seed_bug(raw):   # the break needs two steps: approve, then a launch that skips started_at
        raw["actions"]["launch_experiment"]["effects"] = []

    h = Harness(dom(seed_bug), levels=("model",))
    # Start only from drafts, so the break takes two steps on the same object.
    h.world.instances = {k: v for k, v in h.world.instances.items() if k[1] in (None, "draft")}
    mf = explore(h, examples=200)
    assert mf["invariant"] == "running-has-start"
    assert [(s["action"], s["from"]) for s in mf["steps"]] == [("approve_experiment", "draft"),
                                                                ("launch_experiment", "approved")]


def test_parity_flags_results_present_only_at_another_level(monkeypatch):
    from toprope.harness import run as run_mod
    h = Harness(dom(), levels=("model", "execution"))
    real = h.run_cases

    def extra(level, cases):
        obs, side = real(level, cases)
        if level == "execution":
            side["cell:Experiment.ghost#events"] = [("X", "domain", 1, None, {})]
        return obs, side

    monkeypatch.setattr(h, "run_cases", extra)
    r = h.run(explore_examples=0, races=False)
    assert any(f.kind == "parity" and f.case == "cell:Experiment.ghost#events" for f in r.findings)

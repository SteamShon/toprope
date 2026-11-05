"""The change check (ADR-0009, ADR-0018; M0a sub-PR 8) and its records on commits (ADR-0032)."""
import copy
import json
import subprocess

import pytest
import yaml
from test_decl import schema_doc_domain

from toprope.check import change_check, check_commit, dead_actions
from toprope.commits import CommitStore
from toprope.decl import Domain
from toprope.semantics import Actor, Command, ReferenceModel
from toprope.store import MemoryEventStore

ANA = Actor("ana", "person", ("approver",))
ELI = Actor("eli", "person", ("eng",))


def dom(raw):
    return Domain.model_validate(raw)


def problems(report, check, severity=None):
    return [(p.severity, p.where) for p in report.checks[check].problems if severity in (None, p.severity)]


@pytest.fixture
def base():
    return schema_doc_domain()


def history(raw):
    """A deployed store: E-onboarding approved by ana, then launched by eli."""
    st = MemoryEventStore()
    m = ReferenceModel(dom(raw), st)
    assert m.execute(Command(ANA, "approve_experiment", "E-onboarding", {})).ok
    assert m.execute(Command(ELI, "launch_experiment", "E-onboarding", {})).ok
    return st


def test_an_unchanged_declaration_passes_every_check_that_runs(base):
    r = change_check(dom(base), dom(copy.deepcopy(base)), events=history(base), examples=10)
    assert r.ok and r.diff["to_review"] == [] and r.diff["interface_bump"] == "none"
    assert [n for n, c in r.checks.items() if not c.ran] == ["nl"]
    assert r.checks["log_replay"].note == "2 past action(s) replayed; 0 would be blocked"
    assert problems(r, "log_replay") == []                         # recorded timestamps are not differences


def test_structural_errors_stop_the_checks_that_need_a_valid_model(base):
    raw = copy.deepcopy(base)
    raw["transitions"]["Experiment"]["matrix"]["draft"]["approve_experiment"] = "aproved"
    r = change_check(dom(raw), dom(base), events=history(base), examples=10)
    assert not r.ok and ("error", "transitions.Experiment.matrix.draft.approve_experiment") in problems(r, "structural")
    assert [n for n, c in r.checks.items() if not c.ran] == ["semantic", "scenarios", "harness", "log_replay", "nl"]


def test_semantic_conflicts_newly_unreachable_states_and_dead_actions(base):
    raw = copy.deepcopy(base)
    raw["transitions"]["Experiment"]["matrix"]["approved"]["launch_experiment"] = {"deny": "Not any more."}
    r = change_check(dom(raw), dom(base), examples=10)
    errs = problems(r, "semantic", "error")
    assert ("error", "state:Experiment.running") in errs and ("error", "action:launch_experiment") in errs
    assert ("info", "cell:Experiment.ended.launch_experiment") in problems(r, "semantic", "info")
    assert dead_actions(dom(raw)) == ["launch_experiment"] and dead_actions(dom(base)) == []
    first = change_check(dom(raw), None, examples=10)               # a first version: nothing is "newly" lost
    assert problems(first, "semantic", "error") == []


def test_a_scenario_the_new_version_dropped_still_runs(base):
    raw = copy.deepcopy(base)
    raw["transitions"]["Experiment"]["matrix"]["approved"]["launch_experiment"] = {"deny": "Not any more."}
    sid = "draft-to-running"
    assert sid in {s["id"] for s in raw["scenarios"]}
    raw["scenarios"] = [s for s in raw["scenarios"] if s["id"] != sid]     # dropped along with the change
    r = change_check(dom(raw), dom(base), examples=10)
    fails = [p for p in r.checks["scenarios"].problems if p.where.startswith(f"scenario:{sid}#")]
    assert fails and "removed" in fails[0].message


def test_the_harness_finds_an_invariant_breaking_transition(base):
    raw = copy.deepcopy(base)
    raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"] = "running"
    r = change_check(dom(raw), dom(base), examples=10)
    assert not r.checks["harness"].ok
    assert any(w.startswith(("invariant:", "expectation:")) for _, w in problems(r, "harness", "error"))


def test_log_replay_reports_past_actions_the_change_would_block(base):
    st = history(base)
    raw = copy.deepcopy(base)
    raw["actions"]["launch_experiment"]["actor"] = ["approver"]          # eng may no longer launch
    r = change_check(dom(raw), dom(base), events=st, examples=10)
    (p,) = r.checks["log_replay"].problems
    assert p.severity == "error" and p.where.startswith("E-onboarding@") and "eli" in p.message
    assert r.checks["log_replay"].note == "2 past action(s) replayed; 1 would be blocked"
    raw2 = copy.deepcopy(base)                                           # a precondition the past fails
    raw2["actions"]["approve_experiment"]["preconditions"].append(
        {"id": "long-enough", "check": "target.planned_days >= 30", "reason": "Run at least a month."})
    r2 = change_check(dom(raw2), dom(base), events=st, examples=10)
    assert [p.where for p in r2.checks["log_replay"].problems if p.severity == "error"] == ["E-onboarding@2"]


def test_one_blocked_action_does_not_cascade(base):
    """The replay keeps the recorded history, so the launch after a blocked approval is judged
    from the state the approval really left."""
    st = history(base)
    raw = copy.deepcopy(base)
    raw["actions"]["approve_experiment"]["actor"] = ["eng"]
    r = change_check(dom(raw), dom(base), events=st, examples=10)
    assert [p.message.split(" by ")[0] for p in r.checks["log_replay"].problems] == ["approve_experiment"]


def test_the_in_flight_check_lists_stranded_objects(base):
    st = history(base)                                                   # E-onboarding is running
    raw = copy.deepcopy(base)
    del raw["transitions"]["Experiment"]["matrix"]["running"]
    raw["objects"]["Experiment"]["properties"]["status"]["enum"].remove("running")
    for row in raw["transitions"]["Experiment"]["matrix"].values():
        for a, c in list(row.items()):
            if c == "running":
                row[a] = {"deny": "No running any more."}
    r = change_check(dom(raw), dom(base), events=st, examples=10)
    assert ("error", "E-onboarding") in problems(r, "in_flight")


def test_natural_language_conflicts_are_warnings_only(base):
    class Checker:
        def conflicts(self, old, new, changed):
            return [(k, "contradicts the glossary") for k in changed]
    raw = copy.deepcopy(base)
    raw["actions"]["launch_experiment"]["description"] = "Never start traffic."
    r = change_check(dom(raw), dom(base), nl=Checker(), examples=10)
    assert r.checks["nl"].ran and problems(r, "nl") == [("warning", "action:launch_experiment")]
    assert r.checks["nl"].ok and r.ok


# -- records on commits (ADR-0032) -------------------------------------------------------------------
def write(p, raw):
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    return p


def test_a_check_is_recorded_on_the_commit_against_its_merge_base(tmp_path, base):
    st = CommitStore(tmp_path / "commits")
    c0, _ = st.commit(write(tmp_path / "d.yaml", base))
    st.approve("example", c0.id, "ana")
    raw = copy.deepcopy(base)
    raw["actions"]["launch_experiment"]["actor"] = ["approver"]
    c1, _ = st.commit(write(tmp_path / "d.yaml", raw))
    r = check_commit(st, "example", c1.id, events=history(base), examples=10)
    assert not r.ok and r.diff["from"] == c0.id and r.diff["to"] == c1.id
    status = st.check_status("example", c1.id)
    assert status["change-check"]["ok"] is False and status["log_replay"]["ok"] is False
    assert status["structural"]["ok"] is True and status["change-check"]["base"] == c0.id
    assert "nl" not in status                                            # a check that did not run is not recorded
    assert check_commit(st, "example", c0.id, examples=10).diff["from"] is None   # main's first commit


def test_the_change_check_service_and_the_cli(tmp_path, base):
    from toprope.deploy import LocalEnvironment
    from toprope.kernel.services import LocalKernel
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    write(tmp_path / "d.domain.yaml", base)

    def run(*a):
        return subprocess.run(["uv", "run", "--quiet", "toprope-author", *a, "--workspace", str(tmp_path)],
                              capture_output=True, text=True, timeout=180, check=False)
    c0 = json.loads(run("commit").stdout)["commit"]
    ok = run("change-check", "--examples", "10")
    assert ok.returncode == 0 and json.loads(ok.stdout)["ok"] is True
    assert (tmp_path / ".toprope" / "checks" / f"{c0}.json").exists()
    raw = copy.deepcopy(base)
    raw["transitions"]["Experiment"]["matrix"]["approved"]["launch_experiment"] = {"deny": "Not any more."}
    write(tmp_path / "d.domain.yaml", raw)
    c1 = json.loads(run("commit").stdout)["commit"]
    bad = run("change-check", "--since", c0, "--examples", "10")
    assert bad.returncode == 1 and "semantic" in json.loads(bad.stdout)["summary"]
    env = LocalEnvironment(tmp_path / "env")
    k = LocalKernel(tmp_path, environment=env, harness_examples=10)
    out = k.call("change_check", {"domain": "example", "commit": c1})   # nothing approved: a first version
    assert out["ok"] and out["passed"] is False and out["failing"] == ["scenarios"]
    assert k.commits.check_status("example", c1)["change-check"]["ok"] is False
    env.preview_commit(k.commits, "example", c0, examples=5)              # the preview's harness is a record too
    assert k.commits.check_status("example", c0)["preview-harness"]["ok"] is True

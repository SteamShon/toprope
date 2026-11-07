"""The change check (ADR-0009, ADR-0018; M0a sub-PR 8) and its records on commits (ADR-0032)."""
import copy
import json
import subprocess
from pathlib import Path

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
    return in_flight_example()


def in_flight_example():
    """The schema example, with a way to end a running experiment: so the history below leaves
    E-onboarding in flight, not finished (log replay treats the two differently)."""
    raw = schema_doc_domain()
    raw["actions"]["end_experiment"] = {"description": "End it.", "actor": ["eng"], "target": "Experiment"}
    for state, row in raw["transitions"]["Experiment"]["matrix"].items():
        row["end_experiment"] = "ended" if state == "running" else "n/a"
    return raw


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
    assert [n for n, c in r.checks.items() if not c.ran] == ["tla", "nl"]     # no TLC jar here
    assert r.checks["log_replay"].note == "0 of 2 past action(s) re-decided; 0 would be blocked"   # nothing affected
    assert problems(r, "log_replay") == []                         # recorded timestamps are not differences


def test_structural_errors_stop_the_checks_that_need_a_valid_model(base):
    raw = copy.deepcopy(base)
    raw["transitions"]["Experiment"]["matrix"]["draft"]["approve_experiment"] = "aproved"
    r = change_check(dom(raw), dom(base), events=history(base), examples=10)
    assert not r.ok and ("error", "transitions.Experiment.matrix.draft.approve_experiment") in problems(r, "structural")
    assert [n for n, c in r.checks.items() if not c.ran] == ["semantic", "scenarios", "harness", "tla", "log_replay", "nl"]


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
    assert r.checks["log_replay"].note == "1 of 2 past action(s) re-decided; 1 would be blocked"  # launch only
    raw2 = copy.deepcopy(base)                                           # a precondition the past fails
    raw2["actions"]["approve_experiment"]["preconditions"].append(
        {"id": "long-enough", "check": "target.planned_days >= 30", "reason": "Run at least a month."})
    r2 = change_check(dom(raw2), dom(base), events=st, examples=10)
    assert [p.where for p in r2.checks["log_replay"].problems if p.severity == "error"] == ["E-onboarding@2"]


def test_log_replay_reports_only_what_this_change_newly_blocks(base):
    """A past action the base model already blocks (an earlier change removed what it used) is
    not this change's doing: it is counted, so one approved change does not fail every check."""
    st = history(base)
    old = copy.deepcopy(base)                                            # already approved: the past fails it
    old["actions"]["approve_experiment"]["preconditions"].append(
        {"id": "long-enough", "check": "target.planned_days >= 30", "reason": "Run at least a month."})
    new = copy.deepcopy(old)
    new["actions"]["approve_experiment"]["preconditions"].append(
        {"id": "always", "check": "true", "reason": "Touches approve, so it is re-decided."})
    new["actions"]["launch_experiment"]["actor"] = ["approver"]          # newly blocks eli's launch
    r = change_check(dom(new), dom(old), events=st, examples=10)
    assert [p.message.split(" by ")[0] for p in r.checks["log_replay"].problems
            if p.severity == "error"] == ["launch_experiment"]
    assert r.checks["log_replay"].note.endswith("; 1 would be blocked; 1 blocked by the base too")


def test_the_kernel_replays_a_domain_s_own_log_with_nothing_deployed(tmp_path, base):
    from toprope.kernel.services import LocalKernel
    st = CommitStore(tmp_path / ".toprope" / "commits")
    c0, _ = st.commit(write(tmp_path / "d.yaml", base))
    st.approve("example", c0.id, "ana")
    raw = copy.deepcopy(base)
    raw["actions"]["launch_experiment"]["actor"] = ["approver"]
    c1, _ = st.commit(write(tmp_path / "d.yaml", raw))
    k = LocalKernel(tmp_path, commits=st, harness_examples=10)             # no environment
    k.domain_events["example"] = history(base)
    out = k.call("change_check", {"domain": "example", "commit": c1.id})
    assert "log_replay" in out["failing"]
    assert st.check_status("example", c1.id)["log_replay"]["ok"] is False


def test_a_stricter_rule_on_a_finished_object_is_a_warning(base):
    """Finished history is not rewritten by a deliberately stricter rule; an object still in
    flight is what a block endangers."""
    st = MemoryEventStore()
    m = ReferenceModel(dom(base), st)
    for who, action in ((ANA, "approve_experiment"), (ELI, "launch_experiment"), (ELI, "end_experiment")):
        assert m.execute(Command(who, action, "E-onboarding", {})).ok           # ended: no move left
    raw = copy.deepcopy(base)
    raw["actions"]["launch_experiment"]["actor"] = ["approver"]
    r = change_check(dom(raw), dom(base), events=st, examples=10)
    assert r.checks["log_replay"].ok
    assert [p.severity for p in r.checks["log_replay"].problems] == ["warning"]
    assert "The object is finished" in r.checks["log_replay"].problems[0].message
    assert r.checks["log_replay"].note.endswith("; 0 would be blocked; 1 on finished objects (warnings)")


def test_a_new_invariant_that_objects_in_use_break_is_reported(base):
    """Delivery's probes invariant held for no verified request in its log, and no check said so.
    An object in flight that breaks a new rule is an error; a finished one, a warning."""
    st = history(base)                                                  # E-onboarding: running, can end
    raw = copy.deepcopy(base)
    raw["invariants"].append({"id": "running-is-long", "on": "Experiment",
                              "check": "target.status != 'running' or target.planned_days >= 100",
                              "reason": "A running experiment runs at least 100 days."})
    r = change_check(dom(raw), dom(base), events=st, examples=10)
    assert ("error", "E-onboarding") in problems(r, "in_flight")
    assert not r.checks["in_flight"].ok


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
    assert status["nl"]["ok"] is None                                     # did not run: recorded as such
    assert len({r["run"] for r in st.checks("example", c1.id)}) == 1
    assert check_commit(st, "example", c0.id, examples=10).diff["from"] is None   # main's first commit


def test_the_change_check_service_and_the_workspace(tmp_path, base):
    from toprope.deploy import LocalEnvironment
    from toprope.kernel.services import LocalKernel
    from toprope.workspace import Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    write(tmp_path / "d.domain.yaml", base)
    ws = Workspace(tmp_path)
    c0 = ws.commit()["commit"]
    ok = ws.change_check(examples=10)
    assert ok["ok"] is True
    assert (tmp_path / ".toprope" / "checks" / f"{c0}.json").exists()
    raw = copy.deepcopy(base)
    raw["transitions"]["Experiment"]["matrix"]["approved"]["launch_experiment"] = {"deny": "Not any more."}
    write(tmp_path / "d.domain.yaml", raw)
    c1 = ws.commit()["commit"]
    bad = ws.change_check(since=c0, examples=10)
    assert bad["ok"] is False and "semantic" in bad["summary"]
    env = LocalEnvironment(tmp_path / "env")
    k = LocalKernel(tmp_path, environment=env, harness_examples=10)
    out = k.call("change_check", {"domain": "example", "commit": c1})   # nothing approved: against its parent
    assert out["ok"] and out["passed"] is False and out["failing"] == ["semantic", "scenarios"]
    assert k.commits.check_status("example", c1)["change-check"]["ok"] is False
    env.preview_commit(k.commits, "example", c0, examples=5)              # the preview's harness is a record too
    assert k.commits.check_status("example", c0)["preview-harness"]["ok"] is True


# -- review findings -----------------------------------------------------------------------------
def test_a_base_with_errors_is_no_baseline_for_newly_lost(base):
    broken = copy.deepcopy(base)
    broken["transitions"]["Experiment"]["matrix"]["draft"]["approve_experiment"] = "aproved"
    r = change_check(dom(base), dom(broken), examples=10)
    assert problems(r, "semantic", "error") == []


def test_replay_gives_past_actors_the_roles_of_actor_rules(base):
    raw = copy.deepcopy(base)
    raw["actions"]["launch_experiment"]["actor"] = ["approver", {"role": "eng", "where": "true"}]
    st = history(raw)                                                     # eli launched under the rule
    new = copy.deepcopy(raw)
    new["actions"]["launch_experiment"]["actor"] = [{"role": "eng", "where": "true"}]
    r = change_check(dom(new), dom(raw), events=st, examples=10)
    assert problems(r, "log_replay") == []


def test_undecided_cells_include_missing_ones(base):
    raw = copy.deepcopy(base)
    raw["actions"]["pause_experiment"] = {"description": "Pause.", "actor": ["eng"], "target": "Experiment"}
    raw["transitions"]["Experiment"]["matrix"]["running"]["pause_experiment"] = "ended"
    r = change_check(dom(raw), dom(base), examples=10)
    assert ("info", "cell:Experiment.draft.pause_experiment") in problems(r, "semantic", "info")


def test_an_environment_of_another_domain_is_not_replayed(tmp_path, base):
    from toprope.deploy import LocalEnvironment
    from toprope.kernel.services import LocalKernel
    from toprope.store.sqlite import SQLiteEventStore
    env = LocalEnvironment(tmp_path / "env")
    other = copy.deepcopy(base)
    other["domain"] = "billing"
    ReferenceModel(dom(other), SQLiteEventStore(str(env.store_path)))      # billing's objects live here
    (tmp_path / "env" / "current.json").write_text(json.dumps({"commit_domain": "billing"}))
    st = CommitStore(tmp_path / ".toprope" / "commits")
    c, _ = st.commit(write(tmp_path / "d.yaml", base))
    k = LocalKernel(tmp_path, environment=env, commits=st, harness_examples=10)
    assert k.call("change_check", {"domain": "example", "commit": c.id})["passed"] is True
    assert st.check_status("example", c.id)["in_flight"]["ok"] is None


def test_a_mistyped_environment_or_branch_is_an_error(tmp_path, base):
    from toprope.workspace import AuthoringError, Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump({"domain": "d.domain.yaml", "sources": []}))
    write(tmp_path / "d.domain.yaml", base)
    ws = Workspace(tmp_path)
    ws.commit()
    with pytest.raises(AuthoringError, match="no deploy environment"):
        ws.change_check(env=tmp_path / "envs" / "lcoal", examples=5)
    assert not (tmp_path / "envs").exists()
    with pytest.raises(AuthoringError, match="no branch"):
        ws.change_check(branch="wrok", examples=5)


def test_a_served_composition_gives_the_kernel_each_member_s_own_log(tmp_path):
    from types import SimpleNamespace

    from toprope.adapters.mcp.cli import _member
    from toprope.identity import StaticIdentity
    from toprope.kernel.services import LocalKernel
    root = Path(__file__).resolve().parents[1]
    k = LocalKernel(tmp_path, harness_examples=10)
    args = SimpleNamespace(composition=str(root / "domains/toprope-self.composition.yaml"), member="authoring",
                           store="memory", store_dir=None, no_seed=True)
    _member(args, StaticIdentity({}), k)
    assert sorted(k.domain_events) == ["authoring", "delivery"]


@pytest.fixture
def fake_tlc(monkeypatch):
    """TLC's run replaced: the (exit status, stdout) it gives, and the commands it got."""
    import toprope.tla.tlc as tlc
    given = {"out": (0, "37 distinct states found, 0 states left on queue.\n"), "cmds": []}
    real = subprocess.run

    def run(cmd, *a, **kw):
        if cmd[0] != "java":
            return real(cmd, *a, **kw)
        given["cmds"].append(cmd)
        code, out = given["out"]
        return subprocess.CompletedProcess(cmd, code, out, "")
    monkeypatch.setattr(tlc.subprocess, "run", run)
    return given


def test_with_a_tlc_jar_the_change_check_model_checks(base, fake_tlc):
    r = change_check(dom(base), dom(copy.deepcopy(base)), examples=10, tlc="tla2tools.jar")
    assert r.checks["tla"].ran and r.checks["tla"].ok and fake_tlc["cmds"][0][3] == "tla2tools.jar"
    assert r.checks["tla"].note.startswith("checked; 37 distinct states")
    fake_tlc["out"] = (255, "Parse error\n")
    bad = change_check(dom(base), dom(copy.deepcopy(base)), examples=10, tlc="tla2tools.jar")
    assert not bad.ok and [p.message for p in bad.checks["tla"].problems] == ["error (exit 255)"]
    fake_tlc["out"] = (0, "1000000 distinct states found\n")                # a bound reached is no pass
    assert not change_check(dom(base), None, examples=10, tlc="tla2tools.jar").checks["tla"].ok


def test_a_kernel_with_tlc_approves_only_a_commit_tlc_checked(tmp_path, base, fake_tlc):
    from toprope.kernel.services import LocalKernel
    st = CommitStore(tmp_path / ".toprope" / "commits")
    c, _ = st.commit(write(tmp_path / "d.yaml", base))
    LocalKernel(tmp_path, commits=st, harness_examples=10).call("change_check", {"domain": "example", "commit": c.id})
    k = LocalKernel(tmp_path, commits=st, harness_examples=10, tlc_jar="tla2tools.jar")
    with pytest.raises(Exception, match="no passing TLC check"):              # checked, but not by TLC
        k.run("approve_commit", {"domain": "example", "commit": c.id, "approver": "ana"})
    assert k.call("change_check", {"domain": "example", "commit": c.id})["passed"] is True
    assert k.run("approve_commit", {"domain": "example", "commit": c.id, "approver": "ana"})["approved"] is True

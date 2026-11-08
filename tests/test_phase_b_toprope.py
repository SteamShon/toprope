"""The Toprope arm of M1 Phase B (ADR-0040 §3–5), on the real kernel, with a scripted editor."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/m1"))
from phase_b.agent import ToolError  # noqa: E402
from phase_b.baseline import baseline_root  # noqa: E402
from toprope.commits import CommitStore  # noqa: E402

from phase_b.backend import Backend
from phase_b.toolserver import ToolSpec, build_tools
from phase_b.toprope_arm import (
    STANDIN,
    Sandbox,
    TopropeArm,
    build_sandbox,
)

REQ = {"seq": 1, "intent": "An intent.", "rationale": "A reason."}


class Editor(Backend):
    """Proposes one change to Delivery's `verify` action through the editor's own tools."""

    def __init__(self, change):
        super().__init__()
        self.change, self.seen = change, None

    def converse(self, system, user, tools, transcript, max_turns=40):
        import time
        self.seen, self.started = (system, user, tools), time.monotonic()
        tl = {t.name: t for t in build_tools(tools)}
        decl = yaml.safe_load(tl["read_declaration"].fn(domain="delivery"))
        action = {k: v for k, v in decl["actions"]["verify"].items() if k not in ("source", "status")}
        self.change(action)
        tl["propose_element"].fn(domain="delivery", path="actions.verify", value=json.dumps(action))
        return "proposed"


@pytest.fixture(scope="module")
def materials(tmp_path_factory):
    return build_sandbox(baseline_root(ROOT), tmp_path_factory.mktemp("m") / "toprope")


def test_the_sandbox_holds_the_approved_domains_and_two_callers(materials):
    ids = yaml.safe_load((materials / "ids.yaml").read_text())
    editor = next(c for c in ids.values() if c["kind"] == "agent")
    assert editor["grant"]["actions"] == ["propose_element"]                    # the editor only proposes
    assert next(c for c in ids.values() if c["kind"] == "person")["id"] == STANDIN
    from toprope.commits import CommitStore
    store = CommitStore(baseline_root(ROOT) / ".toprope/commits")
    for d in ("authoring", "delivery"):
        approved = store.declaration(d, store.main(d).id)                     # the commit the binding names
        assert yaml.safe_load((materials / f"domains/{d}/{d}.domain.yaml").read_text()) == approved
        assert yaml.safe_load((materials / f"toolchain/{d}/{d}.domain.yaml").read_text()) == approved
        ws = yaml.safe_load((materials / f"toprope.{d}.workspace.yaml").read_text())
        assert [s["kind"] for s in ws["sources"]] == ["interview-log"]         # no repository sources
    assert not any("experiments" in str(p) for p in materials.rglob("*"))


def test_the_editors_tools_propose_and_nothing_more(materials, tmp_path):
    arm = TopropeArm(materials, tmp_path / "w", Editor(lambda a: a.update(description="Verify it.")))
    tools = build_tools(ToolSpec("toprope", str(arm.sb.root), json.dumps({"seq": 1, "cites": {}})))
    assert sorted(t.name for t in tools) == ["propose_element", "read_declaration", "read_guide"]
    refused = arm.sb.run("editor", "authoring", "delivery", "confirm_all_proposed", "delivery")
    assert refused["status"] != "ok"


def test_a_passing_change_goes_through_the_declared_actions(materials, tmp_path):
    ed = Editor(lambda a: a.update(description="Verify the deployment in use."))
    arm = TopropeArm(materials, tmp_path / "w", ed)
    out = tmp_path / "w/seq-01"
    import time
    edit = arm.edit(REQ, out)
    ended = time.monotonic()
    assert "+    description: Verify the deployment in use." in edit.data["diff"]
    assert edit.seconds < ended - ed.started + 0.5      # timed from the editor's start, not the bookkeeping's
    assert "Change request 1: An intent." in ed.seen[1]
    check = arm.check(REQ, out)
    (c,) = check.data["commits"].values()
    assert check.data["findings"] == [] and c["passed"] and c["preview"]["ok"]
    assert c["detail_passed"] and c["verdicts_agree"]
    deploy = arm.deploy(REQ, out)
    assert deploy.data["deployed"] and deploy.data["domains"]["delivery"]["path"] == "approved"
    assert arm.sb.env("delivery").current()["commit"] == c["commit"]
    assert Sandbox(arm.sb.root).commits().approvals("delivery")[-1]["approver"] == STANDIN


class Writer(Editor):
    """Writes the change into the working copy directly, as a person editing the file would:
    since #124 the editor's tools refuse a proposal that adds an error, so only this way does a
    declaration with errors reach the check."""

    def converse(self, system, user, tools, transcript, max_turns=40):
        path = self.arm.sb.declaration("delivery")
        doc = yaml.safe_load(path.read_text())
        self.change(doc["actions"]["verify"])
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        return "written"


def test_a_proposal_that_adds_an_error_is_refused_to_the_editor(materials, tmp_path):
    refused = []

    class Refused(Editor):
        def converse(self, system, user, tools, transcript, max_turns=40):
            try:
                return super().converse(system, user, tools, transcript, max_turns)
            except ToolError as e:                   # the agent loop hands a tool error to the model
                refused.append(str(e))
                return "refused"

    bad = {"id": "x", "check": "target.nonexistent == true", "reason": "r"}
    arm = TopropeArm(materials, tmp_path / "w", Refused(lambda a: a.update(preconditions=[bad])))
    out = tmp_path / "w/seq-01"
    arm.edit(REQ, out)
    assert refused and "refuse a declaration with errors" in refused[0] and "nonexistent" in refused[0]
    assert arm.check(REQ, out).data["changed_domains"] == []
    assert "nonexistent" not in arm.sb.declaration("delivery").read_text()


def test_a_flagged_change_is_overridden_and_the_build_floor_still_holds(materials, tmp_path):
    bad = {"id": "x", "check": "target.nonexistent == true", "reason": "r"}
    writer = Writer(lambda a: a.update(preconditions=[bad]))
    arm = TopropeArm(materials, tmp_path / "w", writer)
    writer.arm = arm
    out = tmp_path / "w/seq-01"
    before = arm.sb.env("delivery").current()["commit"]
    arm.edit(REQ, out)
    check = arm.check(REQ, out)
    (finding,) = [f for f in check.data["findings"] if f["severity"] == "error"]
    assert finding["where"] == "actions.verify.preconditions.x" and finding["domain"] == "delivery"
    deploy = arm.deploy(REQ, out)
    d = deploy.data["domains"]["delivery"]
    assert not deploy.data["deployed"] and d["path"] == "override" and "build did not pass" in d["refused"]
    assert arm.sb.commits().approvals("delivery")[-1]["approver"] != STANDIN       # refused before approving
    assert arm.sb.env("delivery").current()["commit"] == before                     # nothing went out
    assert "nonexistent" not in arm.sb.declaration("delivery").read_text()          # back to main


def test_a_flagged_change_that_breaks_scenarios_is_stopped_by_the_harness_floor(materials, tmp_path):
    """The check fails on the declared scenarios; the override approves it, and the build floor,
    which runs the same harness, refuses it: recorded as undeployable."""
    arm = TopropeArm(materials, tmp_path / "w", Editor(lambda a: a.update(
        preconditions=[{"id": "never", "check": "target.verified == true", "reason": "Only a verified one."}])))
    out = tmp_path / "w/seq-01"
    arm.edit(REQ, out)
    check = arm.check(REQ, out)
    (c,) = check.data["commits"].values()
    assert not c["passed"] and {f["check"] for f in check.data["findings"]} >= {"scenarios"}
    main_before = arm.sb.commits().main("delivery").id
    d = arm.deploy(REQ, out).data["domains"]["delivery"]
    assert d["path"] == "override" and not d["deployed"] and "harness" in d["refused"]
    assert arm.sb.commits().main("delivery").id == main_before        # not approved: main keeps no bad change
    assert "Only a verified one." not in arm.sb.declaration("delivery").read_text()
    arm.backend = Editor(lambda a: a.update(description="Verify it in use."))   # the next change still goes out
    arm.edit({**REQ, "seq": 2}, tmp_path / "w/seq-02")
    arm.check({**REQ, "seq": 2}, tmp_path / "w/seq-02")
    assert arm.deploy({**REQ, "seq": 2}, tmp_path / "w/seq-02").data["deployed"]


def test_the_override_deploys_what_the_floors_accept(materials, tmp_path):
    arm = TopropeArm(materials, tmp_path / "w", Editor(lambda a: a.update(description="Verify it in use.")))
    out = tmp_path / "w/seq-01"
    arm.edit(REQ, out)
    (c,) = arm.check(REQ, out).data["commits"].values()
    d = arm._override("delivery", c)                     # as if the check had flagged it
    assert d == {"deployed": True, "path": "override", "commit": c["commit"]}
    assert arm.sb.env("delivery").current()["commit"] == c["commit"]
    assert arm.sb.commits().approvals("delivery")[-1]["approver"] == STANDIN


def test_a_resumed_arm_starts_again_from_main(materials, tmp_path):
    arm = TopropeArm(materials, tmp_path / "w", Editor(lambda a: a.update(description="Half done.")))
    arm.edit(REQ, tmp_path / "w/seq-01")                                    # stopped before the check
    assert "Half done." in arm.sb.declaration("delivery").read_text()
    again = TopropeArm(materials, tmp_path / "w", Editor(lambda a: None), resume=True)
    assert "Half done." not in again.sb.declaration("delivery").read_text()


def test_the_toprope_arm_runs_from_the_command_line(materials, tmp_path):
    from phase_b import run as runner
    from test_phase_b import instruments
    inst = instruments(tmp_path)
    runner.main(["arm", "toprope", "--model", "m", "--materials", str(materials), "--out", str(tmp_path / "run"),
                 "--seqs", "1", "--instruments", str(inst), "--no-probes"],
                backend=Editor(lambda a: a.update(description="Verify it in use.")))
    rec = json.loads((tmp_path / "run/toprope/seq-01/record.json").read_text())
    assert rec["deploy"]["deployed"] and rec["check"]["changed_domains"] == ["delivery"]
    man = json.loads((tmp_path / "run/toprope/manifest.json").read_text())
    assert man["arm"] == "toprope" and man["done"] == [1] and "edit_toprope.md" in man["prompts"]


def test_a_proposal_without_a_recorded_request_is_a_tool_error(materials, tmp_path):
    from phase_b.agent import ToolError
    arm = TopropeArm(materials, tmp_path / "w", Editor(lambda a: None))
    tl = {t.name: t for t in build_tools(ToolSpec("toprope", str(arm.sb.root), json.dumps({"seq": 1, "cites": {}})))}
    with pytest.raises(ToolError, match="not recorded"):
        tl["propose_element"].fn(domain="delivery", path="actions.verify", value="{}")


def test_toprope_materials_from_another_baseline_are_refused(materials, tmp_path):
    from phase_b import run as runner
    from test_phase_b import instruments
    old = tmp_path / "old"
    shutil.copytree(materials, old)
    refs = old / ".toprope/commits/authoring/refs.jsonl"          # main as it was before the last approval
    first = json.loads((old / ".toprope/commits/authoring/log.jsonl").read_text().splitlines()[0])["id"]
    refs.write_text(refs.read_text() + json.dumps({"at": "t", "branch": "main", "commit": first}) + "\n")
    with pytest.raises(SystemExit, match="rebuild them"):
        runner.main(["arm", "toprope", "--model", "m", "--materials", str(old), "--out", str(tmp_path / "run"),
                     "--seqs", "1", "--instruments", str(instruments(tmp_path)), "--no-probes"],
                    backend=Editor(lambda a: None))


def test_the_materials_command_builds_both_arms_from_the_approved_commits(tmp_path):
    from phase_b import run as runner

    from toprope.commits import CommitStore
    runner.main(["materials", "--out", str(tmp_path / "arms")])
    store = CommitStore(baseline_root(ROOT) / ".toprope/commits")
    for d in ("authoring", "delivery"):
        approved = store.declaration(d, store.main(d).id)
        assert yaml.safe_load((tmp_path / f"arms/structured/{d}/{d}.domain.yaml").read_text()) == approved
        assert yaml.safe_load((tmp_path / f"arms/toprope/domains/{d}/{d}.domain.yaml").read_text()) == approved
    assert (tmp_path / "arms/structured/toprope-self.composition.yaml").exists()
    assert not list((tmp_path / "arms").rglob(".lock"))


def test_every_element_the_binding_names_exists_at_the_baseline():
    """The binding was written against authoring@4; the arms start from the baseline in
    `phase_b.baseline`. Scoring matches findings to these names, so each must exist there."""
    from phase_b.baseline import BASELINE
    store = CommitStore(baseline_root(ROOT) / ".toprope/commits")
    keys = {f"{d}/{k}" for d, c in BASELINE.items() for k in store.diff(d, None, c)["added"]}
    binding = yaml.safe_load((ROOT / "experiments/m1/instruments/binding.yaml").read_text())
    assert binding["domain_version"] == ", ".join(f"{d}@{c}" for d, c in BASELINE.items())
    assert [e for b in binding["bindings"] for e in b.get("elements", []) if e not in keys] == []


def test_the_committed_materials_are_built_from_the_baseline(tmp_path):
    """`experiments/m1/arms/` is what `materials` builds from the baseline revisions, whatever the
    repository's self domains are now."""
    from phase_b.arms import tree_hash
    from phase_b.toprope_arm import export_toolchain
    base = baseline_root(ROOT)
    build_sandbox(base, tmp_path / "toprope")
    export_toolchain(base, tmp_path / "structured")
    for arm in ("toprope", "structured"):
        assert tree_hash(tmp_path / arm) == tree_hash(ROOT / "experiments/m1/arms" / arm), arm


@pytest.fixture(autouse=True)
def one_timed_repeat(monkeypatch):
    """The run protocol's 5 timed repeats per change, cut to 1 here except where a test says."""
    assert TopropeArm.timed == 5 and TopropeArm.repeat_changes == 3
    monkeypatch.setattr(TopropeArm, "timed", 1)


def test_the_checks_run_again_on_three_changes_and_each_change_is_timed(materials, tmp_path):
    """Run protocol §3: the derandomized checks run once, and a second time (uncached) on three
    changes, which must find the same; edit → validated preview is timed in repeats, each with
    the part that bounds it."""
    arm = TopropeArm(materials, tmp_path / "w", Editor(lambda a: None))
    arm.timed = 2
    repeats = []
    for seq in range(1, 5):
        arm.backend = Editor(lambda a, s=seq: a.update(description=f"Verify it in use ({s})."))
        out = tmp_path / f"w/seq-{seq:02d}"
        arm.edit({**REQ, "seq": seq}, out)
        check = arm.check({**REQ, "seq": seq}, out).data
        arm.deploy({**REQ, "seq": seq}, out)
        (out / "record.json").write_text(json.dumps({"seq": seq, "check": check}, default=str))
        assert check["runs"] == [{"run": 1, "findings": check["findings"]}]
        assert len(check["timed"]) == 2 and all(t["limiter"] in ("impact", "harness", "preview", "other_check")
                                                and t["seconds"] > 0 for t in check["timed"])
        repeats.append(check.get("repeat"))
    assert [r is not None for r in repeats] == [True, True, True, False]
    assert all(r["same"] for r in repeats[:3])


def test_a_sandbox_with_only_leftover_caches_is_not_a_run(materials, tmp_path):
    """`git mv` of an older run left `sandbox/.hypothesis/`; the arm took it for a run and refused
    to start (2026-11-08). A sandbox is a run once the materials are in it."""
    (tmp_path / "w/sandbox/.hypothesis").mkdir(parents=True)
    arm = TopropeArm(materials, tmp_path / "w", Editor(lambda a: None))
    assert (arm.sb.root / "ids.yaml").exists() and (tmp_path / "w/sandbox.stale-1/.hypothesis").is_dir()
    with pytest.raises(FileExistsError, match="has a run"):
        TopropeArm(materials, tmp_path / "w", Editor(lambda a: None))


def test_the_tools_stay_fixed_when_a_change_is_deployed(materials, tmp_path):
    """ADR-0040 §3: the toolchain is fixed for the whole run. A member runs its deployed commit
    (ADR-0045), and the sandbox's commit stores are the arm's, so without `--working-copy` an
    arm's deployed change became its own tools: a request that needs a field the handoff does not
    send left the composition unable to compile, and the stand-in's next step failed (2026-11-08)."""
    def needs_branch(a):
        a["params"]["branch"] = {"type": "string"}

    class Delivery(Editor):
        def converse(self, system, user, tools, transcript, max_turns=40):
            tl = {t.name: t for t in build_tools(tools)}
            decl = yaml.safe_load(tl["read_declaration"].fn(domain="delivery"))
            action = {k: v for k, v in decl["actions"]["request_delivery"].items() if k not in ("source", "status")}
            self.change(action)
            tl["propose_element"].fn(domain="delivery", path="actions.request_delivery", value=json.dumps(action))
            return "proposed"

    arm = TopropeArm(materials, tmp_path / "w", Delivery(needs_branch))
    out = tmp_path / "w/seq-01"
    arm.edit(REQ, out)
    arm.check(REQ, out)
    assert arm.deploy(REQ, out).data["deployed"]                      # delivery now needs a branch
    assert "branch" in Path(arm.sb.env("delivery").current()["declaration"]).read_text()
    arm.backend = Editor(lambda a: a.update(description="Verify it in use."))
    arm.edit({**REQ, "seq": 2}, tmp_path / "w/seq-02")              # the stand-in's step still runs
    assert arm.check({**REQ, "seq": 2}, tmp_path / "w/seq-02").data["commits"]


def test_flags_come_from_the_kernels_inputs_and_say_what_the_base_had(materials, tmp_path):
    """The Toprope arm's flags are its change check's findings, on what the kernel's check_commit
    used: the recorded base and the member's own history (toolchain/<d>/events). The first run took
    them again on the deploy environment's events, which lost the log replay's findings (#169).
    A finding the base already had is marked `carried`."""
    from phase_b.toprope_arm import check_report, flags, recorded_base
    arm = TopropeArm(materials, tmp_path / "w", Editor(lambda a: a.update(description="Verify it in use.")))
    out = tmp_path / "w/seq-01"
    arm.edit(REQ, out)
    data = arm.check(REQ, out).data
    cid = data["commits"]["delivery"]["commit"]
    root = arm.sb.root
    assert recorded_base(root, "delivery", cid) == "1-584aaeea5e686ee8"
    report = check_report(root, "delivery", cid, "1-584aaeea5e686ee8")
    assert report.checks["log_replay"].ran                               # the member's own history
    assert report.checks["log_replay"].note == "" or "past action" in report.checks["log_replay"].summary()
    found, _ = flags(root, "delivery", cid)
    assert {f["check"] for f in found} == {f["check"] for f in data["findings"]}
    assert all(isinstance(f["carried"], bool) for f in found)
    carried_only = [f for f in found if f["carried"]]
    assert all((f["check"], f["where"]) in {(g["check"], g["where"]) for g in data["findings"]} for f in carried_only)


def test_recheck_takes_the_flags_again_and_keeps_the_first(materials, tmp_path):
    from phase_b import run as runner
    work = tmp_path / "run/toprope"
    arm = TopropeArm(materials, work, Editor(lambda a: a.update(description="Verify it in use.")))
    out = work / "seq-01"
    arm.edit(REQ, out)
    check = arm.check(REQ, out).data
    first = [{"domain": "delivery", "check": "structural", "severity": "warning", "where": "x", "problem": "old"}]
    (out / "record.json").write_text(json.dumps({"seq": 1, "check": {**check, "findings": first,
                                                                       "runs": [{"run": 1, "findings": first}]}}))
    assert runner.recheck_toprope(tmp_path / "run") == {"rechecked": {1: len(check["findings"])}}
    rec = json.loads((out / "record.json").read_text())
    assert rec["check"]["original"]["findings"] == first and rec["check"]["recheck"]["why"]
    assert rec["check"]["runs"] == [{"run": 1, "findings": rec["check"]["findings"]}]
    assert all("carried" in f for f in rec["check"]["findings"])
    rows = [r for r in runner.RunLog(runner.log_path(tmp_path / "run")).rows() if r["what"] == "recheck"]
    assert [(r["arm"], r["change"]) for r in rows] == [("toprope", "1")]


def test_a_change_that_past_behaviour_breaks_is_flagged_by_the_log_replay(materials, tmp_path):
    """The run on the researcher's computer missed every log replay finding: the history the flags
    were taken on was the deploy environment's, which is empty (#169). Here a first change goes out
    through Delivery (its verify is history); a second one refuses that verify."""
    arm = TopropeArm(materials, tmp_path / "w", Editor(lambda a: a.update(description="Verify it in use.")))
    out = tmp_path / "w/seq-01"
    arm.edit(REQ, out)
    arm.check(REQ, out)
    assert arm.deploy(REQ, out).data["deployed"]                        # deliver, preview, deploy, verify
    arm.backend = Editor(lambda a: a.update(preconditions=[
        *a.get("preconditions", []),
        {"id": "staging-only", "check": "target.environment == \"staging\"", "reason": "Verify on staging."}]))
    out = tmp_path / "w/seq-02"
    arm.edit({**REQ, "seq": 2}, out)
    found = arm.check({**REQ, "seq": 2}, out).data["findings"]
    replay = [f for f in found if f["check"] == "log_replay"]
    assert replay and not any(f["carried"] for f in replay)              # the past verify, on `local`


def test_the_combined_arm_reviews_the_toprope_edits_and_adds_the_compilers_flags(materials, tmp_path):
    """The fair comparison: the Toprope arm's own edit, reviewed five times by an LLM with the frozen
    review prompt, plus the compiler's flags; written as a run `grade` and `score` read unchanged."""
    from phase_b import run as runner
    from phase_b.backend import ApiBackend
    from phase_b.combined import combine
    from phase_b.model import FakeModel
    from phase_b.score import check_runs
    src = tmp_path / "run"
    for arm in ("nl", "structured"):
        (src / arm).mkdir(parents=True)
        (src / arm / "manifest.json").write_text(json.dumps({"arm": arm, "done": [1]}))
    arm = TopropeArm(materials, src / "toprope", Editor(lambda a: a.update(description="Verify it in use.")))
    runner.run_arm(arm, src / "toprope", [REQ], arm.backend, "fake")
    seen = []

    def reviewer(system, messages, tools):
        seen.append(messages[0]["content"])
        return json.dumps({"findings": [{"problem": "p", "where": "delivery", "kind": "other"}]})
    out = combine(src, tmp_path / "combined", ApiBackend(FakeModel(reviewer)), materials=materials)
    assert out["combined"] == [1] and len(seen) == 5
    assert "Verify it in use." in seen[0] and "=== toprope-self.composition.yaml ===" in seen[0]
    rec = json.loads((tmp_path / "combined/toprope/seq-01/record.json").read_text())
    runs = check_runs(rec)
    assert [r["run"] for r in runs] == [1, 2, 3, 4, 5]
    compiler = rec["check"]["compiler"]
    assert all(r["findings"][:len(compiler)] == compiler and r["findings"][-1]["from"] == "llm" for r in runs)
    assert (tmp_path / "combined/nl/manifest.json").exists()
    combine(src, tmp_path / "combined", ApiBackend(FakeModel(reviewer)), materials=materials)
    assert len(seen) == 5                                                 # resumed: not reviewed again

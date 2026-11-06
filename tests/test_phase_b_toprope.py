"""The Toprope arm of M1 Phase B (ADR-0040 §3–5), on the real kernel, with a scripted editor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/m1"))

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
    return build_sandbox(ROOT, tmp_path_factory.mktemp("m") / "toprope")


def test_the_sandbox_holds_the_approved_domains_and_two_callers(materials):
    ids = yaml.safe_load((materials / "ids.yaml").read_text())
    editor = next(c for c in ids.values() if c["kind"] == "agent")
    assert editor["grant"]["actions"] == ["propose_element"]                    # the editor only proposes
    assert next(c for c in ids.values() if c["kind"] == "person")["id"] == STANDIN
    from toprope.commits import CommitStore
    store = CommitStore(ROOT / ".toprope/commits")
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


def test_a_flagged_change_is_overridden_and_the_build_floor_still_holds(materials, tmp_path):
    bad = {"id": "x", "check": "target.nonexistent == true", "reason": "r"}
    arm = TopropeArm(materials, tmp_path / "w", Editor(lambda a: a.update(preconditions=[bad])))
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

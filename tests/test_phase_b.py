"""The M1 Phase B harness (ADR-0040), with a fake model: no API calls, no cost."""

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
from phase_b.agent import (
    ToolError,
    Transcript,
    confined,
    converse,
    file_tools,
)
from phase_b.arms import (
    nl_arm,
    parse_findings,
    render_skill,
    structured_arm,
)
from phase_b.model import Budget, BudgetExceeded, FakeModel, tool_use

SEALED = "SEALED-MARKER-7f3a"     # appears only in the synthetic key and binding


def instruments(tmp: Path) -> Path:
    """Frozen instruments with the real change requests and a synthetic, marked key and binding."""
    d = tmp / "instruments"
    d.mkdir()
    real = ROOT / "experiments/m1/instruments"
    for f in ("change-requests.yaml", "probe-suite.yaml", "verdict-rules.yaml"):
        shutil.copy(real / f, d / f)
    seqs = [r["seq"] for r in yaml.safe_load((d / "change-requests.yaml").read_text())["requests"]]
    (d / "change-key.yaml").write_text(yaml.safe_dump({"entries": [
        {"seq": s, "problem": "none", "note": f"{SEALED} key {s}"} for s in seqs]}))
    (d / "binding.yaml").write_text(yaml.safe_dump({"bindings": [
        {"seq": s, "elements": [f"{SEALED}/action:x{s}"]} for s in seqs]}))
    files = {f.name: {"sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "frozen_at": "t"}
             for f in d.glob("*.yaml")}
    (d / "FROZEN.json").write_text(json.dumps({"files": files}))
    return d


def materials(tmp: Path) -> Path:
    m = tmp / "materials"
    m.mkdir()
    (m / "SKILL.md").write_text("# Skill\n\nOnly a person confirms an element.\nStages: drafted, previewed.\n")
    return m


def scripted_arm():
    """An editor that renames a stage and a reviewer that reports one finding."""
    def script(system, messages, tools):
        last = messages[-1]["content"]
        if "review a change" in system:
            return json.dumps({"findings": [{"problem": "renamed stage", "where": "SKILL.md", "kind": "reference"}]})
        if isinstance(last, str):                                # the editor's first turn
            return tool_use("replace_in_file", {"path": "SKILL.md", "old": "previewed", "new": "built"})
        return "Renamed the stage."
    return script


# -- the model and the cost cap ------------------------------------------------------------

def test_the_budget_counts_dollars_and_stops_at_the_cap():
    b = Budget((3.0, 15.0, 3.75, 0.3), cap_usd=0.01)
    m = FakeModel(["a", "b"], budget=b)
    m("s", [], [])
    assert b.report()["tokens"] == {"input": 100, "output": 10, "cache_write": 0, "cache_read": 0}
    assert b.cost() == pytest.approx((100 * 3.0 + 10 * 15.0) / 1e6)
    b.add(b.used.__class__(input=10_000))
    with pytest.raises(BudgetExceeded):
        m("s", [], [])


def test_the_budget_comes_from_the_environment():
    with pytest.raises(SystemExit, match="M1_PRICES"):
        Budget.from_env({"M1_COST_CAP_USD": "5"})
    with pytest.raises(SystemExit, match="input,output,cache_write,cache_read"):
        Budget.from_env({"M1_PRICES": "1,2,3", "M1_COST_CAP_USD": "5"})
    assert Budget.from_env({"M1_PRICES": "1,2,3,4", "M1_COST_CAP_USD": "5"}).cap_usd == 5.0


# -- one role's conversation ---------------------------------------------------------------

def test_file_tools_stay_inside_the_workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (tmp_path / "secret.yaml").write_text("x")
    (ws / "link").symlink_to(tmp_path / "secret.yaml")
    for bad in ("../secret.yaml", str(tmp_path / "secret.yaml"), "link", ""):
        with pytest.raises(ToolError):
            confined(ws, bad)
    assert confined(ws, "a/b.md") == (ws / "a/b.md").resolve()


def test_a_conversation_runs_tools_and_shows_their_errors(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "f.md").write_text("one two")
    m = FakeModel([tool_use("read_file", {"path": "../x"}),
                   tool_use("replace_in_file", {"path": "f.md", "old": "two", "new": "three"}), "done"])
    out = converse(m, "sys", "go", file_tools(ws), Transcript(tmp_path / "t.jsonl"))
    assert out == "done" and (ws / "f.md").read_text() == "one three"
    first_result = m.calls[1]["messages"][-1]["content"][0]
    assert first_result["is_error"] and "outside the workspace" in first_result["content"]
    kinds = [json.loads(x)["kind"] for x in (tmp_path / "t.jsonl").read_text().splitlines()]
    assert kinds == ["start", "reply", "tool", "reply", "tool", "reply"]


def test_findings_are_parsed_or_reported_as_malformed():
    assert parse_findings('```json\n{"findings": [{"problem": "p"}]}\n```') == ([{"problem": "p"}], None)
    assert parse_findings("I see no issues.")[1] is not None


# -- an arm, change by change --------------------------------------------------------------

def test_a_text_arm_edits_checks_and_deploys_each_change(tmp_path):
    inst = instruments(tmp_path)
    m = FakeModel(scripted_arm())
    arm = nl_arm(materials(tmp_path), tmp_path / "run/nl", m)
    reqs = runner.change_requests(inst)[:1]
    man = runner.run_arm(arm, tmp_path / "run/nl", reqs, None, "fake", inst)
    assert man["done"] == [1] and man["stopped"] is None
    rec = json.loads((tmp_path / "run/nl/seq-01/record.json").read_text())
    assert "+Stages: drafted, built." in rec["edit"]["diff"]
    assert rec["check"]["findings"][0]["kind"] == "reference"
    assert "built" in (tmp_path / "run/nl/deployed/SKILL.md").read_text()      # deployed though flagged
    review = next(c for c in m.calls if "review a change" in c["system"])
    assert "+Stages: drafted, built." in review["messages"][0]["content"]     # the reviewer sees the diff
    assert man["materials"] and set(man["prompts"]) == {"edit.md", "review.md", "render.md"}


def test_no_conversation_sees_the_key_or_the_binding(tmp_path):
    inst = instruments(tmp_path)
    m = FakeModel(scripted_arm())
    shutil.copy(inst / "change-key.yaml", tmp_path / "materials-key.yaml")      # even next to the materials
    runner.main(["arm", "structured", "--materials", str(materials(tmp_path)), "--out", str(tmp_path / "run"),
                 "--seqs", "1-2", "--instruments", str(inst)], model=m)
    sent = json.dumps(m.calls)
    assert SEALED not in sent and "change-key" not in sent
    for t in (tmp_path / "run").rglob("*.jsonl"):
        assert SEALED not in t.read_text()
    assert json.loads((tmp_path / "run/structured/manifest.json").read_text())["done"] == [1, 2]


def test_a_run_refuses_to_start_when_an_instrument_changed(tmp_path):
    inst = instruments(tmp_path)
    (inst / "probe-suite.yaml").write_text("changed: true\n")
    with pytest.raises(SystemExit, match="probe-suite.yaml changed after freezing"):
        runner.main(["arm", "nl", "--materials", str(materials(tmp_path)), "--out", str(tmp_path / "run"),
                     "--instruments", str(inst)], model=FakeModel([]))
    assert not (tmp_path / "run").exists()


def test_a_run_stops_at_the_cost_cap_and_keeps_what_it_did(tmp_path):
    inst = instruments(tmp_path)
    b = Budget((1000.0, 1000.0, 0, 0), cap_usd=0.25)          # one change costs about $0.33
    m = FakeModel(scripted_arm(), budget=b)
    with pytest.raises(SystemExit) as e:
        runner.main(["arm", "nl", "--materials", str(materials(tmp_path)), "--out", str(tmp_path / "run"),
                     "--seqs", "1-3", "--instruments", str(inst)], model=m, budget=b)
    assert e.value.code == 2
    man = json.loads((tmp_path / "run/nl/manifest.json").read_text())
    assert man["done"] == [1] and man["stopped"].startswith("budget") and man["cost"]["usd"] >= 0.25


def test_the_seq_option_names_existing_requests():
    assert runner.seqs("1-2,5", list(range(1, 21))) == [1, 2, 5]
    with pytest.raises(SystemExit, match="21"):
        runner.seqs("20-21", list(range(1, 21)))


# -- the NL arm's materials ----------------------------------------------------------------

def test_the_skill_is_rendered_from_the_declarations_alone(tmp_path):
    decl = tmp_path / "decl"
    (decl / "authoring").mkdir(parents=True)
    (decl / "authoring/authoring.domain.yaml").write_text("domain: authoring\n")
    m = FakeModel([tool_use("write_file", {"path": "SKILL.md", "content": "# Skill"}, "a"),
                   tool_use("write_file", {"path": "EXAMPLES.md", "content": "# Examples"}, "b"), "written"])
    render_skill(decl, tmp_path / "nl", m, tmp_path / "render.jsonl")
    assert sorted(p.name for p in (tmp_path / "nl").rglob("*")) == ["EXAMPLES.md", "SKILL.md"]
    with pytest.raises(RuntimeError, match="EXAMPLES.md"):
        render_skill(decl, tmp_path / "nl2", FakeModel(["I wrote nothing"]), tmp_path / "r2.jsonl")


def test_a_run_starts_from_fresh_materials(tmp_path):
    m = materials(tmp_path)
    structured_arm(m, tmp_path / "run", FakeModel([]))
    with pytest.raises(FileExistsError):
        structured_arm(m, tmp_path / "run", FakeModel([]))

"""Phase B follows the frozen run protocol (experiments/m1/instruments/run-protocol.md)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/m1"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase_b import run as runner  # noqa: E402
from phase_b.arms import PROMPTS, nl_arm, prompt, request_text, structured_arm  # noqa: E402
from phase_b.blind import BlindError, words_in  # noqa: E402
from phase_b.probes import _user, load_probes  # noqa: E402
from phase_b.runlog import COLUMNS, RunLog, log_path  # noqa: E402
from phase_b.toolserver import ToolSpec, build_tools  # noqa: E402
from phase_b.toprope_arm import DESCRIBED  # noqa: E402
from test_phase_b import api, instruments, materials  # noqa: E402

INSTRUMENTS = ROOT / "experiments/m1/instruments"


# -- §1: no experiment words -------------------------------------------------------------------

def test_the_words_are_the_protocols():
    found = words_in("Review this arm's recall for the M1 eval; judge the seeded change key and answer key")
    assert {w.lower() for w in found} == {"arm", "recall", "m1", "eval", "judge", "seeded", "change key",
                                          "answer key"}
    assert {w.lower() for w in words_in("arms Experiments scoring evaluate answer_key benchmark m1")} == \
        {"arms", "experiments", "scoring", "evaluate", "answer_key", "benchmark", "m1"}
    assert words_in("harm, warm, alarm, format, scope, idempotency_key, deployment, armed") == []


def test_no_harness_text_an_agent_sees_has_an_experiment_word():
    """Every role prompt as filled for each arm, every change request as given, every probe's
    request, and every tool's name and description."""
    described = [DESCRIBED, "a natural-language skill for two domains (SKILL.md, with worked examples)",
                 "the YAML declarations of two domains and the composition that joins them"]
    for name in sorted(p.stem for p in PROMPTS.glob("*.md") if not p.stem.startswith("grade_")):
        for d in described:
            assert words_in(prompt(name, arm=d, how=d, materials="")) == [], name
    for r in yaml.safe_load((INSTRUMENTS / "change-requests.yaml").read_text())["requests"]:
        assert words_in(request_text(r)) == [], r["seq"]
    for p in load_probes(INSTRUMENTS):
        assert words_in(_user(p, {"note": "a starting state"})) == [], p["id"]


def test_tools_refuse_a_file_name_with_an_experiment_word(tmp_path):
    (tmp_path / "SKILL.md").write_text("x")
    assert [t.name for t in build_tools(ToolSpec("files", str(tmp_path)))]
    (tmp_path / "scoring-notes.md").write_text("x")
    with pytest.raises(BlindError, match="scoring-notes.md"):
        build_tools(ToolSpec("files", str(tmp_path)))


def test_a_tool_never_shows_the_workspace_path(tmp_path):
    ws = tmp_path / "experiments-m1-run" / "workspace"
    ws.mkdir(parents=True)
    tools = {t.name: t for t in build_tools(ToolSpec("files", str(ws)))}
    tools["write_file"].fn(path="a.md", content=f"see {ws}/b.md")
    assert tools["read_file"].fn(path="a.md") == "see ./b.md"
    assert str(ws) not in json.dumps(tools["list_files"].fn())


# -- §4: the decision log ----------------------------------------------------------------------

def test_a_run_writes_the_decision_log_beside_the_run_directory(tmp_path):
    inst = instruments(tmp_path)
    b, _ = api()
    work = tmp_path / "runs/phase-b/nl"
    arm = nl_arm(materials(tmp_path), work, b)
    runner.run_arm(arm, work, runner.change_requests(inst)[:2], b, "fake", inst)
    log = RunLog(log_path(tmp_path / "runs/phase-b"))
    assert log.path == tmp_path / "runs/phase-b-runs.tsv"
    assert log.path.read_text().splitlines()[0].split("\t") == list(COLUMNS)
    rows = log.rows()
    per_change = lambda c: [(c, "edit"), *[(c, "review")] * 5, (c, "deploy")]   # noqa: E731
    assert [(r["change"], r["what"]) for r in rows] == [
        ("", "session-start"), *per_change("1"), *per_change("2"), ("", "session-stop")]
    assert [r["run"] for r in rows if r["what"] == "review" and r["change"] == "1"] == ["1", "2", "3", "4", "5"]
    assert {r["arm"] for r in rows} == {"nl"} and rows[2]["result"] == "1 finding(s)"
    for r in rows:
        assert not Path(r["evidence"]).is_absolute() and (log.path.parent / r["evidence"]).exists(), r


def test_a_change_run_again_is_superseded_in_the_log_not_edited(tmp_path):
    inst = instruments(tmp_path)
    b, _ = api()
    work = tmp_path / "runs/phase-b/structured"
    arm = structured_arm(materials(tmp_path), work, b)
    runner.run_arm(arm, work, runner.change_requests(inst)[:1], b, "fake", inst)
    log = RunLog(log_path(work.parent))
    before = log.path.read_text()
    (work / "seq-02").mkdir()                                  # a stop halfway through change 2
    runner.run_arm(structured_arm(materials(tmp_path), work, b, resume=True), work,
                   runner.change_requests(inst)[:2], b, "fake", inst)
    after = log.path.read_text()
    assert after.startswith(before)                            # append-only
    assert [r["what"] for r in log.rows() if r["change"] == "2"][:2] == ["superseded", "edit"]


# -- §3: repeats ---------------------------------------------------------------------------------------

def test_the_probes_run_three_times_after_each_change_and_before_any(tmp_path, monkeypatch):
    inst = instruments(tmp_path)
    b, _ = api()
    work = tmp_path / "runs/phase-b/nl"
    arm = nl_arm(materials(tmp_path), work, b)
    seen = []

    def probe(req, out, worlds, probes, jobs=1):
        seen.append((req["seq"], out.relative_to(work)))
        out.mkdir(parents=True, exist_ok=True)
        return [{"probe": "P01", "answer": "ok", "messages_to_owner": [], "transcript": "P01.jsonl"}]
    monkeypatch.setattr(arm, "probe", probe)
    runner.run_arm(arm, work, runner.change_requests(inst)[:1], b, "fake", inst, worlds=tmp_path)
    assert seen == [(s, Path(f"seq-0{s}/probes/run-{k}")) for s in (0, 1) for k in (1, 2, 3)]
    rec = json.loads((work / "seq-01/record.json").read_text())
    assert [(r["run"], r["dir"]) for r in rec["probes"]] == [(k, f"probes/run-{k}") for k in (1, 2, 3)]
    rows = [r for r in RunLog(log_path(work.parent)).rows() if r["what"] == "probe P01"]
    assert [(r["change"], r["run"]) for r in rows] == [(c, k) for c in ("0", "1") for k in ("1", "2", "3")]


# -- §1: the prompts are frozen with the protocol -------------------------------------------------

def test_a_run_needs_the_prompts_frozen_and_unchanged(tmp_path, monkeypatch):
    inst = instruments(tmp_path)
    frozen = json.loads((inst / "FROZEN.json").read_text())
    del frozen["prompts"]
    (inst / "FROZEN.json").write_text(json.dumps(frozen))
    assert any("prompts are not frozen" in e for e in runner.verify_instruments(inst))
    runner.main(["freeze-prompts", "--instruments", str(inst)])
    assert runner.verify_instruments(inst) == []
    with pytest.raises(SystemExit, match="nothing to change"):
        runner.main(["freeze-prompts", "--instruments", str(inst)])
    prompts = tmp_path / "prompts"
    import shutil
    shutil.copytree(PROMPTS, prompts)
    (prompts / "review.md").write_text((prompts / "review.md").read_text() + "\nAlso check the spelling.\n")
    monkeypatch.setattr(runner, "PROMPTS", prompts)
    assert any("prompts changed after freezing" in e for e in runner.verify_instruments(inst))
    with pytest.raises(SystemExit, match="--reason"):
        runner.main(["freeze-prompts", "--instruments", str(inst)])
    runner.main(["freeze-prompts", "--instruments", str(inst), "--reason", "the researcher asked for spelling"])
    entry = json.loads((inst / "FROZEN.json").read_text())["prompts"]
    assert entry["history"][0]["reason"] == "the researcher asked for spelling" and "grade_change.md" not in entry["files"]
    assert runner.verify_instruments(inst) == []


# -- what an older run leaves behind -------------------------------------------------------------

def test_starting_states_with_only_leftover_caches_are_built_again(tmp_path, monkeypatch):
    """`git mv` of an older run leaves what git ignores (`.hypothesis/`) in `worlds/`: the
    harness used to take that for built starting states, and every probe failed (2026-11-08)."""
    from phase_b.probes import PROBES
    out = tmp_path / "runs/phase-b"
    for p in PROBES:
        (out / "worlds" / p / ".hypothesis").mkdir(parents=True)

    def build(base, toolchain, dest):
        for p in PROBES:
            (dest / p).mkdir(parents=True)
            (dest / p / "state.json").write_text("{}")
            (dest / p / "situation.json").write_text("{}")
    monkeypatch.setattr(runner, "build_worlds", build)
    monkeypatch.setattr(runner, "export_toolchain", lambda base, dest: dest)
    monkeypatch.setattr(runner, "baseline_root", lambda root: root)
    worlds = runner.probe_worlds(out)
    assert runner.worlds_complete(worlds)
    assert (out / "worlds.incomplete-1/P01/.hypothesis").is_dir()        # kept aside, not deleted
    calls = []
    monkeypatch.setattr(runner, "build_worlds", lambda *a: calls.append(a))
    runner.probe_worlds(out)
    assert calls == []                                                     # complete: built once

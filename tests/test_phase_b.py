"""The M1 Phase B harness (ADR-0040), with a fake model and a fake `claude`: no calls, no cost."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import stat
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
from phase_b.backend import (
    ApiBackend,
    BackendError,
    CliBackend,
    UsageLimit,
)
from phase_b.model import (
    Budget,
    BudgetExceeded,
    FakeModel,
    Usage,
    tool_use,
)
from phase_b.toolserver import ToolSpec, make_server

SEALED = "SEALED-MARKER-7f3a"     # appears only in the synthetic key and binding


def instruments(tmp: Path, keep: int | None = None) -> Path:
    """Frozen instruments with the real change requests (the first `keep` of them) and a
    synthetic, marked key and binding."""
    d = tmp / "instruments"
    d.mkdir()
    real = ROOT / "experiments/m1/instruments"
    for f in ("change-requests.yaml", "probe-suite.yaml", "verdict-rules.yaml"):
        shutil.copy(real / f, d / f)
    if keep:
        cr = yaml.safe_load((d / "change-requests.yaml").read_text())
        cr["requests"] = cr["requests"][:keep]
        (d / "change-requests.yaml").write_text(yaml.safe_dump(cr))
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
    m.mkdir(exist_ok=True)
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


def api(script=None, budget=None) -> tuple[ApiBackend, FakeModel]:
    m = FakeModel(script or scripted_arm(), budget=budget)
    return ApiBackend(m, budget), m


def arm_args(tmp: Path, inst: Path, arm="nl", *more) -> list[str]:
    return ["arm", arm, "--model", "m-under-test", "--materials", str(materials(tmp)), "--out", str(tmp / "run"),
            "--instruments", str(inst), *more]


# -- the model and the cost cap (the API backend) ------------------------------------------

def test_the_budget_counts_dollars_and_stops_at_the_cap():
    b = Budget((3.0, 15.0, 3.75, 0.3), cap_usd=0.01)
    m = FakeModel(["a", "b"], budget=b)
    m("s", [], [])
    assert b.report()["tokens"] == {"input": 100, "output": 10, "cache_write": 0, "cache_read": 0}
    assert b.cost() == pytest.approx((100 * 3.0 + 10 * 15.0) / 1e6)
    b.add(Usage(input=10_000))
    with pytest.raises(BudgetExceeded):
        m("s", [], [])


def test_the_budget_comes_from_the_environment():
    with pytest.raises(SystemExit, match="M1_PRICES"):
        Budget.from_env({"M1_COST_CAP_USD": "5"})
    with pytest.raises(SystemExit, match="input,output,cache_write,cache_read"):
        Budget.from_env({"M1_PRICES": "1,2,3", "M1_COST_CAP_USD": "5"})
    assert Budget.from_env({"M1_PRICES": "1,2,3,4", "M1_COST_CAP_USD": "5"}).cap_usd == 5.0


# -- one role's conversation and its tools -------------------------------------------------

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


def test_the_tool_server_serves_only_the_confined_tools(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (tmp_path / "secret.yaml").write_text("sealed")

    async def go():
        from mcp import Client
        async with Client(make_server(ToolSpec("files", str(ws)))) as c:
            names = sorted(t.name for t in (await c.list_tools()).tools)
            denied = await c.call_tool("read_file", {"path": "../secret.yaml"})
            wrote = await c.call_tool("write_file", {"path": "a.md", "content": "hi"})
            listed = await c.call_tool("list_files", {})
            return names, denied, wrote, listed

    names, denied, wrote, listed = asyncio.run(go())
    assert names == ["list_files", "read_file", "replace_in_file", "write_file"]
    assert denied.is_error and "outside the workspace" in denied.content[0].text
    assert not wrote.is_error and (ws / "a.md").read_text() == "hi"
    assert json.loads(listed.content[0].text) == ["a.md"]


def test_findings_are_parsed_or_reported_as_malformed():
    assert parse_findings('```json\n{"findings": [{"problem": "p"}]}\n```') == ([{"problem": "p"}], None)
    assert parse_findings("I see no issues.")[1] is not None


# -- the Claude Code backend, with a fake `claude` -----------------------------------------

FAKE_CLAUDE = r'''#!{python}
import json, os, sys
args = sys.argv[1:]
prompt = sys.stdin.read()
def out(ev): print(json.dumps(ev), flush=True)
log = os.environ["FAKE_CLAUDE_LOG"]
with open(log, "a") as f:
    f.write(json.dumps({{"args": args, "cwd": os.getcwd(), "stdin": prompt,
                        "api_key": "ANTHROPIC_API_KEY" in os.environ}}) + "\n")
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
tools = os.environ.get("FAKE_CLAUDE_TOOLS", "")
if mode == "noisy":
    sys.stderr.write("w" * 300_000); sys.stderr.flush()
if mode == "rate-limit":
    out({{"type": "result", "subtype": "error", "is_error": True, "result": "API error: rate limit exceeded"}}); sys.exit(1)
if mode == "limit-stderr":
    sys.stderr.write("You've hit your session limit · resets 3pm\n"); sys.exit(1)
out({{"type": "system", "subtype": "init", "tools": [t for t in tools.split(",") if t], "model": "m"}})
out({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": "thinking"}}], "usage": {{}}}}}})
if mode == "limit-result":
    out({{"type": "result", "subtype": "error", "is_error": True, "result": "Usage limit reached"}}); sys.exit(1)
out({{"type": "result", "subtype": "success", "is_error": False, "result": "the answer",
     "usage": {{"input_tokens": 50, "output_tokens": 5}}, "total_cost_usd": 0.01, "num_turns": 1}})
'''


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    exe = bin_ / "claude"
    exe.write_text(FAKE_CLAUDE.format(python=sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(tmp_path / "claude.log"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "would-bill-the-api")
    return lambda: [json.loads(x) for x in (tmp_path / "claude.log").read_text().splitlines()]


def test_a_cli_conversation_is_blind_and_recorded(tmp_path, monkeypatch, fake_claude):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("FAKE_CLAUDE_TOOLS", "mcp__phase_b__read_file,mcp__phase_b__write_file")
    b = CliBackend("m-under-test")
    out = b.converse("the role", "the message", ToolSpec("files", str(ws)), Transcript(tmp_path / "t.jsonl"))
    assert out == "the answer"
    (call,) = fake_claude()
    a = call["args"]
    assert a[a.index("--tools") + 1] == "" and "--strict-mcp-config" in a                  # no built-in tools
    assert a[a.index("--system-prompt") + 1] == "the role" and a[a.index("--model") + 1] == "m-under-test"
    assert call["stdin"] == "the message" and not call["api_key"]                          # the subscription
    assert ROOT not in Path(call["cwd"]).parents and Path(call["cwd"]) != ROOT             # outside the repository
    kinds = [json.loads(x)["kind"] for x in (tmp_path / "t.jsonl").read_text().splitlines()]
    assert kinds == ["start", "init", "reply", "result"]
    assert b.report()["tokens"]["input"] == 50 and b.usd == pytest.approx(0.01)


def test_a_cli_conversation_with_other_tools_stops_the_run(tmp_path, monkeypatch, fake_claude):
    monkeypatch.setenv("FAKE_CLAUDE_TOOLS", "Read,Bash")
    with pytest.raises(BackendError, match="Bash"):
        CliBackend("m").converse("r", "m", None, Transcript(tmp_path / "t.jsonl"))


@pytest.mark.parametrize("mode", ["limit-stderr", "limit-result"])
def test_the_usage_limit_is_recognised(tmp_path, monkeypatch, fake_claude, mode):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    with pytest.raises(UsageLimit):
        CliBackend("m").converse("r", "m", None, Transcript(tmp_path / "t.jsonl"))


def test_the_cli_run_refuses_user_memory_unless_allowed(tmp_path, monkeypatch, fake_claude):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "CLAUDE.md").write_text("Always answer in French.")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    inst = instruments(tmp_path)
    with pytest.raises(SystemExit, match="CLAUDE.md"):
        runner.main(arm_args(tmp_path, inst))
    runner.main(arm_args(tmp_path, inst, "nl", "--allow-user-memory", "--seqs", "1"))     # end to end on `claude`
    man = json.loads((tmp_path / "run/nl/manifest.json").read_text())
    assert man["user_memory"] == hashlib.sha256(b"Always answer in French.").hexdigest()
    assert man["backend"] == "cli" and man["done"] == [1]
    rec = json.loads((tmp_path / "run/nl/seq-01/record.json").read_text())
    assert rec["check"]["error"] and rec["tokens"]["input"] == 100      # a review that is not JSON is recorded
    assert [c["args"][c["args"].index("--model") + 1] for c in fake_claude()] == ["m-under-test"] * 2


# -- an arm, change by change --------------------------------------------------------------

def test_a_text_arm_edits_checks_and_deploys_each_change(tmp_path):
    inst = instruments(tmp_path)
    b, m = api()
    arm = nl_arm(materials(tmp_path), tmp_path / "run/nl", b)
    man = runner.run_arm(arm, tmp_path / "run/nl", runner.change_requests(inst)[:1], b, "fake", inst)
    assert man["done"] == [1] and man["sessions"][-1]["stopped"] is None
    rec = json.loads((tmp_path / "run/nl/seq-01/record.json").read_text())
    assert "+Stages: drafted, built." in rec["edit"]["diff"]
    assert rec["check"]["findings"][0]["kind"] == "reference"
    assert "built" in (tmp_path / "run/nl/deployed/SKILL.md").read_text()      # deployed though flagged
    review = next(c for c in m.calls if "review a change" in c["system"])
    assert "+Stages: drafted, built." in review["messages"][0]["content"]     # the reviewer sees the diff
    assert man["materials"] and set(man["prompts"]) == {"edit.md", "review.md", "render.md"}
    assert rec["tokens"]["input"] == 0                    # the fake API backend has no budget to count


def test_no_conversation_sees_the_key_or_the_binding(tmp_path):
    inst = instruments(tmp_path)
    b, m = api()
    runner.main(arm_args(tmp_path, inst, "structured", "--seqs", "1-2"), backend=b)
    sent = json.dumps(m.calls)
    assert SEALED not in sent and "change-key" not in sent
    for t in (tmp_path / "run").rglob("*.jsonl"):
        assert SEALED not in t.read_text()
    assert json.loads((tmp_path / "run/structured/manifest.json").read_text())["done"] == [1, 2]


def test_a_run_refuses_to_start_when_an_instrument_changed(tmp_path):
    inst = instruments(tmp_path)
    (inst / "probe-suite.yaml").write_text("changed: true\n")
    with pytest.raises(SystemExit, match="probe-suite.yaml changed after freezing"):
        runner.main(arm_args(tmp_path, inst), backend=api()[0])
    assert not (tmp_path / "run").exists()


def test_a_stopped_run_resumes_where_it_stopped(tmp_path):
    inst = instruments(tmp_path)
    b = Budget((1000.0, 1000.0, 0, 0), cap_usd=0.25)          # one change costs about $0.33
    with pytest.raises(SystemExit) as e:
        runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1-3"), backend=api(budget=b)[0])
    assert e.value.code == 2
    man = json.loads((tmp_path / "run/nl/manifest.json").read_text())
    assert man["done"] == [1] and man["sessions"][0]["stopped"].startswith("BudgetExceeded")
    assert (tmp_path / "run/nl/seq-02").is_dir()                               # the change left half done
    (tmp_path / "run/nl/workspace/SKILL.md").write_text("half-edited")

    b2, m2 = api()
    runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1-3"), backend=b2)
    man = json.loads((tmp_path / "run/nl/manifest.json").read_text())
    assert man["done"] == [1, 2, 3] and len(man["sessions"]) == 2
    first_edit = next(c for c in m2.calls if "review a change" not in c["system"])
    assert "Change request 2:" in first_edit["messages"][0]["content"]          # 1 was not run again
    assert "half-edited" not in (tmp_path / "run/nl/deployed/SKILL.md").read_text()


def test_a_run_does_not_resume_with_another_model(tmp_path):
    inst = instruments(tmp_path)
    runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1"), backend=api()[0])
    args = arm_args(tmp_path, inst, "nl", "--seqs", "1-2")
    args[args.index("--model") + 1] = "another"
    with pytest.raises(SystemExit, match="model differs"):
        runner.main(args, backend=api()[0])


def test_status_shows_how_far_each_arm_got(tmp_path, capsys):
    inst = instruments(tmp_path)
    runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1-2"), backend=api()[0])
    capsys.readouterr()
    runner.main(["status", "--out", str(tmp_path / "run")])
    (row,) = json.loads(capsys.readouterr().out)
    assert row["arm"] == "nl" and row["done"] == 2 and row["of"] == 20 and row["last_stopped"] is None


def test_the_seq_option_names_existing_requests():
    assert runner.seqs("1-2,5", list(range(1, 21))) == [1, 2, 5]
    with pytest.raises(SystemExit, match="21"):
        runner.seqs("20-21", list(range(1, 21)))


# -- the NL arm's materials ----------------------------------------------------------------

def test_the_skill_is_rendered_from_the_declarations_alone(tmp_path):
    decl = tmp_path / "decl"
    (decl / "authoring").mkdir(parents=True)
    (decl / "authoring/authoring.domain.yaml").write_text("domain: authoring\n")
    b, _ = api([tool_use("write_file", {"path": "SKILL.md", "content": "# Skill"}, "a"),
                tool_use("write_file", {"path": "EXAMPLES.md", "content": "# Examples"}, "b"), "written"])
    render_skill(decl, tmp_path / "nl", b, tmp_path / "render.jsonl")
    assert sorted(p.name for p in (tmp_path / "nl").rglob("*")) == ["EXAMPLES.md", "SKILL.md"]
    with pytest.raises(RuntimeError, match="EXAMPLES.md"):
        render_skill(decl, tmp_path / "nl2", api(["I wrote nothing"])[0], tmp_path / "r2.jsonl")


def test_a_new_run_does_not_overwrite_an_old_one(tmp_path):
    m = materials(tmp_path)
    structured_arm(m, tmp_path / "run", api()[0])
    with pytest.raises(FileExistsError):
        structured_arm(m, tmp_path / "run", api()[0])


# -- review fixes ----------------------------------------------------------------------------

def test_changes_run_in_the_frozen_order(tmp_path):
    inst = instruments(tmp_path)
    with pytest.raises(SystemExit, match=r"next is \[1\], asked for \[3\]"):
        runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "3"), backend=api()[0])
    runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1-2"), backend=api()[0])
    with pytest.raises(SystemExit, match=r"next is \[3\], asked for \[4, 5\]"):
        runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "4-5"), backend=api()[0])
    runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1-3"), backend=api()[0])     # done ones are skipped


@pytest.mark.parametrize("left", [("old", "new"), ("old",)])
def test_a_deploy_stopped_halfway_is_recovered_on_resume(tmp_path, left):
    inst = instruments(tmp_path)
    runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1"), backend=api()[0])
    work = tmp_path / "run/nl"
    for suffix in left:                                    # a stop between the copy and the renames
        shutil.copytree(work / "deployed", work / f"deployed.{suffix}")
    shutil.rmtree(work / "deployed")
    runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1-2"), backend=api()[0])
    assert json.loads((work / "manifest.json").read_text())["done"] == [1, 2]
    assert not (work / "deployed.old").exists() and not (work / "deployed.new").exists()


def test_an_error_is_recorded_on_the_session_before_it_propagates(tmp_path):
    inst = instruments(tmp_path)

    def boom(system, messages, tools):
        raise RuntimeError("claude crashed")
    with pytest.raises(RuntimeError, match="crashed"):
        runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1"), backend=api(boom)[0])
    (s,) = json.loads((tmp_path / "run/nl/manifest.json").read_text())["sessions"]
    assert s["stopped"] == "error: RuntimeError: claude crashed" and s["finished_at"]


def test_a_noisy_claude_does_not_block_the_run(tmp_path, monkeypatch, fake_claude):
    import threading
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "noisy")
    got = {}
    th = threading.Thread(target=lambda: got.update(out=CliBackend("m").converse(
        "r", "m", None, Transcript(tmp_path / "t.jsonl"))), daemon=True)
    th.start()
    th.join(30)
    assert got.get("out") == "the answer"


def test_a_rate_limit_is_an_error_not_the_usage_limit(tmp_path, monkeypatch, fake_claude):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "rate-limit")
    with pytest.raises(BackendError, match="rate limit"):
        CliBackend("m").converse("r", "m", None, Transcript(tmp_path / "t.jsonl"))


def test_a_run_does_not_resume_with_other_user_memory(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    inst = instruments(tmp_path)
    runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1"), backend=api()[0])
    (cfg / "CLAUDE.md").write_text("Be brief.")
    with pytest.raises(SystemExit, match="user_memory differs"):
        runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1-2", "--allow-user-memory"), backend=api()[0])


def test_status_counts_the_runs_own_requests(tmp_path, capsys):
    inst = instruments(tmp_path, keep=3)
    runner.main(arm_args(tmp_path, inst, "nl", "--seqs", "1"), backend=api()[0])
    capsys.readouterr()
    runner.main(["status", "--out", str(tmp_path / "run")])
    assert json.loads(capsys.readouterr().out)[0]["of"] == 3


def test_findings_are_found_among_other_braces():
    text = 'Note {previewed} is renamed.\n{"findings": [{"problem": "p"}]}\nSee {built}.'
    assert parse_findings(text) == ([{"problem": "p"}], None)

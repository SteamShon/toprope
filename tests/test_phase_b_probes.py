"""The M1 Phase B probes (ADR-0040 §6): their starting states, their tools, and running them."""

from __future__ import annotations

import asyncio
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
from phase_b.baseline import baseline_root  # noqa: E402

from phase_b import run as runner
from phase_b.agent import ToolError, Transcript
from phase_b.backend import ApiBackend, CliBackend
from phase_b.model import FakeModel, tool_use
from phase_b.probes import (
    PROBES,
    RULES_URL,
    build_worlds,
    generic_tools,
    load_probes,
    run_probe,
    servers,
)
from phase_b.toprope_arm import export_toolchain

INSTRUMENTS = ROOT / "experiments/m1/instruments"


@pytest.fixture(scope="module")
def worlds(tmp_path_factory):
    base = tmp_path_factory.mktemp("worlds")
    situations = build_worlds(baseline_root(ROOT), export_toolchain(baseline_root(ROOT), base / "toolchain"), base / "worlds")
    return base / "worlds", situations, base / "toolchain"


def state(worlds, pid):
    return json.loads((worlds[0] / pid / "state.json").read_text())["objects"]


def tools(root, objects=True):
    return {t.name: t for t in generic_tools(root, with_objects=objects)}


# -- the starting states ----------------------------------------------------------------------

def test_every_probe_has_a_starting_state(worlds):
    assert sorted(worlds[1]) == PROBES == [p["id"] for p in load_probes(INSTRUMENTS)]


def test_p01_has_drafted_elements_awaiting_a_person(worlds):
    objs = state(worlds, "P01")
    assert [objs[e]["review"] for e in worlds[1]["P01"]["proposed"]] == ["proposed", "proposed"]


def test_p02_has_a_newer_commit_than_the_one_reviewed(worlds):
    s, objs = worlds[1]["P02"], state(worlds, "P02")
    assert objs[s["reviewed_by_owner"]]["type"] == objs[s["newest"]]["type"] == "Commit"
    assert not objs[s["reviewed_by_owner"]].get("approved") and not objs[s["newest"]].get("approved")


def test_p03_has_a_source_nobody_can_read(worlds):
    assert state(worlds, "P03")["rules"]["path"] == RULES_URL
    with pytest.raises(ToolError, match="cannot read"):
        tools(worlds[0] / "P03")["read_source"].fn(source="rules")


def test_p04_has_an_open_bundle(worlds):
    assert state(worlds, "P04")["library"]["bundle"].startswith("bundle:")


def test_p05_p06_p07_p08_have_the_commits_their_states_say(worlds):
    p05, p06, p07, p08 = (state(worlds, p) for p in ("P05", "P06", "P07", "P08"))
    assert not p05[worlds[1]["P05"]["unapproved"]].get("approved")
    assert all(p06[c]["approved"] for c in worlds[1]["P06"]["approved_since"])
    log = tools(worlds[0] / "P06")["commit_log"].fn()
    assert [c["approved"] for c in log] == [True, True, True]
    assert tools(worlds[0] / "P06")["deployed"].fn()["current"]["commit"] == worlds[1]["P06"]["deployed"]
    assert p07[worlds[1]["P07"]["approved"]]["approved"]
    assert not [o for o in p07.values() if o["type"] == "DeliveryRequest" and o["commit"] == worlds[1]["P07"]["approved"]]
    refused = p08[worlds[1]["P08"]["request"]]
    assert refused["refusal"].startswith("superseded") and refused["deployed"] is False
    assert worlds[1]["P08"]["refusal"] == refused["refusal"] and worlds[1]["P08"]["deployed"] is False  # as shown


# -- the probe agent's tools ------------------------------------------------------------------

def test_the_generic_tools_reach_the_owner_and_the_records_only(worlds, tmp_path):
    root = tmp_path / "w"
    shutil.copytree(worlds[0] / "P06", root)
    t = tools(root)
    assert "Sent to the owner" in t["message_person"].fn(text="Which commit?", choices=["C2", "C3"])
    assert json.loads((root / "outbox.jsonl").read_text())["choices"] == ["C2", "C3"]
    c2, c3 = worlds[1]["P06"]["approved_since"]
    assert t["commit_diff"].fn(from_commit=c2, to_commit=c3)["added"] == ["action:inspect"]
    t["update_object"].fn(id=c3, fields={"note": "seen"})
    assert t["get_object"].fn(id=c3)["note"] == "seen"
    assert "list_objects" not in tools(root, objects=False)          # the Toprope arm has its own tools


def test_a_text_arm_probe_runs_blind_to_what_the_probe_checks(worlds, tmp_path):
    (p01,) = [p for p in load_probes(INSTRUMENTS) if p["id"] == "P01"]
    m = FakeModel([tool_use("message_person", {"text": "Please confirm E-renew and E-inspect.",
                                               "choices": ["confirm", "reject"]}), "I asked the owner."])
    out = run_probe(ApiBackend(m), worlds[0], p01, tmp_path, "a skill", "# Skill\nOnly a person confirms.")
    assert out["answer"] == "I asked the owner." and out["messages_to_owner"][0]["choices"] == ["confirm", "reject"]
    sent = json.dumps(m.calls)
    assert p01["task"] in sent and "# Skill" in sent
    assert not any(x in sent for x in [*p01["must"], *p01["must_not"]])                    # the grader's only
    assert not list(tmp_path.glob("P01-*"))                                                 # the copy is gone


def test_a_failing_probe_is_recorded_not_raised(worlds, tmp_path):
    (p05,) = [p for p in load_probes(INSTRUMENTS) if p["id"] == "P05"]

    def boom(system, messages, tools):
        raise RuntimeError("the conversation broke")
    out = run_probe(ApiBackend(FakeModel(boom)), worlds[0], p05, tmp_path, "a skill", "")
    assert out["error"] == "RuntimeError: the conversation broke"


# -- the Toprope arm's probes: the generated MCP of what is deployed ----------------------------

def test_the_generated_servers_open_a_probe_world(worlds, tmp_path):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    root = tmp_path / "w"
    shutil.copytree(worlds[0] / "P07", root)
    cfg = servers(root)["authoring"]

    async def go():
        params = StdioServerParameters(command=cfg["command"], args=cfg["args"], env={**os.environ, **cfg["env"]})
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
            got = await s.call_tool("get_object", {"object_id": worlds[1]["P07"]["approved"]})
            refused = await s.call_tool("approve_commit", {"target_id": worlds[1]["P07"]["approved"],
                                                           "idempotency_key": "k1"})
            return names, got, refused

    names, got, refused = asyncio.run(go())
    assert {"deliver", "propose_element", "request_decision"} <= names
    assert json.loads(got.content[0].text)["approved"] is True                     # the world's state
    assert refused.structured_content["status"] == "denied"                        # a person's action
    assert refused.structured_content["code"] == "actor"


def test_each_probe_agent_may_take_what_its_task_asks_and_a_person_still_decides(worlds, tmp_path):
    """The M1 recheck (probe-baseline-findings.md, cause 2): P07's agent may hand the commit over,
    and P06's agent is refused a deploy because it requires a person, not for want of a grant."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def call(pid, member, tool, args):
        root = tmp_path / pid
        shutil.copytree(worlds[0] / pid, root)
        cfg = servers(root)[member]
        params = StdioServerParameters(command=cfg["command"], args=cfg["args"], env={**os.environ, **cfg["env"]})
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            return (await s.call_tool(tool, {**args, "idempotency_key": "k1"})).structured_content

    handed = asyncio.run(call("P07", "authoring", "deliver",
                              {"target_id": worlds[1]["P07"]["approved"], "environment": "local"}))
    assert handed["status"] == "ok", handed
    request = asyncio.run(call("P08", "delivery", "deploy", {"target_id": worlds[1]["P08"]["request"]}))
    assert (request["status"], request["code"]) == ("denied", "actor"), request
    assert "grant" not in (request.get("reason") or "").lower()


FAKE = r'''#!{python}
import json, os, sys
args = sys.argv[1:]
cfg = json.load(open(args[args.index("--mcp-config") + 1])) if "--mcp-config" in args else {{}}
open(os.environ["FAKE_LOG"], "w").write(json.dumps({{"args": args, "cfg": cfg}}))
sys.stdin.read()
tools = os.environ.get("FAKE_TOOLS", "").split(",")
print(json.dumps({{"type": "system", "subtype": "init", "tools": tools}}))
print(json.dumps({{"type": "result", "subtype": "success", "is_error": False, "result": "done", "usage": {{}}}}))
'''


def test_a_toprope_probe_gets_the_deployed_servers_and_nothing_else(worlds, tmp_path, monkeypatch):
    exe = tmp_path / "bin/claude"
    exe.parent.mkdir()
    exe.write_text(FAKE.format(python=sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "log.json"))
    monkeypatch.setenv("FAKE_TOOLS", "mcp__authoring__deliver,mcp__delivery__deploy,mcp__phase_b__message_person")
    (p07,) = [p for p in load_probes(INSTRUMENTS) if p["id"] == "P07"]
    deployed = tmp_path / "deployed"
    shutil.copytree(worlds[2], deployed)
    decl = yaml.safe_load((deployed / "delivery/delivery.domain.yaml").read_text())
    decl["actions"]["verify"]["description"] = "Changed by a deployed change."
    (deployed / "delivery/delivery.domain.yaml").write_text(yaml.safe_dump(decl, sort_keys=False))
    out = run_probe(CliBackend("m"), worlds[0], p07, tmp_path / "probes", "Toprope", "guides", deployed)
    assert out["answer"] == "done"
    log = json.loads((tmp_path / "log.json").read_text())
    assert set(log["cfg"]["mcpServers"]) == {"phase_b", "authoring", "delivery"}
    a = log["args"]
    assert {"mcp__phase_b", "mcp__authoring", "mcp__delivery"} <= set(a) and a[a.index("--tools") + 1] == ""
    spec = json.loads(log["cfg"]["mcpServers"]["phase_b"]["args"][-1])
    assert json.loads(spec["context"])["objects"] is False                     # no JSON objects: its own tools
    monkeypatch.setenv("FAKE_TOOLS", "mcp__authoring__deliver,Bash")
    bad = run_probe(CliBackend("m"), worlds[0], p07, tmp_path / "probes", "Toprope", "guides", deployed)
    assert "Bash" in bad["error"]


def test_the_toprope_probe_tools_follow_the_deployed_declarations(worlds, tmp_path):
    """The world's tools are replaced by the deployed declarations before the probe runs."""
    seen = {}

    class Spy(ApiBackend):
        def converse(self, system, user, tools, transcript, max_turns=40):
            root = Path(tools.root)
            seen["decl"] = (root / "toolchain/delivery/delivery.domain.yaml").read_text()
            seen["servers"] = sorted(json.loads(tools.context)["servers"])
            return "ok"
    deployed = tmp_path / "deployed"
    shutil.copytree(worlds[2], deployed)
    (deployed / "delivery/delivery.domain.yaml").write_text(
        (deployed / "delivery/delivery.domain.yaml").read_text().replace("domain: delivery", "domain: delivery\n# deployed"))
    (p07,) = [p for p in load_probes(INSTRUMENTS) if p["id"] == "P07"]
    run_probe(Spy(FakeModel([])), worlds[0], p07, tmp_path / "probes", "Toprope", "guides", deployed)
    assert "# deployed" in seen["decl"] and seen["servers"] == ["authoring", "delivery"]


# -- the run ------------------------------------------------------------------------------------

def test_a_run_probes_after_every_change(worlds, tmp_path):
    from test_phase_b import instruments, materials
    inst = instruments(tmp_path)
    out = tmp_path / "run"
    out.mkdir()
    shutil.copytree(worlds[0], out / "worlds")                          # built once per run directory

    def script(system, messages, tools):
        if "review a change" in system:
            return '{"findings": []}'
        if "Change request" in str(messages[0]["content"]) and len(messages) == 1:
            return tool_use("replace_in_file", {"path": "SKILL.md", "old": "previewed", "new": "built"})
        return "done"
    runner.main(["arm", "nl", "--model", "m", "--materials", str(materials(tmp_path)), "--out", str(out),
                 "--seqs", "1", "--instruments", str(inst)], backend=ApiBackend(FakeModel(script)))
    rec = json.loads((out / "nl/seq-01/record.json").read_text())
    assert [r["run"] for r in rec["probes"]] == [1, 2, 3]                     # run protocol §3: three runs
    assert all([p["probe"] for p in r["results"]] == PROBES for r in rec["probes"]) and rec["seconds"]["probes"] > 0
    assert [len(list((out / "nl/seq-01/probes" / f"run-{k}").glob("P0*.jsonl"))) for k in (1, 2, 3)] == [8, 8, 8]
    before = json.loads((out / "nl/seq-00/record.json").read_text())             # the probes before any change
    assert all([p["probe"] for p in r["results"]] == PROBES for r in before["probes"])
    assert set(before["tokens"]) >= {"input", "output"}                         # what the probes before any change cost
    man = json.loads((out / "nl/manifest.json").read_text())
    assert man["probes"] and man["sessions"][-1]["probes"] == man["probes"]
    assert man["sessions"][-1]["jobs"] == 4                                  # probes four at a time by default
    assert man["baseline"] == runner.baseline() and set(man["baseline"]) == {"authoring", "delivery"}
    with pytest.raises(SystemExit, match="probes differs"):                 # a run does not switch them off
        runner.main(["arm", "nl", "--model", "m", "--materials", str(materials(tmp_path)), "--out", str(out),
                     "--seqs", "1-2", "--instruments", str(inst), "--no-probes"], backend=ApiBackend(FakeModel(script)))


def test_the_starting_states_are_the_same_for_every_change(worlds):
    a = {p: json.loads((worlds[0] / p / "situation.json").read_text()) for p in PROBES}
    assert a == worlds[1]


def test_transcripts_name_each_probe(worlds, tmp_path):
    (p02,) = [p for p in load_probes(INSTRUMENTS) if p["id"] == "P02"]
    out = run_probe(ApiBackend(FakeModel(["ok"])), worlds[0], p02, tmp_path, "a skill", "")
    assert out["transcript"] == "P02.jsonl" and Transcript(tmp_path / "P02.jsonl").path.exists()


# -- probes in parallel -------------------------------------------------------------------------------

class Slow(ApiBackend):
    """Takes a while per conversation and counts how many run at once."""

    def __init__(self, fail_on=None):
        super().__init__(FakeModel([]))
        import threading
        self.now = self.peak = 0
        self.lock, self.fail_on = threading.Lock(), fail_on

    def converse(self, system, user, tools, transcript, max_turns=40):
        import time
        with self.lock:
            self.now += 1
            self.peak = max(self.peak, self.now)
        time.sleep(0.4)
        with self.lock:
            self.now -= 1
        if self.fail_on and self.fail_on in user:
            from phase_b.backend import UsageLimit
            raise UsageLimit("hit your limit")
        transcript.write("result", result=user[:20])
        return "done"


def test_probes_run_at_once_and_keep_their_order(worlds, tmp_path):
    import time

    from phase_b.probes import run_probes
    b = Slow()
    t = time.monotonic()
    out = run_probes(b, worlds[0], load_probes(INSTRUMENTS), tmp_path, "a skill", "", jobs=4)
    assert [r["probe"] for r in out] == PROBES and all(r["answer"] == "done" for r in out)
    assert b.peak == 4 and time.monotonic() - t < 8 * 0.4                  # not one after another


def test_a_usage_limit_in_one_probe_stops_after_the_others_finish(worlds, tmp_path):
    from phase_b.backend import UsageLimit
    from phase_b.probes import run_probes
    probes = load_probes(INSTRUMENTS)
    with pytest.raises(UsageLimit):
        run_probes(Slow(fail_on=probes[2]["task"]), worlds[0], probes, tmp_path, "a skill", "", jobs=4)
    ran = sorted(x.stem for x in tmp_path.glob("P0*.jsonl"))                 # every other probe ran to its end
    assert ran == [p["id"] for p in probes if p is not probes[2]]


def test_token_counts_add_up_when_conversations_run_at_once(tmp_path, monkeypatch):
    import threading
    exe = tmp_path / "bin/claude"
    exe.parent.mkdir()
    exe.write_text(FAKE.format(python=sys.executable).replace('"usage": {}', '"usage": {"input_tokens": 50}')
                   .replace('os.environ.get("FAKE_TOOLS", "").split(",")',
                            '[t for t in os.environ.get("FAKE_TOOLS", "").split(",") if t]'))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "log.json"))
    monkeypatch.setenv("FAKE_TOOLS", "")
    b = CliBackend("m")
    threads = [threading.Thread(target=b.converse, args=("r", "m", None, Transcript(tmp_path / f"t{i}.jsonl")))
               for i in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert b.report()["tokens"]["input"] == 8 * 50

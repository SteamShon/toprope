import asyncio
import json
import subprocess

import yaml
from mcp import Client

from test_decl import schema_doc_domain
from toprope.adapters.mcp import build_server
from toprope.decl import Domain
from toprope.exec import Execution
from toprope.harness import run_harness
from toprope.identity import Caller, StaticIdentity
from toprope.semantics import Actor, Grant
from toprope.store import MemoryEventStore
from toprope.worldmap import build_world_map, how_to_reach, to_mermaid

ANA = Actor("ana", "person", ("approver",))
ELI = Actor("eli", "person", ("eng",))


def dom(mutate=None) -> Domain:
    raw = schema_doc_domain()
    if mutate:
        mutate(raw)
    return Domain.model_validate(raw)


def edge(m, eid):
    return next(e for e in m["behavior"]["edges"] if e["id"] == eid)


def test_structure_and_behavior_layers_come_from_the_declaration():
    m = build_world_map(dom())
    assert {n["id"] for n in m["structure"]["nodes"]} == {"Experiment", "Hypothesis", "Metric", "Readout"}
    hyp = next(e for e in m["structure"]["edges"] if e["id"] == "hypothesis")
    assert (hyp["from"], hyp["to"], hyp["required"], hyp["status"]) == ("Experiment", "Hypothesis", True, "proposed")
    states = {s["state"]: s for s in m["behavior"]["states"]}
    assert states["draft"]["initial"] and states["decided"]["terminal"] and not states["approved"]["terminal"]
    assert len(m["behavior"]["edges"]) == 10                      # 5 states x 2 actions
    ap = edge(m, "Experiment.draft.approve_experiment")
    assert ap["outcome"] == {"kind": "to", "to": "approved"}
    assert ap["unlock"]["actors"] == [{"role": "approver"}]
    assert [p["id"] for p in ap["unlock"]["preconditions"]] == ["has-guardrails"]
    assert ap["records_decision"] is True and "running-has-approver" in ap["invariants"]
    deny = edge(m, "Experiment.running.approve_experiment")["outcome"]
    assert deny["kind"] == "deny" and deny["status"] == "confirmed"
    fog = edge(m, "Experiment.ended.launch_experiment")
    assert fog["fog"] is True and fog["outcome"] == {"kind": "undecided"}
    assert all(e["harness"] == "unknown" for e in m["behavior"]["edges"])     # no harness report given


def test_by_role_and_to_cells_and_where_rules_are_mapped():
    def mutate(raw):
        m = raw["transitions"]["Experiment"]["matrix"]
        m["approved"]["launch_experiment"] = {"by_role": {"eng": "running", "pm": {"deny": "PMs never launch."}}}
        raw["actions"]["launch_experiment"]["actor"] = [{"role": "eng", "where": "target.planned_days >= 1"}, "pm"]
    m = build_world_map(dom(mutate))
    la = edge(m, "Experiment.approved.launch_experiment")
    assert la["outcome"]["kind"] == "by_role"
    assert la["outcome"]["by_role"]["pm"] == {"kind": "deny", "reason": "PMs never launch.", "status": None}
    assert la["unlock"]["actors"] == [{"role": "eng", "where": "target.planned_days >= 1"}, {"role": "pm"}]
    path = how_to_reach(m, "Experiment", "approved", "running", ("pm",))
    assert path["steps"][0]["who"] == ["eng"] and path["steps"][0]["you_can"] is False


def test_harness_results_are_overlaid_per_edge():
    d = dom()
    m = build_world_map(d, run_harness(d, explore_examples=0, races=False).to_json())
    assert edge(m, "Experiment.draft.approve_experiment")["harness"] == "verified"
    assert edge(m, "Experiment.decided.launch_experiment")["harness"] == "uncovered"   # no instance in decided
    assert m["unreachable"] == {"Experiment": ["ended", "decided"]}

    def seed_bug(raw):
        raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"] = "running"
    bad = dom(seed_bug)
    m2 = build_world_map(bad, run_harness(bad, levels=("model",), explore_examples=0, races=False).to_json())
    assert edge(m2, "Experiment.draft.launch_experiment")["harness"] == "failed"
    assert edge(m2, "Experiment.draft.approve_experiment")["harness"] == "verified"


def test_world_map_is_deterministic():
    a = json.dumps(build_world_map(dom()), sort_keys=True)
    b = json.dumps(build_world_map(dom()), sort_keys=True)
    assert a == b


def test_how_to_reach_paths_and_who_can_act():
    m = build_world_map(dom())
    p = how_to_reach(m, "Experiment", "draft", "running", ("eng",))
    assert [(s["action"], s["from"], s["to"], s["who"], s["you_can"]) for s in p["steps"]] == [
        ("approve_experiment", "draft", "approved", ["approver"], False),
        ("launch_experiment", "approved", "running", ["eng"], True)]
    assert p["steps"][0]["requires"] == ["An experiment needs at least one guardrail metric before approval."]
    assert how_to_reach(m, "Experiment", "draft", "draft")["steps"] == []
    no = how_to_reach(m, "Experiment", "running", "decided")
    assert no["reachable"] is False and "running" in no["reason"]


def test_how_to_reach_prefers_steps_the_caller_can_take():
    def two_routes(raw):   # pm may also approve, via its own by_role column
        raw["actions"]["approve_experiment"]["actor"] = ["approver", "pm"]
        raw["transitions"]["Experiment"]["matrix"]["draft"]["approve_experiment"] = {
            "by_role": {"approver": "approved", "pm": "approved"}}
    m = build_world_map(dom(two_routes))
    p = how_to_reach(m, "Experiment", "draft", "approved", ("pm",))
    assert p["steps"][0]["you_can"] is True and "pm" in p["steps"][0]["who"]


def test_mermaid_export():
    mm = to_mermaid(build_world_map(dom()))
    assert "Experiment -->|hypothesis| Hypothesis" in mm["structure"]
    sd = mm["states"]["Experiment"]
    assert "[*] --> draft" in sd and "draft --> approved: approve_experiment" in sd
    assert "note right of ended: launch_experiment undecided" in sd


def _payload(res):
    sc = res.structured_content
    return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc


def test_world_map_and_how_to_reach_mcp_tools():
    bot = Caller(Actor("bot", "agent", ("approver", "eng")), ANA, Grant("g", frozenset({"approve_experiment"})))
    ids = StaticIdentity({"t-eli": Caller(ELI), "t-bot": bot})
    ex = Execution(dom(), MemoryEventStore(), ids)
    ex.seed_world()
    tok = {"v": None}
    report = {"coverage": {"edges": {"Experiment.draft.approve_experiment": "verified"}, "unreachable": {}}}

    async def go():
        async with Client(build_server(ex, lambda: tok["v"], harness=report)) as c:
            wm = _payload(await c.call_tool("world_map", {}))
            assert edge(wm, "Experiment.draft.approve_experiment")["harness"] == "verified"
            r = await c.call_tool("how_to_reach", {"object_id": "E-onboarding", "target_state": "running"})
            assert r.is_error                                                # needs a caller
            tok["v"] = "t-eli"
            p = _payload(await c.call_tool("how_to_reach", {"object_id": "E-onboarding", "target_state": "running"}))
            assert [s["you_can"] for s in p["steps"]] == [False, True]
            tok["v"] = "t-bot"   # the agent holds eng, but its principal does not
            p = _payload(await c.call_tool("how_to_reach", {"object_id": "E-onboarding", "target_state": "running"}))
            assert [s["you_can"] for s in p["steps"]] == [True, False]
            gone = _payload(await c.call_tool("how_to_reach", {"object_id": "nope", "target_state": "running"}))
            assert gone["reachable"] is False
    asyncio.run(go())


def test_cli_writes_map_and_mermaid(tmp_path):
    f = tmp_path / "d.domain.yaml"
    f.write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    out = tmp_path / "world-map.json"
    r = subprocess.run(["uv", "run", "--quiet", "toprope-worldmap", "--domain", str(f), "--out", str(out),
                        "--harness", "--mermaid", str(tmp_path / "mm")], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    m = json.loads(out.read_text())
    assert m["format"] == "toprope.world-map/1" and edge(m, "Experiment.draft.approve_experiment")["harness"] == "verified"
    assert (tmp_path / "mm" / "Experiment.states.mmd").read_text().startswith("stateDiagram-v2")


def test_a_report_without_coverage_is_tolerated():
    m = build_world_map(dom(), {"ok": False, "coverage": None})
    assert m["unreachable"] == {} and all(e["harness"] == "unknown" for e in m["behavior"]["edges"])

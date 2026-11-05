"""Drive the generated MCP server like an agent would, and assert the outcomes."""
import asyncio
import json
import sys

from mcp import Client

from toprope_spike.kernel import Domain
from toprope_spike.server import build_server


def payload(res):
    if getattr(res, "structured_content", None):
        sc = res.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(res.content[0].text)


async def run(target):
    async with Client(target) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        assert {"approve_experiment", "launch_experiment", "get_object", "world_map", "history"} <= set(tools)
        print("tools:", sorted(tools))
        print("approve_experiment description:", tools["approve_experiment"].description)
        print("approve_experiment input schema:", json.dumps(tools["approve_experiment"].input_schema)[:300])

        async def call(name, **args):
            r = payload(await c.call_tool(name, args))
            print(f"  {name}({args}) -> {r.get('status')} {r.get('reason_code') or ''} {r.get('reason') or ''}")
            return r

        A = dict(actor_id="ana", actor_role="approver")
        E = dict(actor_id="eli", actor_role="eng")
        assert (await call("launch_experiment", target_id="E1", **E))["reason_code"] == "matrix"
        assert (await call("approve_experiment", target_id="E1", **E))["reason_code"] == "actor"
        assert (await call("approve_experiment", target_id="E2", **A))["reason_code"] == "has-guardrails"
        r = await call("approve_experiment", target_id="E1", note="ok", **A)
        assert r["status"] == "ok" and r["state"]["status"] == "approved" and r["state"]["approved_by"] == "ana"
        r = await call("launch_experiment", target_id="E1", **E)
        assert r["status"] == "ok" and r["state"]["status"] == "running"
        assert (await call("launch_experiment", target_id="E1", **E))["reason_code"] == "not-applicable"
        h = payload(await c.call_tool("history", {"object_id": "E1"}))
        kinds = [e["type"] for e in h["attempts"]]
        print("E1 events:", [e["type"] for e in h["events"]], "attempts:", kinds)
        assert kinds.count("DeniedAttempt") == 3 and "DecisionRecorded" in kinds
        wm = payload(await c.call_tool("world_map", {"role": "eng"}))
        unlocked = [(e["from"], e["action"]) for e in wm["edges"] if e["unlocked_for_role"] and e["to"]]
        print("world map edges:", len(wm["edges"]), "unlocked for eng:", unlocked)
        assert unlocked == [("approved", "launch_experiment")]
    print("PASS:", target if isinstance(target, str) else type(target).__name__)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else build_server(Domain("toy.domain.yaml"))
    asyncio.run(run(target))

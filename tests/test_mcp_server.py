import asyncio
import json
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from mcp import Client, StdioServerParameters

from test_decl import schema_doc_domain
from toprope.adapters.mcp import build_server
from toprope.decl import Domain
from toprope.exec import Execution
from toprope.identity import Caller, StaticIdentity
from toprope.semantics import Actor, Grant
from toprope.store import MemoryEventStore

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)
ANA = Actor("ana", "person", ("approver",))
ELI = Actor("eli", "person", ("eng",))
IDS = StaticIdentity({"t-ana": Caller(ANA), "t-eli": Caller(ELI)})


def make_ex(store=None):
    ex = Execution(Domain.model_validate(schema_doc_domain()), store or MemoryEventStore(), IDS, clock=lambda: NOW)
    ex.seed_world()
    return ex


def payload(res):
    sc = getattr(res, "structured_content", None)
    if sc is not None:
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    return json.loads(res.content[0].text)


class As:
    """Switchable credentials for in-process tests (stdio-like: one caller at a time)."""
    def __init__(self): self.token = None
    def __call__(self): return self.token


def run(coro):
    return asyncio.run(coro)


def test_tools_are_generated_from_the_declaration():
    async def go():
        async with Client(build_server(make_ex(), As())) as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
            assert {"approve_experiment", "launch_experiment", "get_object", "history", "attempts",
                    "allowed_actions", "describe_domain"} <= set(tools)
            ap = tools["approve_experiment"]
            assert set(ap.input_schema["required"]) == {"target_id", "idempotency_key"}
            assert "note" in ap.input_schema["properties"]
            assert "Who: approver." in ap.description and "Allowed when status is draft." in ap.description
            assert "at least one guardrail" in ap.description
            assert "Launch requires approval." in tools["launch_experiment"].description
    run(go())


def test_flow_through_mcp():
    who = As()

    async def go():
        async with Client(build_server(make_ex(), who)) as c:
            call = lambda n, **a: c.call_tool(n, a)  # noqa: E731
            who.token = None
            assert payload(await call("approve_experiment", target_id="E-onboarding", idempotency_key="k0"))["code"] == "unauthenticated"
            who.token = "t-eli"
            out = payload(await call("launch_experiment", target_id="E-onboarding", idempotency_key="k1"))
            assert out["status"] == "denied" and out["code"] == "matrix" and out["reason"] == "Launch requires approval."
            who.token = "t-ana"
            out = payload(await call("approve_experiment", target_id="E-onboarding", note="ok", idempotency_key="k2"))
            assert out["status"] == "ok" and out["state"]["status"] == "approved"
            again = payload(await call("approve_experiment", target_id="E-onboarding", note="ok", idempotency_key="k2"))
            assert again == out
            who.token = "t-eli"
            assert payload(await call("allowed_actions", object_id="E-onboarding")) == ["launch_experiment"]
            assert payload(await call("launch_experiment", target_id="E-onboarding", idempotency_key="k3"))["state"]["status"] == "running"
            types = [e["type"] for e in payload(await call("history", object_id="E-onboarding"))]
            assert types == ["ExperimentCreated", "ExperimentApproveExperiment", "DecisionRecorded", "ExperimentLaunchExperiment"]
            assert [a["payload"]["code"] for a in payload(await call("attempts", object_id="E-onboarding"))] == ["matrix"]
            assert payload(await call("describe_domain"))["domain"] == "example"
    run(go())


SEQUENCE = [("t-eli", "launch_experiment", "E-onboarding", {}), ("t-ana", "approve_experiment", "E-bare", {}),
            ("t-ana", "approve_experiment", "E-onboarding", {"note": "ok"}), ("t-eli", "approve_experiment", "E-onboarding", {}),
            ("t-eli", "launch_experiment", "E-onboarding", {}), ("t-eli", "launch_experiment", "E-onboarding", {}),
            ("t-ana", "approve_experiment", "E-ghost", {}), ("t-ana", "approve_experiment", "E-onboarding", {"note": 3})]


def test_parity_mcp_equals_execution():
    """The same commands through MCP and directly through Execution: identical outcomes and streams."""
    direct = make_ex()
    want = [direct.submit(t, a, tgt, p, f"k{i}") for i, (t, a, tgt, p) in enumerate(SEQUENCE)]
    via, who = make_ex(), As()

    async def go():
        got = []
        async with Client(build_server(via, who)) as c:
            for i, (t, a, tgt, p) in enumerate(SEQUENCE):
                who.token = t
                res = await c.call_tool(a, {"target_id": tgt, "idempotency_key": f"k{i}", **p})
                got.append("schema-rejected" if res.is_error else payload(res))
        return got

    got = run(go())
    from toprope.adapters.mcp import outcome_json
    for g, w in zip(got, want):
        if g == "schema-rejected":
            # The typed MCP schema refuses a mistyped param before Execution; Execution itself
            # refuses it as invalid-command. Both reject: that is parity for malformed input.
            assert w.code == "invalid-command"
        else:
            assert g == json.loads(json.dumps(outcome_json(w)))
    assert "schema-rejected" in got, "the sequence must exercise the malformed-input case"
    for oid in ("E-onboarding", "E-bare"):
        assert via.history(oid) == direct.history(oid)
        assert [a.payload for a in via.attempts(oid)] == [a.payload for a in direct.attempts(oid)]


# -- HTTP with bearer tokens ----------------------------------------------------------------------
def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture
def http_server():
    import uvicorn
    from toprope.adapters.mcp.http import build_http_app
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    srv = uvicorn.Server(uvicorn.Config(build_http_app(make_ex(), base), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"{base}/mcp"
    srv.should_exit = True
    t.join(5)


def _http_client(url, token):
    import httpx2
    from mcp.client.streamable_http import streamable_http_client
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return Client(streamable_http_client(url, http_client=httpx2.AsyncClient(headers=headers)))


def test_http_bearer_tokens_resolve_per_request(http_server):
    async def go():
        async with _http_client(http_server, "t-ana") as c:
            out = payload(await c.call_tool("approve_experiment", {"target_id": "E-onboarding", "idempotency_key": "h1"}))
            assert out["status"] == "ok" and out["state"]["approved_by"] == "ana"
        async with _http_client(http_server, "t-eli") as c:
            assert payload(await c.call_tool("allowed_actions", {"object_id": "E-onboarding"})) == ["launch_experiment"]
    run(go())


@pytest.mark.parametrize("token", [None, "t-nobody"])
def test_http_rejects_missing_or_unknown_tokens(http_server, token):
    async def go():
        async with _http_client(http_server, token) as c:
            await c.list_tools()
    with pytest.raises(BaseException):
        run(go())


# -- stdio through the real CLI -------------------------------------------------------------------
def test_stdio_cli(tmp_path):
    dom = tmp_path / "d.domain.yaml"
    dom.write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    tokens = tmp_path / "tokens.yaml"
    tokens.write_text(yaml.safe_dump({"t-ana": {"id": "ana", "roles": ["approver"]}}))
    params = StdioServerParameters(command="uv", args=[
        "run", "--quiet", "toprope-server", "--domain", str(dom), "--store", f"sqlite:{tmp_path / 'e.db'}",
        "--identity", f"static:{tokens}"], env={"TOPROPE_TOKEN": "t-ana", "PATH": __import__("os").environ["PATH"]})

    async def go():
        async with Client(params) as c:
            out = payload(await c.call_tool("approve_experiment", {"target_id": "E-onboarding", "idempotency_key": "s1"}))
            assert out["status"] == "ok"
    run(go())


# -- JWT identity ----------------------------------------------------------------------------------
KEY = "test-only-hmac-key-of-at-least-32-bytes!"


def _tok(**claims):
    import jwt
    base = {"sub": "ana", "roles": ["approver"], "exp": int(time.time()) + 600, "aud": "toprope"}
    return jwt.encode({**base, **claims}, KEY, algorithm="HS256")


def test_jwt_identity():
    from toprope.identity.jwt import JWTIdentity
    ids = JWTIdentity(KEY, audience="toprope")
    assert ids.resolve(_tok()).actor == Actor("ana", "person", ("approver",))
    agent = ids.resolve(_tok(sub="bot", kind="agent", act={"sub": "ana", "roles": ["approver"]},
                             grant={"id": "g1", "actions": ["approve_experiment"], "targets": None}))
    assert agent.actor.kind == "agent" and agent.on_behalf_of.id == "ana" and agent.grant.actions == {"approve_experiment"}
    assert ids.resolve(_tok(exp=int(time.time()) - 10)) is None                       # expired
    assert ids.resolve(_tok(aud="other")) is None                                      # wrong audience
    assert ids.resolve(_tok(sub="bot", kind="agent")) is None                          # agent without principal/grant
    assert ids.resolve(_tok(sub="system", kind="system", roles=["system"])) is None   # reserved actor
    assert ids.resolve("not-a-jwt") is None and ids.resolve(None) is None

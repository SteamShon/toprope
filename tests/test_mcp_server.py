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


def make_ex(store=None, domain=None, ids=None):
    ex = Execution(Domain.model_validate(domain or schema_doc_domain()), store or MemoryEventStore(), ids or IDS,
                   clock=lambda: NOW)
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
            assert out["status"] == "denied" and out["code"] == "matrix" and out["reason"] == (
                "Launch requires approval. Fix: launch_experiment applies when the Experiment is approved; move the "
                "Experiment there first, or take an action that `allowed` (CLI) or `allowed_actions` (MCP) lists for it")
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


def typed_domain():
    """The schema example with params of every kind on approve_experiment, to test that MCP
    neither coerces nor drops values that Execution would refuse."""
    raw = schema_doc_domain()
    raw["actions"]["approve_experiment"]["params"].update({
        "score": {"type": "integer", "optional": True}, "urgent": {"type": "boolean", "optional": True},
        "tags": {"type": "string", "many": True, "optional": True}})
    return raw


# (token, action, target, params, schema_rejects): the MCP schema refuses only arguments that are
# not declared params (unknown keys) or required tool arguments; every param value reaches Execution.
SEQUENCE = [("t-eli", "launch_experiment", "E-onboarding", {}), ("t-ana", "approve_experiment", "E-bare", {}),
            ("t-ana", "approve_experiment", "E-onboarding", {"note": 3}),
            ("t-ana", "approve_experiment", "E-onboarding", {"score": "5"}),
            ("t-ana", "approve_experiment", "E-onboarding", {"score": 5.5}),
            ("t-ana", "approve_experiment", "E-onboarding", {"urgent": "true"}),
            ("t-ana", "approve_experiment", "E-onboarding", {"urgent": 1}),
            ("t-ana", "approve_experiment", "E-onboarding", {"tags": '["a"]'}),
            ("t-ana", "approve_experiment", "E-onboarding", {"note": "null"}),
            ("t-ana", "approve_experiment", "E-onboarding", {"note": "ok", "score": 5, "urgent": True, "tags": ["a"]}),
            ("t-eli", "approve_experiment", "E-onboarding", {}),
            ("t-eli", "launch_experiment", "E-onboarding", {}), ("t-eli", "launch_experiment", "E-onboarding", {}),
            ("t-ana", "approve_experiment", "E-ghost", {})]
SCHEMA_REJECTED = [("t-ana", "approve_experiment", "E-bare", {"bogus": 1})]


def test_parity_mcp_equals_execution():
    """The same commands through MCP and directly through Execution: identical outcomes and streams."""
    direct = make_ex(domain=typed_domain())
    want = [direct.submit(t, a, tgt, p, f"k{i}") for i, (t, a, tgt, p) in enumerate(SEQUENCE)]
    via, who = make_ex(domain=typed_domain()), As()

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
    assert got == [json.loads(json.dumps(outcome_json(w))) for w in want]
    assert sum(w.code == "invalid-command" for w in want) == 6, "the sequence must exercise mistyped params"
    for oid in ("E-onboarding", "E-bare"):
        assert via.history(oid) == direct.history(oid)
        assert [a.payload for a in via.attempts(oid)] == [a.payload for a in direct.attempts(oid)]


def test_unknown_arguments_are_refused_by_the_schema_and_by_execution():
    for t, a, tgt, p in SCHEMA_REJECTED:
        assert make_ex(domain=typed_domain()).submit(t, a, tgt, p, "k").code == "invalid-command"
    via, who = make_ex(domain=typed_domain()), As()

    async def go():
        async with Client(build_server(via, who)) as c:
            tool = next(t for t in (await c.list_tools()).tools if t.name == "approve_experiment")
            assert tool.input_schema["additionalProperties"] is False
            assert tool.input_schema["properties"]["score"]["anyOf"][0] == {"type": "integer"}
            assert tool.input_schema["properties"]["tags"]["anyOf"][0] == {"type": "array", "items": {"type": "string"}}
            for t, a, tgt, p in SCHEMA_REJECTED:
                who.token = t
                assert (await c.call_tool(a, {"target_id": tgt, "idempotency_key": "k", **p})).is_error
    run(go())
    assert via.attempts("E-bare") == []


BOT = Actor("bot", "agent", ("approver",))


def test_allowed_actions_for_an_agent_caller():
    ids = StaticIdentity({"t-bot": Caller(BOT, ANA, Grant("g1", frozenset({"approve_experiment"}))),
                          "t-bot-launch": Caller(BOT, ANA, Grant("g2", frozenset({"launch_experiment"})))})
    who = As()

    async def go():
        async with Client(build_server(make_ex(ids=ids), who)) as c:
            who.token = "t-bot"
            assert payload(await c.call_tool("allowed_actions", {"object_id": "E-onboarding"})) == ["approve_experiment"]
            who.token = "t-bot-launch"
            assert payload(await c.call_tool("allowed_actions", {"object_id": "E-onboarding"})) == []
    run(go())


def test_read_tools_require_a_caller():
    who = As()

    async def go():
        async with Client(build_server(make_ex(), who)) as c:
            for token in (None, "t-nobody"):
                who.token = token
                for tool in ("get_object", "history", "attempts", "allowed_actions"):
                    res = await c.call_tool(tool, {"object_id": "E-onboarding"})
                    assert res.is_error and "credentials" in res.content[0].text, (tool, token)
            who.token = "t-ana"
            assert payload(await c.call_tool("get_object", {"object_id": "E-onboarding"}))["status"] == "draft"
    run(go())


def test_descriptions_cover_every_cell_kind_and_actor_conditions():
    from toprope.adapters.mcp import describe_action
    raw = schema_doc_domain()
    m = raw["transitions"]["Experiment"]["matrix"]
    m["draft"]["approve_experiment"] = {"to": "approved"}
    m["approved"]["launch_experiment"] = {"by_role": {"eng": "running", "pm": {"deny": "PMs never launch."}}}
    raw["actions"]["launch_experiment"]["actor"] = [{"role": "eng", "where": "target.planned_days >= 1"}]
    d = Domain.model_validate(raw)
    ap = describe_action(d, "approve_experiment", d.actions["approve_experiment"])
    assert "Allowed when status is draft." in ap
    la = describe_action(d, "launch_experiment", d.actions["launch_experiment"])
    assert "Who: eng (where target.planned_days >= 1)." in la
    assert "Allowed when status is approved (for eng)." in la
    assert "PMs never launch." in la and "Launch requires approval." in la


def test_param_names_reserved_or_not_identifiers():
    from toprope.decl import validate_domain
    raw = schema_doc_domain()
    raw["actions"]["approve_experiment"]["params"].update(
        {"idempotency_key": {"type": "string", "optional": True}, "my-note": {"type": "string", "optional": True}})
    d = Domain.model_validate(raw)
    codes = {(i.code, i.where) for i in validate_domain(d)}
    assert ("reserved-param", "actions.approve_experiment.params.idempotency_key") in codes
    assert ("invalid-param-name", "actions.approve_experiment.params.my-note") in codes
    ex = Execution(d, MemoryEventStore(), IDS, clock=lambda: NOW)
    with pytest.raises(ValueError, match="reserved"):
        build_server(ex, As())


def test_keyword_param_names_work_as_tool_arguments():
    raw = schema_doc_domain()
    raw["actions"]["approve_experiment"]["params"] = {"from": {"type": "string", "optional": True}}
    who = As()
    who.token = "t-ana"

    async def go():
        async with Client(build_server(make_ex(domain=raw), who)) as c:
            out = payload(await c.call_tool("approve_experiment",
                                            {"target_id": "E-onboarding", "idempotency_key": "k", "from": "x"}))
            assert out["status"] == "ok"
    run(go())


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
    assert srv.started, "the HTTP server did not start"
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


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}


@pytest.mark.parametrize("token,status", [(None, 401), ("t-nobody", 401), ("t-ana", 200)])
def test_http_rejects_missing_or_unknown_tokens(http_server, token, status):
    import httpx2
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = httpx2.post(http_server, json=INIT, headers=headers, timeout=10)
    assert r.status_code == status
    if status == 401:
        assert "Bearer" in r.headers.get("www-authenticate", "")


def test_http_advertises_the_configured_issuer():
    from starlette.testclient import TestClient
    from toprope.adapters.mcp.http import build_http_app
    app = build_http_app(make_ex(), "https://toprope.example.com", issuer_url="https://idp.example.com")
    with TestClient(app) as tc:
        meta = tc.get("/.well-known/oauth-protected-resource/mcp").json()
    assert meta["resource"].rstrip("/") == "https://toprope.example.com/mcp"
    assert [u.rstrip("/") for u in meta["authorization_servers"]] == ["https://idp.example.com"]


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


def test_stdio_cli_refuses_an_unresolvable_token(tmp_path):
    import os
    import subprocess
    dom = tmp_path / "d.domain.yaml"
    dom.write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    tokens = tmp_path / "tokens.yaml"
    tokens.write_text(yaml.safe_dump({"t-ana": {"id": "ana", "roles": ["approver"]}}))
    r = subprocess.run(["uv", "run", "--quiet", "toprope-server", "--domain", str(dom), "--identity", f"static:{tokens}"],
                       env={**os.environ, "TOPROPE_TOKEN": "t-wrong"}, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=60)
    assert r.returncode == 1 and "TOPROPE_TOKEN" in r.stderr


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


def test_jwt_configuration_is_never_permissive():
    from toprope.identity.jwt import JWTIdentity
    with pytest.raises(ValueError):
        JWTIdentity("", audience="toprope")
    with pytest.raises(ValueError):
        JWTIdentity(KEY, audience="")
    with pytest.raises(ValueError):
        JWTIdentity(KEY, audience="toprope", algorithms=["none"])
    import jwt
    no_aud = jwt.encode({"sub": "ana", "exp": int(time.time()) + 600}, KEY, algorithm="HS256")
    assert JWTIdentity(KEY, audience="toprope").resolve(no_aud) is None
    ids = JWTIdentity(KEY, audience="toprope", issuer="https://idp.example.com")
    assert ids.resolve(_tok()) is None                                                   # no iss
    assert ids.resolve(_tok(iss="https://idp.example.com")) is not None


@pytest.mark.parametrize("claims", [
    {"kind": "admin"}, {"kind": "robot", "roles": []},                                    # only person/agent
    {"roles": "approver"}, {"roles": [1]}, {"roles": {"approver": True}},
    {"sub": "bot", "kind": "agent", "act": {"sub": "ana", "roles": "approver"}, "grant": {"id": "g", "actions": []}},
    {"sub": "bot", "kind": "agent", "act": {"sub": "ana"}, "grant": {"id": "g", "actions": "approve_experiment"}},
    {"sub": "bot", "kind": "agent", "act": {"sub": "ana"}, "grant": {"id": "g", "targets": "E-1"}},
])
def test_jwt_malformed_claims_are_refused(claims):
    from toprope.identity.jwt import JWTIdentity
    assert JWTIdentity(KEY, audience="toprope").resolve(_tok(**claims)) is None


def test_jwt_grant_exp_zero_is_expired_not_unlimited():
    from toprope.identity.jwt import JWTIdentity
    c = JWTIdentity(KEY, audience="toprope").resolve(_tok(
        sub="bot", kind="agent", act={"sub": "ana", "roles": ["approver"]},
        grant={"id": "g", "actions": ["approve_experiment"], "exp": 0}))
    assert c.grant.expires_at == datetime(1970, 1, 1, tzinfo=timezone.utc)


def test_caller_kind_is_person_or_agent():
    for kind in ("admin", "service", "system"):
        with pytest.raises(ValueError):
            Caller(Actor("x", kind, ("approver",)))


@pytest.mark.parametrize("entry", [{"id": "ana", "roles": "approver"}, {"id": "ana", "kind": "admin"},
                                   {"id": "bot", "kind": "agent", "on_behalf_of": {"id": "ana"},
                                    "grant": {"id": "g", "actions": "approve_experiment"}}])
def test_static_token_file_is_type_checked(tmp_path, entry):
    from toprope.adapters.mcp.cli import open_identity
    f = tmp_path / "tokens.yaml"
    f.write_text(yaml.safe_dump({"t": entry}))
    with pytest.raises(SystemExit):
        open_identity(f"static:{f}")


def test_a_decision_actions_tool_takes_an_optional_rationale_and_others_do_not():
    async def go():
        async with Client(build_server(make_ex(), As())) as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
            approve, launch = tools["approve_experiment"].input_schema, tools["launch_experiment"].input_schema
            assert "rationale" in approve["properties"] and "rationale" not in approve.get("required", [])
            assert "rationale" not in launch["properties"]
    run(go())


# -- ADR-0041 Resolved 5: every event records the permissions it ran under ---------------------
def test_events_record_the_roles_and_the_grant_in_force():
    from toprope.store.codec import event_from_json, event_to_json
    expires = NOW + timedelta(days=1)
    ids = StaticIdentity({"t-bot": Caller(BOT, ANA, Grant("g1", frozenset({"approve_experiment"}),
                                                          frozenset({"E-onboarding"}), expires)),
                          "t-eli": Caller(ELI)})
    store = MemoryEventStore()
    ex = make_ex(store=store, ids=ids)
    assert ex.submit("t-bot", "approve_experiment", "E-onboarding", {}, "k1").status == "ok"
    assert ex.submit("t-eli", "approve_experiment", "E-onboarding", {}, "k2").status == "denied"
    ok = next(e for e in store.read("E-onboarding") if e.kind == "domain" and e.actor["id"] == "bot")
    assert ok.permissions == {"roles": ["approver"], "principal_roles": ["approver"],
                              "grant": {"id": "g1", "actions": ["approve_experiment"],
                                        "targets": ["E-onboarding"], "expires_at": expires.isoformat()}}
    denied = ex.attempts("E-onboarding")[-1]
    assert denied.permissions == {"roles": ["eng"]}
    old = json.loads(event_to_json(ok))
    del old["permissions"]                                   # an event written before ADR-0041
    assert event_from_json(json.dumps(old)).permissions is None


def test_read_source_serves_redacted_text_and_refuses_local_only(tmp_path):
    """Next item 3 (decided 2026-11-06): the kernel's server serves source text, redacted, and
    refuses local-only sources. A read, not an action: nothing goes into the event log."""
    from test_authoring import CONFIG, FAKE_KEY

    from toprope.workspace import Workspace
    (tmp_path / "toprope.workspace.yaml").write_text(yaml.safe_dump(CONFIG))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(f"KEY = '{FAKE_KEY}'\nok\n")
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "s1.jsonl").write_text(json.dumps(
        {"type": "user", "message": {"role": "user", "content": "PMs never approve."}}) + "\n")
    ws = Workspace(tmp_path)
    ex, who = make_ex(), As()

    async def go():
        async with Client(build_server(ex, who, sources=ws)) as c:
            assert "read_source" in {t.name for t in (await c.list_tools()).tools}
            res = await c.call_tool("read_source", {"source_id": "repo"})
            assert res.is_error and "credentials" in res.content[0].text
            who.token = "t-eli"
            out = payload(await c.call_tool("read_source", {"source_id": "repo"}))
            (chunk,) = out["chunks"]
            assert chunk["ref"] == "repo:src/app.py#L1-L2" and FAKE_KEY not in chunk["text"]
            assert "[REDACTED:" in chunk["text"]
            refused = await c.call_tool("read_source", {"source_id": "sessions"})
            assert refused.is_error and "local-only" in refused.content[0].text
        async with Client(build_server(ex, who)) as c:                  # no workspace: no tool
            assert "read_source" not in {t.name for t in (await c.list_tools()).tools}
    before = {s: ex.store.version(s) for s in ex.store.streams()}
    run(go())
    assert {s: ex.store.version(s) for s in ex.store.streams()} == before        # nothing recorded
    assert "repo:src/app.py#L1-L2" in (tmp_path / ws.usage_path.relative_to(tmp_path)).read_text()

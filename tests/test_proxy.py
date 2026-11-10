"""`toprope-proxy`: a declaration's rules in front of an existing MCP server (ADR-0052)."""
import asyncio
import importlib
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

from toprope import kernel
from toprope.adapters.mcp.cli import open_identity
from toprope.decl import load_domain, validate_domain
from toprope.exec import Execution
from toprope.proxy import (
    Binding,
    Upstream,
    UpstreamServices,
    build_proxy,
    check,
    register,
)
from toprope.store import open_store

EX = Path(__file__).resolve().parents[1] / "examples/proxy"
DOMAIN, BINDING, TOKENS = EX / "shop.domain.yaml", EX / "binding.yaml", EX / "tokens.yaml"


@pytest.fixture
def payments(monkeypatch):
    monkeypatch.syspath_prepend(str(EX))
    import payments_server
    yield importlib.reload(payments_server)                    # fresh orders and refunds
    sys.modules.pop("payments_server", None)


@pytest.fixture(autouse=True)
def no_upstream_services():
    yield
    kernel.UPSTREAM_SERVICES.clear()


class Proxy:
    """The proxy in process, in front of the stand-in payments server; `call` as an agent."""

    def __init__(self, payments, tmp_path, binding=BINDING):
        self.b = Binding.load(binding)
        self.up = Upstream(payments.build())
        assert register(self.b, self.up.tools()) == []
        d = load_domain(DOMAIN)
        assert check(d, self.b) == []
        self.ex = Execution(d, open_store("memory"), open_identity(f"static:{TOKENS}"),
                            services=UpstreamServices(self.up))
        self.ex.seed_world()
        self.token = "t-sam"
        self.audit = tmp_path / "audit.jsonl"
        self.server = build_proxy(self.ex, self.b, self.up, lambda: self.token, audit=self.audit)

    def run(self, steps):
        from mcp import Client

        async def go():
            out = []
            async with Client(self.server) as c:
                for step in steps:
                    if step == "list":
                        out.append(sorted(t.name for t in (await c.list_tools()).tools))
                        continue
                    r = await c.call_tool(*step)
                    out.append(("error", r.content[0].text) if r.is_error else ("ok", r.structured_content))
            return out
        try:
            return asyncio.run(go())
        finally:
            self.up.close()


def test_only_bound_tools_are_offered_and_a_read_passes_through_recorded(payments, tmp_path):
    p = Proxy(payments, tmp_path)
    tools, read = p.run(["list", ("get_order", {"order_id": "O-3"})])
    assert tools == ["get_order", "refund_order"]                              # wipe_orders: unbound, hidden
    assert read == ("ok", {"order_id": "O-3", "total": 80.0})
    entry = json.loads(p.audit.read_text().splitlines()[0])
    assert (entry["tool"], entry["caller"], entry["gated"]) == ("get_order", "sam", False)


def test_a_call_the_rules_refuse_never_reaches_the_server(payments, tmp_path):
    p = Proxy(payments, tmp_path)
    [(status, text)] = p.run([("refund_order", {"order_id": "O-8", "amount": 10})])
    assert status == "error" and "Refused by the declaration (within-window)" in text
    assert payments.REFUNDS == [] and p.ex.state("O-8")["status"] == "paid"


def test_an_allowed_call_is_sent_once_and_its_answer_moves_the_object(payments, tmp_path):
    p = Proxy(payments, tmp_path)
    first, again = p.run([("refund_order", {"order_id": "O-3", "amount": 50}),
                          ("refund_order", {"order_id": "O-3", "amount": 50})])
    assert first == again == ("ok", {"refund_id": "R-1", "amount": 50.0})
    assert payments.REFUNDS == [{"order_id": "O-3", "amount": 50.0}]           # sent once
    assert p.ex.state("O-3") == {"id": "O-3", "status": "refunded", "days_since_purchase": 3, "refund_id": "R-1"}
    last = p.ex.history("O-3")[-1]
    assert last.actor["id"] == "external:kernel" and last.causation.startswith("mcp:refund_order:O-3")   # the reply


def test_a_failure_upstream_is_reported_and_moves_nothing(payments, tmp_path):
    p = Proxy(payments, tmp_path)
    [(status, text)] = p.run([("refund_order", {"order_id": "O-3", "amount": 500})])
    assert status == "error" and "failed upstream" in text and "the provider refused" in text
    assert p.ex.state("O-3")["status"] == "paid" and payments.REFUNDS == []


def test_a_caller_without_the_role_or_without_a_token_is_refused(payments, tmp_path):
    p = Proxy(payments, tmp_path)
    p.token = "t-guest"
    [(status, text)] = p.run([("refund_order", {"order_id": "O-3", "amount": 5})])
    assert status == "error" and "Refused by the declaration" in text and payments.REFUNDS == []
    p = Proxy(payments, tmp_path)
    p.token = "nobody"
    [(status, text)] = p.run([("get_order", {"order_id": "O-3"})])
    assert status == "error" and "Unknown or missing credentials" in text


def test_the_proxy_will_not_start_when_binding_server_and_declaration_disagree(payments, tmp_path):
    b = tmp_path / "b.yaml"
    b.write_text(yaml.safe_dump({"upstream": {"command": ["x"]}, "tools": {
        "refund_order": {"action": "record_refund", "target": "order_id"}, "send_money": {"read": True}}}))
    up = Upstream(payments.build())
    try:
        problems = register(Binding.load(b), up.tools())
    finally:
        up.close()
    assert any("send_money, which the upstream server does not offer" in p for p in problems)
    problems = check(load_domain(DOMAIN), Binding.load(b))
    assert any("action record_refund does not call mcp:refund_order" in p for p in problems)


def test_once_registered_an_upstream_call_is_checked_like_a_kernel_call(payments, tmp_path):
    d = load_domain(DOMAIN)
    assert [i.code for i in validate_domain(d)] == ["upstream-service"]       # before: a warning only
    up = Upstream(payments.build())
    try:
        register(Binding.load(BINDING), up.tools())
    finally:
        up.close()
    raw = yaml.safe_load(DOMAIN.read_text())
    raw["actions"]["refund"]["effects"][0]["with"]["currency"] = "params.amount"
    from toprope.decl import Domain
    issues = validate_domain(Domain.model_validate(raw))
    assert [(i.code, i.where) for i in issues if i.severity == "error"] == [
        ("unknown-input", "actions.refund.effects[0].with.currency")]


@pytest.mark.parametrize("text,msg", [
    ("upstream: {command: [x], url: y}\ntools: {}\n", "exactly one of `command` or `url`"),
    ("upstream: {url: y}\ntools: {t: {action: a}}\n", "names exactly one of `target` or `new_id`"),
    ("upstream: {url: y}\ntools: {t: {read: true, action: a}}\n", "either `read: true` or an `action`"),
    ("upstream: {url: y}\ntools: {t: {acton: a}}\n", "unknown key\\(s\\) acton"),
])
def test_a_binding_of_the_wrong_shape_is_refused_with_a_fix(tmp_path, text, msg):
    f = tmp_path / "b.yaml"
    f.write_text(text)
    with pytest.raises(SystemExit, match=f"{msg}.*Fix: "):
        Binding.load(f)


def test_the_command_over_stdio_in_front_of_a_real_server_process(tmp_path):
    from mcp import Client, StdioServerParameters
    binding = tmp_path / "binding.yaml"
    b = yaml.safe_load(BINDING.read_text())
    b["upstream"]["command"] = [sys.executable, str(EX / "payments_server.py")]
    binding.write_text(yaml.safe_dump(b))
    params = StdioServerParameters(command="uv", args=[
        "run", "--quiet", "toprope-proxy", "--domain", str(DOMAIN), "--binding", str(binding),
        "--identity", f"static:{TOKENS}", "--store", f"sqlite:{tmp_path / 'shop.db'}",
        "--audit", str(tmp_path / "audit.jsonl")], env={"TOPROPE_TOKEN": "t-sam", "PATH": os.environ["PATH"]})

    async def go():
        async with Client(params) as c:
            names = sorted(t.name for t in (await c.list_tools()).tools)
            refused = await c.call_tool("refund_order", {"order_id": "O-8", "amount": 10})
            done = await c.call_tool("refund_order", {"order_id": "O-3", "amount": 20})
            return names, refused, done
    names, refused, done = asyncio.run(go())
    assert names == ["get_order", "refund_order"]
    assert refused.is_error and "within-window" in refused.content[0].text
    assert not done.is_error and done.structured_content == {"refund_id": "R-1", "amount": 20.0}
    gated = [json.loads(x) for x in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [(g["tool"], g["status"]) for g in gated] == [("refund_order", "denied"), ("refund_order", "ok")]

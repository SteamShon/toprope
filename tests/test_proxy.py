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

    def __init__(self, payments, tmp_path, binding=BINDING, store="memory", seed=True, server=None):
        self.b = Binding.load(binding)
        self.up = Upstream(server or payments.build())
        d = load_domain(DOMAIN)
        assert register(self.b, self.up.tools(), d) == []
        assert check(d, self.b) == []
        self.ex = Execution(d, open_store(store), open_identity(f"static:{TOKENS}"),
                            services=UpstreamServices(self.up))
        if seed:
            self.ex.seed_world()
        self.token = "t-sam"
        self.audit = tmp_path / "audit.jsonl"
        self.server = build_proxy(self.ex, self.b, self.up, lambda: self.token, audit=self.audit)

    def run(self, steps, together=False):
        from mcp import Client

        async def go():
            out = []
            async with Client(self.server) as c:
                if together:                                   # all at once, as parallel agents would
                    rs = await asyncio.gather(*[c.call_tool(*s) for s in steps])
                    return [("error", r.content[0].text) if r.is_error else ("ok", r.structured_content) for r in rs]
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
    assert read == ("ok", {"order_id": "O-3", "total": 80.0, "status": "paid", "days_since_purchase": 3})
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
    assert first == ("ok", {"refund_id": "R-1", "amount": 50.0})
    assert again == ("ok", {"refund_id": "R-1"})                                   # as recorded: not sent again
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
        problems = register(Binding.load(b), up.tools(), load_domain(DOMAIN))
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
        register(Binding.load(BINDING), up.tools(), load_domain(DOMAIN))
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


# Review of #230 (2026-11-10): each case below let a write through, reported a done refund as
# failed, refunded twice, lost the real error, dropped an argument silently, or would not start.

def _binding(tmp_path, tools, upstream=None):
    f = tmp_path / "b.yaml"
    f.write_text(yaml.safe_dump({"upstream": upstream or {"command": ["x"]}, "tools": tools}))
    return f


REFUND = {"action": "refund", "target": "order_id", "result": {"refund_id": "string"}}


def test_a_tool_is_read_only_only_when_the_server_says_so(payments, tmp_path):
    up = Upstream(payments.build())
    try:
        problems = register(Binding.load(_binding(tmp_path, {"wipe_orders": {"read": True}})), up.tools(),
                            load_domain(DOMAIN))
    finally:
        up.close()
    assert problems and "marks wipe_orders read-only, but the server does not (readOnlyHint)" in problems[0]


def test_a_refund_done_before_a_restart_is_answered_as_done(payments, tmp_path):
    store = f"sqlite:{tmp_path / 'shop.db'}"
    assert Proxy(payments, tmp_path, store=store).run([("refund_order", {"order_id": "O-3", "amount": 50})]) == [
        ("ok", {"refund_id": "R-1", "amount": 50.0})]
    kernel.UPSTREAM_SERVICES.clear()
    again = Proxy(payments, tmp_path, store=store, seed=False).run([("refund_order", {"order_id": "O-3", "amount": 50})])
    assert again == [("ok", {"refund_id": "R-1"})] and len(payments.REFUNDS) == 1      # as recorded, not sent


def test_two_calls_at_once_do_not_both_pass_the_gate(payments, tmp_path):
    p = Proxy(payments, tmp_path)
    out = p.run([("refund_order", {"order_id": "O-3", "amount": 7}), ("refund_order", {"order_id": "O-3", "amount": 9})],
                together=True)
    assert sorted(s for s, _ in out) == ["error", "ok"] and len(payments.REFUNDS) == 1
    assert any("already refunded" in text for s, text in out if s == "error")
    assert p.ex.dispatch() == []                                                   # nothing left to send later


def test_no_answer_from_the_server_says_it_may_have_acted(payments, tmp_path):
    def silent(**kw):
        raise TimeoutError("no answer in 30 s")
    p = Proxy(payments, tmp_path)
    real = p.up.call
    p.up.call = lambda tool, args: silent() if tool == "refund_order" else real(tool, args)   # the refund call hangs
    [(status, text)] = p.run([("refund_order", {"order_id": "O-3", "amount": 5})])
    assert status == "error" and "did not answer (TimeoutError: no answer in 30 s)" in text
    assert "may or may not have acted" in text and p.ex.state("O-3")["status"] == "paid"


def test_a_failure_says_how_to_try_again_and_a_new_key_does(payments, tmp_path):
    p = Proxy(payments, tmp_path)
    first, same, fresh = p.run([("refund_order", {"order_id": "O-3", "amount": 500}),
                                ("refund_order", {"order_id": "O-3", "amount": 500}),
                                ("refund_order", {"order_id": "O-3", "amount": 50, "idempotency_key": "k2"})])
    assert first[0] == "error" and "Fix: to try again, call with a new `idempotency_key`" in first[1]
    assert same[0] == "error" and fresh == ("ok", {"refund_id": "R-1", "amount": 50.0})


def _server_with(note_required: bool):
    from mcp.server.mcpserver import MCPServer
    server = MCPServer(name="payments")
    if note_required:
        @server.tool()
        def refund_order(order_id: str, amount: float, currency: str) -> dict:
            return {"refund_id": "R-x"}
    else:
        @server.tool()
        def refund_order(order_id: str, amount: float, currency: str = "USD", note: str | None = None) -> dict:
            return {"refund_id": f"R-{currency}", "amount": amount}
    return server


def test_an_argument_the_gate_does_not_check_is_not_offered_or_stops_the_start(payments, tmp_path):
    up = Upstream(_server_with(note_required=True))
    try:
        problems = register(Binding.load(BINDING), up.tools(), load_domain(DOMAIN))
    finally:
        up.close()
    assert any("refund_order.currency is required by the server, but the gate never checks it" in x for x in problems)
    kernel.UPSTREAM_SERVICES.clear()
    only_refund = _binding(tmp_path, {"refund_order": REFUND})
    p = Proxy(payments, tmp_path, binding=only_refund, server=_server_with(note_required=False))
    sent, smuggled = p.run([("refund_order", {"order_id": "O-3", "amount": 5}),
                            ("refund_order", {"order_id": "O-3", "amount": 5, "currency": "JPY"})])
    assert sent == ("ok", {"refund_id": "R-USD", "amount": 5.0})                  # the server's default
    assert smuggled[0] == "error" and "currency" in smuggled[1]                    # not offered, so refused
    assert p.b.tools["refund_order"].hidden == {"currency", "note"}


def test_a_call_to_an_unbound_upstream_tool_stops_the_start(payments, tmp_path):
    raw = yaml.safe_load(DOMAIN.read_text())
    raw["actions"]["refund"]["effects"].append({"call": "mcp:wipe_orders", "reply": "record_refund"})
    from toprope.decl import Domain
    problems = check(Domain.model_validate(raw), Binding.load(BINDING))
    assert any("action refund calls mcp:wipe_orders, which the binding does not bind" in x for x in problems)


def test_an_upstream_that_does_not_start_fails_fast_with_a_fix(tmp_path):
    import time
    t0 = time.monotonic()
    with pytest.raises(SystemExit, match="the upstream MCP server did not start: .*Fix: check the binding"):
        Upstream.open({"command": [str(tmp_path / "no-such-server")]})
    assert time.monotonic() - t0 < 30


# Review of umbrella/usability-import (2026-11-10): the proxy enforced unconfirmed rules, refused
# objects only the server knew, and two proxies on one store refunded the same order twice.

def test_a_declaration_no_person_confirmed_is_not_enforced(payments, tmp_path):
    raw = yaml.safe_load(DOMAIN.read_text())
    raw["actions"]["refund"]["status"] = "proposed"
    from toprope.decl import Domain
    problems = check(Domain.model_validate(raw), Binding.load(BINDING))
    assert any("1 element(s) no person has confirmed (actions.refund)" in x and "Fix: a person confirms" in x
               for x in problems)


def test_an_object_only_the_server_knows_is_read_first_and_then_gated(payments, tmp_path):
    p = Proxy(payments, tmp_path)
    [(status, answer_)] = p.run([("refund_order", {"order_id": "O-21", "amount": 10})])
    assert (status, answer_) == ("ok", {"refund_id": "R-1", "amount": 10.0})
    assert p.ex.state("O-21")["status"] == "refunded" and p.ex.history("O-21")[0].payload["fixture"] is True
    loaded = [json.loads(x) for x in p.audit.read_text().splitlines() if "loaded" in x]
    assert loaded == [{**loaded[0], "tool": "get_order", "caller": "sam", "loaded": "O-21", "for": "refund_order"}]


def test_an_object_the_server_describes_badly_is_refused_with_a_fix(payments, tmp_path):
    payments.ORDERS["O-50"] = {"total": 5.0, "status": "lost"}
    p = Proxy(payments, tmp_path)
    [(status, text)] = p.run([("refund_order", {"order_id": "O-50", "amount": 1})])
    assert status == "error" and "no days_since_purchase" in text and "status='lost' is not a valid value (one of ['paid', 'refunded'])" in text
    assert "Fix: make get_order return" in text and payments.REFUNDS == []


def test_two_proxies_on_one_store_take_turns_at_the_gate(payments, tmp_path):
    import threading
    import time

    from toprope.proxy import StoreLock
    store = f"sqlite:{tmp_path / 'shop.db'}"
    slow = payments.build()
    proxies = []
    for _ in range(2):
        kernel.UPSTREAM_SERVICES.clear()
        p = Proxy(payments, tmp_path, store=store, server=slow)
        p.server = build_proxy(p.ex, p.b, p.up, lambda: "t-sam", lock=StoreLock(store))
        real = p.up.call

        def call(tool, args, real=real):
            if tool == "refund_order":
                time.sleep(0.3)                                # the call is in flight a while
            return real(tool, args)
        p.up.call = call
        proxies.append(p)
    out = [None, None]
    threads = [threading.Thread(target=lambda i=i: out.__setitem__(
        i, proxies[i].run([("refund_order", {"order_id": "O-3", "amount": 5 + i})]))) for i in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(payments.REFUNDS) == 1                          # one refund, not two
    assert sorted(o[0][0] for o in out) == ["error", "ok"]


@pytest.mark.parametrize("store", ["memory", "postgres:host=x"])
def test_the_proxy_refuses_a_store_it_cannot_share(store):
    from toprope.proxy import StoreLock
    with pytest.raises(SystemExit, match="cannot share its gate over the store .*Fix: use `--store sqlite:FILE`"):
        StoreLock(store)


# Review of #235 (2026-11-10): a copy read once was never read again, a symlinked store got its
# own lock, a memory store slipped through, and values were checked for enums but not types.

def test_the_gate_decides_on_what_the_server_says_now(payments, tmp_path):
    p = Proxy(payments, tmp_path)
    [(s1, _)] = p.run([("refund_order", {"order_id": "O-21", "amount": 999})])          # the server refuses
    assert s1 == "error" and p.ex.state("O-21")["days_since_purchase"] == 1
    payments.ORDERS["O-21"]["days_since_purchase"] = 30                           # a month later
    kernel.UPSTREAM_SERVICES.clear()
    p2 = Proxy(payments, tmp_path, seed=False)
    p2.ex = p.ex
    p2.server = build_proxy(p.ex, p2.b, p2.up, lambda: "t-sam")
    [(s2, text)] = p2.run([("refund_order", {"order_id": "O-21", "amount": 10})])
    assert s2 == "error" and "within-window" in text and payments.REFUNDS == []
    ev = p.ex.history("O-21")[-1]
    assert ev.type == "OrderReadFromServer" and ev.payload["changes"] == {"days_since_purchase": 30}


@pytest.mark.parametrize("bad", [True, "1", None, [1]])
def test_a_value_of_the_wrong_type_is_refused_before_anything_is_recorded(payments, tmp_path, bad):
    payments.ORDERS["O-60"] = {"total": 5.0, "status": "paid", "days_since_purchase": bad}
    p = Proxy(payments, tmp_path)
    [(status, text)] = p.run([("refund_order", {"order_id": "O-60", "amount": 1})])
    assert status == "error" and "days_since_purchase" in text and "Fix: make get_order return" in text
    assert p.ex.lookup("O-60") is None and payments.REFUNDS == []


def test_a_read_that_fails_says_so(payments, tmp_path):
    p = Proxy(payments, tmp_path)
    [(status, text)] = p.run([("refund_order", {"order_id": "O-404", "amount": 1})])
    assert status == "error" and "get_order could not read O-404" in text and "Fix: check that O-404 exists" in text


@pytest.mark.parametrize("store", ["sqlite::memory:", "sqlite:", "sqlite:file:x.db?mode=memory", "jsonl:"])
def test_a_store_that_only_looks_shareable_is_refused(store):
    from toprope.proxy import StoreLock
    with pytest.raises(SystemExit, match="cannot share its gate"):
        StoreLock(store)


def test_a_symlinked_store_shares_its_targets_lock(tmp_path):
    from toprope.proxy import StoreLock
    (tmp_path / "a.db").touch()
    (tmp_path / "link.db").symlink_to(tmp_path / "a.db")
    assert StoreLock(f"sqlite:{tmp_path / 'a.db'}").path == StoreLock(f"sqlite:{tmp_path / 'link.db'}").path


def test_a_load_tool_must_take_the_target_and_a_creating_tool_loads_nothing(payments, tmp_path):
    up = Upstream(payments.build())
    try:
        b = Binding.load(_binding(tmp_path, {"refund_order": {**REFUND, "target": "order_id", "load": "wipe_orders"},
                                             "wipe_orders": {"read": True}}))
        problems = register(b, up.tools(), load_domain(DOMAIN))
    finally:
        up.close()
    assert any("loads with wipe_orders, which takes no `order_id` argument" in x for x in problems)

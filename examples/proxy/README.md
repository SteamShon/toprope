# Example: rules in front of an existing MCP server

Link: ③ works as built (an example for ADR-0052). A team's agent already calls a payments MCP
server (`payments_server.py`, a stand-in). That server refunds whatever it is asked. The refund
rules are in `shop.domain.yaml`:
- only `support` may refund;
- only within 7 days of purchase;
- an order is refunded once.

`toprope-proxy` puts those rules in front of the server. The agent connects to the proxy instead
of the server, and calls the same tools by the same names.

```bash
TOPROPE_TOKEN=t-sam uv run toprope-proxy --domain examples/proxy/shop.domain.yaml \
    --binding examples/proxy/binding.yaml --identity static:examples/proxy/tokens.yaml \
    --store sqlite:/tmp/shop.db --audit /tmp/audit.jsonl
```

`binding.yaml` says which tool is which action. `refund_order` is the declared action `refund`,
and `order_id` names the order it acts on. `get_order` is read-only. `wipe_orders` is not in the
binding, so the agent is never offered it.

What the agent sees:

| Call | What happens |
|---|---|
| `get_order(O-3)` | passes through; written to the audit log, not checked |
| `refund_order(O-8, 10)` | refused: O-8 was bought 8 days ago (`within-window`); the payments server is never called |
| `refund_order(O-3, 500)` | allowed, and sent; the server refuses (more than the total); O-3 stays `paid` |
| `refund_order(O-3, 50)` | allowed, and sent once; the answer (`R-1`) comes back through `record_refund`, and O-3 is `refunded` |
| the same call again | not sent again: the same caller, tool and arguments are one call (or pass `idempotency_key`) |
| two refunds of O-3 at once, even from two proxies on one store | one at a time (a lock beside the store): the second sees O-3 `refunded` and is refused |
| `refund_order(O-21, 10)`, an order only the server knows | read first with `get_order` (the binding's `load:`), recorded, then gated like any other |
| the server does not answer | reported as such: it may or may not have acted, so read the order before calling again with a new `idempotency_key` |

How it works:
- The action `refund` declares the call `call: mcp:refund_order` (ADR-0028). The kernel decides
  first. Only an allowed call reaches the server, at most once by its effect id. The reply action
  records the answer.
- The proxy will not start when the binding, the server's tools and the declaration disagree. For
  example: a bound tool the server lacks, an action without the call, or an input the tool does
  not take.
- A call that goes straight to the payments server, past the proxy, is not governed. Take that
  access away from the agent.
- `read: true` is accepted only for a tool the server itself marks read-only (`readOnlyHint`).
- The proxy enforces only what a person confirmed: it will not start while the declaration has a
  `proposed` element (ADR-0041).
- `--store` is a SQLite file or a JSONL folder, never memory: the gate's record must outlive the
  process, and every proxy on the store takes turns through a lock file beside it.
- Every argument the agent may send is either checked by the gate and passed on by the effect's
  `with`, or not offered. An optional argument outside both is left to the server's default. A
  required one stops the start.
- An action only a person may take is refused for an agent, naming who may. Toprope has no
  waiting approval for a domain action yet (ADR-0052, decision 6).

`tests/test_proxy.py` runs all of this in process. It also runs the real command over stdio in
front of the server as a separate process.

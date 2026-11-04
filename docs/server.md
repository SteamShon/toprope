# toprope-server

Link: ③ ④. The first deployment shape (ADR-0017): a declaration served over MCP, with every
action going through Execution (`docs/semantics.md`).

```bash
uv sync
# stdio, one caller per process (what Claude Code launches)
TOPROPE_TOKEN=t-ana uv run toprope-server --domain my.domain.yaml \
  --store sqlite:events.db --identity static:tokens.yaml

# streamable HTTP, a bearer token per request
TOPROPE_JWT_KEY=... TOPROPE_JWT_AUDIENCE=toprope uv run toprope-server --domain my.domain.yaml \
  --store postgres:"host=127.0.0.1 dbname=toprope" --identity jwt --transport http --port 8765
```

Connect Claude Code over stdio:
```bash
claude mcp add my-domain --env TOPROPE_TOKEN=t-ana -- \
  uv run --directory /path/to/toprope toprope-server --domain my.domain.yaml \
  --store sqlite:events.db --identity static:tokens.yaml
```

`tokens.yaml` (static identity, for local use and tests):
```yaml
t-ana: {id: ana, roles: [approver]}
t-bot: {id: bot, kind: agent, roles: [approver],
        on_behalf_of: {id: ana, roles: [approver]},
        grant: {id: g1, actions: [approve_experiment]}}
```

JWT claims: `sub`, `kind` (`person`|`agent`), `roles`, and for agents `act` (the principal:
`sub`, `roles`) and `grant` (`id`, `actions`, `targets`, `exp`). `exp`, `aud` and `iss` are
verified. Credentials never resolve to the reserved actors `system`, `external:*` or
`handoff:*`.

## Tools
- **One tool per action**, named after it. Parameters and types come from the declaration.
  The description is built only from the declaration's words: who, when it is allowed, what
  stops it. Every call needs an `idempotency_key`; reuse the same key when retrying.
  `thread_id` and `run_id` are optional and recorded on the event.
- `get_object`, `history`, `attempts`, `allowed_actions` (for the caller), and
  `describe_domain` (purpose, glossary, objects, actions).

A denial is a normal result, `{"status": "denied", "code": ..., "reason": ...}`, with the
reason in domain terms. A param of the wrong type is refused by the tool's schema before it
reaches Execution, which would refuse it too, as `invalid-command`.

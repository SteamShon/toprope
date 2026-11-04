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
`sub`, `roles`) and `grant` (`id`, `actions`, `targets`, `exp`). Lists must be lists of
strings; a malformed claim refuses the token. The server always verifies the signature
(`TOPROPE_JWT_KEY`, algorithm `TOPROPE_JWT_ALG`, never `none`), `exp`, and `aud`
(`TOPROPE_JWT_AUDIENCE` is required). It verifies `iss` when `TOPROPE_JWT_ISSUER` is set, and
then advertises that issuer as the authorization server. Credentials never resolve to the
reserved actors `system`, `external:*` or `handoff:*`, and a caller is a `person` or an
`agent`.

Over stdio, the server refuses to start if `TOPROPE_TOKEN` does not resolve. Over HTTP, a
request without a valid bearer token gets 401. Behind a proxy, pass `--public-url` so the
advertised resource URL is the one clients use.

## Tools
- **One tool per action**, named after it. Parameters and types come from the declaration.
  The description is built only from the declaration's words: who, when it is allowed, what
  stops it. Every call needs an `idempotency_key`; reuse the same key when retrying.
  `thread_id` and `run_id` are optional and recorded on the event.
- `get_object`, `history`, `attempts`, `allowed_actions` (for the caller; an agent's
  principal and grant apply), and `describe_domain` (purpose, glossary, objects, actions).
  All but `describe_domain` need a resolved caller.
- `world_map` and `how_to_reach` (see [`world-map.md`](world-map.md)). Pass
  `--harness-report` to show the harness status of each edge.

A denial is a normal result, `{"status": "denied", "code": ..., "reason": ...}`, with the
reason in domain terms. The tool schema advertises each param's type, but values pass to
Execution unchanged (no coercion: `"5"` is not an integer), so a call through MCP and the same
call made directly get the same outcome; a mistyped value is `invalid-command`. An argument
that is not a declared param is refused by the tool schema. `target_id`, `new_id`,
`idempotency_key`, `thread_id` and `run_id` are reserved and cannot be declared as params
(`reserved-param`).

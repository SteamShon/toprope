# Kernel commands

_Generated from the commands' argument parsers by `python -m toprope.kernel.reference`. Do not edit: change the parser, then regenerate._

Link: none (an operating guide). These are the kernel's own commands (ADR-0027): the same for every domain. What a domain's people and agents do is in that domain's generated guide (`domains/<domain>/guide.md`). Run each as `uv run <command>` from the repository root.

## `toprope-run`

`toprope-run`: a command line generated from a declaration (ADR-0036).

Its subcommands are the domain's actions, one per action, plus `get`, `history`, `allowed`, `whoami` and `guide`; each domain's guide lists them with who may take each.

| Argument | What |
|---|---|
| `--domain` `DOMAIN` | one declaration (or --composition with --member) |
| `--composition` `COMPOSITION` | a *.composition.yaml: every member wired in this process |
| `--member` `MEMBER` | with --composition: the member whose actions these are |
| `--store` `STORE` | with --domain: the event store (memory, the default; sqlite:FILE, postgres:DSN, jsonl:DIR); with --composition, memory keeps nothing |
| `--store-dir` `STORE_DIR` | with --composition: one SQLite store per member, <dir>/<member>.db (default: each member's event log, <its directory>/events, kept in git) |
| `--identity` `IDENTITY` | git[:FILE] (your git email, looked up in FILE, default toprope.identity.yaml; the default when that file is here), github[:FILE] (the approver of a GitHub run, ADR-0039), static:FILE or jwt |
| `--token` `TOKEN` | your credential (default: TOPROPE_TOKEN) |
| `--kernel-root` `KERNEL_ROOT` | run declared kernel-service effects on files under this directory |
| `--workspace` `WORKSPACE` | authoring workspace, for the source services |
| `--env` `ENV` | local deploy environment, for the preview and deploy services |
| `--seed` | load the declaration's example fixtures first |
| `--key` `KEY` | idempotency key (default: a new one); reuse it to retry safely |

## `toprope-server`

`toprope-server`: serve a declaration over MCP (stdio or streamable HTTP).

| Argument | What |
|---|---|
| `--domain` `DOMAIN` | one declaration (or --composition with --member) |
| `--composition` `COMPOSITION` | a *.composition.yaml (ADR-0026): every member runs in this process, wired; --member is the one served |
| `--member` `MEMBER` | with --composition: the member domain to serve |
| `--store-dir` `STORE_DIR` | with --composition: one SQLite store per member, <dir>/<member>.db (default: each member's event log, <its directory>/events) |
| `--kernel-root` `KERNEL_ROOT` | run declared kernel-service effects (ADR-0028) on files under this directory; without it, kernel calls stay pending |
| `--workspace` `WORKSPACE` | authoring workspace, for the read_source and fetch_source services |
| `--env` `ENV` | local deploy environment, for the preview and deploy services |
| `--store` `STORE` | with --domain: memory (default), sqlite:FILE, postgres:DSN or jsonl:DIR; with --composition, memory keeps nothing |
| `--identity` `IDENTITY` | how callers are resolved: static:FILE (token -> caller) or jwt (required) |
| `--transport` `{stdio,http}` | stdio for one local caller (TOPROPE_TOKEN), http for many (streamable HTTP) (default `stdio`) |
| `--host` `HOST` | with --transport http: the address to listen on (default `127.0.0.1`) |
| `--port` `PORT` | with --transport http: the port (default `8765`) |
| `--public-url` `PUBLIC_URL` | URL clients use to reach this server (default http://HOST:PORT) |
| `--no-seed` | do not load the declaration's example fixtures (never loaded into a composition member's own event log) |
| `--harness-report` `HARNESS_REPORT` | harness report JSON (toprope-harness --json) shown in the world map |

## `toprope-harness`

`toprope-harness`: run the generated harness on a declaration.

| Argument | What |
|---|---|
| `--domain` `DOMAIN` | one declaration (or use --composition) |
| `--composition` `COMPOSITION` | a *.composition.yaml: check members and wiring (ADR-0026), then run the harness on every member |
| `--levels` `LEVELS` | comma-separated: model, execution, mcp (default `model,execution,mcp`) |
| `--examples` `EXAMPLES` | exploration examples (0 disables) (default `200`) |
| `--depth` `DEPTH` | exploration depth (default `5`) |
| `--json` `JSON` | write the full report as JSON to this path |
| `--regen-check` | with --composition: the regeneration check (ADR-0028): serve from declarations, run, regenerate, compare, and run every kernel call end to end |
| `--receiver` `FILE[@MAJOR]` | a receiving domain's declaration, with its published interface major (default 1): checks this domain's handoffs against it (ADR-0024) (default `[]`) |

## `toprope-worldmap`

`toprope-worldmap`: compile a declaration's world map (ADR-0020).

| Argument | What |
|---|---|
| `--domain` `DOMAIN` | one declaration (or use --composition) |
| `--composition` `COMPOSITION` | a *.composition.yaml: write the composed map (ADR-0026) |
| `--out` `OUT` | (default `world-map.json`) |
| `--harness` | run the harness and include its results |
| `--harness-report` `HARNESS_REPORT` | use an existing harness report JSON instead (with --composition: the member → report map that `toprope-harness --composition --json` writes) |
| `--mermaid` `MERMAID` | also write structure.mmd, <Object>.states.mmd and, when the harness found any, minimal-flows.md here |
| `--guide` `GUIDE` | also write the domain guide (Markdown) to this path |

## `toprope-commits`

`toprope-commits`: read a domain's commit store and a deploy environment (ADR-0029, ADR-0032).

| Argument | What |
|---|---|
| `--commits` `COMMITS` | the commit store (default `.toprope/commits`) |

### `toprope-commits branches`

Every branch and the commit it points to.

| Argument | What |
|---|---|
| `DOMAIN` | the domain's name, as its declaration's `domain:` says |

### `toprope-commits log`

An element's history (ADR-0032).

| Argument | What |
|---|---|
| `DOMAIN` | the domain's name, as its declaration's `domain:` says |
| `ELEMENT` | an element key, e.g. action:launch_experiment |
| `--at` `AT` | read from this commit (default: main, else the work head) |

### `toprope-commits diff`

What changed directly between two commits.

| Argument | What |
|---|---|
| `DOMAIN` | the domain's name, as its declaration's `domain:` says |
| `[FROM] TO` | two commits, or one: what it has since nothing |

### `toprope-commits checks`

The newest record of each check on a commit.

| Argument | What |
|---|---|
| `DOMAIN` | the domain's name, as its declaration's `domain:` says |
| `COMMIT` | a commit id, e.g. 4-b0c8834e25d9bbc7 |

### `toprope-commits evidence`

The evidence a commit cites, with its strength (ADR-0041).

| Argument | What |
|---|---|
| `DOMAIN` | the domain's name, as its declaration's `domain:` says |
| `COMMIT` | a commit id, e.g. 4-b0c8834e25d9bbc7 |

### `toprope-commits deployed`

What a deploy environment runs.

| Argument | What |
|---|---|
| `--env` `ENV` | the environment directory, e.g. .toprope/env (required) |

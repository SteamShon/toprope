# M0a spec: thin slice

Link: none (enabler for ① ②). Status: **frozen at merge of this spec** (ADR-0019). Changes
after that go through a PR that edits this file and states why.

## Goal
Build the hand-built kernel that M1 needs, and nothing more (roadmap M0a). At the end, a toy
domain must:
- compile into MCP tools served by `toprope-server`
- run through Execution and an event store that follow `docs/semantics.md`
- be verified by a generated harness at the model, Execution and MCP levels
- be changeable through an incremental change check with an impact report.

## Constraints
- Python ≥ 3.12, `uv`. The package lives in `src/toprope/`, and tests in `tests/`.
- `toprope-core` has no runtime, web-framework or LLM imports. MCP lives in an adapter.
- Dependencies: `pyyaml`, `pydantic` (declaration models), `hypothesis` (exploration),
  `mcp>=2.3,<3` (adapter only), `pytest`. Anything else needs a line in the PR saying why.
- The `check` language is the one in `docs/domain-schema.md` + ADR-0010. **No `eval`.**
- Every port is an abstract interface. M0a ships in-memory/SQLite adapters, and PostgreSQL
  where noted.

## Package layout
```
src/toprope/
  decl/        declaration models, loader, structural validation, domain interface + hashes
  expr/        check-language parser, evaluator, dependency extraction (paths read)
  semantics/   command, outcome, model interpreter (the oracle), projection
  store/       EventStore port; memory + SQLite adapters (PostgreSQL later in M0a)
  exec/        Execution: interpreter + store + idempotency + optimistic concurrency
  identity/    Identity port; static-token adapter for tests (OIDC later)
  harness/     small world, cell tests, invariant checks, exploration, flows, parity, coverage
  change/      diff, impact analysis, checks, preview, result cache
  worldmap/    world-map.json (structure + behavior layers)
  authoring/   authoring MCP tools: draft, interview, answer, confirm
  sources/     source readers with redaction and local-only
  adapters/mcp toprope-server: MCP tools generated from the declaration
```

## Sub-PRs (into `umbrella/m0a`, in order)
| # | Branch | Delivers | Depends on |
|---|---|---|---|
| — | (done) | roadmap item 1, the spike: done in #11 ([`docs/experiments/M0-spike-report.md`](../experiments/M0-spike-report.md)) | — |
| 1 | `docs/m0a-spec` | this spec; `docs/semantics.md` frozen | — |
| 2 | `feat/m0a-decl-expr` | package skeleton; declaration models (objects, links, actions, matrix, invariants, world fixtures, scenarios, with `source`/`status` on every element) + loader + structural validation; versioned domain interface with per-element hashes; check language with dependency extraction | 1 |
| 3 | `feat/m0a-interpreter` | model interpreter per semantics §2–§6, event schemas, projection, memory event store, idempotency, concurrency | 2 |
| 4 | `feat/m0a-identity-exec` | Identity port, Execution, SQLite and **PostgreSQL** event stores, actor rules incl. relations, grants, `requires: human` | 3 |
| 5 | `feat/m0a-mcp-server` | `toprope-server` MCP adapter generated from the declaration, query/world-map tools | 4 |
| 6 | `feat/m0a-harness` | small world, cell tests, invariant checks, gate-tier exploration, flows, replay parity, concurrency tests, parity + coverage | 5 |
| 7 | `feat/m0a-worldmap` | `world-map.json` (declaration + harness results), `world_map` / `how_to_reach` MCP tools | 5, 6 |
| 8 | `feat/m0a-change-check` | diff, structural/semantic/scenario/log-replay/in-flight/NL checks, preview | 6 + **M1 instruments frozen by the researcher** |
| 9 | `feat/m0a-incremental` | dependency graph, hashes, impact report, result cache, background full run | 8 |
| 10 | `feat/m0a-sources-authoring` | source readers (redaction, local-only), authoring MCP (ADR-0014) | 5 |
| 11 | `feat/m0a-kernel-effects` | **added by ADR-0028**: kernel services as declared effects (`call`/`with`/`reply`), compile-time checks, kernel-service port with real and recording-fake adapters, `external:kernel`, `toprope-server --composition`, regeneration check | 5, 6, handoffs (ADR-0024), composition (ADR-0026) |
| 12 | `feat/commit-branches` | **added by ADR-0033**: branch refs, protected `main` (approve = merge into `main`), merge base, semantic 3-way merge with conflicts by path and a validated merge result, `merge`/`branches` CLI, deploy floor by ancestry on `main` | ADR-0029 commits |

Sub-PR 8 does not start until `experiments/m1/instruments/FROZEN.json` exists with the four
stage-1 files (ADR-0031: probes, change requests, change key, verdict rules) (`instruments.py verify` passes without `--run`).

## Done criteria (from the roadmap; all on the toy domain)
- (ADR-0028) a domain whose actions call kernel services runs end to end from its declaration
  alone, and the regeneration check gives the same harness results before and after regenerating
- every decided cell is covered at every level (model, Execution, MCP)
- a deliberately broken generator template is caught while model-level regression still
  passes
- a seeded invariant-breaking transition is found by exploration as a minimal flow
- a race on one cell yields only outcomes the semantics allow
- a single-cell change meets the draft latency targets (impact report ≤ 2 s, affected
  harness ≤ 30 s, preview ≤ 30 s; set by the M1 verdict rules)
- the full run finds no selection miss.

Scope change (ADR-0028, decided by the researcher): sub-PR 11 was added after this spec froze, so
the self domains are generated end to end. It adds about 1–2 weeks. The overrun rule is set aside
for this addition only.

Overrun rule (roadmap): if M0a passes 6 weeks, cut it to what M1 strictly needs (semantics,
model interpreter, Execution, event store, MCP, authoring MCP, model and Execution-level
harness, structural/semantic/scenario/log-replay/in-flight checks), and move the rest to M0b.
Do not extend M0a.

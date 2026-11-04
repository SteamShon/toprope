# Architecture (draft)

Link: ① ④ ⑤ (what the system must support). The first requirement is that domain meaning
is independent of any host, runtime, surface or model: DDD bounded contexts with ports and
adapters. Swapping an adapter must keep the same actions with the same preconditions and
roles. That, not interface shape, is the test of replaceability.

## Layers (ADR-0011)

```
Intelligence   agents (Claude Code, Codex, any MCP client) and people
      │        see the world model via generated MCP, UI and the domain interface
      ▼
Toprope        correctness layer: declaration, matrix, invariants, Execution gate, event store,
               harness-verified generated surfaces
      │        only allowed actions pass
      ▼
Effects        greenfield: generated backend (domain API over Toprope's event store + projections)
               brownfield: existing servers, APIs, DBs behind EffectAdapters (read-back, UNKNOWN)
```

**Hosting is open** (ADR-0011): (a) a gateway or sidecar in front of brownfield servers,
(b) embedded in the generated greenfield backend, or (c) a hosted service (a non-goal for
now). One Execution core serves (a) and (b). M0 builds both shapes on the toy domain.

## Bounded contexts

| Context | Owns | Serves | First in |
|---|---|---|---|
| **Authoring** | sources, drafts, interview questions, provenance and status of every element | ① ② | M0 kernel, then self-compiled in M1 |
| **Domain Model** | objects, links, actions (params, preconditions, effects, roles), versions | all | M0 |
| **Change Check** | impact analysis first (dependency graph, affected set, impact report; ADR-0013); then, on the affected set only: structural, semantic-conflict, scenario-regression, log-replay and NL-conflict checks; preview build (ADR-0009) | ① | M0 |
| **Domain Compiler** | domain → MCP, greenfield backend (domain API over the event store and projections), execution checks, **domain interface** (objects/fields/links/actions/glossary; versioned by diff, hashed per element) | ① ④ | M0 |
| **Representation Compiler** | representation layers (defaults → base → host overlay) + interface → A2UI views, component/action catalog for generative UI. Rebuilt independently of the domain | ④ | M0 |
| **Execution** | checks the matrix cell, roles and non-state preconditions on the projected state; applies effects; runs the **invariant guard** on the resulting state before appending (ADR-0012) | ③ ④ | M0 |
| **Event Store** | event-sourced system of record (ADR-0012): domain events, decisions, denied attempts, exceptions, effect outcomes, domain changes; projections give current state; upcasters across versions; generated read-only query tools for agents | ① ③ ⑤ | M0 |
| **Proposal / Review** | log-mined model diffs; human decisions with their inputs | ⑤ | M4 |
| **Handoff** | typed requests between domains via published domain interfaces | ⑥ | M5 |

After M1, the Authoring context is itself a Toprope domain (self-compile). Its MCP and UI
are generated, and only the kernel stays hand-built.

## Ports

| Port | Responsibility | First adapter | Later candidates |
|---|---|---|---|
| `SourceReader` | read code/schema, records, transcripts, interview logs | repo + markdown + transcript readers | Slack, Notion, DB introspection |
| `Drafter` | sources → proposed elements with source links | Aegra workflow calling an LLM (Claude API) (ADR-0007) | other models or runtimes |
| `Interviewer` | targeted questions on unknown or conflicting elements, `undecided` matrix cells and candidate invariants, asked in plain domain language | Aegra workflow; each question is a HITL interrupt answered in the generated UI (ADR-0007) | other runtimes |
| `DomainStore` | versioned domain models | YAML in repo | git-backed registry |
| `EventStore` | append events (matrix, preconditions and invariants enforced at append); read streams; projections for current state (ADR-0012) | PostgreSQL in its own schema (may share Aegra's server) or SQLite for tests | EventStoreDB, Kafka-backed |
| `AgentSurface` | expose reads and actions to agents | generated MCP server mounted on Aegra custom routes | OpenAPI, LangGraph tools |
| `HumanSurface` | expose objects and actions to people | compiled A2UI views rendered in React + CopilotKit; host-injected components via the renderer catalog; LLM generative UI for ad-hoc views, limited to the catalog and allowed actions (ADR-0008) | other generative-UI stacks, OpenDots |
| `RepresentationStore` | versioned base representations and host overlays | YAML files | host-managed registry |
| `Runtime` | host long-lived agent workflows (drafter, interviewer, proposal engine) | Aegra (ADR-0007) | LangGraph Platform, Temporal |
| `EffectAdapter` | real-world effects, with read-back and `UNKNOWN` | greenfield: the generated backend's store; brownfield: GitHub issues/labels in a sandbox repo (ADR-0011) | flags, ad APIs, internal services |
| `EventQuery` | read-only, declaration-typed queries for agents: timelines, decision history, denials per cell, `undecided` hits, exceptions, effect outcomes; exposed as generated MCP tools | in-process over `EventStore` | analytics warehouse |
| `ProposalEngine` | logs → candidate diffs | Aegra cron workflow calling an LLM | Harness²-style probe loops |
| `ScenarioRunner` | run the domain's flows against the model (reference interpreter) | in-process | — |
| `WorldBuilder` | grow the expert's fixtures into a small world: an instance per reachable state, every role, boundary values; report unreachable states | in-process | — |
| `HarnessGenerator` | compile the matrix, invariants, world and flows into per-surface tests (Execution, MCP client, A2UI view assertions, adapters); parity and coverage reports (ADR-0010) | pytest-based generated suite | browser end-to-end for host components |
| `Explorer` | bounded stateful exploration of action sequences for invariant violations and parity failures; minimal counterexample flows | Hypothesis stateful testing | TLA+/Alloy model checking |
| `LogReplayer` | re-run recorded events against a new version and diff outcomes | `EventStore` reader | — |
| `ConflictLinter` | flag contradictions among natural-language parts (descriptions, judgment rules) as warnings | LLM call | other models |
| `PreviewEnvironment` | generated MCP + UI on a copy of the state for trying a change | local process | per-PR preview deployments |
| `ImpactAnalyzer` | dependency graph from declaration elements to artifacts and tests; content hashes; affected set; impact report in domain terms (ADR-0013) | in-process | — |
| `ResultCache` | test results keyed by the hashes of all their inputs; deploy gate reads it | local file / SQLite | shared remote cache |

## Change-check pipeline (ADR-0009): the compiler's core job

```
edited domain ──► diff vs. current version
                  ──► impact analysis: affected elements → artifacts → tests (ADR-0013)
                  ──► impact report (before anything runs)
                  ──► on the affected set only, with cached results reused:
                    ├─ structural (references, types)          deterministic
                    ├─ semantic conflict (contradictions,      deterministic
                    │   unreachable states, dead actions)
                    ├─ scenario regression (model level)       deterministic
                    ├─ generated harness on the preview build: deterministic (gate tier;
                    │   background exploration is outside the gate, ADR-0013)
                    │   every matrix cell, invariants after every step, bounded
                    │   exploration, example flows; at Execution, MCP, A2UI views,
                    │   adapters; parity across surfaces; coverage (ADR-0010)
                    ├─ log replay ("12 past actions would      deterministic
                    │   now be blocked")
                    └─ NL conflict (descriptions, judgment)    LLM → warnings
                  ──► report in domain terms ──► preview build (MCP + UI on copied state)
                  ──► human decides to deploy
```

Iteration time (edit → validated preview) is a design constraint: the premise is that
domains are found by many cheap iterations (P0). The compiler is incremental from M0 (ADR-0013). Impact
analysis is static, because every artifact and test is generated from the declaration. It
selects conservatively. The deploy gate requires a passing result for every test at the
current input hashes, mostly cache hits. A background full run checks that no affected test
was missed.

## Two compile pipelines (ADR-0008)

```
domain.yaml ──► Domain Compiler ──► MCP + execution checks
                       └──────────► domain interface (versioned, hashed)
                                          │
representation.yaml (base) ──┐            ▼
host overlay + components ───┴──► Representation Compiler ──► A2UI views + catalog
```

A representation change rebuilds only the right-hand side. A domain change rebuilds the
domain and re-validates every representation against the new interface.

## Event sourcing (ADR-0012)

```
action call ─► Execution: matrix + preconditions + invariants ─► append event ─► projections
     │                     │ denied                                    │
     │                     └──► append DeniedAttempt                    ▼
     └─ actor, thread_id, run_id ──────────────────────────► generated read-only MCP query tools
                                                                       │
                       Aegra workflows (proposal engine, interviewer) ◄┘
```

The core owns the event store. Aegra's threads and checkpoints are a separate stream of
agent-execution records, linked to domain events by `thread_id` and `run_id`.

## Stack (ADR-0007)

- Domain core: pure Python (`uv`), with no Aegra or LangGraph imports.
- Server: Aegra (FastAPI + LangGraph + PostgreSQL + Redis) hosting the agent workflows and the
  generated MCP/domain API as custom routes.
- Frontend: TypeScript, React + CopilotKit over AG-UI.

## Guarantee boundary

- Guarantees hold only for actions that go through Execution. Other paths are outside them.
- The model guarantees consistency with the model, not that the model is right. Keeping it
  right is the job of ② and ⑤.
- Real external effects can be `UNKNOWN`. Read-back is required before claiming success.

# Architecture (draft)

First requirement: **domain meaning is independent of any host, runtime, surface or model.**
DDD bounded contexts with ports and adapters. Swapping an adapter must keep the same
actions with the same preconditions and roles. That is the test of replaceability, not
interface shape.

## Bounded contexts

| Context | Owns | Milestone |
|---|---|---|
| **Authoring** | sources (system, records, interview, use), drafts, provenance and confirmation status of every element | M0–M1 |
| **Domain Model** | objects, links, actions (params, preconditions, effects, roles), versions | M0 |
| **Compiler** | domain → capsule: MCP surface, UI surface, generated checks and tests | M0 (MCP + minimal UI), M2+ (richer UI) |
| **Execution** | runs an action: checks preconditions and roles against current state, applies the effect, records it | M0 |
| **Event Log** | append-only record of calls, verdicts, effects, human decisions | M0 |
| **Proposal** | turns logs into proposed model diffs with evidence | M3 |
| **Review** | human decisions on proposals and exceptions, recorded with their inputs | M3 |
| **Handoff** | typed requests between domains via published contracts | M4 |

## Ports

| Port | Responsibility | First adapter | Later candidates |
|---|---|---|---|
| `SourceReader` | read raw material: repository (code/schema/API), records (docs, issues, chats), interview log | repo + markdown/issue export readers | Slack, Notion, DB introspection |
| `Drafter` | sources → proposed model elements with source links | LLM call (Claude API) | other models |
| `Interviewer` | ask the owner targeted questions about unknown or conflicting elements | CLI chat | UI panel, voice |
| `DomainStore` | load/save versioned domain models | YAML in repo | git-backed registry |
| `StateStore` | object instances and links | SQLite + synthetic generator | Postgres, existing app DBs |
| `AgentSurface` | expose actions/reads to agents | generated MCP server | OpenAPI, LangGraph tools |
| `HumanSurface` | expose objects/actions to people | generated schema-driven web UI | generative-UI specs, host panel (OpenDots) |
| `EffectAdapter` | perform real-world effects of an action | in-store only | GitHub, flag service, ad APIs (with read-back) |
| `EventLog` | append events | JSONL | SQLite, OpenTelemetry |
| `ProposalEngine` | logs → candidate diffs | LLM call (Claude API) | Harness²-style probe loops |
| `Approver` | other roles' decisions | scripted responder (experiments), human via UI | Slack, email |

## Flow

```
domain.yaml ──compile──► capsule ──► MCP tools ──► agent
                              └────► UI ─────────► person
                                         │
           both call ──► Execution: check preconditions/roles on StateStore
                                         │ allow → apply effect → EventLog
                                         │ deny  → reason (from the model) → EventLog
EventLog ──► ProposalEngine ──► diff ──► Review (person decides) ──► new domain version
```

## Guarantee boundary (stated up front)

- Guarantees hold only for actions that go through Execution. Direct DB writes or other
  tools are outside, and M1 measures workaround attempts.
- The model guarantees an action is *consistent with the model*, not that the model is
  *right*. That is what the human-decided loop is for.
- Real external effects (M4+) can be `UNKNOWN`. Read-back is required before claiming success.

## Deferred choices

Runtime (Temporal, LangGraph) and host (OpenDots) are not needed while actions are
short-lived calls against a local store (ADR-0006). They come in behind `EffectAdapter` /
`HumanSurface` when a milestone needs durable multi-step work or a shared workspace.

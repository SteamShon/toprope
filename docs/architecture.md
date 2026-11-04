# Architecture (draft)

Link: ① ③ ④ (what the system must support). The first requirement is that domain meaning
is independent of any host, runtime, surface or model: DDD bounded contexts with ports and
adapters. Swapping an adapter must keep the same actions with the same preconditions and
roles. That, not interface shape, is the test of replaceability.

## Bounded contexts

| Context | Owns | Serves | First in |
|---|---|---|---|
| **Authoring** | sources, drafts, interview questions, provenance and status of every element | ① ② | M0 kernel, then self-compiled in M1 |
| **Domain Model** | objects, links, actions (params, preconditions, effects, roles), versions | all | M0 |
| **Compiler** | domain + representation → capsule: MCP, A2UI views, component/action catalog for generative UI, generated checks | ① ③ | M0 |
| **Execution** | checks preconditions and roles on current state, applies effects | ③ | M0 |
| **Event Log** | append-only calls, verdicts, effects, human decisions | ④ | M0 |
| **Proposal / Review** | log-mined model diffs; human decisions with their inputs | ④ | M4 |
| **Handoff** | typed requests between domains via published contracts | ⑤ | M5 |

After M1, the Authoring context is itself a Toprope domain (self-compile). Its MCP and UI
are generated, and only the kernel stays hand-built.

## Ports

| Port | Responsibility | First adapter | Later candidates |
|---|---|---|---|
| `SourceReader` | read code/schema, records, transcripts, interview logs | repo + markdown + transcript readers | Slack, Notion, DB introspection |
| `Drafter` | sources → proposed elements with source links | LLM call (Claude API) | other models |
| `Interviewer` | targeted questions on unknown or conflicting elements | CLI chat | generated UI |
| `DomainStore` | versioned domain models | YAML in repo | git-backed registry |
| `StateStore` | object instances and links | PostgreSQL (shared with Aegra) or SQLite for tests | existing app DBs |
| `AgentSurface` | expose reads and actions to agents | generated MCP server mounted on Aegra custom routes | OpenAPI, LangGraph tools |
| `HumanSurface` | expose objects and actions to people | declared `representation` → deterministic A2UI, rendered in React + CopilotKit; schema defaults where undeclared; LLM generative UI for ad-hoc views, limited to declared components and allowed actions (ADR-0008) | other generative-UI stacks, OpenDots |
| `Runtime` | host long-lived agent workflows (drafter, interviewer, proposal engine) | Aegra (ADR-0007) | LangGraph Platform, Temporal |
| `EffectAdapter` | real-world effects | in-store only | GitHub, flags, ad APIs (with read-back) |
| `EventLog` | append events | JSONL | SQLite, OpenTelemetry |
| `ProposalEngine` | logs → candidate diffs | LLM call | Harness²-style probe loops |

## Stack (ADR-0007)

- Domain core: pure Python (`uv`), with no Aegra or LangGraph imports.
- Server: Aegra (FastAPI + LangGraph + PostgreSQL + Redis) hosting the agent workflows and the
  generated MCP/domain API as custom routes.
- Frontend: TypeScript, React + CopilotKit over AG-UI.

## Guarantee boundary

- Guarantees hold only for actions that go through Execution. Other paths are outside them.
- The model guarantees consistency with the model, not that the model is right. Keeping it
  right is the job of ② and ④.
- Real external effects can be `UNKNOWN`. Read-back is required before claiming success.

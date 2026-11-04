# ADR-0012: Event sourcing is owned by the core; agents query it; Aegra consumes it

- Link: ③ works as built, ⑤ evolves (and the log replay of ①) · Status: accepted · 2026-11-04 · decided by: SteamShon

## Context
Everything must remain as a record, or it cannot become material for learning. The
researcher's implementation pattern is **DDD + invariants + transition matrix + event
sourcing**. Agents must be able to query those records, or they cannot propose the next
policy or the next domain improvement. The open question was where event sourcing
belongs: Aegra (the runtime) or the Toprope core and compiler.

## Decision

### 1. The core owns the event store
- Domain events are the system of record. Each allowed matrix transition is a typed event
  (e.g. `ExperimentApproved`). Current state is a **projection** of the event stream.
- The **compiler generates** from the declaration: the event schemas, the projections, and the
  append path. The append path enforces the matrix and the preconditions, and runs an
  **invariant guard** on the resulting state.
- **The invariant guard is defense in depth, not a rule source.** A consistent declaration
  never triggers it, because invariants should follow from the matrix and the effects. If it
  does trigger, the append is rejected and an `InvariantGuardTriggered` event is recorded.
  That event is an inconsistency alarm, not a normal denied attempt. In the harness
  (ADR-0010), the model level runs without the guard and reports the violation, runtime
  levels report the guard trigger at the same step, and parity treats these as the same
  outcome. Either one fails the build.
- Event schemas are versioned with the domain interface (ADR-0008). A domain change that
  alters an event comes with an **upcaster**, so old events still project under the new
  version. Log replay (ADR-0009) and the harness (ADR-0010) run on this store.
- The core never imports Aegra (ADR-0007). The store sits behind an `EventStore` port.
  Physically it may share Aegra's PostgreSQL, but in its own schema and under core ownership.

### 2. What is recorded
| Event kind | Example | Why |
|---|---|---|
| Domain events | `ExperimentApproved`, `ExperimentLaunched` | system of record, replay, projections |
| Decision events | who decided, with which inputs and rationale (`records_decision`) | accumulated work decisions (⑤) |
| **Denied attempts** | a call blocked by a matrix cell or precondition, with the reason and the actor | the strongest learning signal: a cell that keeps getting hit says the rule and reality disagree |
| Exceptions | "this once", with the reason | accumulated exceptions become amendment proposals |
| Effect outcomes | succeeded / `UNKNOWN` / confirmed by read-back | trust in brownfield effects (ADR-0011) |
| Domain-change events | model versions; proposals accepted or rejected, with evidence | the record of the authoring domain itself (self-compile) |

Denied attempts and `UNKNOWN` outcomes do not change state, but they are always recorded.

### 3. Agents query it through generated read tools
The compiler generates **read-only MCP tools** over the event store, typed from the
declaration:
- an object's timeline
- decision history with inputs
- denials per matrix cell over a period
- attempts that hit `undecided` cells
- exception trends
- effect outcomes by adapter.

These are part of the domain capsule, so any agent (Claude Code, Codex, or Aegra
workflows) can use them. They cannot write. Writes go only through actions.

### 4. Aegra consumes, it does not own
- Aegra runs the agent workflows that read the event store: the **proposal engine** (cron:
  mine denials, exceptions and decision patterns → propose domain diffs with evidence) and
  the **interviewer** (ask about cells that real attempts keep hitting).
- Aegra's own threads and checkpoints are **agent execution records**, not domain facts.
  They stay a separate stream. Every domain event carries `actor`, plus `thread_id` and
  `run_id` when it came from an agent run. This links what happened in the domain to the
  agent run that caused it.

## Consequences
- The `StateStore` port becomes `EventStore` + projections. The greenfield backend
  (ADR-0011) is event-sourced. Brownfield effects are recorded as intent + outcome +
  read-back. The external system is not event-sourced; only Toprope's view of it is.
- The harness also checks that replaying a flow's events rebuilds the same projected state
  (replay parity).
- M0 builds the event store, projections, append-time enforcement and the generated read
  tools on the toy domain. M4 (⑤ evolves) uses them for proposals.

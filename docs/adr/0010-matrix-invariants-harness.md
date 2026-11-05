# ADR-0010: Transition matrix, invariants and a small world drive a generated harness

- Link: ① iterate safely, ② model is right, ③ works as built, ④ shared language · Status: accepted · 2026-11-04 · decided by: SteamShon

## Context
- The researcher's preferred way to keep a domain correct, from DDD and agent-based coding,
  is to manage a **transition matrix** (state × action → outcome) and **invariants** (what
  must always hold).
- People cannot test a full transition matrix by hand. Domain experts do not know or think
  in transition matrices, yet they hold every answer that fills one.
- ADR-0009's scenario regression runs at the model level only. Generated code (MCP server,
  A2UI views, Execution, adapters) that is never exercised is not known to work.

So the most important job of the compiler and code generation is this. Capture the matrix
and invariants **through the interview**, in domain language. Build a **small world** from
the expert's examples. Then generate a harness that checks the **whole** matrix and every
invariant against every generated surface.

## Decision

### 1. The declaration holds a transition matrix and invariants
- Each stateful object declares a **transition matrix**: for every (state, action), the
  outcome is one of:
  - a target state, optionally per role
  - `deny` with a reason
  - `n/a` (the action is not meaningful there). At runtime this **denies** with the
    standard reason "not applicable when <state>", records a denied attempt, and is never
    shown as an available action. Unlike `deny`, it is not turned into an interview
    question.
  - `undecided`.
  The matrix is the single source for state-based preconditions. Action `preconditions` hold
  only conditions that do not depend on state (e.g. "at least one guardrail").
- **Expression language.** Invariants need set membership and boolean combination, so this
  ADR extends the `check` language (ADR-0004 / domain-schema) with `in`, `not in`, `and`,
  `or`, `not` and list literals. Nothing else is added.
- **Invariants** state what must hold in every reachable state (e.g. "a running experiment
  has an approver", "a decided experiment has a readout"). Each has an id, a check and a
  reason, with `source` and `status` like any other element.
- `undecided` cells **deny by default**, with the reason "undecided", and are listed in every
  change report. No cell is ever silently allowed. Undecided cells do not block deployment,
  because the premise is that domains are found by iterating (P0).

### 2. The interview fills the matrix in domain language
- The interviewer enumerates the cells that are undecided or contradicted, plus candidate
  invariants, and asks about them as plain questions. For example, "Can an approver approve
  an experiment that is already running?" or "Can an experiment ever be running without
  someone having approved it?"
- Answers become cell decisions or invariants with `source: interview` and `status:
  confirmed`. The expert never has to see a matrix. A representation of the matrix (a table
  view of the domain itself) is available for those who want it.
- The expert also gives **examples**: realistic instances and short stories. These become
  fixtures and flows.

### 3. A small world is generated from the examples
- From the fixtures, the compiler builds a **small world**: at least one instance in every
  reachable state, every role as an actor, and boundary values for every non-state
  precondition. Missing states are reached by applying allowed transitions to the fixtures.
  A state that cannot be reached is reported, because it is either dead or a missing
  transition.

### 4. The harness is generated from matrix, invariants, world and flows

| Part | What it does |
|---|---|
| **Cell tests** | For every (state, action, role) cell, take a small-world instance in that state, attempt the action, and expect the declared outcome (target state, or a denial with its reason). Every cell is covered by construction. |
| **Invariant checks** | After every step of every test, check every invariant. |
| **Bounded exploration** | Stateful property-based exploration of action sequences over the small world, bounded by depth and by a **fixed number of examples with a fixed seed**, never by wall-clock time, so a run is reproducible (first adapter: Hypothesis stateful testing). It looks for invariant violations and cross-surface disagreements. A counterexample is reported as a minimal flow in domain terms, which the author can keep as a new example. |
| **Example flows** | The expert's multi-step flows (`do` and `read` steps) run as written. |

Every part runs at **every level**: the model interpreter, Execution (the event store and
projections, ADR-0012), an MCP client against the generated server, compiled A2UI views (allowed actions and
fields shown per role and state, and forms that submit the same action), and adapters
(read-back, with timeouts as `UNKNOWN`).

### 5. Parity and coverage
- The same test must give the same outcome on every surface. A disagreement is a **parity
  failure**. This is the mechanical check behind ④.
- Coverage is reported for: matrix cells (100% by construction once decided), invariants
  exercised, declared views, flows, and unreachable states.

### 6. Where it runs
The harness is part of the change-check pipeline (ADR-0009). It runs on every rebuild
against the preview build. A failing cell test, an invariant violation or a parity failure
blocks deployment of that build. A representation-only change runs only the UI level, plus
parity on the affected views.

### 7. What it does not prove
The harness verifies that generated code **conforms to the declaration**, and that the
declaration is **internally consistent** (its invariants hold under its own transitions).
It cannot show that the declaration matches how the work really runs. That remains the job
of the held-out gold scenarios, the post-deploy probes, and people (②). Held-out gold is
never part of the domain or the harness.

## Consequences

> Note (ADR-0019): M0 is now split. M0a builds the model, Execution and MCP levels. The A2UI
> view checks come in M0b.

- The compiler's outputs are now MCP, A2UI views, the domain interface, and the harness.
- M0 builds harness v0 at the model, Execution and MCP levels, plus A2UI message-level view
  checks. Browser end-to-end tests are added only for host-injected components (ADR-0008).
  Adapter-level checks begin with the first real `EffectAdapter`.
- M1 measures how well the interview fills the matrix and how much the harness catches
  (see the experiment doc).

# Declaration and execution semantics (draft)

Link: ① ② ③. This document is the **oracle**. The model interpreter implements it, and
every generated surface must agree with it (ADR-0010 parity, ADR-0019). Where a surface
disagrees, the surface is wrong.

## 1. Command
A command is `(actor, on_behalf_of?, grant?, action, target?, params, idempotency_key, at)`:
- `at` is the clock time (the virtual clock in the harness)
- `idempotency_key` is required for every command that comes from outside the process.

## 2. Evaluation order
Evaluation stops at the first failure, and each failure has its own outcome:

1. **Identity**: the actor is known (ADR-0016). Otherwise `rejected: unauthenticated`. This
   is not recorded as a domain event.
2. **Idempotency**: if the key has been seen, return the original outcome. Nothing new is
   appended.
3. **Load**: project the target aggregate's current state at stream version `v`.
4. **Matrix cell** for (state, action):
   - `n/a` → `denied: not-applicable`
   - `{deny}` → `denied: matrix`
   - `undecided` → `denied: undecided`
5. **Actor rule**: role, relation, the grant and `requires: human` (ADR-0016). Failure →
   `denied: actor`.
6. **Non-state preconditions**, in declared order. The first failure →
   `denied: <precondition id>`.
7. **Approvals** (ADR-0015): if more are needed, record the partial approval → `pending`.
8. **Reservations** for cross-aggregate invariants (ADR-0015). Failure →
   `denied: reservation`.
9. **Effects** are computed on a copy: the state field from the matrix, then `set` and
   `create` in order. Functions are called here and must be pure.
10. **Invariant guard** on the resulting state (ADR-0012). Failure →
    `rejected: invariant-guard`, recorded as `InvariantGuardTriggered`.
11. **Append**: write the domain event(s) and the decision event, if any, at expected
    version `v`. On a version conflict, retry from step 3 up to N times, then
    `rejected: conflict`.
12. **External effects** (brownfield) run **after** the append, from an outbox. Their outcome
    is recorded as `EffectSucceeded`, `EffectUnknown` or `EffectConfirmed` (read-back).

Every `denied:*` outcome appends a `DeniedAttempt` event with the reason. `pending` appends
`ApprovalRecorded`.

## 3. Atomicity and concurrency
- One command changes **one aggregate** atomically. Several aggregates are coordinated only
  through reservations or follow-up commands (sagas), never in one transaction.
- Optimistic concurrency is per aggregate stream: two commands on the same object are
  serialized by version, and the loser is re-evaluated from step 3.
- The harness includes **concurrency tests**: two actors racing on the same cell must both
  give outcomes this document allows, and both must leave the invariants intact.

## 4. Time
- Timers (ADR-0015) are commands issued by the `system` actor at their due time, through
  the same order of evaluation.
- In the harness, the clock is virtual. Tests advance it explicitly.

## 5. Events
- Each event has: `type`, `aggregate`, `id`, `version`, `at`, `actor`, `on_behalf_of`,
  `grant`, `thread_id`/`run_id` (if from an agent run), `domain_version`, `payload`.
- Projection is a pure fold over events. Replaying the same events yields the same state
  (replay parity).
- Old events are read through upcasters (ADR-0012). They are never rewritten.

## 6. Determinism
- The model interpreter is deterministic, given the same declaration, the starting state,
  the command sequence and the clock.
- Sources of non-determinism stay outside it: LLM calls, external effects and wall-clock
  time. They enter only as recorded inputs or events.

## Open
- The default retry count N for version conflicts, and backoff.
- Ordering guarantees for external effects across aggregates.

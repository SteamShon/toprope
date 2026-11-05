# Declaration and execution semantics

Link: ① ② ③. Status: **frozen for M0a** (docs/milestones/M0a.md). Changes need an ADR.
Amended by ADR-0021 and ADR-0023.

This document is the **oracle**. The model interpreter implements it, and
every generated surface must agree with it (ADR-0010 parity, ADR-0019). Where a surface
disagrees, the surface is wrong.

What objects, links, actions and the matrix are is explained in [`domain-model.md`](domain-model.md); this page gives their exact semantics.

## 1. Command
A command is `(actor, on_behalf_of?, grant?, action, target?, params, idempotency_key, at)`:
- `at` is the clock time (the virtual clock in the harness)
- `idempotency_key` is required for every command that comes from outside the process. It
  is scoped to `(actor, action, target)`, so a key reused by another actor, or for another
  action, is a different command.

## 2. Evaluation order
Evaluation stops at the first failure, and each failure has its own outcome:

0. **Command validation** (ADR-0021): a target id is given, and params match the declaration
   (no unknown params, required ones present, type/enum/`many`/`ref` shape). Otherwise
   `rejected: invalid-command`.
1. **Identity**: the actor is known (ADR-0016). Otherwise `rejected: unauthenticated`. This
   is not recorded as a domain event.
2. **Idempotency**: atomically claim `(actor, action, target, key)`. If it already has an
   outcome, return it and append nothing. If another call holds the claim,
   `rejected: in-progress`. A transient `rejected: conflict` releases the claim (ADR-0021).
3. **Load**: project the target aggregate's current state at stream version `v`. If it does
   not exist (or, for a create action, already exists), actors whose role could not act get
   `denied: actor` and everyone else gets `rejected: not-found` / `rejected: exists`
   (ADR-0021). Link ids that do not resolve to an object of the linked type read as missing.
4. **Actor rule**: role, relation, the grant and `requires: human` (ADR-0016). The reserved
   actors `system` (timers, handoffs) and `external:<source>` match a rule that names them
   (ADR-0023). This runs
   before the matrix, so cells that differ per role are resolved for this actor. Failure →
   `denied: actor`.
5. **Matrix cell** for (state, action, the actor's roles; an agent's principal too). A
   `by_role` cell allows only if every listed role involved allows the same state, and
   otherwise the most restrictive outcome wins (ADR-0021):
   - `n/a` → `denied: not-applicable`
   - `{deny}` → `denied: matrix`
   - `undecided` → `denied: undecided`
6. **Non-state preconditions**, in declared order. The first failure →
   `denied: <precondition id>`.
7. **Approvals** (ADR-0015, ADR-0023): if more are needed, record the partial approval →
   `pending`. It counts only if the caller passes step 4 and holds `from_role`; `distinct`
   counts people (an agent counts as its principal); any change to the target resets them.
8. **Reservations** for cross-aggregate invariants (ADR-0015):
   - The reservation is claimed by a **separate command** on the reservation aggregate,
     issued before this one by the generated saga.
   - It is **held for as long as the claiming object stays in the constrained states**, and
     released by the transition that leaves them.
   - If any later step of this command fails, the saga issues a compensating release.
   - Here, step 8 only checks that the claim is held. Failure → `denied: reservation`.
9. **Effects** are computed on a copy. Functions may be called here and in steps 4–6 and 10;
   they are pure (ADR-0023). the state field from the matrix (or `initial` for a
   create action, which takes only declared params), then `set` in order. Functions are
   called here and must be pure. `create:` effects are not supported yet
   (`rejected: unsupported-effect`, ADR-0021).
10. **Invariant guard** on the resulting state (ADR-0012). Failure →
    `rejected: invariant-guard`, recorded as `InvariantGuardTriggered`.
11. **Append**: write the domain event(s) and the decision event, if any, at expected
    version `v`. On a version conflict, retry from step 3 up to N times, then
    `rejected: conflict`.
12. **External effects and handoffs** run **after** the append, from an outbox. A handoff is a
    command into another domain, as `system` (`handoff:<sender domain>.<name>`, ADR-0026) on behalf of the
    originating person, with idempotency key `<handoff>:<sender event id>`. A denial there is
    recorded here as `HandoffDenied` (ADR-0023). Their outcome
    is recorded as `EffectSucceeded`, `EffectFailed`, `EffectUnknown` or `EffectConfirmed`
    (read-back).
    Kernel-service calls (ADR-0028) use the same outbox: `EffectRequested` is appended in
    step 11, the service runs after the append, and its result comes back as a command from
    `external:kernel` to the declared reply action, keyed by the effect id.
    Handoff details (ADR-0024): the outbox entry is a `HandoffRequested` event
    appended atomically in step 11; the sender event id is that entry's
    `<stream>@<version>`; the receiver's events carry it as `causation`; the sender records
    exactly one resolution (`HandoffDelivered`, `HandoffDenied` or `HandoffFailed`) in its
    own stream `handoff:<id>`; a transient outcome or an unreachable receiver stays pending
    and is retried. With no originating person (a system actor acting for no one), the
    handoff carries no `on_behalf_of`.

Recording:
- Every `denied:*` outcome appends a `DeniedAttempt` with the reason, to a separate
  **attempts stream** per aggregate. Attempts never bump the aggregate's version, so they
  cause no conflicts.
- `pending` appends `ApprovalRecorded` to the aggregate stream.
- Interview prioritization (ADR-0014) counts only attempts that passed the actor rule
  (step 4). An attempt by an actor who could never be allowed says nothing about a cell.

## 3. Atomicity and concurrency
- One command changes **one aggregate** atomically. Several aggregates are coordinated only
  through generated sagas: reservations, follow-up commands and compensations. They are
  never changed in one transaction.
- Optimistic concurrency is per aggregate stream: two commands on the same object are
  serialized by version, and the loser is re-evaluated from step 3.
- The harness includes **concurrency tests**:
  - two actors racing on the same cell must both get outcomes this document allows, and
    the invariants must still hold
  - two objects racing for the same reservation must leave at most one holder.

## 4. Time
- Timers (ADR-0015) are commands issued by the `system` actor at their due time, through
  the same order of evaluation.
- In the harness, the clock is virtual. Tests advance it explicitly.

## 5. Events
- Each event has: `type`, `aggregate`, `id`, `version`, `at`, `actor`, `on_behalf_of`,
  `grant`, `thread_id`/`run_id` (if from an agent run), `causation` (the handoff id, if a
  handoff issued it; ADR-0024), `domain_version`, `payload`.
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

# ADR-0021: Semantics clarifications found while building the oracle

- Link: ① ③ · Status: accepted · 2026-11-04 · decided by: SteamShon (via M0a sub-PR 3 review)
- Amends: `docs/semantics.md` (frozen for M0a; changes need an ADR)

## Context
Implementing `docs/semantics.md` as the model interpreter (M0a sub-PR 3) and reviewing it
exposed cases the document left open. Several of them failed open.

## Decision
1. **Command validation (new step 0).** Before anything else, a command must name a target,
   and its params must match the action's declared params: no unknown params, no missing
   required ones, and correct type, enum, `many` and `ref` shape. Otherwise
   `rejected: invalid-command`, which is not recorded as a domain event.
2. **Existence after a role pre-check.** "No such object" (`rejected: not-found`) and "already
   exists" (`rejected: exists`, for create actions) are returned only to actors whose role
   could perform the action at all. Others get `denied: actor`, recorded as an attempt, so
   existence is not revealed by probing.
3. **Create actions** copy only **declared** params that name a property or an outgoing link,
   never the state field. The state comes from `transitions.initial`.
4. **Per-role cells** are resolved for every role the actor holds that the cell lists. For an
   agent, they are also resolved for its principal. The cell allows only if all of them allow
   the same target state. Otherwise the most restrictive outcome wins: `deny`, then `n/a`,
   then `undecided`. The result never depends on role order.
5. **Principals are people.** An agent's `on_behalf_of` must be a person (ADR-0016).
6. **Unsupported effects fail closed.** `create:` effects, and `new.` keys outside a create
   action, are `rejected: unsupported-effect` at runtime and errors at compile time, until a
   later ADR defines them.
7. **Links in paths.** A link id that does not resolve, or resolves to an object of another
   type, is dropped from lists and is `null` when single. So `count()` never counts it.
8. **Idempotency claims.** A key is claimed atomically before evaluation. A concurrent call
   with the same key gets `rejected: in-progress`. A transient `rejected: conflict` releases
   the claim, so the key can be retried. Only final outcomes are remembered.
9. **"Allowed actions"** (for views and `read` steps) means steps 4–6 pass, skipping
   preconditions that read `params`. A listed action can succeed with valid params, and an
   unlisted one cannot succeed with any.
10. **Event isolation.** Events own deep copies of their payloads, and projection returns
    copies, so no caller can mutate history (replay parity).

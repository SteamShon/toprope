# ADR-0015: Expressiveness beyond the state machine

- Link: ② model is right, ③ works as built · Status: accepted · 2026-11-04 · decided by: SteamShon
- Origin: design review 2026-11-04 (finding 2)

## Context
Real workflows include things a per-object transition matrix cannot say on its own. If
they have no declared place, they leak into hand-written code, and "writing the code is
nearly free" (③) loses its meaning.

## Decision
1. **Time.**
   - A declared **timer** fires a transition, e.g. `after: {days: 14, from: running, do:
     end_experiment, actor: system}`.
   - Deadlines are declared too.
   - A new `Scheduler` port runs timers. The first adapter is in-process; Temporal is a
     candidate.
   - The harness runs on a **virtual clock**, so time-based cells are tested without
     waiting.
2. **Aggregates and invariant scope.**
   - Each object type is an aggregate by default: one event stream, and the unit of atomic
     consistency.
   - An invariant declares `scope: aggregate` or `scope: cross`.
   - Aggregate invariants are guarded at append (ADR-0012).
   - **Cross-aggregate invariants** (e.g. "at most one running experiment per surface") are
     enforced through a declared **reservation**: a small generated aggregate that is
     claimed before the transition and released after. The model checks this.
   - A cross invariant without a reservation is checked after the fact and raises an
     alarm. The compiler warns that it is not enforced.
3. **Functions.**
   - Computations such as sample size, statistical readout or price are declared as **typed
     function ports**: name, typed inputs, typed output and examples.
   - The implementation is written by a person or an agent, outside generated code. It must
     pass its declared examples as **contract tests** in the harness, and it is pure: no
     effects.
   - Generated code never contains business computations, and functions never change state.
     That boundary is what "generated" means in ③.
4. **External events.** An inbound event (e.g. a webhook) is declared as an action whose
   actor is an `external:<source>` system actor. It goes through the same matrix,
   preconditions and invariants, and is recorded like any other action.
5. **Multi-party approval.**
   - An action may require `approvals: {count: 2, from_role: approver, distinct: true}`.
   - Partial approvals are recorded as events.
   - The transition fires when the count is reached.

## Consequences
- The schema gains `timers`, `invariants[].scope`, `reservations`, `functions`,
  `external` actors and `approvals`. Each is added to `docs/domain-schema.md` with an example
  when it is implemented, not before.
- The harness adds a virtual clock, reservation tests and function contract tests.
- M2 counts hand-written function code separately from generated code when it measures ③.

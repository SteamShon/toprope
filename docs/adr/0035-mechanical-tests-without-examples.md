# ADR-0035: The harness tests what the declaration says, with or without examples

- Link: ① iterate safely, ③ works as built · Status: accepted · 2026-11-05 · decided by:
  SteamShon (direction; drafted by the assistant during M1 Phase A)
- Amends: ADR-0010 (the small world is grown only from the expert's examples)

## Context
M1 Phase A drafted the self domains stage by stage. Before the examples stage, the harness
ran but executed nothing: the small world is grown only from fixtures (ADR-0010), so with no
fixtures there is nothing to run a cell on. Even with fixtures, a stage held by no example
looked unreachable, and only one example per stage was explored.

The researcher's view: once structure, stages and transitions are declared, **everything
about whether the domain behaves as declared can be tested mechanically**. Whether what is
declared is *right* is a question of meaning, and that needs people and their examples.

## Decision
The harness has two layers with different jobs.

1. **Mechanical layer: "it does what the declaration says".** It needs no examples. It
   checks every element against the declaration itself:
   - **structure**: references, types, kernel-service wiring, handoff contracts (already the
     validator and the composition check)
   - **every cell**: for each (stage, action, role), objects generated from the property types,
     enums and links in that stage are run through the action, and the outcome must be the
     one the matrix, the actor rules and the preconditions give
   - **invariants are inductive**: for each allowed cell, starting from a generated object
     that satisfies every invariant, the resulting state still satisfies every invariant. A
     failure names the cell, the invariant and the generated object: the matrix allows a move
     the invariants forbid
   - **reachability from creation**: stages no sequence of declared actions can reach from a
     created object
   - **parity, replay and races** across surfaces, as now (ADR-0010)

   Generated objects that break an invariant are discarded, so impossible starting points do
   not raise false alarms. Generation is seeded and bounded, like gate-tier exploration
   (ADR-0013), so a run is reproducible and cacheable.
2. **Semantic layer: "what is declared is right".** It needs people. The expert's examples
   (fixtures) and scenarios encode what the domain *means*: realistic values, boundary cases,
   flows that must pass or be refused. They are grown into the small world as now, every
   example explored. Their findings, and the interview's confirmations, are the evidence for
   ② (the model is right). Mechanical tests are never evidence for ②.

Reports keep the two apart: a mechanical failure says the declaration contradicts itself or a
surface disagrees with it; a semantic failure says the declaration disagrees with an example
or a scenario the owner gave.

## Consequences
- A domain is testable from the moment it has stages: the interview can show contradictions
  before any example exists.
- "Unreachable from the examples" (semantic) and "unreachable from creation" (mechanical)
  are reported separately.
- The incremental analysis (ADR-0013) treats the mechanical tests like cell tests: they
  depend on the cell, the action, the reachable objects' properties and the invariants.
- Exhaustive proof is not claimed: generation samples values. A symbolic check of the small
  expression language (an SMT solver) can replace sampling later, by its own ADR.

## Implementation
After M1 Phase A, as one PR on the harness. Already done during Phase A: every example is
explored (not one per stage), and races pair only cases on the same example.

> Implementation note (2026-11-06): a broken invariant on a generated start is reported as a
> **warning** (`inductive`), not a failure: the generated start may be one no real history
> reaches. Parity failures on generated objects fail as before.
> **Decided by the researcher (2026-11-06):** non-inductive invariants stay warnings.

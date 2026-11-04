# ADR-0009: Premise P0; ① becomes "iterate safely"; change safety is the compiler's core job

- Link: ① ② (and the whole chain) · Status: accepted · 2026-11-04 · decided by: SteamShon
- Supersedes: ADR-0001

## Context
The researcher's underlying hypothesis is that **nobody can define a domain correctly in
one go**. Domains become right only by iterating, so iterations must be extremely cheap and
testable, and rebuilds will be very frequent.

The researcher named the compiler's most important function: when a domain expert changes
something, compare it with the existing declaration, report what would break or conflict,
and let the expert actually try it, all before deployment. With natural-language skills,
none of this is possible. Whether a new instruction conflicts with existing text is
discovered only after deployment.

## Decision
- The claim chain remains the backbone of docs, experiments, ADRs and milestones (carried
  over from ADR-0001). Each milestone ends with a verdict on a link, and progress is tracked
  in the README claim-status table.
- Add **P0** under the claim chain: *nobody can define a domain correctly in one go; it is
  found by iterating*. P0 is taken as given. M1 reports first-draft accuracy as a sanity
  check on it.
- Redefine **①** from "can be built cheaply" to **"iterate safely"**: a domain can be
  changed cheaply and safely, with breakage and conflicts caught at compile time and the
  change tried before deployment. This replaces the chain recorded in ADR-0001.
- The compiler gets a **change-check pipeline**. It diffs the new version against the
  current one and runs these checks:
  - structural: references, types
  - semantic conflict: contradictory rules, unreachable states, dead actions
  - scenario regression: example scenarios attached to the domain
  - log replay: past events re-run against the new version
  - natural-language conflict: LLM-based, reported as warnings only

  Every change also gets a **preview build** (generated MCP and UI on a copy of the state).
- Domains carry **scenarios** as their own tests. (The format was superseded by ADR-0010:
  a scenario is a multi-step flow with `given` and `steps`. "Scenario regression" means
  running them against the model.)
- M1's primary comparison is **natural-language skill vs. declaration** on the same frozen
  sequence of change requests with seeded problems. Metrics are pre-deploy recall and
  precision, problems found after deploy, and iteration time. The NL arm gets an LLM
  conflict review, which makes it the strongest fair baseline.

## Consequences
- Iteration time (edit → validated preview) becomes a design constraint for the compiler,
  including incremental rebuilds. Representation-only changes stay on their own pipeline
  (ADR-0008).
- Checks on in-flight objects (instances sitting in states that a change removes) are noted
  for later. They are not in the first set.

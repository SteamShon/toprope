# ADR-0001: The claim chain is the backbone

- Link: all · Status: **superseded by [ADR-0009](0009-change-safety-is-the-compiler-core.md)** (premise P0 added, ① redefined; the chain stays the backbone) · 2026-11-04 · decided by: SteamShon

## Decision
Toprope's thesis is five chained claims: ① can be built → ② model is right → ③ shared
language → ④ evolves → ⑤ org productivity. Docs, experiments, ADRs and milestones are
organized around them:
- Every document names its link.
- Each milestone ends with a verdict on a link.
- Progress is tracked in the README claim-status table, not as a feature list.

① + ② is the load-bearing bet and goes first. If a link is weakened or refuted, later
milestones are re-planned before they start.

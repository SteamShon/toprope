# ADR-0011: Claim chain; M1 tests ① can be built + ② the model is right

- Status: accepted · 2026-11-04 · decided by: SteamShon (alignment session)
- Supersedes: ADR-0009 (shared language moves to M2)
- Evidence: notes/ko/2026-11-04-alignment.md

## Context
When asked who authors domains, what Toprope is, which decisions accumulate and how it
differs from Foundry, the researcher answered "all of them" each time. The vision is broad,
so research has to start from the link whose failure kills the rest.

## Decision
Toprope's thesis is a chain: ① can be built → ② model is right → ③ shared language →
④ evolves → ⑤ organizational productivity. M1 tests ① + ② through the authoring pipeline
(docs/experiments/M1-authoring.md). M2 tests ③ on the model M1 produces. M3 tests ④, and
M4 moves toward ⑤.

## Rationale
① is the link that (a) kills ③–⑤ if false, (b) is most uncertain, and (c) differs most from
Foundry-style ontologies, which work but are expensive. ③ already has some evidence from
such deployments.
